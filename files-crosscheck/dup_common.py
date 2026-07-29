"""dup_common.py — shared core for local-dup-match.py,
local-dup-match-cross.py, s3-dup-match-cross.py, and
local-folder-win-dup-check.py.

Two catalog formats are supported:

* **Linux NAS dump** — every line is::

      <size_in_bytes> bytes <full_posix_path>

  e.g. ``468068018 bytes /Volumes/YuData/Korea.50G/episode01.mp4``.

* **S3 / AWS CLI listing** — every line is::

      YYYY-MM-DD HH:MM:SS  <size_in_bytes>  <relative_key>

  e.g. ``2025-09-14 01:40:40    1057437 X-twitter/HK141Channel/01.mp4``.
  Directory placeholder rows (size 0 + key ending with ``/``) are skipped.

Every parsed line becomes a :class:`Record` tagged with:

* ``side``   — a label identifying the folder it came from (so cross-folder
               scripts can require members on >= 2 distinct sides)
* ``source`` — the catalog filename inside that folder

Both ``side`` and ``source`` participate in deduplication grouping rules.

Workspace rules
---------------
* All string comparisons are lowercase + whitespace stripped.
* Numeric ratios are rounded to two decimals.
"""

from __future__ import annotations

import csv
import difflib
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

SIMILARITY_THRESHOLD = 0.85
MIN_NORM_LENGTH = 4

_LINUX_LINE_RE = re.compile(r"^\s*(\d+)\s+bytes\s+(.+?)\s*$")
_S3_LINE_RE = re.compile(
    r"^\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+(\d+)\s+(.+?)\s*$"
)

_SYSTEM_FILE_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
_SYSTEM_FILE_PREFIXES = ("._",)

_NORMALIZE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\s*\(\d+\)$"),
    re.compile(r"\s*-\s*copy(\s*\(\d+\))?$"),
    re.compile(r"\s*copy(\s*\(\d+\))?$"),
    re.compile(r"[_\-\s]+v\d+$"),
    re.compile(r"[_\-\s]+(final|edit|edited|new|old|backup|bak)$"),
)

_GENERIC_NORMS = {
    "img",
    "image",
    "images",
    "video",
    "videos",
    "file",
    "files",
    "photo",
    "photos",
    "pic",
    "pics",
    "movie",
    "movies",
    "mov",
    "dsc",
    "dscn",
    "dscf",
    "doc",
    "document",
    "tmp",
    "temp",
    "untitled",
    "new",
    "copy",
    "scan",
    "scanned",
    "screenshot",
    "capture",
    "recording",
}


@dataclass(frozen=True)
class Record:
    """One file-listing entry produced by a catalog text dump."""

    side: str
    source: str
    size: int
    path: str
    name: str


def _norm_str(s: str) -> str:
    """Workspace rule: case-insensitive + whitespace-trimmed comparison."""
    return s.strip().lower()


def is_system_file(basename: str) -> bool:
    """True for OS-junk files (.DS_Store / Thumbs.db / ._* etc.)."""
    lname = _norm_str(basename)
    if lname in _SYSTEM_FILE_NAMES:
        return True
    return any(lname.startswith(p) for p in _SYSTEM_FILE_PREFIXES)


def normalize_name(filename: str) -> str:
    """Strip extension + common copy/version markers for fuzzy grouping."""
    stem = _norm_str(PurePosixPath(filename).stem)
    prev = ""
    while prev != stem:
        prev = stem
        for pat in _NORMALIZE_PATTERNS:
            stem = pat.sub("", stem).strip()
    return re.sub(r"\s+", " ", stem).strip()


def is_too_generic(norm: str) -> bool:
    """Filter out normalized names that are too short / pure-digit / generic
    camera-or-scan prefixes — otherwise they over-cluster."""
    if not norm or len(norm) < MIN_NORM_LENGTH:
        return True
    if norm.isdigit():
        return True
    return norm in _GENERIC_NORMS


ParseFn = Callable[[Path, str], tuple[list[Record], int, int]]


