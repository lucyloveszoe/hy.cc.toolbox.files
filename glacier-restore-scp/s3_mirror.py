"""Mirror any S3 prefix to a local directory.

Generic: normal objects and restored Glacier objects download the same way. As a
safety check, GLACIER / DEEP_ARCHIVE objects that have not been restored are
reported and skipped instead of erroring.
Files matching the exclude patterns (e.g. Thumbs.db) are never downloaded.
All name comparisons are case-insensitive and whitespace-stripped.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

DEFAULT_EXCLUDES = ["Thumbs.db", "desktop.ini", ".DS_Store", "~$*"]
ARCHIVE_CLASSES = {"GLACIER", "DEEP_ARCHIVE"}


def norm(s: str) -> str:
    """Normalize for comparison: lowercase, no whitespace."""
    return re.sub(r"\s+", "", s).lower()


def is_excluded(key: str, patterns: list[str]) -> bool:
    """True if any path component of the key matches an exclude pattern."""
    parts = [norm(p) for p in key.split("/") if p]
    pats = [norm(p) for p in patterns]
    return any(fnmatch.fnmatchcase(part, pat) for part in parts for pat in pats)


def is_restored(obj: dict, head: dict | None) -> bool:
    """Whether the object is downloadable now."""
    if obj.get("StorageClass", "STANDARD") not in ARCHIVE_CLASSES:
        return True
    restore = (head or {}).get("Restore", "")
    return 'ongoing-request="false"' in restore


def safe_local_path(dest: Path, rel: str) -> Path | None:
    """Resolve rel under dest; None if it would escape dest."""
    target = (dest / rel).resolve()
    try:
        target.relative_to(dest.resolve())
    except ValueError:
        return None
    return target


def mb(n: int) -> float:
    return round(n / 1024 / 1024, 2)


@dataclass
class Stats:
    downloaded: int = 0
    skipped_same: int = 0
    excluded: int = 0
    not_restored: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    extra_local: list[str] = field(default_factory=list)
    bytes: int = 0


def mirror(client, bucket: str, prefix: str, dest: Path, excludes: list[str],
           dry_run: bool = False) -> Stats:
    prefix = prefix.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    st = Stats()
    seen: set[Path] = set()

    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):  # folder marker
                continue
            rel = key[len(prefix):]
            if is_excluded(rel, excludes):
                st.excluded += 1
                continue
            target = safe_local_path(dest, rel)
            if target is None:
                st.failed.append(f"{key} (unsafe path)")
                continue
            seen.add(target)

            head = None
            if obj.get("StorageClass") in ARCHIVE_CLASSES:
                try:
                    head = client.head_object(Bucket=bucket, Key=key)
                except (ClientError, BotoCoreError) as e:
                    st.failed.append(f"{key}: {e}")  # log and move on
                    continue
            if not is_restored(obj, head):
                st.not_restored.append(key)
                continue

            if target.is_file() and target.stat().st_size == obj["Size"]:
                st.skipped_same += 1
                continue

            print(f"{'[dry-run] ' if dry_run else ''}get {rel} ({mb(obj['Size'])} MB)")
            if dry_run:
                st.downloaded += 1
                st.bytes += obj["Size"]
                continue
            tmp = target.with_name(target.name + ".part")
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                client.download_file(bucket, key, str(tmp))
                os.replace(tmp, target)
                st.downloaded += 1
                st.bytes += obj["Size"]
            except (ClientError, BotoCoreError, OSError) as e:
                st.failed.append(f"{key}: {e}")
                tmp.unlink(missing_ok=True)

    # Local files with no remote counterpart (reported only, never deleted).
    for root, _, files in os.walk(dest):
        for f in files:
            p = (Path(root) / f).resolve()
            if p not in seen and not f.endswith(".part"):
                st.extra_local.append(str(p))
    return st


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bucket")
    ap.add_argument("prefix", help="folder (S3 prefix) to mirror; use '' for whole bucket")
    ap.add_argument("dest", type=Path, help="local mirror directory")
    ap.add_argument("-x", "--exclude", action="append", default=None,
                    help="glob pattern to skip (repeatable); replaces defaults "
                         f"{DEFAULT_EXCLUDES}")
    ap.add_argument("--add-exclude", action="append", default=[],
                    help="extra pattern added to the defaults")
    ap.add_argument("--profile")
    ap.add_argument("--region")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    excludes = (a.exclude if a.exclude is not None else DEFAULT_EXCLUDES) + a.add_exclude
    session = boto3.Session(profile_name=a.profile, region_name=a.region)
    a.dest.mkdir(parents=True, exist_ok=True)
    st = mirror(session.client("s3"), a.bucket, a.prefix, a.dest, excludes,
                a.dry_run)

    print(f"\ndownloaded {st.downloaded} ({mb(st.bytes)} MB), unchanged {st.skipped_same}, "
          f"excluded {st.excluded}, not restored {len(st.not_restored)}, "
          f"failed {len(st.failed)}, extra local {len(st.extra_local)}")
    for k in st.not_restored:
        print(f"  not restored: {k}")
    for k in st.failed:
        print(f"  FAILED: {k}")
    if st.extra_local:
        print("  extra local files kept (never deleted):")
        for p in st.extra_local[:20]:
            print(f"    {p}")
    return 1 if st.failed else 0


if __name__ == "__main__":
    sys.exit(main())
