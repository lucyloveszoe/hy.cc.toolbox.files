#!/usr/bin/env python3
"""
Shared Amazon Photos client for mirror-amazonphotos.
Handles auth, browser-side API calls, node enumeration, and file download.

Auth pattern identical to sync-amazonphotos/sync.py (proven in production).
All API calls run as fetch() inside the real Playwright browser session —
this is the only reliable way past Amazon's session binding and CSRF checks.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests as _requests

log = logging.getLogger(__name__)


# ── Session save ─────────────────────────────────────────────────────────────

def save_amazon_session(session_path: Path) -> None:
    """Open a visible browser for manual Amazon login. Saves full state to session_path."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright is not installed.\n"
            "  Run: pip install playwright && playwright install chromium"
        )

    print("\nOpening Amazon Photos in a browser window.")
    print("Sign in when prompted — session saves automatically once photos are loaded.")
    print("(You have up to 3 minutes.)\n")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.goto("https://www.amazon.com/photos/all", timeout=60000)

    if "signin" in page.url or "ap/signin" in page.url:
        print("Browser is on the sign-in page — please sign in...")
        page.wait_for_url("**/photos/**", timeout=180000)

    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    ctx.storage_state(path=str(session_path))
    browser.close()
    pw.stop()
    print(f"\nSession saved → {session_path}")
    print("Future runs will load this session automatically.")


# ── Amazon Photos Client ──────────────────────────────────────────────────────

