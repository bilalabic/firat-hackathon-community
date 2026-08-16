#!/usr/bin/env python3
"""Issue Form gövdesini events.json'a güvenli biçimde ekler.

Girdi (ortam değişkenleri):
  ISSUE_BODY   : GitHub Issue Form gövdesi (güvenilmeyen kullanıcı girdisi)
  EVENTS_FILE  : hedef JSON dosyası (varsayılan: events.json)
  GITHUB_OUTPUT: GitHub Actions output dosyası (opsiyonel, local testte gerekmez)

Çıktı (GITHUB_OUTPUT):
  changed = true|false
  name    = eklenen etkinliğin adı
  errors  = doğrulama hataları (markdown liste)

JSON asla string birleştirmesiyle üretilmez; json modülü ile okunur/yazılır.
Hata durumunda dosyaya hiçbir şey yazılmaz.
"""

import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from urllib.parse import urlsplit

FIELDS = {
    "etkinlik adi": "name",
    "organizator": "organizer",
    "son basvuru tarihi": "deadline",
    "etkinlik tarihi": "eventDate",
    "konum": "location",
    "format": "format",
    "takim buyuklugu": "teamSize",
    "aciklama": "description",
    "resmi baglanti": "url",
}

REQUIRED = ["name", "deadline", "eventDate", "url"]

MAX_LEN = {
    "name": 120,
    "organizer": 80,
    "location": 80,
    "teamSize": 40,
    "description": 400,
    "url": 300,
}

FORMATS = {"Yüz yüze", "Online", "Hibrit"}

KEY_ORDER = ["id", "name", "organizer", "deadline", "eventDate",
             "location", "format", "teamSize", "description", "url"]

TR_ASCII = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
})

NO_RESPONSE = {"_no response_", "_yanıt yok_", "_yanit yok_", "-", ""}


def ascii_key(text):
    """Başlıkları eşleştirmek için ASCII, küçük harfli, sade bir anahtar üretir."""
    text = text.replace("İ", "i").replace("I", "ı")
    text = text.lower().translate(TR_ASCII)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


def clean(text, keep_newlines=False):
    """Kontrol karakterlerini temizler, boşlukları sadeleştirir."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch)[0] != "C")
    if keep_newlines:
        text = re.sub(r"\n{2,}", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_body(body):
    """`### Başlık` bloklarını {alan: değer} sözlüğüne çevirir."""
    values = {}
    current = None
    buffer = []

    def flush():
        if current is None:
            return
        raw = "\n".join(buffer).strip()
        if raw.strip().lower() in NO_RESPONSE:
            raw = ""
        values[current] = raw

    for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            flush()
            buffer = []
            current = FIELDS.get(ascii_key(heading.group(1)))
        elif current is not None:
            buffer.append(line)
    flush()
    return values


def slugify(name):
    slug = name.translate(TR_ASCII)
    slug = unicodedata.normalize("NFKD", slug)
    slug = "".join(ch for ch in slug if not unicodedata.combining(ch))
    slug = slug.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:60].strip("-") or "etkinlik"


def unique_id(base, taken):
    if base not in taken:
        return base
    for suffix in range(2, 100):
        candidate = "%s-%d" % (base, suffix)
        if candidate not in taken:
            return candidate
    raise ValueError("Benzersiz bir ID üretilemedi.")


def parse_date(value):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_url(value):
    parts = urlsplit(value)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    return host + path


def write_output(pairs):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in pairs.items():
            value = str(value)
            if "\n" in value:
                handle.write("%s<<__EOF_%s__\n%s\n__EOF_%s__\n" % (key, key, value, key))
            else:
                handle.write("%s=%s\n" % (key, value))


def main():
    events_file = os.environ.get("EVENTS_FILE", "events.json")
    body = os.environ.get("ISSUE_BODY", "")
    errors = []

    values = parse_body(body)

    data = {}
    for key in FIELDS.values():
        raw = values.get(key, "")
        data[key] = clean(raw, keep_newlines=(key == "description"))

    for key in REQUIRED:
        if not data[key]:
            errors.append("`%s` alanı zorunlu ve boş olamaz." % key)

    for key, limit in MAX_LEN.items():
        if len(data[key]) > limit:
            errors.append("`%s` alanı en fazla %d karakter olabilir." % (key, limit))

    deadline = parse_date(data["deadline"]) if data["deadline"] else None
    event_date = parse_date(data["eventDate"]) if data["eventDate"] else None

    if data["deadline"] and not deadline:
        errors.append("Son başvuru tarihi geçersiz. Biçim `YYYY-AA-GG` olmalı (örnek: 2026-08-25).")
    if data["eventDate"] and not event_date:
        errors.append("Etkinlik tarihi geçersiz. Biçim `YYYY-AA-GG` olmalı (örnek: 2026-09-05).")
    if deadline and event_date and event_date < deadline:
        errors.append("Etkinlik tarihi, son başvuru tarihinden önce olamaz.")
    if event_date and event_date.year > date.today().year + 5:
        errors.append("Etkinlik tarihi çok ileri bir yılda görünüyor.")

    if data["url"]:
        parts = urlsplit(data["url"])
        if parts.scheme not in ("http", "https") or "." not in parts.netloc or " " in data["url"]:
            errors.append("Resmi bağlantı `http://` veya `https://` ile başlayan geçerli bir adres olmalı.")

    if data["format"] and data["format"] not in FORMATS:
        errors.append("Format yalnızca `Yüz yüze`, `Online` veya `Hibrit` olabilir.")

    try:
        with open(events_file, encoding="utf-8") as handle:
            events = json.load(handle)
        if not isinstance(events, list):
            raise ValueError("events.json bir dizi olmalı.")
    except Exception as exc:  # noqa: BLE001 - kullanıcıya raporlanır
        errors.append("Mevcut `events.json` okunamadı: %s" % exc)
        events = None

    existing_ids = set()
    if events is not None and not errors:
        existing_ids = {str(item.get("id", "")) for item in events if isinstance(item, dict)}
        existing_urls = {
            normalize_url(str(item.get("url", "")))
            for item in events
            if isinstance(item, dict) and item.get("url")
        }
        if normalize_url(data["url"]) in existing_urls:
            errors.append("Bu bağlantıya sahip bir etkinlik zaten listede var.")

    if errors:
        write_output({"changed": "false", "errors": "\n".join("- " + e for e in errors)})
        print("Doğrulama başarısız:")
        for error in errors:
            print(" -", error)
        return 0

    event = {"id": unique_id(slugify(data["name"]), existing_ids)}
    for key in KEY_ORDER[1:]:
        if data.get(key):
            event[key] = data[key]

    events.append(event)

    serialized = json.dumps(events, ensure_ascii=False, indent=2) + "\n"
    json.loads(serialized)  # yazmadan önce son doğrulama

    with open(events_file, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)

    with open(events_file, encoding="utf-8") as handle:
        json.load(handle)  # yazdıktan sonra doğrulama

    write_output({"changed": "true", "name": event["name"], "id": event["id"]})
    print("Eklendi: %s (%s)" % (event["name"], event["id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
