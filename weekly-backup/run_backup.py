"""Zip today's dated folders under C:\\Temp and upload them to S3.

Direct child folders of C:\\Temp ending in "_yyyy.MM.dd" (today's date) are archived
with 7-Zip. Folders whose name contains "_Enc_" are additionally password + header
encrypted using the password stored in credentail.txt.
"""

import subprocess
import sys
from datetime import date
from pathlib import Path

SOURCE_ROOT = Path(r"C:\Temp")
ZIP_DIR = Path(r"C:\Temp\zip")
SEVEN_ZIP = r"C:\Program Files\7-Zip\7z.exe"
S3_BUCKET = "s3://wwlydata.backup"
CRED_FILE = Path(__file__).parent / "credentail.txt"


def find_todays_folders():
    suffix = "_" + date.today().strftime("%Y.%m.%d")
    return sorted(p for p in SOURCE_ROOT.iterdir() if p.is_dir() and p.name.endswith(suffix))


def zip_folder(folder):
    archive_path = ZIP_DIR / (folder.name + ".7z")
    needs_encryption = "_Enc_" in folder.name

    print(f"=== Zipping {folder.name} -> {archive_path} (encrypted: {needs_encryption}) ===")
    cmd = [SEVEN_ZIP, "a", "-t7z"]
    if needs_encryption:
        password = CRED_FILE.read_text(encoding="utf-8").strip()
        cmd += [f"-p{password}", "-mhe=on"]
    cmd += [str(archive_path), str(folder)]
    subprocess.run(cmd, check=True)

    return archive_path


def upload_to_s3(archive_path):
    print(f"=== Uploading {archive_path} -> {S3_BUCKET}/ (STANDARD) ===")
    subprocess.run(
        ["aws", "s3", "cp", str(archive_path), f"{S3_BUCKET}/", "--storage-class", "STANDARD"],
        check=True,
    )


def main():
    folders = find_todays_folders()
    if not folders:
        print(f"No folders under {SOURCE_ROOT} end with today's date suffix. Nothing to back up.")
        return

    print(f"Found {len(folders)} folder(s) to back up:")
    for folder in folders:
        print(f"  - {folder.name}")

    for folder in folders:
        try:
            archive_path = zip_folder(folder)
            upload_to_s3(archive_path)
            print(f"=== Done: {folder.name} ===")
        except subprocess.CalledProcessError as exc:
            print(f"ERROR: step failed for {folder.name}: {exc}", file=sys.stderr)
            continue


if __name__ == "__main__":
    main()
