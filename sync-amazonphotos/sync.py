#!/usr/bin/env python3
"""
sync-amazonphotos: Sync a pics/vids folder to Amazon Photos + AWS S3.

Usage:
    python sync.py --sync-root C:\\tmp\\yu.sync
    python sync.py --sync-root C:\\tmp\\yu.sync --dry-run
    python sync.py --sync-root C:\\tmp\\yu.sync --skip-amazon
    python sync.py --save-session          # one-time login, no sync
"""

import argparse
import json
import logging
import os
import shutil
import zipfile
from pathlib import Path
from urllib.parse import quote

import boto3
from boto3.s3.transfer import TransferConfig as S3TransferConfig
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from tqdm import tqdm

PICTURE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".heic", ".webp", ".raw"}
VIDEO_EXTS   = {".mp4", ".avi", ".mov", ".flv", ".mkv", ".wmv", ".m4v", ".3gp"}
S3_BUCKET    = "yu.vbackup.family"

# 32 MB chunks → ≤5 parts for a 135 MB file; serial to avoid connection storms
_S3_TRANSFER = S3TransferConfig(multipart_chunksize=32 * 1024 * 1024, max_concurrency=1)

log = logging.getLogger(__name__)


# ── Amazon Photos cookie parser ─────────────────────────────────────────────

def _parse_netscape_cookies(path: Path) -> list[dict]:
    """Convert Netscape cookies.txt (7-column TSV) to the list-of-dicts Playwright expects."""
    cookies = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        http_only = False
        if line.startswith("#HttpOnly_"):
            http_only = True
            line = line[len("#HttpOnly_"):]
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, path_, secure, expiry_str, name, value = parts[:7]
        try:
            expiry = int(expiry_str)
        except ValueError:
            expiry = -1
        cookies.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path_,
            "expires": expiry,
            "httpOnly": http_only,
            "secure": secure.upper() == "TRUE",
        })
    return cookies


# ── Amazon Photos Client (Playwright-based) ─────────────────────────────────

def save_amazon_session(session_path: Path) -> None:
    """
    Open a VISIBLE browser so the user can log in to Amazon Photos manually.
    Saves the full browser state (including session cookies) to session_path.
    Run once with: python sync.py --save-session
    """
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

    # If Amazon redirected to sign-in, wait for the user to complete it
    if "signin" in page.url or "ap/signin" in page.url:
        print("Browser is on the sign-in page — please sign in...")
        page.wait_for_url("**/photos/**", timeout=180000)

    # Wait for the photos page to fully settle
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    ctx.storage_state(path=str(session_path))
    browser.close()
    pw.stop()
    print(f"\nSession saved → {session_path}")
    print("Future runs will load this session automatically.")


