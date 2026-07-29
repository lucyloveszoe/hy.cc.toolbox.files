# 子项目：Cross check files difference across different sources

Tool-box for finding duplicate / near-duplicate file records across
**file-listing dumps** (a NAS `find` dump, an S3 `aws s3 ls --recursive`
dump, etc.). Three of the five scripts never touch the original files —
they only diff the catalog text reports. The other two
(`local-folder-win-dup-check.py`, `folder-win-vs-s3list-dup-check.py`)
scan a real folder directly, but only read file sizes (`Path.stat()`) —
no script ever reads or hashes file content.

## How to Run

```powershell
cd files-crosscheck
.\venv\Scripts\Activate.ps1

# (1) Single folder — find dupes inside one catalog source
python local-dup-match.py                              # default folder
python local-dup-match.py D:\other\linux\catalogs      # custom folder
python local-dup-match.py --output-dir .\out --fuzzy   # opt-in flags

# (2) Two folders, same Linux format — cross-source dupes only
python local-dup-match-cross.py                                 # defaults
python local-dup-match-cross.py D:\linux\a D:\linux\b           # custom
python local-dup-match-cross.py --output-dir .\out-cross

# (3) Linux folder vs S3 folder — different formats, cross-source dupes
python s3-dup-match-cross.py                                    # defaults
python s3-dup-match-cross.py D:\linux\nas D:\s3\listings        # custom
python s3-dup-match-cross.py --output-dir .\out-s3

# (4) Single real Windows folder — scans actual files, no catalog dump
python local-folder-win-dup-check.py                            # default folder
python local-folder-win-dup-check.py D:\Videos                  # custom folder
python local-folder-win-dup-check.py --output-dir .\out-win

# (5) Real Windows folder vs a single S3 listing file — cross-source dupes
python folder-win-vs-s3list-dup-check.py                                    # defaults
python folder-win-vs-s3list-dup-check.py D:\Videos D:\s3\listing.txt       # custom
python folder-win-vs-s3list-dup-check.py --output-dir .\out-win-s3
```

## 功能要求

1. **`local-dup-match.py`** — single folder duplicates check.
   - `folder` is the argument; default `C:\tmp\files-list\linux.nas`.
   - Scan all catalog files in that folder (they share the same line
     format) and produce:
     - (a) Same byte size → `exact.csv`
     - (b) Different byte size but similar file name → `potential.csv`

2. **`local-dup-match-cross.py`** — duplicates check across **two**
   folders of the same Linux dump format.
   - Two folders are the arguments; defaults
     `C:\tmp\files-list\linux.nas` + `C:\tmp\files-list\linux.mac`.
   - Same two outputs, but a group is reported only when its members
     span **both** folders.

3. **`s3-dup-match-cross.py`** — duplicates check between a Linux dump
   folder and an S3 listing folder (different formats).
   - Two folders are the arguments; defaults
     `C:\tmp\files-list\linux.nas` + `C:\tmp\files-list\win.s3`.
   - Linux side uses the Linux line parser; S3 side uses the S3 line
     parser. Otherwise identical to (2).

4. **`local-folder-win-dup-check.py`** — single **real** Windows folder
   duplicates check (no catalog dump — scans actual files on disk).
   - `folder` is the argument; default `C:\Temp\self\video`.
   - Recursively walks every file under that folder (`Path.rglob`),
     reads each file's actual size via `Path.stat()`, and produces:
     - Same byte size → `exact.csv` (only report; no `potential.csv`)

5. **`folder-win-vs-s3list-dup-check.py`** — duplicates check between a
   real Windows folder and a single S3 listing file (different formats,
   no catalog folder on either side needed).
   - First argument is Windows folder path, default `C:\Temp\self\video`;
     second argument is path to a single S3 listing file, default
     `C:\tmp\files-list\win.s3\s3.vids.txt`.
   - Windows side uses recursive filesystem scanning as in (4). S3 side
     uses the S3 line parser on that one file (not a globbed folder).
   - Same two outputs as (2)/(3), but a group is reported only when its
     members span **both** sides: same byte size → `exact.csv`;
     similar file name but different size → `potential.csv`.

## Input File Formats

Both formats are line-oriented plain text. Each line becomes one
`Record(side, source, size, path, name)`.

### Linux NAS dump

