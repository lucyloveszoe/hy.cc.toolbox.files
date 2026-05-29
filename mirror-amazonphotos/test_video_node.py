#!/usr/bin/env python3
"""
Debug single-video node — dumps full API response and attempts to intercept streaming URL.

Steps:
  1. Fetch 1 video node (first result from VIDEO enumeration)
  2. Dump full tempLink response — look for download/streaming URL fields
  3. Navigate browser to video detail page — intercept any streaming requests
"""

import json
import logging
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

# ── Step 1: grab exactly 1 video node ────────────────────────────────────────
log.info("▶ Fetching 1 video node...")
filters = quote("kind:FILE")
list_url = (f"{client._api_base}/nodes?ContentType=JSON&resourceVersion=V2"
            f"&filters={filters}&limit=200&tempLink=false")
list_result = client._eval_fetch("GET", list_url)

if list_result["status"] != 200:
    log.error("Node list failed: HTTP %s — %s", list_result["status"], list_result.get("data"))
    client.close()
    exit(1)

all_items = list_result.get("data", {}).get("data", [])
video_nodes = [n for n in all_items
               if n.get("contentProperties", {}).get("contentType", "").startswith("video/")]

if not video_nodes:
    log.error("No video nodes found in the first 200 nodes — try running against a library with videos")
    client.close()
    exit(1)

node = video_nodes[0]
node_id = node["id"]
node_name = node.get("name", "unknown")
node_mime = node.get("contentProperties", {}).get("contentType", "unknown")
owner_id = node.get("ownerId", "")
log.info("Test video node: id=%s  name=%s  mime=%s  owner=%s", node_id, node_name, node_mime, owner_id)

# ── Step 2: dump the full node structure (what we already have) ───────────────
log.info("\n=== Full node object (from list response) ===")
log.info("%s", json.dumps(node, indent=2))

# ── Step 3: fetch with tempLink=true — dump full raw response ─────────────────
log.info("\n▶ Calling tempLink endpoint for node %s...", node_id)
tl_url = (f"{client._api_base}/nodes/{node_id}"
          f"?ContentType=JSON&resourceVersion=V2&tempLink=true")
tl_result = client._eval_fetch("GET", tl_url)

log.info("tempLink response HTTP status: %d", tl_result["status"])
log.info("\n=== Full tempLink response body ===")
log.info("%s", json.dumps(tl_result.get("data", {}), indent=2))

# ── Step 4: check what the thumbnail CDN returns for a video node ─────────────
import requests as _req
thumb_url = (f"https://thumbnails-photos.amazon.com/v1/thumbnail/{node_id}"
             f"?viewBox=10000&ownerId={owner_id}")
log.info("\n▶ Probing thumbnail CDN URL for video: %s", thumb_url)
try:
    r = _req.head(thumb_url, cookies=client._download_cookies, timeout=15, allow_redirects=True)
    log.info("Thumbnail CDN HEAD response: HTTP %d  Content-Type: %s  Content-Length: %s",
             r.status_code, r.headers.get("content-type", "?"), r.headers.get("content-length", "?"))
    log.info("Final URL after redirects: %s", r.url)
except Exception as e:
    log.error("Thumbnail CDN request failed: %s", e)

# ── Step 5: navigate to video detail page — intercept streaming requests ───────
log.info("\n▶ Navigating to video detail page to intercept streaming URL...")

streaming_urls: list[dict] = []

VIDEO_DOMAINS = (
    "thumbnails-photos.amazon.com",
    "streaming-photos.amazon.com",
    "drive.amazonaws.com",
    "cloudfront.net",
    "akamaihd.net",
    "amazon.com",
)

def _capture(request):
    url = request.url
    ct = request.headers.get("accept", "")
    # Capture anything that looks like a media/streaming request
    if any(d in url for d in VIDEO_DOMAINS):
        if any(kw in url.lower() for kw in ("video", "stream", "media", "mp4", "mov", "m3u", ".ts", "segment")):
            streaming_urls.append({
                "url": url[:200],
                "method": request.method,
                "accept": ct[:80],
            })

client._page.on("request", _capture)

# Navigate to the video's detail page in Amazon Photos
detail_url = f"https://www.amazon.com/photos/detail/{node_id}"
log.info("Navigating to: %s", detail_url)
try:
    client._page.goto(detail_url, timeout=30000, wait_until="load")
    client._page.wait_for_timeout(5000)
except Exception as e:
    log.warning("Navigation error (may be OK): %s", e)

if streaming_urls:
    log.info("\n=== Streaming/media requests intercepted ===")
    for i, req in enumerate(streaming_urls):
        log.info("[%d] %s %s", i, req["method"], req["url"])
        if req["accept"]:
            log.info("    Accept: %s", req["accept"])
else:
    log.info("No video streaming URLs intercepted on detail page navigation")

# ── Step 6: also try the /photos/all page and capture ALL requests ─────────────
log.info("\n▶ Re-checking full request log on /photos/all for any video-related URLs...")
all_requests: list[str] = []

def _capture_all(request):
    url = request.url
    if any(kw in url.lower() for kw in ("video", "stream", "media", ".mp4", ".mov", ".m3u8", "cdproxy")):
        all_requests.append(url[:200])

client._page.on("request", _capture_all)
client._page.goto("https://www.amazon.com/photos/all", timeout=30000, wait_until="load")
client._page.wait_for_timeout(4000)

if all_requests:
    log.info("Video-related requests on /photos/all:")
    for url in all_requests[:10]:
        log.info("  %s", url)
else:
    log.info("No video-related requests captured on /photos/all")

client.close()
log.info("\n✓ Done — review the output above to identify the video download URL pattern")