class AmazonPhotosClient:
    """
    Uses a headless Chromium browser (via Playwright) to interact with Amazon Photos.
    All API calls are executed as fetch() inside the real browser session — this bypasses
    Amazon's CSRF tokens, session binding, and anti-bot checks that block plain requests.
    """
    BOOTSTRAP = "https://www.amazon.com/drive/v1"

    def __init__(self, session_path: Path | None, cookies_path: Path | None,
                 dry_run: bool = False):
        self.dry_run = dry_run
        self._pw = None
        self._page = None
        self._api_base = self.BOOTSTRAP
        self._auth_headers: dict = {}

        if dry_run:
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "playwright is not installed.\n"
                "  Run: pip install playwright && playwright install chromium"
            )

        self._pw = sync_playwright().start()
        browser = self._pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )

        ctx_kwargs: dict = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if session_path and session_path.exists():
            ctx_kwargs["storage_state"] = str(session_path)
            log.info("Amazon Photos: loading saved session from %s", session_path.name)
        elif cookies_path and cookies_path.exists():
            log.info("Amazon Photos: loading %d cookies from %s",
                     len(_parse_netscape_cookies(cookies_path)), cookies_path.name)
        else:
            raise RuntimeError(
                "No Amazon Photos session found.\n"
                "  Run: python sync.py --save-session   (one-time setup)"
            )

        ctx = browser.new_context(**ctx_kwargs)
        if not (session_path and session_path.exists()) and cookies_path:
            ctx.add_cookies(_parse_netscape_cookies(cookies_path))

        self._page = ctx.new_page()
        self._page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        # Playwright's page.on("request") fires at the real network layer — after service
        # workers and JS frameworks have added their auth headers.  This is the only
        # reliable way to see what the web app actually sends to the Drive API.
        _STRIP = {"content-length", "host", "origin", "referer", "accept-encoding", "connection"}
        _first_api_url: list[str] = []   # mutable container for closure

        def _on_request(request: object) -> None:
            if "/drive/v1/" in request.url and not self._native_api_headers:
                _first_api_url.append(request.url)
                h = {k: v for k, v in request.headers.items()
                     if k.lower() not in _STRIP and not k.lower().startswith("sec-")}
                self._native_api_headers = h
                log.info("Amazon Photos: native API call → %s", request.url[:90])
                log.info("Amazon Photos: native header keys: %s",
                         [k for k in h if k.lower() != "cookie"])

        self._native_api_headers: dict = {}
        self._page.on("request", _on_request)

        log.info("Amazon Photos: launching headless Chrome → https://www.amazon.com/photos/all")
        self._page.goto("https://www.amazon.com/photos/all", timeout=60000, wait_until="load")
        self._page.wait_for_timeout(5000)   # let React app boot and fire initial API calls
        log.info("Amazon Photos: landed on %s", self._page.url)

        if "signin" in self._page.url or "ap/signin" in self._page.url:
            self.close()
            raise RuntimeError(
                "Amazon Photos redirected to sign-in — session is expired or missing.\n"
                "  Run: python sync.py --save-session   to log in and save a fresh session."
            )
        log.info("Amazon Photos: page loaded (%s)", self._page.url)

        # Derive API base URL from the first captured native request
        if _first_api_url:
            raw = _first_api_url[0]
            idx = raw.find("/drive/v1/") + len("/drive/v1")
            self._api_base = raw[:idx]    # e.g. "https://www.amazon.com/drive/v1"

        log.info("Amazon Photos: API base = %s", self._api_base)

        # Promote captured native headers (excluding cookie — browser sends it automatically).
        # Auth might be x-amz-access-token, Authorization, or something else — we take whatever
        # the web app actually sends rather than guessing.
        if self._native_api_headers:
            for k, v in self._native_api_headers.items():
                if k.lower() != "cookie":
                    self._auth_headers[k] = v
            log.info("Amazon Photos: auth headers from native call: %s", list(self._auth_headers))
        else:
            log.warning("Amazon Photos: no native API headers captured — API calls may fail")

    def _eval_fetch(self, method: str, url: str, body: dict | None = None) -> dict:
        """Run a fetch() call inside the browser and return {status: int, data: dict}."""
        if not url.startswith("http"):
            url = f"https://www.amazon.com{url}"

        body_arg = "null"
        if body is not None:
            body_arg = json.dumps(json.dumps(body))  # outer quotes make it a JS string literal

        # Build headers: start from native auth headers, then force our Content-Type.
        # Skip cookie (browser sends it automatically) and content-type from native
        # headers (we always want application/json for these API calls).
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

    def _find_album(self, name: str) -> str | None:
        """Return album node id if an album with this exact name exists, else None."""
        filters = quote(f"kind:VISUAL_COLLECTION AND name:{name}")
        url = f"{self._api_base}/nodes?ContentType=JSON&filters={filters}&resourceVersion=V2"
        result = self._eval_fetch("GET", url)
        if result["status"] != 200:
            log.error("Failed to search album '%s': HTTP %s — %s", name, result["status"], result.get("data"))
            return None
        data = result.get("data", {})
        items = data.get("data", []) if isinstance(data, dict) else data
        for item in (items if isinstance(items, list) else []):
            if item.get("name", "").lower().strip() == name.lower().strip():
                return item["id"]
        return None

    def create_album(self, name: str) -> str | None:
        """Create album. Returns album_id, or None if album already exists (caller should skip)."""
        if self.dry_run:
            log.info("[DRY-RUN] Would create Amazon Photos album: %s", name)
            return "dry-run-album-id"
        existing = self._find_album(name)
        if existing:
            log.warning("Amazon Photos: album '%s' already exists — skipping upload", name)
            return None
        result = self._eval_fetch(
            "POST",
            f"{self._api_base}/nodes?ContentType=JSON&resourceVersion=V2",
            body={"name": name, "kind": "VISUAL_COLLECTION"},
        )
        album_id = result.get("data", {}).get("id")
        if not album_id:
            log.error("Album creation failed for '%s': HTTP %s — %s",
                      name, result["status"], result.get("data"))
            return None
        log.info("Created Amazon Photos album '%s' (id=%s)", name, album_id)
        return album_id

    def _find_photo_by_name(self, name: str) -> str | None:
        """Search All Photos for a file node with this exact name; return its node id."""
        filters = quote(f"name:{name} AND status:AVAILABLE")
        r = self._eval_fetch(
            "GET",
            f"{self._api_base}/nodes?ContentType=JSON&filters={filters}&resourceVersion=V2",
        )
        data = r.get("data", {})
        items = data.get("data", []) if isinstance(data, dict) else data
        matches = [i for i in (items if isinstance(items, list) else [])
                   if i.get("name", "").lower() == name.lower()]
        # VISUAL_COLLECTION rejects raw FILE nodes (no contentProperties.image).
        # Prefer fully-processed nodes that have image metadata.
        for item in matches:
            if item.get("contentProperties", {}).get("image"):
                return item["id"]
        if matches:
            return matches[0]["id"]
        return None

    def upload_photo(self, album_id: str, file_path: Path) -> bool:
        """Upload one photo to Amazon Photos via the web UI (Add → Upload photos),
        then link it to the album via API."""
        if self.dry_run:
            log.info("[DRY-RUN] Would upload %s → album", file_path.name)
            return True

        # Stay on the album page (navigate once)
        album_url = f"https://www.amazon.com/photos/album/{album_id}"
        if f"/album/{album_id}" not in self._page.url:
            self._page.goto(album_url, timeout=30000, wait_until="networkidle")
            self._page.wait_for_timeout(2000)

        try:
            # 3-step UI flow: Add dropdown → Upload photos → Upload and add to this album
            with self._page.expect_file_chooser(timeout=12000) as fc:
                self._page.click("button.toggle:has-text('Add')", timeout=5000)
                self._page.click("li:has-text('Upload photos')", timeout=3000)
                # Disambiguation dialog — choose the album-scoped upload
                self._page.click(
                    "button:has-text('Upload and add to this album')", timeout=5000
                )
            fc.value.set_files(str(file_path.resolve()))
            self._page.wait_for_load_state("networkidle", timeout=60000)
            self._page.wait_for_timeout(2000)   # let async album-link complete
        except Exception as e:
            log.error("Upload UI failed for %s: %s", file_path.name, e)
            # Don't return — still try to link via API below

        # Always link via API: handles fresh uploads AND deduplicated (already-existing) files.
        node_id = self._find_photo_by_name(file_path.name)
        if not node_id:
            log.error("Could not find %s in Amazon Photos after upload", file_path.name)
            return False

        add = self._eval_fetch(
            "PUT",
            f"{self._api_base}/nodes/{album_id}/children/{node_id}?ContentType=JSON&resourceVersion=V2",
        )
        if add["status"] in (200, 201, 204):
            log.info("Uploaded %s → Amazon Photos album", file_path.name)
            return True
        # 409 = already in the album
        if add["status"] == 409:
            log.info("Uploaded %s → Amazon Photos album (already linked)", file_path.name)
            return True
        log.error("Failed to link %s to album: HTTP %s — %s",
                  file_path.name, add["status"], add.get("data"))
        return False

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


