# sync-amazonphotos — Development Progress

**Last updated: 2026-05-25**  
**Status: Production — stable. Minor known issue: ~5–10% of photos not linked to album (Amazon indexing delay).**

---

## What's Working

- S3 upload: ONEZONE_IA, `s3_key_exists` idempotency, 32 MB multipart chunks (`TransferConfig`), 3-attempt retry — **fully working**
- `--dry-run`, `--skip-amazon`, `--save-session` flags — **fully working**
- Amazon Photos auth: `storage_state` (session.json) restores full session including session-scoped cookies — **fully working**
- Amazon Photos album creation with V2 API (`kind:VISUAL_COLLECTION`, `resourceVersion=V2`) — **fully working**
- `_find_album`: searches by name in filter to avoid pagination bug — **working**
- Playwright UI photo upload: 3-click flow (`Add → Upload photos → Upload and add to this album → expect_file_chooser`) — **fully working**
- `_find_photo_by_name`: prefers nodes with `contentProperties.image` to avoid HTTP 400 — **working**
- Full re-run / crash recovery for pics and vids — **working**
- Empty folder cleanup (both pics and vids delete the folder) — **working**

---

## Idempotency Logic

### Pics

`process_pics` collects both active folders AND orphan zips (zip in `pics/`, folder already deleted):

| State | Action |
|-------|--------|
| Folder exists, no zip, no album | Create album → upload → zip → delete folder → S3 → archive |
| Folder exists, no zip, album exists | Skip album + upload → zip → delete folder → S3 → archive |
| Folder exists, zip exists | Skip Amazon Photos → delete folder → S3 → archive |
| No folder, zip exists (orphan) | Skip Amazon Photos → S3 (skip if key exists) → archive |
| Folder exists, empty, no zip | Delete folder, skip |

### Vids

Per video: `s3_key_exists` check before upload. Whether uploaded fresh or skipped (already in S3), the file is always moved to `.bak/`. Folder is deleted after all files are moved; kept with a warning if any uploads failed.

---

## Amazon Photos — Technical Reference

### Authentication
- **`storage_state`**: `browser.new_context(storage_state="session.json")` restores ALL cookies, including session-scoped ones that `cookies.txt` misses
- **`--save-session`**: opens visible Chromium, waits for manual login, saves full browser state to `session.json`
- **Header capture**: `page.on("request")` listener fires on first `/drive/v1/` call and captures native auth headers (`x-amzn-sessionid`, `x-amz-clouddrive-appid`, etc.) for reuse in `_eval_fetch`

### Amazon Drive V2 API Rules
- ALL node operations require `resourceVersion=V2` query param
- Album kind = `VISUAL_COLLECTION`; photo file nodes kind = `FILE`
- V1 endpoint returns `NODE_NOT_FOUND` for V2-created nodes — never mix versions
- Content upload CDN (`content-na.drive.amazonaws.com`) requires device registration — DO NOT use; UI automation is the only viable upload path

### Key API Calls
```
# Find album by name (V2, name-scoped filter — avoids pagination)
GET /nodes?ContentType=JSON&filters=kind:VISUAL_COLLECTION AND name:{name}&resourceVersion=V2

# Create album
POST /nodes?ContentType=JSON&resourceVersion=V2
Body: {"name": "albumName", "kind": "VISUAL_COLLECTION"}

# Find photo by name (prefer node with contentProperties.image)
GET /nodes?ContentType=JSON&filters=name:{filename} AND status:AVAILABLE&resourceVersion=V2

# Link photo to album
PUT /nodes/{albumId}/children/{nodeId}?ContentType=JSON&resourceVersion=V2
```

### Why `_eval_fetch` (browser-side fetch, not requests)
Amazon Photos API calls must originate from inside the real browser session. Native headers (`x-amzn-sessionid`, etc.) are bound to the session and can't be replicated from Python's `requests`. `page.evaluate(fetch(...))` runs inside Chromium with all cookies and session state intact.

---

## Known Issues

### Photos not linked to album (~5–10%)
- **Cause**: Amazon Photos indexing delay — photo uploaded via UI but not yet searchable when `_find_photo_by_name` runs immediately after
- **Impact**: Photo is in "All Photos" but not in the album. S3 backup is complete.
- **Fix idea**: post-upload retry loop with short sleep — not implemented yet

### `DD46814C-8282-4F65-BEF1-B4B9303AED3E.JPG` — HTTP 400 on album link
- **Cause**: File has two duplicate raw FILE nodes from earlier API experiments, neither has `contentProperties.image`. VISUAL_COLLECTION rejects both.
- **Impact**: Photo in "All Photos" but not linked to album. One-off; won't recur for fresh photos.

---

## Errors Solved (reference)

| Error | Cause | Fix |
|-------|-------|-----|
| HTTP 401 on all API calls | Used deprecated Amazon Cloud Drive API via `requests` | Switch to Playwright + `page.evaluate(fetch(...))` |
| Session cookies missing after restart | `cookies.txt` only saves persistent cookies; session-scoped ones are lost | Use Playwright `storage_state` |
| `pw.__exit__` AttributeError | Wrong Playwright lifecycle | Use `sync_playwright().start()` / `.stop()` |
| `'list' object has no attribute 'get'` | Response shape is `{"data": [...]}` not `{"data": {"items": [...]}}` | `items = data.get("data", []) if isinstance(data, dict) else data` |
| HTTP 400 Invalid Kind VISUAL_COLLECTION | Album POST without `resourceVersion=V2` | Add `resourceVersion=V2` to all node operations |
| Content upload HTTP 403 Not Registered | CDN requires device registration | Abandon API upload; use UI automation only |
| Album page 404 | Used `/photos/albums/` (plural) | Use `/photos/album/` (singular) |
| `set_input_files` no-op | React upload handler not triggered by direct file injection | Use `expect_file_chooser` to intercept the native dialog |
| Photos not added to album (silent dedup) | Amazon silently skips re-uploading existing files | After UI upload, always link via `PUT /nodes/{album}/children/{node}?resourceVersion=V2` |
| HTTP 404 "Node not found for ResourceVersion V1" | `PUT /children` without `resourceVersion=V2` | Add param |
| HTTP 400 "Improper child kind" | `_find_photo_by_name` returned an incompletely-processed FILE node (no image metadata) | Prefer nodes where `contentProperties.image` exists |
| Duplicate albums created on re-run | `_find_album` fetched ALL albums without pagination — missed existing ones | Search by name: `filters=kind:VISUAL_COLLECTION AND name:{name}` |
| S3 multipart upload crash (ConnectionClosedError) | Default 8 MB chunks → 17 parts for 135 MB zip; connection dropped at part 5 | `TransferConfig(multipart_chunksize=32MB, max_concurrency=1)` + 3-attempt retry loop |
| Vids re-run: files not moved to .bak when S3 already had them | `if uploaded:` gate skipped the move when `s3_upload` returned False (key existed) | Removed `uploaded` gate — always move to `.bak` after S3 is confirmed safe; only skip on exception |

---

## Files
```
sync-amazonphotos/
├── sync.py              # Main script — source of truth for behavior
├── requirements.txt     # playwright, boto3, tqdm, python-dotenv
├── .env                 # AWS credentials + region (gitignored)
├── session.json         # Playwright storage_state (gitignored, created by --save-session)
├── .gitignore
├── venv/                # Python 3.12 venv
├── CLAUDE.md            # Project spec, workflow, usage
└── progress.md          # This file — technical reference, API notes, error log
```