```text
<size_in_bytes> bytes <full_posix_path>
```

Example:

```text
468068018 bytes /Volumes/YuData/Korea.50G/.../episode01.mp4
```

Regex: `^\s*(\d+)\s+bytes\s+(.+?)\s*$`

### S3 / AWS CLI listing

```text
YYYY-MM-DD HH:MM:SS  <size_in_bytes>  <relative_key>
```

Example:

```text
2025-09-14 01:40:40    1057437 X-twitter/HK141Channel/01.mp4
```

Regex: `^\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+(\d+)\s+(.+?)\s*$`

Directory placeholder rows (key ending in `/`, typically size 0) are
dropped at parse time.

### Encoding auto-detection

`dup_common._detect_text_encoding` sniffs the first 4 bytes of each
catalog file and selects:

| Leading bytes | Encoding used |
|---------------|---------------|
| `FF FE` or `FE FF` | `utf-16` (PowerShell `Out-File` default) |
| `EF BB BF` | `utf-8-sig` |
| anything else | `utf-8` |

This is required because the S3 catalogs in `win.s3` are UTF-16 LE
(generated by Windows tooling) while the Linux catalogs are plain UTF-8.

### Real Windows folder (no catalog format)

`local-folder-win-dup-check.py` and the Windows side of
`folder-win-vs-s3list-dup-check.py` have no line format to parse — they
read the folder tree directly with `Path.rglob("*")` + `Path.stat()`.
Each file on disk becomes one `Record` via `load_records_from_filesystem`:

| `Record` field | Value |
|---|---|
| `side` | scanned folder's name |
| `source` | file's directory path relative to the scanned folder (`"(root)"` if directly inside it) |
| `size` | `Path.stat().st_size` |
| `path` | absolute path on disk |
| `name` | file basename |

### Single S3 listing file (no folder glob)

The S3 side of `folder-win-vs-s3list-dup-check.py` takes one listing
file directly, not a folder of catalogs. It is parsed with
`load_records_from_catalog_file` — same `parse_s3_catalog` line format
and filtering rules as `load_records`, just for one file instead of a
glob over a folder.

## File Architecture

```text
files-crosscheck/
├── dup_common.py                  # Shared core: parsing, normalizing, finding, writing
├── local-dup-match.py             # CLI (1): single folder
├── local-dup-match-cross.py       # CLI (2): two Linux folders
├── s3-dup-match-cross.py          # CLI (3): Linux folder vs S3 folder
├── local-folder-win-dup-check.py  # CLI (4): single real Windows folder (direct scan)
├── folder-win-vs-s3list-dup-check.py  # CLI (5): real Windows folder vs one S3 listing file
├── requirements.txt               # stdlib only — no third-party deps
├── .gitignore                     # venv/, __pycache__/, *.csv, out/, out-*/
├── venv/                          # Python 3.13 venv (gitignored)
└── CLAUDE.md                      # This file
```

Generated reports always go to `--output-dir` (default `.`). They are
called `exact.csv` and `potential.csv` regardless of which script
produced them.

## Output CSV Schema

Both files are written **UTF-8 with BOM** (`utf-8-sig`) so Excel renders
CJK correctly on Windows.

### `exact.csv`

| Column | Meaning |
|--------|---------|
| `group_id` | 1-based; groups are sorted by descending `size_bytes` |
| `size_bytes` | Common byte size that defines the group |
| `side` | Folder-level label (single mode: folder name; cross mode: A/B or linux/s3 folder name) |
| `source` | Catalog filename within that folder |
| `file_name` | Basename of the entry |
| `file_path` | Full path / key from the catalog line |

### `potential.csv`

| Column | Meaning |
|--------|---------|
| `group_id` | 1-based; groups sorted alphabetically by `normalized_name` |
| `normalized_name` | Output of `normalize_name(file_name)` (the bucket key) |
| `size_bytes` | Byte size of this entry (members differ on this column) |
| `side` | (same as exact.csv) |
| `source` | (same as exact.csv) |
| `file_name` | (same as exact.csv) |
| `file_path` | (same as exact.csv) |

## Decision Logic

### Record filtering (`load_records`)

A parsed line becomes a kept `Record` unless one of these drops it:

