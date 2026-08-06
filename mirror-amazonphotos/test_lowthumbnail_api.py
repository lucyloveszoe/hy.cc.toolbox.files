#!/usr/bin/env python3
"""
Two targeted probes:
  1. Check what lowResThumbnail=true search API returns for video nodes
     (this is the same call the React app makes — may embed streaming URLs)
  2. Try cdproxy with credentials:include from inside the browser
     (cross-origin fetch with all HttpOnly cookies sent)
"""

import json
import logging
import requests as _req
from pathlib import Path

from amazon_client import AmazonPhotosClient

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

session_file = Path(__file__).parent.parent / "sync-amazonphotos" / "session.json"
client = AmazonPhotosClient(session_file, dry_run=False)

# ── 1. Call lowResThumbnail search — find a video node, dump full response ────
log.info("▶ Calling /search?lowResThumbnail=true for video nodes...")
search_url = (
    f"{client._api_base}/search?asset=ALL"
    f"&filters=type%3A(PHOTOS+OR+VIDEOS)"
    f"&limit=200&lowResThumbnail=true"
    f"&searchContext=customer"
    f"&sort=%5B%27contentProperties.contentDate+DESC%27%5D"
    f"&tempLink=false"
)
result = client._eval_fetch("GET", search_url)
all_items = result.get("data", {}).get("data", [])
video_nodes = [n for n in all_items
               if n.get("contentProperties", {}).get("contentType", "").startswith("video/")]

log.info("Found %d video nodes in search results", len(video_nodes))

if video_nodes:
    node = video_nodes[0]
    node_id = node["id"]
    owner_id = node.get("ownerId", "")
    log.info("\n=== First video node from lowResThumbnail search ===")
    log.info("%s", json.dumps(node, indent=2))
else:
    # Fall back to direct node enumeration
    log.info("No videos in recent 200 — fetching with VIDEO filter...")
    from urllib.parse import quote
    filters = quote("kind:FILE")
    r2 = client._eval_fetch("GET",
        f"{client._api_base}/nodes?ContentType=JSON&resourceVersion=V2"
        f"&filters={filters}&limit=200&tempLink=false")
    all_items = r2.get("data", {}).get("data", [])
    video_nodes = [n for n in all_items
                   if n.get("contentProperties", {}).get("contentType", "").startswith("video/")]
    node = video_nodes[0] if video_nodes else None
    if node:
        node_id = node["id"]
        owner_id = node.get("ownerId", "")
        log.info("Fallback node: %s  id=%s", node.get("name"), node_id)

# ── 2. Try cdproxy from browser with credentials:include ─────────────────────
log.info("\n▶ Trying cdproxy HEAD with credentials:include from inside browser...")
cdproxy_url = f"https://content-na.drive.amazonaws.com/cdproxy/nodes/{node_id}"

auth_headers = {k: v for k, v in client._auth_headers.items()
                if k.lower() not in ("cookie", "content-type")}

cdproxy_result = client._page.evaluate(f"""
async () => {{
    try {{
        const r = await fetch({json.dumps(cdproxy_url)}, {{
            method: 'HEAD',
            credentials: 'include',
            headers: {json.dumps(auth_headers)}
        }});
        const hdrs = {{}};
        r.headers.forEach((v, k) => {{ hdrs[k] = v; }});
        return {{status: r.status, headers: hdrs, type: r.type, ok: r.ok}};
    }} catch(e) {{
        return {{status: 0, error: String(e), type: 'error'}};
    }}
}}
""")
log.info("cdproxy HEAD (credentials:include): %s", json.dumps(cdproxy_result, indent=2))

# ── 3. Try python requests with ALL amazon cookies + x-amzn-sessionid ─────────
log.info("\n▶ Trying cdproxy with Python requests + all Amazon cookies + session header...")
headers = {
    "x-amzn-sessionid": client._auth_headers.get("x-amzn-sessionid", ""),
    "x-amz-clouddrive-appid": client._auth_headers.get("x-amz-clouddrive-appid", ""),
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
r = _req.head(cdproxy_url, headers=headers, cookies=client._download_cookies, timeout=15)
log.info("HTTP %d  Content-Type: %s  Content-Length: %s",
         r.status_code, r.headers.get("content-type", "?"), r.headers.get("content-length", "?"))
if r.status_code != 200:
    log.info("Body: %s", r.text[:300])

# ── 4. Also try GET /nodes/{id}/content via browser ────────────────────────────
log.info("\n▶ Trying GET /nodes/{id}/content with no ResourceVersion param...")
content_url2 = f"{client._api_base}/nodes/{node_id}/content"
r2 = client._eval_fetch("GET", content_url2)
log.info("Status: %d  Body: %s", r2["status"], json.dumps(r2.get("data", {}))[:200])

# ── 5. Try /nodes/{id}?asset=VIDEO&tempLink=true ─────────────────────────────
log.info("\n▶ Trying /nodes/{id}?asset=VIDEO&tempLink=true ...")
asset_url = (f"{client._api_base}/nodes/{node_id}"
             f"?ContentType=JSON&resourceVersion=V2&asset=VIDEO&tempLink=true")
r3 = client._eval_fetch("GET", asset_url)
log.info("Status: %d", r3["status"])
body3 = r3.get("data", {})
log.info("tempLink: %s", body3.get("tempLink", "NOT FOUND"))
# Show any new keys vs standard node response
standard_keys = {"id", "name", "kind", "ownerId", "createdDate", "modifiedDate",
                 "contentProperties", "parents", "parentMap", "status"}
new_keys = set(body3.keys()) - standard_keys if isinstance(body3, dict) else set()
if new_keys:
    log.info("New/extra keys in response: %s", new_keys)
    for k in new_keys:
        log.info("  %s: %s", k, str(body3.get(k, ""))[:200])

client.close()
log.info("\n✓ Done")
