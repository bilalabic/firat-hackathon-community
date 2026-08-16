# Fırat Hackathon Community

Fırat Hackathon Community tarafından takip edilen hackathon ve teknoloji yarışmalarını tek sayfada
listeleyen küçük, hızlı ve mobil öncelikli bir site.

**Canlı:** https://bilalabic.github.io/firat-hackathon-community/

Topluluğa katılmak veya etkinlik önermek için: **bilalabic78@gmail.com**

## Teknoloji

HTML + CSS + vanilla JavaScript + JSON. Build sistemi, framework, backend ve veritabanı yok.
Otomasyon GitHub Issue Forms + GitHub Actions, hosting GitHub Pages.

## Repo yapısı

```
index.html                        tek sayfa
style.css                         tasarım (açık tema + otomatik koyu tema)
script.js                         yükleme, durum hesabı, sıralama, arama, filtre
events.json                       tek veri kaynağı
.github/ISSUE_TEMPLATE/event.yml  etkinlik ekleme formu
.github/ISSUE_TEMPLATE/config.yml boş Issue kapalı + iletişim bağlantısı
.github/scripts/add_event.py      form doğrulama + events.json güncelleme
.github/workflows/add-event.yml   Issue → doğrula → commit → deploy → Issue'yu kapat
.github/workflows/deploy-pages.yml GitHub Pages yayını
```

## Etkinlik ekleme

Etkinlikler `events.json` elle düzenlenerek değil, **Issue Form** ile eklenir:

1. GitHub (mobil de olur) → repo → **Issues** → **New issue** → **Etkinlik Ekle**
2. Formu doldur → **Submit**
3. Action formu doğrular, `events.json`'a ekler, commit'ler ve siteyi yeniden yayınlar, Issue'yu kapatır.

Doğrulama hatası varsa commit atılmaz, Issue açık kalır ve hatalar yorum olarak yazılır.
Yalnızca repo sahibinin açtığı `etkinlik` etiketli Issue'lar işlenir.

### Veri biçimi

```json
{
  "id": "ai-hackathon-2026",
  "name": "AI Hackathon 2026",
  "organizer": "ABC Teknoloji",
  "deadline": "2026-08-25",
  "eventDate": "2026-09-05",
  "location": "İstanbul",
  "format": "Yüz yüze",
  "teamSize": "2-4 kişi",
  "description": "Yapay zekâ odaklı hackathon.",
  "url": "https://example.com"
}
```

Durum (`Başvurular Açık` / `Yaklaşan` / `Sona Eren`) JSON'da tutulmaz; tarayıcıda tarihlerden
hesaplanır.

## Local test

```bash
python -m http.server 8000
```

Sonra `http://localhost:8000` adresini aç. (`fetch` kullanıldığı için dosyayı doğrudan `file://`
ile açmak yerine bir sunucu üzerinden aç.)

## GitHub Pages

Yayın kaynağı: **Settings → Pages → Source: GitHub Actions**. `main`'e her push ve her başarılı
etkinlik eklemesi siteyi otomatik olarak yeniden yayınlar; ayrıca manuel adım gerekmez.
