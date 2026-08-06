#!/usr/bin/env python3
"""
amazon.photos.cloner — Mirror all photos and album definitions from Amazon Photos to local storage.

Data flows only one way: Amazon Photos → local. Never writes back to the cloud.

Usage:
    python cloner.py --mirror-root C:\\tmp\\mirror
    python cloner.py --mirror-root C:\\tmp\\mirror --dry-run
    python cloner.py --mirror-root C:\\tmp\\mirror --session-file C:\\path\\to\\session.json
    python cloner.py --save-session        # one-time login, saves session then exits
"""

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Optional

from tqdm import tqdm

import db
from amazon_client import AmazonPhotosClient, save_amazon_session

log = logging.getLogger(__name__)

# Default: share the session from the sibling sync-amazonphotos project
_DEFAULT_SESSION = Path(__file__).parent.parent / "sync-amazonphotos" / "session.json"


def _safe_filename(name: str) -> str:
    """Strip characters that are illegal in Windows/macOS filenames."""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def _node_month(node: dict) -> Optional[str]:
    """Return 'YYYY-MM' from a node's shoot date (exif) or upload date, or None."""
    cp = node.get("contentProperties") or {}
    date_str = (
        (cp.get("image") or {}).get("dateTimeOriginal")
        or node.get("createdDate")
    )
    return date_str[:7] if date_str and len(date_str) >= 7 else None


def sync_photos(
    client: AmazonPhotosClient,
    conn,
    pics_dir: Path,
    dry_run: bool,
    month_filter: Optional[str] = None,
) -> set[str]:
    """
    Download photos from Amazon Photos to pics_dir.

    month_filter: 'YYYY-MM' string — when set, only photos whose shoot date (or
    upload date) falls in that month are downloaded. Deletion cleanup is skipped
    because a partial sync should never remove files from other months.

    Returns the set of cloud node IDs that were considered (after filtering).
    """
    log.info("▶ Enumerating all photos from Amazon Photos...")
    nodes = client.list_nodes("IMAGE")
    log.info("  Found %d photos in Amazon Photos", len(nodes))

    if month_filter:
        nodes = [n for n in nodes if _node_month(n) == month_filter]
        log.info("  After --month %s filter: %d photos", month_filter, len(nodes))

    cloud_ids = {n["id"] for n in nodes if n.get("id")}

    for node in tqdm(nodes, desc="Syncing photos", unit="file"):
        name = node.get("name", "")
        if not name:
            continue

        dest = pics_dir / name

        if dest.exists():
            log.debug("Already exists: %s — skipping download", name)
            if not dry_run:
                db.upsert_photo(conn, node, str(dest))
            continue

        if dry_run:
            log.info("[DRY-RUN] Would download: %s", name)
            continue

        log.info("Downloading: %s", name)
        ok = client.download_node(node, dest)
        if ok:
            db.upsert_photo(conn, node, str(dest))
        else:
            log.warning("  ↳ Failed to download %s — will retry on next run", name)

    # Deletion cleanup only runs on a full (unfiltered) sync.
    # When --month is set we only pulled a subset, so we must not delete
    # files that belong to other months.
    if month_filter:
        return cloud_ids

    local_ids = db.get_all_photo_node_ids(conn)
    removed = local_ids - cloud_ids
    if removed:
        log.info("Cleaning up %d photo(s) deleted from cloud...", len(removed))
    for node_id in removed:
        local_path = db.get_photo_local_path(conn, node_id)
        if local_path and Path(local_path).exists():
            if dry_run:
                log.info("[DRY-RUN] Would delete removed photo: %s", local_path)
            else:
                Path(local_path).unlink()
                log.info("Deleted removed photo: %s", Path(local_path).name)
        if not dry_run:
            db.delete_photo(conn, node_id)

    return cloud_ids


