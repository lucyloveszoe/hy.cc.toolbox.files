#!/usr/bin/env python3
"""
Click play on a video in Amazon Photos — intercept the streaming URL.
The transcoded MP4 must come from somewhere; this captures it.
"""

import json
import logging
from pathlib import Path
from urllib.parse import quote

from amazon_client import AmazonPhotosClient

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

session_file = Path(__file__).parent.parent / "sync-amazonphotos" / "session.json"
client = AmazonPhotosClient(session_file, dry_run=False)

# ── Get a video node ID ───────────────────────────────────────────────────────
filters = quote("kind:FILE")
list_url = (f"{client._api_base}/nodes?ContentType=JSON&resourceVersion=V2"
            f"&filters={filters}&limit=200&tempLink=false")
result = client._eval_fetch("GET", list_url)
all_items = result.get("data", {}).get("data", [])
video_nodes = [n for n in all_items
               if n.get("contentProperties", {}).get("contentType", "").startswith("video/")]

if not video_nodes:
    log.error("No video nodes found")
    client.close()
    exit(1)

node = video_nodes[0]
node_id = node["id"]
owner_id = node.get("ownerId", "")
log.info("Video: %s  id=%s", node.get("name"), node_id)

# ── Intercept ALL network requests while on detail page ───────────────────────
captured: list[dict] = []

def _on_request(req):
    url = req.url
    # Skip common static assets and known non-video domains
    if any(x in url for x in ("google", "analytics", "ads", ".css", ".js", ".svg", ".ico",
                               "cloudfront.net/cooper")):
        return
    captured.append({"url": url, "method": req.method,
                     "resource": req.resource_type,
                     "headers": {k: v for k, v in req.headers.items()
                                 if k.lower() in ("accept", "range", "content-type")}})

client._page.on("request", _on_request)

# ── Navigate to detail page ───────────────────────────────────────────────────
detail_url = f"https://www.amazon.com/photos/detail/{node_id}"
log.info("Loading detail page: %s", detail_url)
client._page.goto(detail_url, timeout=30000, wait_until="domcontentloaded")
client._page.wait_for_timeout(3000)

# ── Try to click the play button ──────────────────────────────────────────────
log.info("Attempting to click play button...")
try:
    # Common selectors for video play buttons
    for selector in ["video", "button[aria-label*='lay']", "[data-testid*='play']",
                     ".play-button", "[class*='play']", "button.play"]:
        el = client._page.query_selector(selector)
        if el:
            log.info("Found element: %s — clicking", selector)
            el.click()
            client._page.wait_for_timeout(5000)
            break
    else:
        log.info("No play button found via CSS selectors — trying video element click")
        client._page.evaluate("""
            const v = document.querySelector('video');
            if (v) { v.play(); }
        """)
        client._page.wait_for_timeout(5000)
except Exception as e:
    log.warning("Click failed: %s — waiting anyway", e)
    client._page.wait_for_timeout(5000)

# ── Print all captured requests ───────────────────────────────────────────────
log.info("\n=== All non-static requests captured (%d total) ===", len(captured))
for i, req in enumerate(captured):
    log.info("[%d] %s %s  type=%s", i, req["method"], req["url"][:180], req["resource"])
    if req["headers"]:
        log.info("     headers: %s", req["headers"])

# ── Also try fetching the cdproxy URL from inside the browser ─────────────────
cdproxy_url = f"https://content-na.drive.amazonaws.com/cdproxy/nodes/{node_id}"
log.info("\n▶ Trying cdproxy URL from inside browser (HEAD only)...")
cdproxy_result = client._page.evaluate(f"""
async () => {{
    try {{
        const r = await fetch({json.dumps(cdproxy_url)}, {{method: 'HEAD'}});
        const hdrs = {{}};
        r.headers.forEach((v, k) => {{ hdrs[k] = v; }});
        return {{status: r.status, headers: hdrs, ok: r.ok}};
    }} catch(e) {{
        return {{status: 0, error: String(e)}};
    }}
}}
""")
log.info("cdproxy HEAD from browser: %s", json.dumps(cdproxy_result, indent=2))

# ── Try GET with Range header (like a video player would) ─────────────────────
log.info("\n▶ Trying cdproxy GET with Range header from inside browser...")
cdproxy_get = client._page.evaluate(f"""
async () => {{
    try {{
        const r = await fetch({json.dumps(cdproxy_url)}, {{
            method: 'GET',
            headers: {{'Range': 'bytes=0-1023'}}
        }});
        const hdrs = {{}};
        r.headers.forEach((v, k) => {{ hdrs[k] = v; }});
        const body = await r.text();
        return {{status: r.status, headers: hdrs, bodyPreview: body.substring(0, 200)}};
    }} catch(e) {{
        return {{status: 0, error: String(e)}};
    }}
}}
""")
log.info("cdproxy GET(Range) from browser: %s", json.dumps(cdproxy_get, indent=2))

client.close()
log.info("\n✓ Done")
