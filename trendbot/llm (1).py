"""Tek API anahtarıyla çalışan sade LLM istemcisi (SDK gerektirmez, sadece `requests`).

Desteklenen sağlayıcılar:
  - anthropic : Claude modelleri (ANTHROPIC_API_KEY)
  - openai    : OpenAI ve OpenAI-uyumlu servisler (OPENAI_API_KEY)
                base_url ile Ollama (yerel/ücretsiz), Groq, OpenRouter, Gemini vb.
"""
from __future__ import annotations

import json
import os
import re
import time

import requests


class LLMError(RuntimeError):
    pass


def _post_with_retry(url: str, headers: dict, payload: dict, timeout: int = 180, retries: int = 2,
                     wait: int = 5) -> dict:
    """Geçici hatalarda (429, 5xx, zaman aşımı) birkaç kez yeniden dener."""
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 529) and attempt < retries:
                time.sleep(wait * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt >= retries:
                raise LLMError(f"Bağlantı hatası: {e}") from e
            time.sleep(5 * (attempt + 1))
    raise LLMError("Bilinmeyen hata")


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
# Ana model yoğunsa sırayla denenecek diğer ücretsiz modeller (biri kalkmışsa atlanır)
GEMINI_EXTRA_FALLBACKS = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-2.5-flash"]


def _keys() -> dict:
    """Anahtarlar önce .env'den, yoksa Onay Masası > Hesaplar sayfasından okunur."""
    from .publishers import load_accounts
    ai = load_accounts().get("yapay_zeka", {})
    return {"gemini": os.getenv("GEMINI_API_KEY") or ai.get("gemini_api_key", ""),
            "anthropic": os.getenv("ANTHROPIC_API_KEY") or ai.get("anthropic_api_key", "")}


def resolve_provider(cfg: dict) -> str:
    """saglayici: otomatik ise hangi anahtar girildiyse onu kullanır (ikisi de varsa Anthropic)."""
    p = (cfg.get("saglayici") or "otomatik").lower()
    if p != "otomatik":
        return p
    k = _keys()
    if k["anthropic"]:
        return "anthropic"
    if k["gemini"]:
        return "gemini"
    raise LLMError("Yapay zekâ anahtarı yok. Onay Masası > Hesaplar sayfasından Gemini anahtarını gir.")


def model_label(cfg: dict) -> str:
    try:
        p = resolve_provider(cfg)
    except LLMError:
        return "-"
    return cfg.get("gemini_model", "gemini-flash-latest") if p == "gemini" else str(cfg.get("model", p))


def complete(system: str, user: str, cfg: dict) -> str:
    """Sistem + kullanıcı mesajını gönderir, modelin metin cevabını döndürür."""
    provider = resolve_provider(cfg)
    model = cfg.get("model")
    temperature = cfg.get("sicaklik", 0.7)

    if provider == "gemini":
        # Google Gemini (ücretsiz katman), OpenAI uyumlu uç nokta üzerinden
        key = _keys()["gemini"]
        if not key:
            raise LLMError("Gemini anahtarı yok. Onay Masası > Hesaplar sayfasından gir.")
        # Ücretsiz modeller yoğun saatlerde "503 high demand" verebiliyor:
        # her modeli birkaç kez bekleyerek dener, olmazsa sıradaki modele geçer.
        models = [cfg.get("gemini_model", "gemini-flash-latest")] + list(
            cfg.get("gemini_yedek_modeller", [])) + GEMINI_EXTRA_FALLBACKS
        models = list(dict.fromkeys(m for m in models if m))  # Tekrarları at, sırayı koru
        last: Exception | None = None
        for m in models:
            try:
                data = _post_with_retry(f"{GEMINI_BASE}/chat/completions",
                                        headers={"Authorization": f"Bearer {key}"},
                                        payload={"model": m, "temperature": temperature,
                                                 "response_format": {"type": "json_object"},
                                                 "messages": [{"role": "system", "content": system},
                                                              {"role": "user", "content": user}]},
                                        retries=3, wait=10)
                return data["choices"][0]["message"]["content"] or ""
            except LLMError as e:
                last = e
                if not any(c in str(e) for c in ("503", "429", "500", "UNAVAILABLE", "404")):
                    raise  # Anahtar hatası gibi kalıcı sorunlarda boşuna deneme
        raise LLMError(f"Google'ın ücretsiz modelleri şu an yoğun, biraz sonra tekrar dene. ({str(last)[:120]})")

    if provider == "anthropic":
        key = _keys()["anthropic"]
        if not key:
            raise LLMError("Anthropic anahtarı yok. Onay Masası > Hesaplar sayfasından gir.")
        data = _post_with_retry(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            payload={"model": model, "max_tokens": int(cfg.get("max_tokens", 8000)),
                     "temperature": temperature, "system": system,
                     "messages": [{"role": "user", "content": user}]},
        )
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

    if provider == "openai":
        base = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        key = os.getenv("OPENAI_API_KEY") or "yerel"  # Ollama anahtar istemez
        payload = {"model": model,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        if temperature is not None:
            payload["temperature"] = temperature
        payload.update(cfg.get("openai_ek_parametreler") or {})
        data = _post_with_retry(f"{base}/chat/completions",
                                headers={"Authorization": f"Bearer {key}"}, payload=payload)
        return data["choices"][0]["message"]["content"] or ""

    raise LLMError(f"Bilinmeyen sağlayıcı: {provider} (anthropic | openai olmalı)")


def extract_json(text: str) -> dict:
    """Model cevabındaki JSON nesnesini ayıklar (```json bloklarını da tolere eder)."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Cevapta JSON bulunamadı.")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON çözümlenemedi: {e}") from e