def sync_albums(
    client: AmazonPhotosClient,
    conn,
    albums_dir: Path,
    pics_dir: Path,
    dry_run: bool,
    month_filter: Optional[str] = None,
) -> None:
    """
    Mirror all Amazon Photos albums as local JSON files in albums_dir.

    Each JSON file contains the album name, ID, and a list of photos with their
    local file paths — so the viewer can reconstruct albums without an internet connection.
    Stale JSON files (albums deleted from cloud) are removed.

    month_filter: 'YYYY-MM' string — when set, only photos from that month are
    included in the album JSONs. Albums themselves are always synced.
    """
    log.info("▶ Enumerating albums from Amazon Photos...")
    albums = client.list_albums()
    log.info("  Found %d albums", len(albums))

    cloud_album_names: set[str] = set()

    for album in tqdm(albums, desc="Syncing albums", unit="album"):
        album_id = album.get("id")
        album_name = album.get("name", album_id)
        if not album_id:
            continue

        safe_name = _safe_filename(album_name)
        cloud_album_names.add(safe_name)

        children = client.list_album_children(album_id)

        if month_filter:
            children = [c for c in children if _node_month(c) == month_filter]
            log.debug("  Album '%s': after --month filter: %d photos", album_name, len(children))
        else:
            log.info("  Album '%s': %d photos", album_name, len(children))

        photo_entries = []
        for child in children:
            child_name = child.get("name", "")
            local_path = str(pics_dir / child_name) if child_name else None
            photo_entries.append({
                "node_id": child.get("id"),
                "name": child_name,
                "local_path": local_path,
            })

        album_def = {
            "name": album_name,
            "album_id": album_id,
            "created_date": album.get("createdDate"),
            "photo_count": len(children),
            "photos": photo_entries,
        }

        json_path = albums_dir / f"{safe_name}.json"

        if dry_run:
            log.info("[DRY-RUN] Would write album '%s' (%d photos) → %s",
                     album_name, len(children), json_path.name)
            continue

        json_path.write_text(
            json.dumps(album_def, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.debug("Wrote album: %s", json_path.name)

        db.upsert_album(conn, album)
        db.clear_album_photos(conn, album_id)
        for child in children:
            if child.get("id"):
                db.upsert_album_photo(conn, album_id, child["id"])

    # Remove local album JSON files for albums no longer in the cloud
    if not dry_run and albums_dir.exists():
        for jf in albums_dir.glob("*.json"):
            if jf.stem not in cloud_album_names:
                jf.unlink()
                log.info("Deleted stale album: %s", jf.name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mirror Amazon Photos (photos + albums) to a local folder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  First-time login:  python cloner.py --save-session\n"
            "  Dry run:           python cloner.py --mirror-root C:\\tmp\\mirror --dry-run\n"
            "  Full sync:         python cloner.py --mirror-root C:\\tmp\\mirror\n"
            "  One month only:    python cloner.py --mirror-root C:\\tmp\\mirror --month 2024-06\n"
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
        help="Preview all actions — no files downloaded or written",
    )
    parser.add_argument(
        "--month",
        metavar="YYYY-MM",
        help="Only clone photos from this month (e.g. 2024-06). Uses shoot date when available, upload date otherwise.",
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
    pics_dir = mirror_root / "pics"
    albums_dir = mirror_root / "albums"

    if args.dry_run:
        log.info("═══ DRY-RUN MODE — no files will be downloaded or written ═══")

    if not args.dry_run:
        pics_dir.mkdir(parents=True, exist_ok=True)
        albums_dir.mkdir(parents=True, exist_ok=True)

    conn = db.init_db(mirror_root / "mirror.db")

    try:
        client = AmazonPhotosClient(session_file, dry_run=args.dry_run)
    except RuntimeError as e:
        log.error("Amazon Photos init failed: %s", e)
        conn.close()
        raise SystemExit(1)

    try:
        cloud_photo_ids = sync_photos(client, conn, pics_dir,
                                      dry_run=args.dry_run, month_filter=args.month)
        sync_albums(client, conn, albums_dir, pics_dir, dry_run=args.dry_run,
                    month_filter=args.month)
        log.info("✓ Done")
    finally:
        client.close()
        conn.close()


if __name__ == "__main__":
    main()
