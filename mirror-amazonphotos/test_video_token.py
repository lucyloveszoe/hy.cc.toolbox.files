#!/usr/bin/env python3
"""
Three-pronged probe:
  1. Extract any OAuth / access tokens from browser localStorage / sessionStorage
  2. Try GET /drive/v1/nodes/{id}/content via _eval_fetch (same auth as working API calls)
  3. Try thumbnails CDN with alternate paths for video content
"""

import json
import logging
import requests as _req
from pathlib import Path
from urllib.parse import quote

from amazon_client import AmazonPhotosClient

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

session_file = Path(__file__).parent.parent / "sync-amazonphotos" / "session.json"
client = AmazonPhotosClient(session_file, dry_run=False)

# Get a video node
filters = quote("kind:FILE")
result = client._eval_fetch("GET",
    f"{client._api_base}/nodes?ContentType=JSON&resourceVersion=V2"
    f"&filters={filters}&limit=200&tempLink=false")
all_items = result.get("data", {}).get("data", [])
video_nodes = [n for n in all_items
               if n.get("contentProperties", {}).get("contentType", "").startswith("video/")]
node = video_nodes[0]
node_id = node["id"]
owner_id = node.get("ownerId", "")
log.info("Video: %s  id=%s", node.get("name"), node_id)

# ── 1. Dump ALL localStorage / sessionStorage keys ───────────────────────────
log.info("\n=== localStorage keys (amazon.com) ===")
ls_data = client._page.evaluate("""
() => {
    const out = {};
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        const v = localStorage.getItem(k);
        out[k] = v ? v.substring(0, 300) : null;
    }
    return out;
}
""")
for k, v in ls_data.items():
    log.info("  %-50s = %s", k, str(v)[:120])

log.info("\n=== sessionStorage keys (amazon.com) ===")
ss_data = client._page.evaluate("""
() => {
    const out = {};
    for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        const v = sessionStorage.getItem(k);
        out[k] = v ? v.substring(0, 300) : null;
    }
    return out;
}
""")
for k, v in ss_data.items():
    log.info("  %-50s = %s", k, str(v)[:120])

# ── 2. Try /drive/v1/nodes/{id}/content via browser fetch ────────────────────
log.info("\n▶ Trying GET /drive/v1/nodes/%s/content ...", node_id)
content_url = f"{client._api_base}/nodes/{node_id}/content?ResourceVersion=V2&ContentType=JSON"
content_result = client._eval_fetch("GET", content_url)
log.info("Status: %d", content_result["status"])
log.info("Response: %s", json.dumps(content_result.get("data", {}))[:400])

# ── 3. Probe thumbnails CDN with alternate video paths ───────────────────────
thumb_base = "https://thumbnails-photos.amazon.com"
paths_to_try = [
    f"/v1/thumbnail/{node_id}?viewBox=10000&ownerId={owner_id}",          # photo path (known → JPEG)
    f"/v1/video/{node_id}?ownerId={owner_id}",                             # guess: video path
    f"/v1/asset/{node_id}?ownerId={owner_id}",                             # guess: generic asset
    f"/v1/thumbnail/{node_id}?viewBox=10000&ownerId={owner_id}&type=video", # guess: type param
]

log.info("\n▶ Probing thumbnails CDN alternate paths...")
for path in paths_to_try:
    url = thumb_base + path
    try:
        r = _req.head(url, cookies=client._download_cookies, timeout=10, allow_redirects=True)
        log.info("HEAD %s\n  → HTTP %d  Content-Type: %s  Content-Length: %s  URL: %s",
                 path[:80], r.status_code,
                 r.headers.get("content-type", "?"),
                 r.headers.get("content-length", "?"),
                 r.url[:120])
    except Exception as e:
        log.error("  → FAILED: %s", e)

# ── 4. Try /cdrs/drive/v2/ API for video download ────────────────────────────
log.info("\n▶ Probing /cdrs/drive/v2/ API endpoints...")
v2_paths = [
    f"/cdrs/drive/v2/nodes/{node_id}?tempLink=true",
    f"/cdrs/drive/v2/nodes/{node_id}/content",
]
for path in v2_paths:
    url = f"https://www.amazon.com{path}"
    r2 = client._eval_fetch("GET", url)
    log.info("GET %s → HTTP %d  body: %s", path, r2["status"], json.dumps(r2.get("data", {}))[:200])

# ── 5. Dump all cookies — look for any OAuth / bearer tokens ─────────────────
log.info("\n=== All browser cookies (names only, not values) ===")
all_cookies = client._page.context.cookies()
for c in all_cookies:
    log.info("  [%-30s] domain=%-30s  httpOnly=%s  secure=%s",
             c["name"], c.get("domain", "?"), c.get("httpOnly", "?"), c.get("secure", "?"))

client.close()
log.info("\n✓ Done")