1. **Zero-byte entry** — `size == 0` → drop (unless `--include-zero-bytes`).
2. **System noise** — basename match → drop (unless `--include-system-files`):
   - exact (case-insensitive): `.DS_Store`, `Thumbs.db`, `desktop.ini`
   - prefix (case-insensitive): `._` (macOS resource forks)
3. **S3 directory placeholder** — path ends with `/` → drop (always, S3 parser only).

`load_records_from_filesystem` (used by `local-folder-win-dup-check.py`)
applies rules 1 and 2 the same way; rule 3 doesn't apply since directories
are simply not files and `Path.rglob` never yields them as entries.

### Filename normalization (`normalize_name`)

Used as the bucket key for `potential.csv`. Steps:

1. Take `PurePosixPath(name).stem` (drop extension).
2. Lowercase + strip whitespace (workspace rule).
3. Repeatedly strip trailing markers until stable:
   - ` (N)`           — e.g. `photo (1)`
   - ` - Copy[ (N)]`  — e.g. `photo - Copy`, `photo - Copy (1)`
   - `Copy[ (N)]`     — e.g. `photoCopy`
   - `[_- ]+vN`       — e.g. `report_v2`, `report-v3`
   - `[_- ]+(final|edit|edited|new|old|backup|bak)` — e.g. `doc_final`
4. Collapse internal whitespace runs to a single space.

**Trailing digits without a version marker are intentionally NOT
stripped** (e.g. `Vol.04 part-1` vs `part-2`, `IMG_1097` vs `IMG_1098`).
Earlier versions stripped them and that over-clustered iPhone-style
camera dumps and multi-part series into one giant bucket.

### Generic-name filter (`is_too_generic`)

A normalized name is rejected from the `potential` bucketing if **any**
of these holds:

- empty or `len(norm) < 4` (`MIN_NORM_LENGTH = 4`)
- `norm.isdigit()` (e.g. `1`, `2`)
- `norm` ∈ generic set:
  - `img`, `image`, `images`, `video`, `videos`, `file`, `files`,
    `photo`, `photos`, `pic`, `pics`, `movie`, `movies`, `mov`,
    `dsc`, `dscn`, `dscf`, `doc`, `document`, `tmp`, `temp`,
    `untitled`, `new`, `copy`, `scan`, `scanned`, `screenshot`,
    `capture`, `recording`

This protects against e.g. every `IMG_xxxx.MOV` collapsing into one
huge cluster, or `1.avi` / `2.avi` / `1-1.mp4` colliding on `1` / `2`.

### Exact-match grouping (`find_exact_duplicates`)

1. Bucket all records by `size_bytes`.
2. Keep buckets with ≥ 2 records.
3. If `require_cross_side=True`, additionally require ≥ 2 distinct
   `side` values per bucket.

### Potential-match grouping (`find_potential_duplicates`)

**Pass 1 — normalized-name bucket (always on):**

1. Compute `normalize_name(record.name)`.
2. Skip if `is_too_generic(norm)`.
3. Bucket by `norm`; promote any bucket with ≥ 2 records to a group.
4. Singleton buckets go to a `leftover` list.

**Pass 2 — fuzzy clustering (opt-in via `--fuzzy`):**

For each `i < j` in `leftover`, compute
`difflib.SequenceMatcher(None, name_i, name_j).ratio()` (rounded to two
decimals). If `>= 0.85` (`SIMILARITY_THRESHOLD`), merge. Pairs whose
length differs by more than 30 % of the longer name are skipped early
to keep the O(n²) scan tolerable.

This is opt-in because it is slow (≥ 60s on 2.5k records) and can
over-cluster (e.g. consecutive episodes of a series get merged).

**Group survival rules:**

A group is written to `potential.csv` only if:

1. its members have ≥ 2 **distinct** `size_bytes` values, **and**
2. (`require_cross_side=True`) its members span ≥ 2 distinct `side`s, **and**
3. (`require_cross_source=True`, only single-folder mode opt-in) its
   members span ≥ 2 distinct `source`s.

### Output cosmetics

- CSV is written with `utf-8-sig` (UTF-8 BOM) so Excel auto-detects
  UTF-8 and CJK characters render correctly.
- When the output CSV is locked by another process (typically Excel
  has it open), the script prints a friendly message and exits with
  code 3 instead of dumping a `PermissionError` stack trace.

