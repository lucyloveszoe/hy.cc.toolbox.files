# mirror-amazonphotos — Development Progress

**Last updated: 2026-05-28**
**Status: Photos ✅ | Albums ✅ | Viewer ✅ (virtual scroll) | Videos ⏳ not yet tested**

---

## Current Checkpoint (2026-05-28)

### ✅ What's Working
1. **Photo enumeration** — client-side MIME type filtering
   - 65,428 photos across 330 API pages, ~2-3 min for full enumeration
   - Month filtering (`--month YYYY-MM`) works correctly

2. **Photo downloads** — `thumbnails-photos.amazon.com` CDN
   - Full library synced to `/Users/superyu/Documents/data/amazon-mirror.2026.05.28`
   - Near-original quality: viewBox=10000 covers full pixel dimensions, slight JPEG recompression (1.86MB vs 2.3MB tested)
   - File mtimes set to EXIF dateTimeOriginal, falling back to createdDate
   - `--month 2026-05` tested: 192 photos, ~5 min, zero errors

3. **Album sync** — 346 albums synced to JSON with local path links

4. **Viewer** — virtual-scroll tkinter GUI, handles 50K+ photos without OOM
   - Only visible rows have widgets in memory (BUFFER_ROWS=3 above/below viewport)
   - LRU thumbnail cache capped at 400 entries
   - Persistent background worker thread + queue; stale items discarded on album switch
   - 80ms scroll debounce; scrollbar drag and mousewheel both trigger re-render
   - Full-size popup, album sidebar, sort by name/date — all working

### ⚠️ Known Limitation — Download Quality
- `cdproxy` tempLink returns `"No Auth Method Provided"` — requires OAuth tokens not available from the browser session approach
- Workaround: `thumbnails-photos.amazon.com?viewBox=10000` — same pixel dimensions, JPEG recompressed (~80% file size of original)
- True original bytes (HEIC, raw) not achievable without OAuth

### Next Steps
1. Test video downloads (`videos_cloner.py`) — thumbnail CDN may not serve videos
2. Test full re-sync (idempotency) — re-run cloner on existing mirror, verify skip + deletion logic
3. Monitor for session expiry on long runs (65K photos takes ~27 hours at 1.5s/photo)

---

## What's Built

- `amazon_client.py` — Playwright client: `list_nodes`, `list_albums`, `list_album_children`, `get_download_url`, `download_node` — **production tested**
- `db.py` — SQLite schema + helpers (photos, albums, album_photos, videos) — **unit tested**
- `cloner.py` — photos + albums sync CLI with `--month` filter — **production tested (50K+ photos)**
- `videos_cloner.py` — videos sync CLI with `--month` filter — **code complete, not yet tested**
- `viewer.py` — virtual-scroll tkinter GUI, LRU cache, album sidebar, full-size popup — **OOM fix applied 2026-05-28**
- `test_download.py` — single-photo download debug tool (no full enumeration)
- venv: Python 3.13, deps: playwright, pillow, pillow-heif, requests, tqdm

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

### Download — `thumbnails-photos.amazon.com` CDN
- `tempLink` IS present in the `/nodes/{id}?tempLink=true` response, but the URL (`cdproxy/nodes/{id}`) requires OAuth — returns "No Auth Method Provided" regardless of how it's called (requests, browser fetch, browser goto)
- Workaround: `thumbnails-photos.amazon.com/v1/thumbnail/{nodeId}?viewBox=10000&ownerId={ownerId}`
  - No OAuth needed — authenticated via Amazon session cookies extracted from browser context at startup
  - `viewBox=10000` exceeds all photo dimensions → serves full pixel resolution, JPEG recompressed
  - Downloaded with `requests.get(cookies=self._download_cookies)` — no browser overhead per file
- `_download_cookies` extracted once in `__init__` from `page.context.cookies()`, reused for all downloads

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

### Viewer — tkinter + PIL (virtual scroll, OOM-safe)
- Reads directly from `pics/` and `albums/*.json` — no internet at view time
- **Virtual scroll**: cells placed directly on canvas as window items at computed (x, y); only rows within BUFFER_ROWS=3 of viewport exist as widgets. 50K photos → ~35 widgets in memory at a time.
- LRU thumbnail cache (`_LRUCache`, max 400): evicts oldest when full; `ImageTk.PhotoImage` kept alive by attaching to cell widget as `cell._photo`
- Persistent daemon worker thread + `queue.Queue`; items carry `stop_event` ref — stale items from previous album view are discarded, not processed
- 80ms debounce on scroll events via `root.after_cancel` / `root.after`
- Scrollbar drag wired via wrapper that calls `canvas.yview()` then `_schedule_render()`
- Initial render deferred 120ms with `root.after` to let window reach final size before first `winfo_height()` call

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

## Known Risks / Open Questions

### Video downloads
- `videos_cloner.py` not yet tested end-to-end
- `thumbnails-photos.amazon.com` likely does not serve video files — may need a different download approach
- If videos also need cdproxy and hit the same OAuth wall, video download is blocked until OAuth is solved

### Session expiry on long runs
- Full sync of 65K photos at 1.5s/photo ≈ 27 hours
- Amazon session cookies may expire mid-run (typical session lifetime: 12–24h)
- Symptom: downloads start returning 401 partway through
- Fix needed: detect 401 on download, refresh cookies from browser context, retry

### `asset=IMAGE` / `asset=VIDEO` parameter — RESOLVED
- Was a risk; now confirmed working via client-side MIME filter fallback (`filters=kind:FILE` + filter by `contentProperties.contentType`)

### cdproxy OAuth — blocked
- `content-na.drive.amazonaws.com/cdproxy/nodes/{id}` always returns "No Auth Method Provided"
- Would need to extract OAuth access token from the React app's token storage — not yet investigated

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