# ── S3 helpers ──────────────────────────────────────────────────────────────

def s3_key_exists(s3_client, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def s3_upload(s3_client, local_path: Path, key: str, dry_run: bool = False) -> bool:
    """Upload file to S3 with ONEZONE_IA storage. Returns True if uploaded, False if skipped."""
    if s3_key_exists(s3_client, key):
        log.warning("S3: s3://%s/%s already exists — skipping", S3_BUCKET, key)
        return False
    if dry_run:
        log.info("[DRY-RUN] Would upload %s → s3://%s/%s [ONEZONE_IA]", local_path.name, S3_BUCKET, key)
        return True
    for attempt in range(1, 4):
        try:
            s3_client.upload_file(
                str(local_path),
                S3_BUCKET,
                key,
                ExtraArgs={"StorageClass": "ONEZONE_IA"},
                Config=_S3_TRANSFER,
            )
            log.info("Uploaded → s3://%s/%s [ONEZONE_IA]", S3_BUCKET, key)
            return True
        except Exception as e:
            if attempt < 3:
                log.warning("S3 upload attempt %d/3 failed (%s) — retrying", attempt, e.__class__.__name__)
            else:
                raise


def extract_year(folder_name: str) -> str | None:
    """Return 4-digit year string from first 4 chars of folder name, or None."""
    prefix = folder_name[:4]
    if prefix.isdigit() and 1900 <= int(prefix) <= 2100:
        return prefix
    log.warning("Cannot extract year from folder '%s' — expected 4-digit year prefix", folder_name)
    return None


# ── Step 1: Integrity check ─────────────────────────────────────────────────

def check_and_fix_integrity(sync_root: Path, dry_run: bool = False) -> None:
    pics_root = sync_root / "pics"
    vids_root = sync_root / "vids"

    # Videos found under pics → move to vids/{grandchild}_vids/
    if pics_root.exists():
        for folder in sorted(pics_root.iterdir()):
            if not folder.is_dir():
                continue
            for f in folder.iterdir():
                if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
                    target_dir = vids_root / f"{folder.name}_vids"
                    log.warning("INTEGRITY: video '%s' in pics/%s — moving to vids/%s_vids/",
                                f.name, folder.name, folder.name)
                    if not dry_run:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(f), str(target_dir / f.name))

    # Pictures found under vids → move to pics/{grandchild}_pics/
    if vids_root.exists():
        for folder in sorted(vids_root.iterdir()):
            if not folder.is_dir():
                continue
            for f in folder.iterdir():
                if f.is_file() and f.suffix.lower() in PICTURE_EXTS:
                    target_dir = pics_root / f"{folder.name}_pics"
                    log.warning("INTEGRITY: picture '%s' in vids/%s — moving to pics/%s_pics/",
                                f.name, folder.name, folder.name)
                    if not dry_run:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(f), str(target_dir / f.name))