## CLI Reference

### `local-dup-match.py`

```text
local-dup-match.py [folder] [options]
  folder                    catalog folder (default: C:\tmp\files-list\linux.nas)
  --output-dir DIR          where to write reports (default: .)
  --catalog-glob GLOB       catalog filename glob (default: *.txt)
  --include-system-files    keep .DS_Store/Thumbs.db/._* records (default: off)
  --include-zero-bytes      keep 0-byte records (default: off)
  --cross-source-only       require potential groups to span >= 2 catalog
                            files within the folder (default: off)
  --fuzzy                   enable Pass 2 SequenceMatcher clustering (default: off)
```

### `local-dup-match-cross.py`

```text
local-dup-match-cross.py [folder_a] [folder_b] [options]
  folder_a                  first folder  (default: C:\tmp\files-list\linux.nas)
  folder_b                  second folder (default: C:\tmp\files-list\linux.mac)
  --output-dir DIR          where to write reports (default: .)
  --catalog-glob GLOB       catalog filename glob (default: *.txt)
  --include-system-files    (same as above)
  --include-zero-bytes      (same as above)
  --fuzzy                   (same as above)
```

Cross-side filter is always on: a group is reported only when it has
members from both `folder_a` and `folder_b`.

### `s3-dup-match-cross.py`

```text
s3-dup-match-cross.py [linux_folder] [s3_folder] [options]
  linux_folder              Linux dump folder (default: C:\tmp\files-list\linux.nas)
  s3_folder                 S3 listing folder (default: C:\tmp\files-list\win.s3)
  --output-dir DIR          (same as above)
  --catalog-glob GLOB       (same as above; applies to BOTH folders)
  --include-system-files    (same as above)
  --include-zero-bytes      (same as above)
  --fuzzy                   (same as above)
```

The Linux side is parsed with `parse_linux_catalog`, the S3 side with
`parse_s3_catalog`. Cross-side filter is always on.

### `local-folder-win-dup-check.py`

```text
local-folder-win-dup-check.py [folder] [options]
  folder                    real folder to scan recursively (default: C:\Temp\self\video)
  --output-dir DIR          where to write exact.csv (default: .)
  --include-system-files    keep .DS_Store/Thumbs.db/._* records (default: off)
  --include-zero-bytes      keep 0-byte records (default: off)
```

No `--catalog-glob` or `--fuzzy` flags — there is no catalog file to glob
for, and only `exact.csv` is produced (no `potential.csv`).

### `folder-win-vs-s3list-dup-check.py`

```text
folder-win-vs-s3list-dup-check.py [windows_folder] [s3_file] [options]
  windows_folder            real folder to scan recursively (default: C:\Temp\self\video)
  s3_file                   single S3 listing file (default: C:\tmp\files-list\win.s3\s3.vids.txt)
  --output-dir DIR          where to write reports (default: .)
  --include-system-files    (same as above)
  --include-zero-bytes      (same as above)
  --fuzzy                   (same as above)
```

No `--catalog-glob` — the Windows side is a direct recursive scan and
the S3 side is one file, not a globbed folder. Cross-side filter is
always on: a group is reported only when it has members from both
`windows_folder` and `s3_file`.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (reports written, possibly empty) |
| 2 | A folder argument is not a directory, or the two folders are equal |
| 3 | Could not write `exact.csv` / `potential.csv` (likely locked by Excel) |

## Restrictions

- **Read-only on the actual data.** `local-dup-match.py`,
  `local-dup-match-cross.py`, and `s3-dup-match-cross.py` parse text
  dumps; they never connect to the NAS, S3, or any cloud.
  `local-folder-win-dup-check.py` and `folder-win-vs-s3list-dup-check.py`
  scan a real folder directly but only call `Path.stat()` for the size —
  no script ever reads or hashes file content.
- **Same byte size is treated as a duplicate.** Without content hashes
  we cannot distinguish "different files that happen to share a byte
  size" (e.g. several 4.6 GB ISO blanks). Treat `exact.csv` as a
  candidate list, not a verdict.
- **Catalog file format must match.** A Linux catalog parsed as S3 (or
  vice versa) will produce all-unparseable warnings and zero records.
- **No third-party dependencies.** Pure Python 3.12+ standard library.
