# weekly-backup

Zips today's dated folders under `C:\Temp` with 7-Zip and uploads them to S3.

## How it works (`run_backup.py`)

1. `find_todays_folders()` — lists direct child folders of `C:\Temp` whose name ends
   with today's date suffix `_yyyy.MM.dd` (e.g. `_2026.08.07`).
2. For each matching folder, `zip_folder()`:
   - Archives it with 7-Zip (`C:\Program Files\7-Zip\7z.exe`) into
     `C:\Temp\zip\<folder name>.7z`.
   - If the folder name contains `_Enc_`, the archive is additionally password-protected
     and header-encrypted (`-mhe=on`), using the password read from `credentail.txt`
     (kept alongside this script, never committed to git).
3. `upload_to_s3()` uploads the resulting `.7z` archive to `s3://wwlydata.backup/`
   via the AWS CLI, with `--storage-class STANDARD`.
4. A failure in either step for one folder is logged and the script continues to the
   next folder rather than aborting the whole run.

## Configuration

| Setting | Value |
|---|---|
| Source root | `C:\Temp` |
| Zip staging dir | `C:\Temp\zip` |
| 7-Zip path | `C:\Program Files\7-Zip\7z.exe` |
| S3 destination | `s3://wwlydata.backup/` |
| Storage class | `STANDARD` |
| Credential file | `credentail.txt` (gitignored) |

## Usage

```
venv\Scripts\activate
python run_backup.py
```

No third-party packages are required (stdlib only); the venv exists to follow this
repo's convention of running every subproject's Python from its own venv. Requires
7-Zip and the AWS CLI (with valid credentials for the target bucket) on `PATH`.

## Run log

### 2026-08-07

Ran via a PowerShell equivalent of the current script (same folder-detection,
zip, and upload logic later ported to `run_backup.py` and verified to select the
identical folder set). 6 folders matched today's date suffix:

| Folder | Encrypted | Archive size | S3 key |
|---|---|---|---|
| Family_Fun_2026.08.07 | No | 784.7 MiB | `Family_Fun_2026.08.07.7z` |
| Notes_2026.08.07 | No | 1.0 GiB | `Notes_2026.08.07.7z` |
| Novels_2026.08.07 | No | 751.5 MiB | `Novels_2026.08.07.7z` |
| Ssrec_Enc_2026.08.07 | Yes | 2.2 GiB | `Ssrec_Enc_2026.08.07.7z` |
| work-II_2026.08.07 | No | 2.2 GiB | `work-II_2026.08.07.7z` |
| work-I_2026.08.07 | No | 2.6 GiB | `work-I_2026.08.07.7z` |

All 6 archives uploaded successfully to `s3://wwlydata.backup/` with `STANDARD`
storage class; no errors in the run log. Local `.7z` copies retained in
`C:\Temp\zip\`.