# ── Step 2: Process pics ────────────────────────────────────────────────────

def process_pics(
    sync_root: Path,
    bak_root: Path,
    amazon: AmazonPhotosClient | None,
    s3_client,
    dry_run: bool = False,
) -> None:
    pics_root = sync_root / "pics"
    if not pics_root.exists():
        log.info("pics/ not found at %s — skipping", pics_root)
        return

    # Collect work: active folders + orphan zips (folder deleted in a prior interrupted run)
    names_from_dirs = {f.name for f in pics_root.iterdir() if f.is_dir()}
    names_from_zips = {z.stem for z in pics_root.glob("*.zip")}
    all_names = sorted(names_from_dirs | names_from_zips)

    if not all_names:
        log.info("Nothing to process under pics/")
        return

    bak_pics = bak_root / "pics"

    for name in all_names:
        folder   = pics_root / name
        zip_path = pics_root / f"{name}.zip"

        folder_exists = folder.is_dir()
        zip_exists    = zip_path.exists()

        # (a) Skip empty folders (no files, no zip)
        pic_files: list[Path] = []
        if folder_exists:
            pic_files = [f for f in folder.iterdir() if f.is_file()]
            if not pic_files and not zip_exists:
                log.info("Skipping empty folder: pics/%s", name)
                if not dry_run:
                    shutil.rmtree(folder)
                continue

        log.info("── pics: %s ──", name)

        if zip_exists:
            # (b) Zip exists from a prior interrupted run — skip Amazon Photos entirely
            log.info("Zip already exists for '%s' — skipping Amazon Photos", name)
        else:
            # (c) Amazon Photos: create album then upload; skip both if album already exists
            if amazon is not None:
                album_id = amazon.create_album(name)
                if album_id:
                    for pic in tqdm(pic_files, desc=f"  Amazon Photos ← {name}", unit="file", leave=False):
                        try:
                            amazon.upload_photo(album_id, pic)
                        except Exception as e:
                            log.error("Failed to upload %s to Amazon Photos: %s", pic.name, e)
                # album_id is None → album already existed; treat as done

            # Create zip now that all uploads are complete
            if dry_run:
                log.info("[DRY-RUN] Would zip %s/ → %s.zip", name, name)
            else:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in folder.rglob("*"):
                        if f.is_file():
                            zf.write(f, f.relative_to(pics_root))
                log.info("Zipped → %s.zip (%.2f MB)", name, zip_path.stat().st_size / 1_048_576)

        # Delete original folder now that zip is safe
        if folder_exists:
            if dry_run:
                log.info("[DRY-RUN] Would delete pics/%s/", name)
            else:
                shutil.rmtree(folder)
                log.info("Deleted pics/%s/", name)

        # Upload zip to S3
        year = extract_year(name)
        if year:
            s3_key = f"singlepics/{year}_Pics/{name}.zip"
            s3_upload(s3_client, zip_path, s3_key, dry_run)
        else:
            log.warning("Skipping S3 upload for '%s' — year not found in folder name", name)

        # Archive zip to .bak/pics/
        if dry_run:
            log.info("[DRY-RUN] Would archive zip to .bak/pics/%s.zip", name)
        else:
            bak_pics.mkdir(parents=True, exist_ok=True)
            shutil.move(str(zip_path), str(bak_pics / zip_path.name))
            log.info("Archived zip → .bak/pics/%s.zip", name)


