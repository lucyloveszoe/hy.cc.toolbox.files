# 子项目：Family Photos and Videos album同步和S3备份

## How to Run

```powershell
# Activate venv first
.\venv\Scripts\Activate.ps1

# Full run (--sync-root is required)
python sync.py --sync-root C:\tmp\yu.sync

# Dry run — preview all actions, no changes made
python sync.py --sync-root C:\tmp\yu.sync --dry-run

# Skip Amazon Photos, S3 backup only
python sync.py --sync-root C:\tmp\yu.sync --skip-amazon

# One-time login — opens visible browser, saves session.json
python sync.py --save-session
```

## Input File Architecture

Sync root contains two subfolders:
- `pics/` — grandchild folders of photos (jpg, jpeg, png, heic, bmp, gif, tiff, webp, raw)
- `vids/` — grandchild folders of videos (mp4, avi, mov, flv, mkv, wmv, m4v, 3gp)

Grandchild folder names must start with a 4-digit year (e.g. `2026.05.08_Lucy_Graduation`).

Credentials:
- AWS: `~/.aws/credentials`
- Amazon Photos: `session.json` (created by `--save-session`, gitignored)
- Other env vars: `.env` (AWS region, cookies file path)

## Workflow

### Step 1 — Integrity check
Enforce file-type rules:
- Videos found under `pics/` → moved to `vids/{folder}_vids/`
- Pictures found under `vids/` → moved to `pics/{folder}_pics/`

### Step 2 — Process pics

For each grandchild folder under `pics/`:

**Empty folder** (no files, no zip): delete folder, skip.

**Normal flow** (no zip exists yet):
1. Check if Amazon Photos album already exists by name — if yes, skip album creation and all uploads
2. If album is new: create album, upload all photos to it
3. Zip the folder → `{folder}.zip`
4. Delete the original folder
5. Upload zip to `s3://yu.vbackup.family/singlepics/{YYYY}_Pics/{folder}.zip` (ONEZONE_IA) — skip if S3 key already exists
6. Move zip to `.bak/pics/`

**Zip already exists** (crash recovery — zip created but not yet uploaded):
- Skip steps 1–3; go straight to step 4 (delete folder if still present), then 5–6

**Orphan zip** (folder already gone from a prior run, zip in `pics/`):
- Skip steps 1–4; go straight to steps 5–6

### Step 3 — Process vids

For each grandchild folder under `vids/`:

**Empty folder** (no video files): delete folder, skip.

**Normal flow**:
1. For each video file: upload to `s3://yu.vbackup.family/vid/{YYYY}_videos/{folder}/{file}` (ONEZONE_IA) — skip if S3 key already exists; then move file to `.bak/vids/{folder}/`
2. After all files processed: delete folder if empty; warn and keep if any files remain (upload errors)

## Idempotency — Re-run Safety

| Check | How |
|-------|-----|
| Amazon Photos album exists | `_find_album` searches by name before creating |
| Photo already in album | `PUT /children/{nodeId}` returns 409 → logged as "already linked" |
| Zip already in S3 | `s3_key_exists` (`head_object`) before each upload |
| Video already in S3 | `s3_key_exists` before each upload |
| Zip already created locally | `pics/{name}.zip` presence check before Amazon Photos work |

## Restrictions

- Credentials must not be committed to Git (`session.json`, `.env`, `~/.aws/credentials`)
- `session.json` is gitignored
- `--sync-root` is a required CLI argument — not in `.env`
