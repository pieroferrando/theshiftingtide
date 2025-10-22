#!/usr/bin/env python3
import json, re, datetime, sys
from urllib.request import urlopen, Request
from xml.etree import ElementTree as ET

FEED_URL = "https://theshiftingtide.substack.com/feed"
MAX_POSTS = 12
NS = {'content':'http://purl.org/rss/1.0/modules/content/','media':'http://search.yahoo.com/mrss/'}

def fetch(url: str) -> bytes:
    # Some hosts block requests without a UA; also follow redirects
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SubstackFeedBot/1.0; +https://theshiftingtide.com)"
        },
    )
    with urlopen(req, timeout=30) as resp:
        return resp.read()

def first_image(html):
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html or "", flags=re.I)
    return m.group(1) if m else None

def strip_html(html):
    t = re.sub(r'<[^>]+>', ' ', html or '')
    return re.sub(r'\s+', ' ', t).strip()

try:
    raw = fetch(FEED_URL)
except Exception as e:
    print(f"[build_feed] ERROR fetching feed: {e}", file=sys.stderr)
    sys.exit(1)

try:
    root = ET.fromstring(raw)
except Exception as e:
    print(f"[build_feed] ERROR parsing XML: {e}", file=sys.stderr)
    sys.exit(1)

channel = root.find('channel')
items = channel.findall('item') if channel is not None else []

out=[]
for it in items[:MAX_POSTS]:
    title = (it.findtext('title') or '').strip()
    link  = (it.findtext('link') or '').strip()
    pub   = (it.findtext('pubDate') or '').strip()
    html  = it.findtext('content:encoded', namespaces=NS) or ''
    desc  = it.findtext('description') or ''
    sub   = strip_html(desc or html)
    if len(sub) > 220: sub = sub[:217].rstrip() + '…'
    media = it.find('media:content', namespaces=NS)
    img   = media.get('url') if (media is not None and media.get('url')) else first_image(html or desc)
    try:
        dt = datetime.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z").astimezone(datetime.timezone.utc)
        iso = dt.isoformat()
    except Exception:
        iso = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
    out.append({"title":title,"subtitle":sub,"date":iso,"url":link,"image":img})

with open("posts.json","w",encoding="utf-8") as f:
    json.dump(out,f,ensure_ascii=False,indent=2)

print(f"[build_feed] wrote posts.json with {len(out)} items")
