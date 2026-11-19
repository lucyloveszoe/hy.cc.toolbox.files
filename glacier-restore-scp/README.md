# glacier-restore-scp

Two independent tools:
- `s3_mirror.py`: generic S3 prefix → local mirror (any storage class; un-restored Glacier objects are checked and skipped)
- `glacier_restore.py`: request restores for archived objects under a prefix

Typical use: restore an AWS Glacier folder, then mirror it locally, skipping unwanted files such as `Thumbs.db`.

## Scope (important)

- `s3_mirror.py` is generic: it mirrors any S3 prefix. For Glacier-class objects only restored ones are downloaded; it is **not** a way to pull un-restored archive objects.
- `s3_mirror.py` does **not** initiate restores. Run `glacier_restore.py` (below) or restore via the S3 console / `aws s3api restore-object`, wait until complete, then run the mirror.
- Objects in `GLACIER` or `DEEP_ARCHIVE` that are not yet restored are **not downloaded**; they are listed under `not restored` and skipped (this is not counted as a failure).
- Objects in any other storage class (e.g. `STANDARD`) are downloaded normally.
- Not handled: Intelligent-Tiering archive tiers (a download error would be reported as `FAILED`), and the legacy Glacier vault API.

## Setup

```
cd glacier-restore-scp
source venv/bin/activate
pip install -r requirements.txt     # boto3, pytest
python -m pytest -q
```

Python 3.12+. Always activate the venv first. AWS credentials come from the normal boto3 chain, or `--profile`. Keep `glacier_restore.py` and `s3_mirror.py` in the same folder (the restore script imports the exclude logic and defaults from the mirror).

## Usage

```
python s3_mirror.py <bucket> <prefix> <dest> [options]
```

| Argument / option | Meaning |
|---|---|
| `bucket` | S3 bucket name |
| `prefix` | Folder to mirror (S3 prefix). `''` = whole bucket. Leading `/` is stripped; a trailing `/` is added if missing |
| `dest` | Local mirror directory (created if missing) |
| `-x`, `--exclude PATTERN` | Glob to skip, repeatable. **Replaces** the default list |
| `--add-exclude PATTERN` | Extra glob, repeatable. **Added** to the defaults (or to `-x` patterns) |
| `--profile`, `--region` | AWS profile / region |
| `--dry-run` | Print what would be downloaded (and counted); download nothing |

Example (preview first):

```
python s3_mirror.py my-bucket photos/2015 ./mirror --dry-run
python s3_mirror.py my-bucket photos/2015 ./mirror
```

## Step 1: request restores (`glacier_restore.py`)

```
python glacier_restore.py <bucket> <prefix>                 # preview only
python glacier_restore.py <bucket> <prefix> --execute       # really request (costs money)
```

| Option | Meaning |
|---|---|
| `--days N` | Days the restored copy stays available (default 7) |
| `--tier Bulk\|Standard\|Expedited` | Retrieval tier (default `Bulk`, cheapest; `Expedited` is not available for `DEEP_ARCHIVE`) |
| `-x`, `--add-exclude`, `--profile`, `--region` | Same meaning and defaults as the mirror |
| `--execute` | Required to send restore requests. Without it, only a preview is printed |

- **Recursive**: lists every object under the prefix at any depth (paginated). The prefix is normalized like the mirror's (leading `/` stripped, trailing `/` added; `''` = whole bucket). Keys ending in `/` are ignored.
- **Excludes**: same defaults (`Thumbs.db`, `desktop.ini`, `.DS_Store`, `~$*`) and same matching rules as the mirror (section below), so excluded files are not restored and not paid for.
- **Skipped without a request**: non-archive objects (`not archived`), objects already restored (`already restored`), and objects with a restore in progress (`in progress`). Status comes from a `head_object` call per remaining archive object (`Restore` header: `ongoing-request="true"` = in progress, any other non-empty value = restored, empty = not restored).
- Only `GLACIER` / `DEEP_ARCHIVE` objects get a `restore_object` request. A `RestoreAlreadyInProgress` response counts as in progress, not failure. Any other error on an object (head or restore call) is recorded, listed as `FAILED` in the summary, and the run **continues with the next object**; the exit code is `1` if any were recorded.
- **Output**: per object `restore <relative path> (<size> GB)`, prefixed `[dry-run] ` in preview. Summary: `requested N (X GB, tier T, D days), already restored N, in progress N, not archived N, excluded N, failed N` (`would request` instead of `requested` in preview), followed by `FAILED: ...` lines, and `preview only; add --execute to request the restores` in preview. Sizes in GB, two decimals. In preview, `requested` means "would request" and head-check failures are also reported.
- **Exit code** `1` if any object failed, otherwise `0`.
- `Expedited` on `DEEP_ARCHIVE` objects is not pre-checked by the script; S3 would reject it and each such object would be listed as `FAILED`.
- Restores take hours (Bulk/Deep Archive up to ~48h). Re-run the preview to see `already restored` counts rise, then run the mirror before the `--days` window expires.

