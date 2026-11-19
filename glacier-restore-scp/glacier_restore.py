"""Request restore of all archived (GLACIER / DEEP_ARCHIVE) objects under an S3 prefix.

Companion to s3_mirror.py: run this first, wait until the restore completes
(hours), then run s3_mirror.py to download. Restores cost money, so nothing is
requested unless --execute is given (default is a preview).
Files matching the exclude patterns are not restored.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from s3_mirror import ARCHIVE_CLASSES, DEFAULT_EXCLUDES, is_excluded

TIERS = ["Bulk", "Standard", "Expedited"]


def gb(n: int) -> float:
    return round(n / 1024 ** 3, 2)


@dataclass
class Stats:
    requested: int = 0
    bytes: int = 0
    already_restored: int = 0
    in_progress: int = 0
    not_archived: int = 0
    excluded: int = 0
    failed: list[str] = field(default_factory=list)


def restore_state(head: dict) -> str:
    """'none' | 'in_progress' | 'restored' from a head_object response."""
    r = head.get("Restore", "")
    if not r:
        return "none"
    return "in_progress" if 'ongoing-request="true"' in r else "restored"


def restore_prefix(client, bucket: str, prefix: str, excludes: list[str],
                   days: int, tier: str, execute: bool = False) -> Stats:
    prefix = prefix.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    st = Stats()
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            if is_excluded(key[len(prefix):], excludes):
                st.excluded += 1
                continue
            if obj.get("StorageClass", "STANDARD") not in ARCHIVE_CLASSES:
                st.not_archived += 1
                continue
            try:
                state = restore_state(client.head_object(Bucket=bucket, Key=key))
                if state == "restored":
                    st.already_restored += 1
                    continue
                if state == "in_progress":
                    st.in_progress += 1
                    continue
                print(f"{'' if execute else '[dry-run] '}restore {key[len(prefix):]} "
                      f"({gb(obj['Size'])} GB)")
                if execute:
                    client.restore_object(
                        Bucket=bucket, Key=key,
                        RestoreRequest={"Days": days,
                                        "GlacierJobParameters": {"Tier": tier}})
                st.requested += 1
                st.bytes += obj["Size"]
            except ClientError as e:
                if e.response["Error"]["Code"] == "RestoreAlreadyInProgress":
                    st.in_progress += 1
                else:
                    st.failed.append(f"{key}: {e}")  # log and move on to next object
            except BotoCoreError as e:
                st.failed.append(f"{key}: {e}")
    return st


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bucket")
    ap.add_argument("prefix", help="S3 prefix to restore recursively; '' = whole bucket")
    ap.add_argument("--days", type=int, default=7,
                    help="days the restored copy stays available (default 7)")
    ap.add_argument("--tier", choices=TIERS, default="Bulk",
                    help="retrieval tier (default Bulk, cheapest; "
                         "Expedited is not available for DEEP_ARCHIVE)")
    ap.add_argument("-x", "--exclude", action="append", default=None,
                    help=f"glob to skip (repeatable); replaces defaults {DEFAULT_EXCLUDES}")
    ap.add_argument("--add-exclude", action="append", default=[])
    ap.add_argument("--profile")
    ap.add_argument("--region")
    ap.add_argument("--execute", action="store_true",
                    help="actually request restores (costs money); default is preview")
    a = ap.parse_args(argv)

    excludes = (a.exclude if a.exclude is not None else DEFAULT_EXCLUDES) + a.add_exclude
    client = boto3.Session(profile_name=a.profile, region_name=a.region).client("s3")
    st = restore_prefix(client, a.bucket, a.prefix, excludes, a.days, a.tier, a.execute)

    print(f"\n{'requested' if a.execute else 'would request'} {st.requested} "
          f"({gb(st.bytes)} GB, tier {a.tier}, {a.days} days), "
          f"already restored {st.already_restored}, in progress {st.in_progress}, "
          f"not archived {st.not_archived}, excluded {st.excluded}, "
          f"failed {len(st.failed)}")
    for k in st.failed:
        print(f"  FAILED: {k}")
    if not a.execute:
        print("preview only; add --execute to request the restores")
    return 1 if st.failed else 0


if __name__ == "__main__":
    sys.exit(main())
