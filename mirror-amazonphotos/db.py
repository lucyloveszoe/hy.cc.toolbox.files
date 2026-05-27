#!/usr/bin/env python3
"""
SQLite helpers for mirror-amazonphotos.
Tracks photos, videos, albums, and album membership for idempotent re-runs.
"""

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    node_id      TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    size         INTEGER,
    md5          TEXT,
    content_type TEXT,
    created_date TEXT,
    modified_date TEXT,
    exif_date    TEXT,
    local_path   TEXT
);

CREATE TABLE IF NOT EXISTS albums (
    album_id     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    created_date TEXT
);

CREATE TABLE IF NOT EXISTS album_photos (
    album_id     TEXT NOT NULL,
    node_id      TEXT NOT NULL,
    PRIMARY KEY (album_id, node_id)
);

CREATE TABLE IF NOT EXISTS videos (
    node_id      TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    size         INTEGER,
    md5          TEXT,
    content_type TEXT,
    created_date TEXT,
    local_path   TEXT
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def upsert_photo(conn: sqlite3.Connection, node: dict, local_path: str) -> None:
    cp = node.get("contentProperties") or {}
    img = cp.get("image") or {}
    conn.execute("""
        INSERT INTO photos
            (node_id, name, size, md5, content_type, created_date, modified_date, exif_date, local_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
            name=excluded.name, size=excluded.size, md5=excluded.md5,
            content_type=excluded.content_type, created_date=excluded.created_date,
            modified_date=excluded.modified_date, exif_date=excluded.exif_date,
            local_path=excluded.local_path
    """, (
        node["id"],
        node.get("name"),
        cp.get("size"),
        cp.get("md5"),
        cp.get("contentType"),
        node.get("createdDate"),
        node.get("modifiedDate"),
        img.get("dateTimeOriginal"),
        local_path,
    ))
    conn.commit()


def upsert_video(conn: sqlite3.Connection, node: dict, local_path: str) -> None:
    cp = node.get("contentProperties") or {}
    conn.execute("""
        INSERT INTO videos
            (node_id, name, size, md5, content_type, created_date, local_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
            name=excluded.name, size=excluded.size, md5=excluded.md5,
            content_type=excluded.content_type, created_date=excluded.created_date,
            local_path=excluded.local_path
    """, (
        node["id"],
        node.get("name"),
        cp.get("size"),
        cp.get("md5"),
        cp.get("contentType"),
        node.get("createdDate"),
        local_path,
    ))
    conn.commit()


def upsert_album(conn: sqlite3.Connection, album: dict) -> None:
    conn.execute("""
        INSERT INTO albums (album_id, name, created_date)
        VALUES (?, ?, ?)
        ON CONFLICT(album_id) DO UPDATE SET
            name=excluded.name, created_date=excluded.created_date
    """, (album["id"], album.get("name"), album.get("createdDate")))
    conn.commit()


def upsert_album_photo(conn: sqlite3.Connection, album_id: str, node_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO album_photos (album_id, node_id) VALUES (?, ?)",
        (album_id, node_id),
    )
    conn.commit()


def clear_album_photos(conn: sqlite3.Connection, album_id: str) -> None:
    conn.execute("DELETE FROM album_photos WHERE album_id = ?", (album_id,))
    conn.commit()


def get_all_photo_node_ids(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT node_id FROM photos").fetchall()
    return {r["node_id"] for r in rows}


def get_all_video_node_ids(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT node_id FROM videos").fetchall()
    return {r["node_id"] for r in rows}


def get_photo_local_path(conn: sqlite3.Connection, node_id: str) -> str | None:
    row = conn.execute("SELECT local_path FROM photos WHERE node_id = ?", (node_id,)).fetchone()
    return row["local_path"] if row else None


def get_video_local_path(conn: sqlite3.Connection, node_id: str) -> str | None:
    row = conn.execute("SELECT local_path FROM videos WHERE node_id = ?", (node_id,)).fetchone()
    return row["local_path"] if row else None


def delete_photo(conn: sqlite3.Connection, node_id: str) -> None:
    conn.execute("DELETE FROM album_photos WHERE node_id = ?", (node_id,))
    conn.execute("DELETE FROM photos WHERE node_id = ?", (node_id,))
    conn.commit()


def delete_video(conn: sqlite3.Connection, node_id: str) -> None:
    conn.execute("DELETE FROM videos WHERE node_id = ?", (node_id,))
    conn.commit()