def _detect_text_encoding(file: Path) -> str:
    """Return the encoding to use for reading ``file`` based on its BOM.

    Supports UTF-16 LE/BE (BOM ``FF FE`` / ``FE FF``) — commonly produced by
    Windows tools like ``Get-ChildItem | Out-File`` — as well as UTF-8 with
    BOM and plain UTF-8.
    """
    with file.open("rb") as fh:
        head = fh.read(4)
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    if head[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    return "utf-8"


def _parse_with_regex(
    file: Path,
    side: str,
    line_re: re.Pattern[str],
    skip_dir_markers: bool,
) -> tuple[list[Record], int, int]:
    """Shared line-by-line parser. ``line_re`` must expose two capture
    groups: ``(size, path)``. When ``skip_dir_markers`` is true, lines
    whose path ends in ``/`` are dropped (S3 directory placeholders)."""
    records: list[Record] = []
    parsed = 0
    skipped = 0
    encoding = _detect_text_encoding(file)
    with file.open(encoding=encoding, errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            m = line_re.match(line)
            if not m:
                skipped += 1
                if skipped <= 3:
                    print(
                        f"warn: {file.name}:{lineno} unparseable -> "
                        f"{line[:80]!r}",
                        file=sys.stderr,
                    )
                continue
            size = int(m.group(1))
            path = m.group(2)
            if skip_dir_markers and path.endswith("/"):
                continue
            parsed += 1
            name = PurePosixPath(path).name or path
            records.append(Record(side, file.name, size, path, name))
    return records, parsed, skipped


def parse_linux_catalog(
    file: Path, side: str
) -> tuple[list[Record], int, int]:
    """Parse a Linux NAS dump: ``<size> bytes <full_posix_path>``."""
    return _parse_with_regex(
        file, side, _LINUX_LINE_RE, skip_dir_markers=False
    )


def parse_s3_catalog(
    file: Path, side: str
) -> tuple[list[Record], int, int]:
    """Parse an S3 / AWS CLI listing: ``YYYY-MM-DD HH:MM:SS <size> <key>``.

    Directory marker rows (key ending with ``/``) are skipped.
    """
    return _parse_with_regex(
        file, side, _S3_LINE_RE, skip_dir_markers=True
    )


def load_records_from_catalog_file(
    file: Path,
    side: str,
    include_system: bool,
    include_zero: bool,
    parse_fn: ParseFn = parse_linux_catalog,
) -> list[Record]:
    """Parse one catalog file, return its filtered Record list."""
    recs, parsed, skipped = parse_fn(file, side)
    kept_records: list[Record] = []
    for r in recs:
        if not include_zero and r.size == 0:
            continue
        if not include_system and is_system_file(r.name):
            continue
        kept_records.append(r)
    print(
        f"  [{side}] {file.name}: parsed={parsed} kept={len(kept_records)} "
        f"unparseable={skipped}"
    )
    return kept_records


def load_records(
    folder: Path,
    glob: str,
    side: str,
    include_system: bool,
    include_zero: bool,
    parse_fn: ParseFn = parse_linux_catalog,
) -> list[Record]:
    """Walk one folder for catalog files, return filtered Record list.

    ``parse_fn`` selects which line format to expect (default: Linux NAS).
    """
    catalogs = sorted(folder.glob(glob))
    if not catalogs:
        print(
            f"warn: no catalog files matching {glob!r} under {folder}",
            file=sys.stderr,
        )
        return []

    all_records: list[Record] = []
    for cat in catalogs:
        all_records.extend(
            load_records_from_catalog_file(
                cat, side, include_system, include_zero, parse_fn
            )
        )
    return all_records


def load_records_from_filesystem(
    folder: Path,
    side: str,
    include_system: bool,
    include_zero: bool,
) -> list[Record]:
    """Recursively walk a real folder on disk and return filtered Records.

    Unlike :func:`load_records`, this reads file sizes straight from the
    filesystem (``Path.stat``) instead of parsing a catalog text dump.
    ``source`` is set to the file's directory path relative to ``folder``
    (``"(root)"`` for files directly inside it), since there is no catalog
    filename to record.
    """
    records: list[Record] = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        name = p.name
        if not include_zero and size == 0:
            continue
        if not include_system and is_system_file(name):
            continue
        rel_dir = p.parent.relative_to(folder).as_posix()
        source = "(root)" if rel_dir == "." else rel_dir
        records.append(Record(side, source, size, str(p), name))
    return records


def find_exact_duplicates(
    records: list[Record],
    require_cross_side: bool = False,
) -> dict[int, list[Record]]:
    """Group records by identical byte size.

    Args:
        records: parsed file records.
        require_cross_side: keep only groups whose members span >= 2 sides.
    """
    by_size: dict[int, list[Record]] = defaultdict(list)
    for r in records:
        by_size[r.size].append(r)
    groups: dict[int, list[Record]] = {}
    for size, members in by_size.items():
        if len(members) < 2:
            continue
        if require_cross_side and len({r.side for r in members}) < 2:
            continue
        groups[size] = members
    return groups


def find_potential_duplicates(
    records: list[Record],
    require_cross_side: bool = False,
    require_cross_source: bool = False,
    enable_fuzzy: bool = False,
) -> list[list[Record]]:
    """Group records with similar basenames but different byte sizes.

    Pass 1 — exact bucket on the normalized basename.
    Pass 2 (optional, ``enable_fuzzy``) — cluster remaining singletons via
        :class:`difflib.SequenceMatcher` >= ``SIMILARITY_THRESHOLD``.

    Buckets whose key is "too generic" (e.g. ``img``, pure digits, < 4 chars)
    are dropped — these over-cluster iPhone-style camera dumps and
    meaningless ``1.avi`` / ``2.avi`` names.
    """
    buckets: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        norm = normalize_name(r.name)
        if is_too_generic(norm):
            continue
        buckets[norm].append(r)

    groups: list[list[Record]] = []
    leftover: list[tuple[str, Record]] = []
    for _, members in buckets.items():
        if len(members) > 1:
            groups.append(members)
        else:
            leftover.append((normalize_name(members[0].name), members[0]))

    if enable_fuzzy:
        used = [False] * len(leftover)
        for i in range(len(leftover)):
            if used[i]:
                continue
            name_i, rec_i = leftover[i]
            cluster: list[Record] = [rec_i]
            for j in range(i + 1, len(leftover)):
                if used[j]:
                    continue
                name_j, rec_j = leftover[j]
                longer = max(len(name_i), len(name_j))
                if longer and abs(len(name_i) - len(name_j)) > longer * 0.3:
                    continue
                ratio = round(
                    difflib.SequenceMatcher(None, name_i, name_j).ratio(),
                    2,
                )
                if ratio >= SIMILARITY_THRESHOLD:
                    cluster.append(rec_j)
                    used[j] = True
            if len(cluster) > 1:
                used[i] = True
                groups.append(cluster)

    def passes(group: list[Record]) -> bool:
        if len({r.size for r in group}) < 2:
            return False
        if require_cross_side and len({r.side for r in group}) < 2:
            return False
        if require_cross_source and len({r.source for r in group}) < 2:
            return False
        return True

    return [g for g in groups if passes(g)]


def _open_for_write(out_path: Path):
    """Open ``out_path`` for writing; on PermissionError, print a hint
    (likely the file is open in Excel) and re-raise."""
    try:
        return out_path.open("w", newline="", encoding="utf-8-sig")
    except PermissionError as exc:
        print(
            f"error: cannot write {out_path} - it appears to be open in "
            f"another application (e.g. Excel). Close it and re-run.",
            file=sys.stderr,
        )
        raise SystemExit(3) from exc


def write_exact_csv(
    groups: dict[int, list[Record]], out_path: Path
) -> int:
    """Write exact-duplicate report. Returns number of data rows written."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with _open_for_write(out_path) as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "group_id",
                "size_bytes",
                "side",
                "source",
                "file_name",
                "file_path",
            ]
        )
        for gid, (size, members) in enumerate(
            sorted(groups.items(), key=lambda kv: -kv[0]), start=1
        ):
            for r in sorted(
                members, key=lambda r: (r.side, r.source, r.path)
            ):
                writer.writerow(
                    [gid, size, r.side, r.source, r.name, r.path]
                )
                rows += 1
    return rows


def write_potential_csv(
    groups: list[list[Record]], out_path: Path
) -> int:
    """Write potential-duplicate report. Returns number of data rows written."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    ordered = sorted(groups, key=lambda g: normalize_name(g[0].name))
    with _open_for_write(out_path) as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "group_id",
                "normalized_name",
                "size_bytes",
                "side",
                "source",
                "file_name",
                "file_path",
            ]
        )
        for gid, members in enumerate(ordered, start=1):
            norm = normalize_name(members[0].name)
            for r in sorted(
                members, key=lambda r: (r.side, r.size, r.path)
            ):
                writer.writerow(
                    [gid, norm, r.size, r.side, r.source, r.name, r.path]
                )
                rows += 1
    return rows