# ── Step 3: Process vids ────────────────────────────────────────────────────

def process_vids(
    sync_root: Path,
    bak_root: Path,
    s3_client,
    dry_run: bool = False,
) -> None:
    vids_root = sync_root / "vids"
    if not vids_root.exists():
        log.info("vids/ not found at %s — skipping", vids_root)
        return

    folders = sorted(f for f in vids_root.iterdir() if f.is_dir())
    if not folders:
        log.info("No folders found under vids/ — nothing to process")
        return

    for folder in folders:
        name = folder.name
        log.info("── vids: %s ──", name)

        year = extract_year(name)
        if not year:
            log.warning("Skipping '%s' — cannot determine year", name)
            continue

        vid_files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTS]
        if not vid_files:
            log.info("No video files in %s — skipping", name)
            if not dry_run:
                shutil.rmtree(folder)
            continue

        for vid in tqdm(vid_files, desc=f"  S3 ← {name}", unit="file", leave=False):
            s3_key = f"vid/{year}_videos/{name}/{vid.name}"
            try:
                s3_upload(s3_client, vid, s3_key, dry_run)
                if not dry_run:
                    bak_file = bak_root / "vids" / name / vid.name
                    bak_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(vid), str(bak_file))
                    log.info("Moved %s → .bak/vids/%s/", vid.name, name)
            except Exception as e:
                log.error("Failed to process %s: %s", vid.name, e)

        # Delete folder after all videos are moved; keep it if any files remain (upload errors)
        if not dry_run:
            remaining = [f for f in folder.iterdir() if f.is_file()]
            if not remaining:
                folder.rmdir()
                log.info("Deleted vids/%s/", name)
            else:
                log.warning("vids/%s/ kept — %d file(s) remain (check errors above)", name, len(remaining))


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Sync pics/vids to Amazon Photos + AWS S3")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview all actions without modifying any files or making any uploads")
    parser.add_argument("--skip-amazon", action="store_true",
                        help="Skip Amazon Photos entirely (S3 sync only)")
    parser.add_argument("--sync-root",
                        help="Path to the sync root folder (e.g. C:\\tmp\\yu.sync)")
    parser.add_argument("--save-session", action="store_true",
                        help="Open a browser window to log in to Amazon Photos and save the session")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    script_dir = Path(__file__).parent
    session_path  = script_dir / "session.json"
    cookies_path  = script_dir / os.getenv("AMAZON_COOKIES_FILE", "cookies.txt")

    # One-time session save mode — opens a visible browser, no sync
    if args.save_session:
        save_amazon_session(session_path)
        return

    if not args.sync_root:
        parser.error("--sync-root is required (e.g. --sync-root C:\\tmp\\yu.sync)")

    sync_root = Path(args.sync_root)
    bak_root  = sync_root / ".bak"

    if not sync_root.exists():
        log.error("Sync root does not exist: %s", sync_root)
        raise SystemExit(1)

    if args.dry_run:
        log.info("═══ DRY-RUN MODE — no files will be changed or uploaded ═══")

    # S3 client
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    )

    # Amazon Photos client
    amazon: AmazonPhotosClient | None = None
    if not args.skip_amazon:
        if not session_path.exists() and not cookies_path.exists():
            log.error("No Amazon Photos session found.")
            log.error("  Run: python sync.py --save-session")
            log.error("  Or:  python sync.py --skip-amazon")
            raise SystemExit(1)
        try:
            amazon = AmazonPhotosClient(
                session_path=session_path if session_path.exists() else None,
                cookies_path=cookies_path if cookies_path.exists() else None,
                dry_run=args.dry_run,
            )
        except RuntimeError as e:
            log.error("Amazon Photos init failed: %s", e)
            raise SystemExit(1)

    log.info("Sync root : %s", sync_root)
    log.info("Bak root  : %s", bak_root)
    log.info("Amazon    : %s", "enabled (headless Chrome)" if amazon else "SKIPPED")

    try:
        log.info("▶ Step 1 — Integrity check")
        check_and_fix_integrity(sync_root, dry_run=args.dry_run)

        log.info("▶ Step 2 — Process pics")
        process_pics(sync_root, bak_root, amazon, s3, dry_run=args.dry_run)

        log.info("▶ Step 3 — Process vids")
        process_vids(sync_root, bak_root, s3, dry_run=args.dry_run)

        log.info("✓ Done")
    finally:
        if amazon is not None:
            amazon.close()


if __name__ == "__main__":
    main()
