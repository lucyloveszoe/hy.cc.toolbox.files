# 子项目：Mirror Amazon Photos to Local with Albums

## Status (2026-05-27)

**Photo enumeration: ✅ WORKING**
- 65,428 photos enumerated successfully
- Client-side MIME type filtering
- Month filtering tested and working

**Photo downloads: ❌ BLOCKED**
- `tempLink` download URL extraction failing
- All 401 Unauthorized on CDN downloads
- Debugging in progress — see progress.md

## How to Run

### macOS / Linux

```bash
# Activate venv first (always)
cd mirror-amazonphotos
source venv/bin/activate

# One-time login — opens visible browser, saves session.json
python cloner.py --save-session

# Dry run — preview what would be downloaded, no files written
python cloner.py --mirror-root /tmp/mirror --dry-run

# Full photo + album sync (CURRENTLY: enumerates only, downloads failing)
python cloner.py --mirror-root /tmp/mirror

# Full video sync
python videos_cloner.py --mirror-root /tmp/mirror

# Filter by month (YYYY-MM) — partial sync, no deletion of other months
python cloner.py --mirror-root /tmp/mirror --month 2026-05
python videos_cloner.py --mirror-root /tmp/mirror --month 2024-06

# Use a non-default session file
python cloner.py --mirror-root /tmp/mirror --session-file /path/to/session.json

# Browse local mirror (no internet needed)
python viewer.py --mirror-root /tmp/mirror
```

### Windows

```powershell
# Activate venv first (always)
cd mirror-amazonphotos
.\venv\Scripts\Activate.ps1

# One-time login — opens visible browser, saves session.json
python cloner.py --save-session

# Dry run — preview what would be downloaded, no files written
python cloner.py --mirror-root C:\tmp\mirror --dry-run

# Full photo + album sync
python cloner.py --mirror-root C:\tmp\mirror

# Full video sync
python videos_cloner.py --mirror-root C:\tmp\mirror

# Filter by month (YYYY-MM) — partial sync, no deletion of other months
python cloner.py --mirror-root C:\tmp\mirror --month 2024-06
python videos_cloner.py --mirror-root C:\tmp\mirror --month 2024-06

# Use a non-default session file
python cloner.py --mirror-root C:\tmp\mirror --session-file C:\path\to\session.json

# Browse local mirror (no internet needed)
python viewer.py --mirror-root C:\tmp\mirror
```

## 功能要求

### This is Downward ONLY data stream, i.e., uni-direction from Cloud to local mirror, including images, videos and album definitions. Never Change at local

### Need be able to run in both Windows and MacOS, cross-platform

### amazon.photos.cloner (`cloner.py`)
1. Traverse all photos and all albums in Amazon Photos
2. Sync all photos to local `pics/` folder with metadata preserved (time created, time uploaded, link to album — stored in `mirror.db`).
   - If any newly uploaded in Cloud → grab to local
   - If any newly deleted in Cloud → delete from local too
3. Sync all album definitions to local `albums/` as JSON files, with links replaced by local file paths.
   - If photo added/removed from album in Cloud → mirror the change in the JSON

### amazon.photos.viewer (`viewer.py`)
1. View all photos with sorting by name or date
2. Select and view specific album

### amazon.videos.cloner (`videos_cloner.py`)
1. Traverse all videos in Amazon Photos
2. Sync all videos to local `vids/` folder with metadata preserved.
   - If newly uploaded → grab to local; if newly deleted → delete from local

## File Architecture

```
mirror-amazonphotos/
├── amazon_client.py     # Shared Playwright client — auth, API calls, download
├── db.py                # SQLite helpers (photos, albums, album_photos, videos)
├── cloner.py            # amazon.photos.cloner CLI
├── videos_cloner.py     # amazon.videos.cloner CLI
├── viewer.py            # amazon.photos.viewer GUI (tkinter)
├── requirements.txt     # playwright, tqdm, pillow, pillow-heif, requests
├── .gitignore
├── venv/                # Python 3.13 venv
├── CLAUDE.md            # This file — spec, workflow, usage
└── progress.md          # Technical reference, API notes, decisions log
```

Mirror root layout (created at runtime, not committed):
- `pics/`    — all photos as flat files
- `albums/`  — one JSON per album, with local file paths
- `vids/`    — all videos as flat files
- `mirror.db` — SQLite metadata (node IDs, dates, album membership)

## Credentials

- Amazon Photos: `session.json` — created by `--save-session`, gitignored
- Default session path: `../sync-amazonphotos/session.json` (shared with sibling project)
- Override with `--session-file PATH`

## Idempotency — Re-run Safety

| Check | How |
|-------|-----|
| Photo/video already downloaded | File exists in `pics/` or `vids/` → skip |
| Photo deleted from cloud | DB node_id diff vs cloud set → delete local file |
| Album definition up to date | Always rewrite JSON on each run |
| `--month` partial sync | Deletion step skipped — only full runs clean up |

## Restrictions

- Credentials must not be committed to Git (`session.json`)
- `session.json` is gitignored
- `--mirror-root` is a required CLI argument — not in `.env`
- Never write back to Amazon Photos — download only