class AmazonPhotosClient:
    """
    Headless Chromium client for Amazon Photos (download-only).

    All API calls execute as fetch() inside the real browser session so that
    native auth headers (x-amzn-sessionid, etc.) are included automatically —
    identical pattern to sync-amazonphotos, which is proven in production.
    """
    BOOTSTRAP = "https://www.amazon.com/drive/v1"

    def __init__(self, session_path: Path, dry_run: bool = False):
        self.dry_run = dry_run
        self._pw = None
        self._page = None
        self._api_base = self.BOOTSTRAP
        self._auth_headers: dict = {}
        self._native_api_headers: dict = {}
        self._download_cookies: dict = {}

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "playwright is not installed.\n"
                "  Run: pip install playwright && playwright install chromium"
            )

        if not session_path.exists():
            raise RuntimeError(
                f"No session found at {session_path}.\n"
                "  Run: python cloner.py --save-session   (one-time setup)"
            )

        self._pw = sync_playwright().start()
        browser = self._pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            storage_state=str(session_path),
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        self._page = ctx.new_page()
        self._page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        # Capture native auth headers from the first /drive/v1/ request the web app fires.
        # These are session-bound and can't be replicated from Python — must come from browser.
        _STRIP = {"content-length", "host", "origin", "referer", "accept-encoding", "connection"}
        _first_api_url: list[str] = []

        def _on_request(request) -> None:
            if "/drive/v1/" in request.url and not self._native_api_headers:
                _first_api_url.append(request.url)
                h = {k: v for k, v in request.headers.items()
                     if k.lower() not in _STRIP and not k.lower().startswith("sec-")}
                self._native_api_headers = h
                log.info("Amazon Photos: native API headers captured from %s", request.url[:80])

        self._page.on("request", _on_request)

        log.info("Amazon Photos: launching headless Chrome...")
        self._page.goto("https://www.amazon.com/photos/all", timeout=60000, wait_until="load")
        self._page.wait_for_timeout(5000)   # let React app boot and fire initial API calls

        if "signin" in self._page.url or "ap/signin" in self._page.url:
            self.close()
            raise RuntimeError(
                "Amazon Photos redirected to sign-in — session is expired.\n"
                "  Run: python cloner.py --save-session   to log in again."
            )

        log.info("Amazon Photos: page loaded (%s)", self._page.url)

        # Derive exact API base from the first captured request URL
        if _first_api_url:
            raw = _first_api_url[0]
            idx = raw.find("/drive/v1/") + len("/drive/v1")
            self._api_base = raw[:idx]

        log.info("Amazon Photos: API base = %s", self._api_base)

        if self._native_api_headers:
            for k, v in self._native_api_headers.items():
                if k.lower() != "cookie":
                    self._auth_headers[k] = v
            log.info("Amazon Photos: auth headers ready: %s", list(self._auth_headers))
        else:
            log.warning("Amazon Photos: no native headers captured — API calls may fail auth")

        # Extract amazon.com cookies for CDN downloads (thumbnails-photos.amazon.com needs them)
        raw_cookies = self._page.context.cookies()
        self._download_cookies = {
            c["name"]: c["value"]
            for c in raw_cookies
            if "amazon" in c.get("domain", "")
        }
        log.info("Amazon Photos: %d download cookies cached", len(self._download_cookies))

    # ── Core browser fetch ────────────────────────────────────────────────────

    def _eval_fetch(self, method: str, url: str, body: dict | None = None) -> dict:
        """Execute fetch() inside the browser. Returns {status: int, data: dict}."""
        if not url.startswith("http"):
            url = f"https://www.amazon.com{url}"

        body_arg = "null"
        if body is not None:
            body_arg = json.dumps(json.dumps(body))

        headers = {k: v for k, v in self._auth_headers.items()
                   if k.lower() not in ("cookie", "content-type")}
        headers["Content-Type"] = "application/json"

        js = f"""
        async () => {{
            const opts = {{
                method: {json.dumps(method)},
                headers: {json.dumps(headers)}
            }};
            const bodyStr = {body_arg};
            if (bodyStr !== null) opts.body = bodyStr;
            try {{
                const r = await fetch({json.dumps(url)}, opts);
                let data;
                try {{ data = await r.json(); }} catch (_) {{ data = {{}}; }}
                return {{status: r.status, data}};
            }} catch (e) {{
                return {{status: 0, data: {{}}, error: String(e)}};
            }}
        }}
        """
        return self._page.evaluate(js)

    # ── Node enumeration ──────────────────────────────────────────────────────

    def list_nodes(self, asset_type: str = "IMAGE", limit: int = 200) -> list[dict]:
        """
        Return all file nodes of the given type. Handles pagination automatically.
        asset_type: "IMAGE" for photos, "VIDEO" for videos.
        Fetches all FILE kind nodes, then filters client-side by MIME type.
        """
        all_nodes: list[dict] = []
        start_token: str | None = None
        page_num = 0

        # Determine MIME prefix for filtering
        mime_prefix = "image/" if asset_type == "IMAGE" else "video/"

        while True:
            # Get all FILE nodes without asset/MIME filter; filter client-side
            filters = quote("kind:FILE")
            url = (f"{self._api_base}/nodes?ContentType=JSON&resourceVersion=V2"
                   f"&filters={filters}&limit={limit}&tempLink=false")
            if start_token:
                url += f"&startToken={quote(start_token)}"

            result = self._eval_fetch("GET", url)
            if result["status"] != 200:
                log.error("list_nodes(%s) page %d failed: HTTP %s — %s",
                          asset_type, page_num, result["status"], result.get("data"))
                break

            body = result.get("data", {})
            items = body.get("data", []) if isinstance(body, dict) else []
            batch = items if isinstance(items, list) else []

            # Filter client-side by MIME type
            filtered = [
                item for item in batch
                if (item.get("contentProperties", {}).get("contentType", "").startswith(mime_prefix))
            ]
            all_nodes.extend(filtered)
            page_num += 1
            log.info("list_nodes(%s): page %d — %d items (filtered: %d, total: %d)",
                     asset_type, page_num, len(batch), len(filtered), len(all_nodes))

            start_token = body.get("nextToken") if isinstance(body, dict) else None
            if not start_token:
                break

        return all_nodes

    def list_albums(self, limit: int = 200) -> list[dict]:
        """Return all album nodes (kind:VISUAL_COLLECTION). Handles pagination."""
        all_albums: list[dict] = []
        start_token: str | None = None

        while True:
            filters = quote("kind:VISUAL_COLLECTION")
            url = (f"{self._api_base}/nodes?ContentType=JSON&resourceVersion=V2"
                   f"&filters={filters}&limit={limit}")
            if start_token:
                url += f"&startToken={quote(start_token)}"

            result = self._eval_fetch("GET", url)
            if result["status"] != 200:
                log.error("list_albums failed: HTTP %s — %s", result["status"], result.get("data"))
                break

            body = result.get("data", {})
            items = body.get("data", []) if isinstance(body, dict) else []
            all_albums.extend(items if isinstance(items, list) else [])

            start_token = body.get("nextToken") if isinstance(body, dict) else None
            if not start_token:
                break

        log.info("list_albums: found %d albums total", len(all_albums))
        return all_albums

    def list_album_children(self, album_id: str, limit: int = 200) -> list[dict]:
        """Return all child node dicts for a given album. Handles pagination."""
        all_children: list[dict] = []
        start_token: str | None = None

        while True:
            # Get all children without filter; filter client-side for image MIME types
            url = (f"{self._api_base}/nodes/{album_id}/children?ContentType=JSON"
                   f"&resourceVersion=V2&limit={limit}")
            if start_token:
                url += f"&startToken={quote(start_token)}"

            result = self._eval_fetch("GET", url)
            if result["status"] != 200:
                log.error("list_album_children(%s) failed: HTTP %s", album_id, result["status"])
                break

            body = result.get("data", {})
            items = body.get("data", []) if isinstance(body, dict) else []
            batch = items if isinstance(items, list) else []

            # Filter client-side to image types only
            image_items = [
                item for item in batch
                if (item.get("contentProperties", {}).get("contentType", "").startswith("image/"))
            ]
            all_children.extend(image_items)

            start_token = body.get("nextToken") if isinstance(body, dict) else None
            if not start_token:
                break

        log.debug("list_album_children(%s): fetched %d items, %d are images",
                  album_id, len(batch), len(image_items))
        return all_children

    # ── Download ──────────────────────────────────────────────────────────────

    def get_download_url(self, node_id: str) -> str | None:
        """
        Fetch a temporary pre-signed download URL for a node via tempLink=true.
        Pre-signed URLs are self-contained — no auth headers needed for the download itself.
        """
        url = (f"{self._api_base}/nodes/{node_id}"
               f"?ContentType=JSON&resourceVersion=V2&tempLink=true")
        result = self._eval_fetch("GET", url)
        if result["status"] != 200:
            log.error("get_download_url(%s) failed: HTTP %s", node_id, result["status"])
            return None

        body = result.get("data", {})
        if not isinstance(body, dict):
            log.error("get_download_url(%s): response not a dict: %s", node_id, type(body))
            return None

        # Try multiple possible field names for the download URL
        temp_url = body.get("tempLink")
        if temp_url:
            log.debug("get_download_url(%s): found tempLink", node_id)
            return temp_url

        # Amazon might return it under a different field name
        if "contentProperties" in body and isinstance(body["contentProperties"], dict):
            cp = body["contentProperties"]
            if "url" in cp:
                log.debug("get_download_url(%s): using contentProperties.url", node_id)
                return cp["url"]

        # Log full response for debugging
        log.warning("get_download_url(%s): no tempLink found. Response keys: %s",
                    node_id, list(body.keys()) if isinstance(body, dict) else type(body))
        return None

    def download_node(self, node: dict, dest_path: Path) -> bool:
        """
        Download a photo or video node to dest_path.

        Photos: thumbnails-photos.amazon.com CDN — no OAuth needed, near-original quality.
        Videos: cdproxy (content-na.drive.amazonaws.com) — requires tempLink + Amazon
                cookies + x-amzn-sessionid. Python requests sends the HttpOnly at-main
                cookie that cross-origin browser fetch cannot include.
        """
        node_id = node["id"]
        name = node.get("name", node_id)
        content_type = node.get("contentProperties", {}).get("contentType", "")

        if content_type.startswith("video/"):
            # Fetch the cdproxy tempLink for this video node
            tl_url = (f"{self._api_base}/nodes/{node_id}"
                      f"?ContentType=JSON&resourceVersion=V2&tempLink=true")
            tl_result = self._eval_fetch("GET", tl_url)
            dl_url = (tl_result.get("data") or {}).get("tempLink")
            if not dl_url:
                log.error("No tempLink for video %s (HTTP %s)", name, tl_result.get("status"))
                return False
            cdproxy_headers = {
                "x-amzn-sessionid": self._auth_headers.get("x-amzn-sessionid", ""),
                "x-amz-clouddrive-appid": self._auth_headers.get("x-amz-clouddrive-appid", ""),
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            req_kwargs = dict(headers=cdproxy_headers, cookies=self._download_cookies,
                              stream=True, timeout=300)
        else:
            owner_id = node.get("ownerId", "")
            dl_url = (f"https://thumbnails-photos.amazon.com/v1/thumbnail/{node_id}"
                      f"?viewBox=10000&ownerId={owner_id}")
            req_kwargs = dict(cookies=self._download_cookies, stream=True, timeout=120)

        try:
            r = _requests.get(dl_url, **req_kwargs)
            r.raise_for_status()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        except Exception as e:
            log.error("Download failed for %s: %s", name, e)
            if dest_path.exists():
                dest_path.unlink()
            return False

        # Preserve the original shoot/upload date as the file mtime
        cp = node.get("contentProperties", {}) or {}
        date_str = (
            (cp.get("image") or {}).get("dateTimeOriginal")
            or (cp.get("video") or {}).get("dateTimeOriginal")
            or node.get("createdDate")
        )
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                ts = dt.timestamp()
                os.utime(dest_path, (ts, ts))
            except Exception:
                pass

        return True

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._pw:
            try:
                self._page.context.browser().close()
            except Exception:
                pass
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None
            self._page = None
