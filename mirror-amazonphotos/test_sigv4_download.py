#!/usr/bin/env python3
"""
Extract Cognito STS credentials from browser localStorage.
Use them to authenticate a cdproxy download via AWS Signature V4.
"""

import json
import logging
import tempfile
from pathlib import Path
from urllib.parse import quote

from amazon_client import AmazonPhotosClient

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

# ── Check aws4auth is available ───────────────────────────────────────────────
try:
    from requests_aws4auth import AWS4Auth
    import requests as _req
except ImportError:
    print("\nInstall missing dep first:")
    print("  pip install requests-aws4auth")
    exit(1)

session_file = Path(__file__).parent.parent / "sync-amazonphotos" / "session.json"
client = AmazonPhotosClient(session_file, dry_run=False)

# ── Get a video node ──────────────────────────────────────────────────────────
filters = quote("kind:FILE")
result = client._eval_fetch("GET",
    f"{client._api_base}/nodes?ContentType=JSON&resourceVersion=V2"
    f"&filters={filters}&limit=200&tempLink=false")
all_items = result.get("data", {}).get("data", [])
video_nodes = [n for n in all_items
               if n.get("contentProperties", {}).get("contentType", "").startswith("video/")]
node = video_nodes[0]
node_id = node["id"]
log.info("Video: %s  id=%s", node.get("name"), node_id)

# ── Extract FULL cwr_c credentials ───────────────────────────────────────────
log.info("\n▶ Extracting full Cognito credentials from localStorage...")
cwr_c_raw = client._page.evaluate("() => localStorage.getItem('cwr_c')")
if not cwr_c_raw:
    log.error("cwr_c not found in localStorage")
    client.close()
    exit(1)

creds = json.loads(cwr_c_raw)
access_key = creds.get("accessKeyId", "")
secret_key = creds.get("secretAccessKey", "")
session_token = creds.get("sessionToken", "")

log.info("accessKeyId:   %s", access_key)
log.info("secretKey len: %d chars", len(secret_key))
log.info("sessionToken len: %d chars (first 40: %s...)", len(session_token), session_token[:40])

if not all([access_key, secret_key, session_token]):
    log.error("Incomplete credentials — cannot proceed")
    client.close()
    exit(1)

# ── Try cdproxy with SigV4 (service=execute-api, then s3, then clouddrive) ────
cdproxy_url = f"https://content-na.drive.amazonaws.com/cdproxy/nodes/{node_id}"
log.info("\n▶ Trying cdproxy download with SigV4 auth...")

for service in ["execute-api", "s3", "clouddrive", "es"]:
    auth = AWS4Auth(access_key, secret_key, "us-east-1", service,
                   session_token=session_token)
    try:
        r = _req.head(cdproxy_url, auth=auth, timeout=15)
        log.info("  service=%-15s → HTTP %d  Content-Type: %s  Content-Length: %s",
                 service, r.status_code,
                 r.headers.get("content-type", "?"),
                 r.headers.get("content-length", "?"))
        if r.status_code in (200, 206):
            log.info("  ✓ SUCCESS with service=%s!", service)
            break
    except Exception as e:
        log.error("  service=%-15s → FAILED: %s", service, e)

# ── If any 200 found, attempt real download ───────────────────────────────────
log.info("\n▶ Trying GET with best candidate (execute-api)...")
auth = AWS4Auth(access_key, secret_key, "us-east-1", "execute-api",
               session_token=session_token)
r = _req.get(cdproxy_url, auth=auth, timeout=30, stream=True)
log.info("GET cdproxy → HTTP %d", r.status_code)
log.info("Headers: %s", dict(r.headers))
if r.status_code == 200:
    dest = Path(tempfile.mkdtemp()) / node.get("name", "video_test")
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
    log.info("✓ Downloaded %d bytes → %s", dest.stat().st_size, dest)
elif r.status_code in (301, 302, 307, 308):
    log.info("Redirect → %s", r.headers.get("location", "?"))
else:
    log.info("Body: %s", r.text[:300])

client.close()
log.info("\n✓ Done")
