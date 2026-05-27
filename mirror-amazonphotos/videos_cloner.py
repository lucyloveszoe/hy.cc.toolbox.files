#!/usr/bin/env python3
"""
amazon.videos.cloner — Mirror all videos from Amazon Photos to local storage.

Data flows only one way: Amazon Photos → local. Never writes back to the cloud.

Usage:
    python videos_cloner.py --mirror-root C:\\tmp\\mirror
    python videos_cloner.py --mirror-root C:\\tmp\\mirror --dry-run
    python videos_cloner.py --mirror-root C:\\tmp\\mirror --session-file C:\\path\\to\\session.json
    python videos_cloner.py --save-session    # one-time login, saves session then exits
"""

import argparse
import logging
from pathlib import Path
from typing import Optional

from tqdm import tqdm

import re

import db
from amazon_client import AmazonPhotosClient, save_amazon_session

log = logging.getLogger(__name__)

_DEFAULT_SESSION = Path(__file__).parent.parent / "sync-amazonphotos" / "session.json"


def _node_month(node: dict) -> Optional[str]:
    """Return 'YYYY-MM' from a node's upload date, or None."""
    date_str = node.get("createdDate")
    return date_str[:7] if date_str and len(date_str) >= 7 else None


def sync_videos(
    client: AmazonPhotosClient,
    conn,
    vids_dir: Path,
    dry_run: bool,
    month_filter: Optional[str] = None,
) -> None:
    """
    Download videos from Amazon Photos to vids_dir.

    month_filter: 'YYYY-MM' string — when set, only videos whose upload date
    falls in that month are downloaded. Deletion cleanup is skipped because a
    partial sync should never remove files from other months.
    """
    log.info("▶ Enumerating all videos from Amazon Photos...")
    nodes = client.list_nodes("VIDEO")
    log.info("  Found %d videos in Amazon Photos", len(nodes))

    if month_filter:
        nodes = [n for n in nodes if _node_month(n) == month_filter]
        log.info("  After --month %s filter: %d videos", month_filter, len(nodes))

    cloud_ids = {n["id"] for n in nodes if n.get("id")}

    for node in tqdm(nodes, desc="Syncing videos", unit="file"):
        name = node.get("name", "")
        if not name:
            continue

        dest = vids_dir / name

        if dest.exists():
            log.debug("Already exists: %s — skipping download", name)
            if not dry_run:
                db.upsert_video(conn, node, str(dest))
            continue

        if dry_run:
            log.info("[DRY-RUN] Would download: %s", name)
            continue

        log.info("Downloading: %s", name)
        ok = client.download_node(node, dest)
        if ok:
            db.upsert_video(conn, node, str(dest))
        else:
            log.warning("  ↳ Failed to download %s — will retry on next run", name)

    # Deletion cleanup only runs on a full (unfiltered) sync.
    if month_filter:
        return

    local_ids = db.get_all_video_node_ids(conn)
    removed = local_ids - cloud_ids
    if removed:
        log.info("Cleaning up %d video(s) deleted from cloud...", len(removed))
    for node_id in removed:
        local_path = db.get_video_local_path(conn, node_id)
        if local_path and Path(local_path).exists():
            if dry_run:
                log.info("[DRY-RUN] Would delete removed video: %s", local_path)
            else:
                Path(local_path).unlink()
                log.info("Deleted removed video: %s", Path(local_path).name)
        if not dry_run:
            db.delete_video(conn, node_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mirror Amazon Photos videos to a local folder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  First-time login:  python videos_cloner.py --save-session\n"
            "  Dry run:           python videos_cloner.py --mirror-root C:\\tmp\\mirror --dry-run\n"
            "  Full sync:         python videos_cloner.py --mirror-root C:\\tmp\\mirror\n"
            "  One month only:    python videos_cloner.py --mirror-root C:\\tmp\\mirror --month 2024-06\n"
        ),
    )
    parser.add_argument(
        "--mirror-root",
        help="Root folder for the local mirror (required unless --save-session)",
    )
    parser.add_argument(
        "--session-file",
        help=f"Path to session.json (default: {_DEFAULT_SESSION})",
    )
    parser.add_argument(
        "--save-session",
        action="store_true",
        help="Open browser to log in to Amazon Photos and save the session, then exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview all actions — no files downloaded",
    )
    parser.add_argument(
        "--month",
        metavar="YYYY-MM",
        help="Only clone videos from this month (e.g. 2024-06). Uses upload date.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    session_file = Path(args.session_file) if args.session_file else _DEFAULT_SESSION

    if args.month and not re.fullmatch(r"\d{4}-\d{2}", args.month):
        parser.error("--month must be in YYYY-MM format (e.g. 2024-06)")

    if args.save_session:
        save_amazon_session(session_file)
        return

    if not args.mirror_root:
        parser.error("--mirror-root is required (e.g. --mirror-root C:\\tmp\\mirror)")

    mirror_root = Path(args.mirror_root)
    vids_dir = mirror_root / "vids"

    if args.dry_run:
        log.info("═══ DRY-RUN MODE — no files will be downloaded ═══")

    if not args.dry_run:
        vids_dir.mkdir(parents=True, exist_ok=True)

    conn = db.init_db(mirror_root / "mirror.db")

    try:
        client = AmazonPhotosClient(session_file, dry_run=args.dry_run)
    except RuntimeError as e:
        log.error("Amazon Photos init failed: %s", e)
        conn.close()
        raise SystemExit(1)

    try:
        sync_videos(client, conn, vids_dir, dry_run=args.dry_run, month_filter=args.month)
        log.info("✓ Done")
    finally:
        client.close()
        conn.close()


if __name__ == "__main__":
    main()
