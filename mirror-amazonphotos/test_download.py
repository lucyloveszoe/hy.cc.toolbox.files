#!/usr/bin/env python3
"""
Debug single-photo download — no full enumeration.
Fetches 1 node directly, dumps full tempLink response, attempts download.
"""

import json
import logging
import tempfile
from pathlib import Path
from urllib.parse import quote

from amazon_client import AmazonPhotosClient

logging.basicConfig(level=logging.DEBUG, format="%(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

session_file = Path(__file__).parent.parent / "sync-amazonphotos" / "session.json"
if not session_file.exists():
    print(f"Session not found at {session_file}")
    exit(1)

client = AmazonPhotosClient(session_file, dry_run=False)

# ── Step 1: grab exactly 1 node (no pagination) ──────────────────────────────
log.info("▶ Fetching 1 node to get a test ID...")
filters = quote("kind:FILE")
list_url = (f"{client._api_base}/nodes?ContentType=JSON&resourceVersion=V2"
            f"&filters={filters}&limit=1&tempLink=false")
list_result = client._eval_fetch("GET", list_url)

if list_result["status"] != 200:
    log.error("Node list failed: HTTP %s — %s", list_result["status"], list_result.get("data"))
    client.close()
    exit(1)

items = list_result.get("data", {}).get("data", [])
if not items:
    log.error("No nodes returned — check filters or session")
    client.close()
    exit(1)

node = items[0]
node_id = node["id"]
node_name = node.get("name", "unknown")
node_mime = node.get("contentProperties", {}).get("contentType", "unknown")
log.info("Test node: id=%s  name=%s  mime=%s", node_id, node_name, node_mime)

# ── Step 2: fetch tempLink — dump full raw response ───────────────────────────
log.info("▶ Calling tempLink endpoint for node %s...", node_id)
dl_url = (f"{client._api_base}/nodes/{node_id}"
          f"?ContentType=JSON&resourceVersion=V2&tempLink=true")
dl_result = client._eval_fetch("GET", dl_url)

log.info("tempLink response status: %d", dl_result["status"])
log.info("tempLink response body:\n%s", json.dumps(dl_result.get("data", {}), indent=2))

# ── Step 3: attempt download if URL found ─────────────────────────────────────
body = dl_result.get("data", {}) or {}
temp_url = body.get("tempLink") or (body.get("contentProperties") or {}).get("url")

if not temp_url:
    log.error("✗ No download URL found. See full response above to identify the correct field.")
    client.close()
    exit(1)

log.info("✓ Got URL: %s...", temp_url[:120])

dest = Path(tempfile.mkdtemp()) / node_name
log.info("▶ Capturing CDN requests fired by the web app (scroll to trigger thumbnails)...")
cdn_seen: list[dict] = []

def _capture_cdn(request):
    url = request.url
    if "drive.amazonaws.com" in url or "amazon.com/photos" in url:
        cdn_seen.append({"url": url, "headers": dict(request.headers)})

client._page.on("request", _capture_cdn)
# Scroll down to force thumbnail loading
client._page.evaluate("window.scrollBy(0, 2000)")
client._page.wait_for_timeout(4000)

if cdn_seen:
    log.info("=== CDN requests captured from web app ===")
    for i, req in enumerate(cdn_seen[:5]):
        log.info("[%d] URL: %s", i, req["url"][:120])
        log.info("    Headers: %s", list(req["headers"].keys()))
else:
    log.warning("No CDN requests captured — photos may not have loaded")

log.info("▶ Downloading to %s ...", dest)
ok = client.download_node(node, dest)
if ok:
    log.info("✓ Download OK — %d bytes saved to %s", dest.stat().st_size, dest)
else:
    log.error("✗ Download failed — see errors above")

client.close()
