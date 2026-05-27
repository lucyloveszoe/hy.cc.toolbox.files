# mirror-amazonphotos — Development Progress

**Last updated: 2026-05-26**
**Status: Built — not yet tested against live Amazon Photos account.**

---

## What's Built

- `amazon_client.py` — Playwright client with `list_nodes`, `list_albums`, `list_album_children`, `get_download_url`, `download_node` — **code complete**
- `db.py` — SQLite schema + helpers (photos, albums, album_photos, videos) — **unit tested, passing**
- `cloner.py` — photos + albums sync CLI with `--month` filter — **code complete**
- `videos_cloner.py` — videos sync CLI with `--month` filter — **code complete**
- `viewer.py` — tkinter GUI, album sidebar, lazy thumbnail loading, full-size popup — **code complete**
- venv set up with Python 3.13, all deps installed (playwright, pillow, pillow-heif, requests, tqdm)

---

## Key Design Decisions

### Auth — identical to sync-amazonphotos (proven in production)
- `storage_state` (session.json) restores the full Playwright browser state including session-scoped cookies
- `--save-session`: opens visible Chromium, waits for manual login, saves full state
- Default session path: `../sync-amazonphotos/session.json` — shares with sibling project, no re-login needed
- Override with `--session-file PATH` if needed

### API calls — `_eval_fetch` (browser-side fetch)
- All Amazon Photos API calls run as `fetch()` inside the real Playwright browser session
- This is the only reliable approach: native headers (`x-amzn-sessionid`, etc.) are session-bound and cannot be replicated from Python's `requests`
- Auth headers captured from the first `/drive/v1/` network request the React app fires on page load
- `resourceVersion=V2` is required on ALL node operations — V1 endpoint returns NODE_NOT_FOUND for V2-created nodes

### Node enumeration — `asset=IMAGE` / `asset=VIDEO` query param
- Used `asset=IMAGE` and `asset=VIDEO` to list photo and video nodes respectively
- Alternative: `filters=kind:FILE AND contentProperties.contentType:image%2F*` — not used because wildcard support in filters is uncertain
- Pagination: loop on `nextToken` from response body until absent

### Download — `tempLink=true` → `requests.get()`
- `GET /nodes/{id}?resourceVersion=V2&ContentType=JSON&tempLink=true` returns a `tempLink` pre-signed URL
- Pre-signed URL is self-contained (auth embedded in URL) — downloaded with plain `requests.get()`, no browser needed
- **RISK**: `tempLink` field not yet verified against a live account. If absent, `download_node` logs an error per file and skips it safely. Re-run after investigating.

### Album children — `GET /nodes/{albumId}/children`
- Uses `asset=IMAGE` to filter to photo nodes only
- Returns full node dicts (not just IDs) so we have names for local path mapping

### File mtime preservation
- After download, file mtime is set to the photo's `exif dateTimeOriginal` (shoot date) when available, falling back to `createdDate` (upload date)
- Implemented in `download_node()` via `os.utime()`

### `--month YYYY-MM` filter
- Filters the already-fetched node list by extracting the `YYYY-MM` prefix from each node's date
- Photos: prefers exif shoot date; falls back to upload date
- Videos: uses upload date only (no exif for videos)
- **Critical**: when `--month` is active, the deletion step is skipped — a partial sync must never delete files from other months

### Local album format — JSON files in `albums/`
- One `{album_name}.json` per album
- Contains: `{name, album_id, created_date, photo_count, photos: [{node_id, name, local_path}]}`
- `local_path` points to the corresponding file in `pics/`
- Viewer reads these JSON files directly — no DB or internet connection needed at view time
- Album names sanitized for filesystem: `re.sub(r'[<>:"/\\|?*]', "_", name)`

### Viewer — tkinter + PIL
- Reads directly from `pics/` and `albums/*.json` — no Amazon connection at view time
- Thumbnails loaded lazily in a background thread; `root.after(0, ...)` used to update tk widgets from thread
- `threading.Event` cancels in-flight thumbnail loading when the user switches albums
- `pillow-heif` registered as optional opener for HEIC files
- Thumbnail size: 160×130 px. Full-size view opens in a `Toplevel` window scaled to screen

### SQLite (`mirror.db`)
- Tracks: photos (node_id, name, size, md5, exif_date, local_path), albums, album_photos join table, videos
- Purpose: detect deletions (DB ids − cloud ids = removed) and skip re-download (file-exists check is primary; DB is the source of truth for deletions)
- Location: `{mirror_root}/mirror.db` — not committed