### `--days` (restore window)

- `--days N`: S3 keeps a temporary copy of each restored object for N days, counted from when the restore **completes** (not when requested). Default 7, minimum 1.
- After expiry the temporary copy is removed; the archived original is untouched and can be restored again.
- You pay normal S3 storage for the temporary copy while it exists, so a longer window costs more. Allow for the restore wait plus mirror time.
- Extending: AWS lets you re-issue a restore with a larger `Days` to push back expiry, but this script skips already-restored objects, so it does **not** extend. Not implemented.

## Mirror behavior (`s3_mirror.py`)

Generic S3 prefix mirror: restored and normal objects download identically. The only Glacier-specific logic is the restore check (step 3).

1. **Recursion**: lists every object under the prefix (paginated) and recreates the relative folder structure under `dest`. Keys ending in `/` (folder markers) are ignored.
2. **Excludes**: default patterns are `Thumbs.db`, `desktop.ini`, `.DS_Store`, `~$*`.
   - Matched with `fnmatch` against **each path component** of the key relative to the prefix, so an excluded folder name skips everything beneath it.
   - Pattern and name are both lowercased and have all whitespace removed before comparing (e.g. `THUMBS.db` and `Thumbs .db` match `Thumbs.db`).
3. **Restore check** (only for `GLACIER` / `DEEP_ARCHIVE`; other classes are always downloadable): for `GLACIER` / `DEEP_ARCHIVE` objects, a `head_object` call is made (if that call fails, the object is recorded as `FAILED` and the run continues); the object is downloadable only if its `Restore` header contains `ongoing-request="false"`.
4. **Skip unchanged**: if the local file exists with the **same size** as the remote object, it is skipped. Size only; no checksum or timestamp comparison.
5. **Safe download**: written to `<name>.part`, then renamed on success; the `.part` file is removed on failure. A failed object (head check, download, or unsafe path) is recorded and the run **continues with the next object**.
6. **Path safety**: a key that would resolve outside `dest` (e.g. contains `..`) is rejected and listed as `FAILED: <key> (unsafe path)`.
7. **Extra local files**: after the run, every file under `dest` that was not matched to a remote object (including previously downloaded excluded files such as an old `Thumbs.db`; `.part` files ignored) is listed (first 20 shown). The tool **never deletes anything**; clean up the folder manually.
   - Objects skipped as not restored, or that failed to download, are not treated as extra.

## Output and exit code

Per download: `get <relative path> (<size> MB)`, prefixed `[dry-run] ` in dry-run mode. After the summary, `not restored: <key>` and `FAILED: <key>...` lines, then the extra-local-files list (`extra local files kept (never deleted):`, first 20).

Summary line: `downloaded N (X MB), unchanged N, excluded N, not restored N, failed N, extra local N`, followed by detail lines for not-restored keys, failures, and extra local files. Under `--dry-run`, `downloaded` means "would download". Sizes are in MB, rounded to two decimals.

Exit code `1` if any object failed (head check, download, or unsafe path); otherwise `0`. Not-restored objects do not affect the exit code.

## Files

- `glacier_restore.py`: step 1, request restores
- `s3_mirror.py`: step 2, generic download (restored Glacier objects included)
- `tests/`: tests with a fake S3 client (no AWS needed). Mirror: exclude matching, not-restored skip, unsafe path, re-run skip, head-check failure continues, deep recursion. Restore: preview sends nothing, execute request shape, already-in-progress handling, failures continue, deep recursion
- `requirements.txt`, `.gitignore`

## Status

Unit tests pass (9). Not yet validated against real S3; pending an example data set.
