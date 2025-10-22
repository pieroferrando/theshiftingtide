#!/usr/bin/env python3
"""
Builds posts.json from your Substack RSS.

- Browser-like headers (avoid 403).
- Retries on 403/429/5xx.
- Robust date parsing (handles GMT / no-seconds).
"""

import json, re, datetime, sys, time
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET

# --- SETTINGS ---
FEED_URL = "https://substack-feed-proxy.piero-ferrando.workers.dev/"  # your Worker URL
MAX_POSTS = 12
NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
}

def fetch(url: str, tries: int = 4, delay: float = 2.0) -> bytes:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://theshiftingtide.com/",
        "Connection": "keep-alive",
    }
    last_err = None
    for i in range(tries):
        try:
            req = Request(url, headers=headers, method="GET")
            with urlopen(req, timeout=30) as resp:
                return resp.read()
        except (HTTPError, URLError) as e:
            last_err = e
            if isinstance(e, HTTPError) and e.code not in (403, 429, 500, 502, 503, 504):
                break
            time.sleep(delay * (i + 1))
    raise last_err

def first_image(html: str | None) -> str | None:
    if not html:
        return None
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.I)
    return m.group(1) if m else None

def strip_html(html: str | None) -> str:
    txt = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", txt).strip()

def parse_date(pub: str | None, alt1: str | None = None, alt2: str | None = None) -> str:
    """
    Return ISO 8601 UTC string from various RSS/Atom date formats.
    Falls back to 'now' only if everything fails.
    """
    candidates = [pub, alt1, alt2]
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z",  # Wed, 22 Oct 2025 07:00:00 +0000
        "%a, %d %b %Y %H:%M:%S %Z",  # ... GMT
        "%a, %d %b %Y %H:%M %z",     # no seconds
        "%a, %d %b %Y %H:%M %Z",     # no seconds + GMT
        "%Y-%m-%dT%H:%M:%S%z",       # Atom-style
        "%Y-%m-%dT%H:%M:%S.%f%z",    # Atom with fractional seconds
    ]
    for raw in candidates:
        if not raw:
            continue
        s = raw.strip()
        # Normalize common quirks
        s = s.replace("GMT", "+0000")
        # Remove comma variants if oddly duplicated, and collapse spaces
        s = re.sub(r"\s+", " ", s)
        for fmt in fmts:
            try:
                dt = datetime.datetime.strptime(s, fmt)
                return dt.astimezone(datetime.timezone.utc).isoformat()
            except Exception:
                continue
    # Last resort: now (prevents script failure, but shouldn't be used often)
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

def main() -> int:
    try:
        raw = fetch(FEED_URL)
    except Exception as e:
        print(f"[build_feed] ERROR fetching feed: {e}", file=sys.stderr)
        return 1

    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[build_feed] ERROR parsing XML: {e}", file=sys.stderr)
        return 1

    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else []

    out = []
    for it in items[:MAX_POSTS]:
        title = (it.findtext("title") or "").strip()
        link  = (it.findtext("link") or "").strip()

        # Prefer <pubDate>, but try dc:date or atom:updated as backups
        pubDate   = (it.findtext("pubDate") or "").strip()
        dcDate    = it.findtext("dc:date", namespaces=NS)
        atomUpd   = it.findtext("atom:updated", namespaces=NS)
        iso       = parse_date(pubDate, dcDate, atomUpd)

        content_html = it.findtext("content:encoded", namespaces=NS) or ""
        description  = it.findtext("description") or ""
        subtitle     = strip_html(description or content_html)
        if len(subtitle) > 220:
            subtitle = subtitle[:217].rstrip() + "…"

        media = it.find("media:content", namespaces=NS)
        image = media.get("url") if (media is not None and media.get("url")) else first_image(content_html or description)

        out.append({
            "title": title,
            "subtitle": subtitle,
            "date": iso,
            "url": link,
            "image": image,
        })

    with open("posts.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[build_feed] wrote posts.json with {len(out)} items")
    return 0

if __name__ == "__main__":
    sys.exit(main())