---

## Amazon Photos — Technical Reference

Inherited from sync-amazonphotos (proven):

### Authentication
- `browser.new_context(storage_state="session.json")` restores ALL cookies including session-scoped ones that `cookies.txt` misses
- Headers captured via `page.on("request")` listener on first `/drive/v1/` call: `x-amzn-sessionid`, `x-amz-clouddrive-appid`, etc.

### Amazon Drive V2 API Rules
- ALL node operations require `resourceVersion=V2` query param
- Album kind = `VISUAL_COLLECTION`; photo/video file nodes kind = `FILE`
- V1 endpoint returns `NODE_NOT_FOUND` for V2-created nodes — never mix versions
- Response shape: `{"count": N, "nextToken": "...", "data": [...]}`

### Key API Calls
```
# List all photo nodes (paginated)
GET /nodes?ContentType=JSON&resourceVersion=V2&asset=IMAGE&limit=200&startToken={token}

# List all video nodes (paginated)
GET /nodes?ContentType=JSON&resourceVersion=V2&asset=VIDEO&limit=200&startToken={token}

# List all albums (paginated)
GET /nodes?ContentType=JSON&resourceVersion=V2&filters=kind:VISUAL_COLLECTION&limit=200

# List album children (paginated)
GET /nodes/{albumId}/children?ContentType=JSON&resourceVersion=V2&asset=IMAGE&limit=200

# Get node with temp download URL
GET /nodes/{nodeId}?ContentType=JSON&resourceVersion=V2&tempLink=true
```

### Why `_eval_fetch` (not Python requests)
Amazon Photos API calls must originate from inside the real browser session. Native headers (`x-amzn-sessionid`, etc.) are bound to the session and can't be replicated from Python's `requests`. `page.evaluate(fetch(...))` runs inside Chromium with all cookies and session state intact.

---

## Known Risks / Not Yet Verified

### `tempLink=true` download URL
- **Risk**: Not yet confirmed that `tempLink` field appears in the GET /nodes/{id} response
- **Symptom if missing**: `download_node` logs "No download URL for {name} — skipping" per file, nothing downloaded
- **Fix options if tempLink absent**:
  1. Try `GET /nodes/{id}/children` pattern (for folder-like nodes)
  2. Try browser-side fetch returning base64: `page.evaluate(fetch(url) → arrayBuffer → btoa)` — works for photos, not practical for large videos
  3. Check if `contentProperties.url` or similar field exists in the node response

### `asset=IMAGE` / `asset=VIDEO` parameter
- **Risk**: Not confirmed this param works for the Amazon Drive V2 endpoint (may be Amazon Photos-specific)
- **Symptom if not working**: `list_nodes` returns 0 items or HTTP error
- **Fallback**: use `filters=kind:FILE` and client-side filter by `contentProperties.contentType`

---

## Errors Solved (inherited from sync-amazonphotos — reference)

| Error | Cause | Fix |
|-------|-------|-----|
| HTTP 401 on all API calls | Used deprecated Amazon Cloud Drive API via `requests` | Switch to Playwright + `page.evaluate(fetch(...))` |
| Session cookies missing after restart | `cookies.txt` only saves persistent cookies; session-scoped ones are lost | Use Playwright `storage_state` |
| HTTP 400 Invalid Kind VISUAL_COLLECTION | Album POST without `resourceVersion=V2` | Add `resourceVersion=V2` to all node operations |
| Content upload HTTP 403 Not Registered | CDN requires device registration | N/A for mirror (download only) |
| Duplicate albums on re-run | `_find_album` fetched ALL albums without name filter → missed existing ones | Search by name: `filters=kind:VISUAL_COLLECTION AND name:{name}` |

---

## Files

```
mirror-amazonphotos/
├── amazon_client.py     # Shared Playwright client
├── db.py                # SQLite helpers
├── cloner.py            # amazon.photos.cloner CLI
├── videos_cloner.py     # amazon.videos.cloner CLI
├── viewer.py            # amazon.photos.viewer GUI (tkinter)
├── requirements.txt     # playwright, tqdm, pillow, pillow-heif, requests
├── .gitignore
├── venv/                # Python 3.13 venv (not committed)
├── CLAUDE.md            # Spec, workflow, how to run
└── progress.md          # This file — decisions, API notes, risk log
```
