#!/usr/bin/env python3
"""
Verify cdproxy download works: GET with Amazon cookies + x-amzn-sessionid.
Downloads the first video node to /tmp and reports file size + content-type.
"""

import logging
import tempfile
from pathlib import Path
from urllib.parse import quote

import requests as _req

from amazon_client import AmazonPhotosClient

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

session_file = Path(__file__).parent.parent / "sync-amazonphotos" / "session.json"
client = AmazonPhotosClient(session_file, dry_run=False)

# Get first video node
filters = quote("kind:FILE")
result = client._eval_fetch("GET",
    f"{client._api_base}/nodes?ContentType=JSON&resourceVersion=V2"
    f"&filters={filters}&limit=200&tempLink=false")
all_items = result.get("data", {}).get("data", [])
video_nodes = [n for n in all_items
               if n.get("contentProperties", {}).get("contentType", "").startswith("video/")]
node = video_nodes[0]
node_id = node["id"]
node_name = node.get("name", node_id)
expected_size = node.get("contentProperties", {}).get("size", 0)
log.info("Video: %s  expected_size=%d bytes", node_name, expected_size)

# Get cdproxy URL
tl_url = (f"{client._api_base}/nodes/{node_id}"
          f"?ContentType=JSON&resourceVersion=V2&tempLink=true")
tl_result = client._eval_fetch("GET", tl_url)
cdproxy_url = tl_result.get("data", {}).get("tempLink")
log.info("cdproxy URL: %s", cdproxy_url)

if not cdproxy_url:
    log.error("No tempLink in response")
    client.close()
    exit(1)

# Download using the proven auth approach
headers = {
    "x-amzn-sessionid": client._auth_headers.get("x-amzn-sessionid", ""),
    "x-amz-clouddrive-appid": client._auth_headers.get("x-amz-clouddrive-appid", ""),
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

dest = Path(tempfile.mkdtemp()) / node_name
log.info("▶ Downloading to %s ...", dest)

r = _req.get(cdproxy_url, headers=headers, cookies=client._download_cookies,
             stream=True, timeout=120)
log.info("HTTP %d  Content-Type: %s  Content-Length: %s",
         r.status_code, r.headers.get("content-type", "?"),
         r.headers.get("content-length", "?"))

if r.status_code not in (200, 206):
    log.error("Download failed: %s", r.text[:300])
    client.close()
    exit(1)

with open(dest, "wb") as f:
    for chunk in r.iter_content(chunk_size=65536):
        f.write(chunk)

actual_size = dest.stat().st_size
log.info("✓ Downloaded %d bytes  (expected ~%d)  → %s", actual_size, expected_size, dest)
log.info("  Size match: %s", "YES" if abs(actual_size - expected_size) < 1024 else "NO — mismatch!")

client.close()
