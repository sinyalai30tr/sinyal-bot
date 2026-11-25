# AI Trend Stüdyosu (v2)

Her gün tek komutla AI dünyasındaki güncel haberleri toplar, en iyi 4-5 konuyu seçer, Türkçe kısa video
taslakları ve **hazır dikey videolar** üretir. Videolar **senin onayına** düşer; sen "Onayla ve paylaş"
demeden hiçbir yere gitmez.

```
run_daily.py  ->  haber topla -> konu seç -> senaryo -> video (MP4)
studio.py     ->  Onay Masası: izle, düzenle, onayla / reddet -> YouTube · Instagram · TikTok · X
```

## 📱 Telefondan kullanım (Telegram + GitHub, ücretsiz)

Bilgisayar kapalıyken de çalışır. Her sabah 08:00'de video Telegram'a gelir,
✅ Onayla'ya basınca YouTube ve Instagram'a gider. Telegram'dan "yeni video" yazarak ek video istenir,
videoya yanıt yazarak açıklama değiştirilir.

GitHub > Settings > Secrets and variables > Actions altında gereken gizli bilgiler:
`TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `UPLOAD_POST_API_KEY`, `UPLOAD_POST_USER`
(isteğe bağlı: `ANTHROPIC_API_KEY`). İş akışları: `.github/workflows/`.

## Windows'ta en kolay yol (çift tıkla)

1. Zip'i bir klasöre çıkar (sağ tık → Tümünü ayıkla).
2. **1-KURULUM.bat** → bir kez çift tıkla (Python ve paketleri kurar).
3. **2-ONAY-MASASI.bat** → Onay Masası ve Hesaplar sayfası tarayıcıda açılır.
4. **3-GUNLUK-VIDEO.bat** → Günün haberlerinden taslak ve video üretir.

## Kurulum (komut satırıyla)

```bash
cd ai-trend-studio
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # Mac/Linux: cp .env.example .env
```

`.env` dosyasına yapay zekâ API anahtarını yaz (varsayılan: `ANTHROPIC_API_KEY`).
ffmpeg ayrıca kurulmaz; `imageio-ffmpeg` paketiyle birlikte gelir.

## Günlük kullanım

```bash
python run_daily.py     # Taslaklar + günün en iyi konusunun videosu (birkaç dakika sürer)
python studio.py        # Onay Masası tarayıcıda açılır: http://127.0.0.1:8765
```

Başka bir konunun videosu için: `python make_video.py --konu 3`

### Çıktılar

| Dosya | Ne işe yarar |
|---|---|
| `outputs/2026-11-19_trendler.html` | Tarayıcıda açılan taslak sayfası (kopyala düğmeleri, not alanı) |
| `outputs/2026-11-19_trendler.md / .json / _senaryolar.txt` | Aynı taslaklar farklı biçimlerde |
| `outputs/videolar/*.mp4` | 1080x1920, en fazla 30 sn, seslendirmeli + altyazılı + müzikli video |
| `outputs/videolar/*.json` | Videonun başlık, açıklama, onay durumu ve paylaşım sonuçları |

## Video nasıl yapılıyor?

- **Ses:** Ücretsiz Microsoft Edge Türkçe sesleri (`edge-tts`). Kadın (Emel) / erkek (Ahmet) sesi
  yapay zekâ konuya göre seçer. İnternet yoksa isteğe bağlı çevrimdışı Piper sesine düşer.
- **Görüntü:** Kayan renkli arka plan, zıplayarak giren dev başlık bantları, sahne tipine göre efektler
  (soru işareti, ışın patlaması, nabız gibi atan "TAKİP ET"), ilk saniyede flaş, kelime kelime yanan
  altyazı, üstte ilerleme çubuğu, kanal adın ve kaynak notu.
- **Müzik:** Kodla üretilen telifsiz lo-fi altyapı, konuşurken otomatik kısılır. Kendi telifsiz
  parçalarını `assets/music/` klasörüne koyarsan onlar kullanılır.
- Ayarlar: `config.yaml` → `video` ve `tts` bölümleri.

## Sosyal medya hesaplarını bağlama

Onay Masası → **Hesaplar** sayfasından yapılır. Önerilen yol **Upload-Post** (tek anahtar, 4 platform):

1. upload-post.com'da ücretsiz hesap aç.
2. "Manage Users" bölümünde bir profil oluştur (ör. `ozan`), YouTube / Instagram / TikTok / X hesaplarını bağla.
3. API anahtarını kopyala → Hesaplar sayfasına anahtarı ve profil adını yaz → **Bağlantıyı test et**.
4. Paylaşmak istediğin platformları "Aktif" yap → Kaydet.

Bilmen gerekenler:
- Upload-Post ücretsiz planı ayda 10 yükleme içerir; TikTok ücretli planda açılır.
- X'in kendi API'si artık ücretli; X'e Upload-Post üzerinden gitmek en kolayı.
- YouTube ve Instagram'a doğrudan (ücretsiz) API ile de gönderilebilir, kurulumu
  `trendbot/publishers/youtube.py` ve `instagram.py` dosyalarının başında anlatılıyor.
  YouTube doğrudan API'de Google denetimi bitene kadar videolar gizli yüklenir.
- Hesap bilgileri sadece senin bilgisayarında, `data/hesaplar.json` içinde saklanır.

## Özelleştirme

- **Kaynak eklemek / kapatmak:** `config.yaml` → `kaynaklar`.
- **Senaryo üslubu, sahne kuralları, ses seçimi:** `trendbot/prompts.py`
- **Video görünümü (renkler, yazı boyutları, efektler):** `trendbot/video/render.py`
- **Günde kaç video:** `config.yaml` → `video.konu_sayisi`
- **Ücretsiz yerel yapay zekâ (Ollama):** `saglayici: openai`, `base_url: http://localhost:11434/v1`
- **Geçmişi sıfırlamak:** `data/history.json` dosyasını sil.

## Seçenekler

```bash
python run_daily.py --deneme      # Geçmişe kaydetmeden dene
python run_daily.py --llm-yok     # API'siz: sadece aday haber listesi
python run_daily.py --video-yok   # Bu sefer video üretme
python run_daily.py --saat 48     # Son 48 saati tara
python studio.py --acma           # Onay Masası'nı tarayıcıda otomatik açma
```
