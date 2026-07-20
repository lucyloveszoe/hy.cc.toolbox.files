"""dup_common_v2.py — shared v2 core for local-dup-match-v2.py,
cross-dup-match-v2.py, and 4tb-prune-v2.py.

Adds a three-tier, mutually-exclusive ("waterfall") duplicate
classification on top of dup_common.py's Record/parsing/normalize
building blocks:

* **exact**     — same byte size AND fuzzy-matched (normalized) name
* **almost**    — same byte size only (not already claimed by exact)
* **potential** — fuzzy-matched name only, size may differ (not already
                  claimed by exact or almost)

A record is claimed by at most one tier — see find_tiered_duplicates().

Also adds remove_catalog_entries(), used by 4tb-prune-v2.py to delete
specific ``<size> bytes <path>`` lines from a Linux-format catalog file
(a ``.bak`` copy is written alongside before the first rewrite).

Workspace rules
---------------
* All string comparisons are lowercase + whitespace stripped.
* Numeric ratios are rounded to two decimals.
"""

from __future__ import annotations

import csv
import difflib
from collections import defaultdict
from pathlib import Path
from typing import Callable

from dup_common import (
    Record,
    SIMILARITY_THRESHOLD,
    _LINUX_LINE_RE,
    _detect_text_encoding,
    _open_for_write,
    is_too_generic,
    normalize_name,
)


def _build_name_clusters(
    records: list[Record], enable_fuzzy: bool
) -> list[list[Record]]:
    """Group records whose normalized basenames match, regardless of size.

    Pass 1 — exact bucket on the normalized basename.
    Pass 2 (optional) — cluster remaining singletons via
        difflib.SequenceMatcher >= SIMILARITY_THRESHOLD.
    """
    buckets: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        norm = normalize_name(r.name)
        if is_too_generic(norm):
            continue
        buckets[norm].append(r)

    groups: list[list[Record]] = []
    leftover: list[Record] = []
    for members in buckets.values():
        if len(members) > 1:
            groups.append(members)
        else:
            leftover.append(members[0])

    if enable_fuzzy:
        used = [False] * len(leftover)
        for i in range(len(leftover)):
            if used[i]:
                continue
            name_i = normalize_name(leftover[i].name)
            cluster = [leftover[i]]
            for j in range(i + 1, len(leftover)):
                if used[j]:
                    continue
                name_j = normalize_name(leftover[j].name)
                longer = max(len(name_i), len(name_j))
                if longer and abs(len(name_i) - len(name_j)) > longer * 0.3:
                    continue
                ratio = round(
                    difflib.SequenceMatcher(None, name_i, name_j).ratio(), 2
                )
                if ratio >= SIMILARITY_THRESHOLD:
                    cluster.append(leftover[j])
                    used[j] = True
            if len(cluster) > 1:
                used[i] = True
                groups.append(cluster)

    return groups


def find_tiered_duplicates(
    records: list[Record],
    require_cross_side: bool = False,
    enable_fuzzy: bool = False,
) -> tuple[list[list[Record]], list[list[Record]], list[list[Record]]]:
    """Classify records into (exact, almost, potential) groups.

    Waterfall: a record claimed by ``exact`` cannot also appear in
    ``almost`` or ``potential``; a record claimed by ``almost`` cannot
    also appear in ``potential``.
    """
    name_clusters = _build_name_clusters(records, enable_fuzzy)

    claimed: set[int] = set()
    exact_groups: list[list[Record]] = []
    for cluster in name_clusters:
        by_size: dict[int, list[Record]] = defaultdict(list)
        for r in cluster:
            by_size[r.size].append(r)
        for members in by_size.values():
            if len(members) > 1:
                exact_groups.append(members)
                claimed.update(id(r) for r in members)

    remaining = [r for r in records if id(r) not in claimed]
    by_size_all: dict[int, list[Record]] = defaultdict(list)
    for r in remaining:
        by_size_all[r.size].append(r)
    almost_groups: list[list[Record]] = []
    for members in by_size_all.values():
        if len(members) > 1:
            almost_groups.append(members)
            claimed.update(id(r) for r in members)

    unclaimed_ids = {id(r) for r in records} - claimed
    potential_groups: list[list[Record]] = []
    for cluster in name_clusters:
        subset = [r for r in cluster if id(r) in unclaimed_ids]
        if len(subset) > 1:
            potential_groups.append(subset)

    def passes(group: list[Record]) -> bool:
        if require_cross_side and len({r.side for r in group}) < 2:
            return False
        return True

    return (
        [g for g in exact_groups if passes(g)],
        [g for g in almost_groups if passes(g)],
        [g for g in potential_groups if passes(g)],
    )


def write_tier_csv(
    groups: list[list[Record]],
    out_path: Path,
    group_sort_key: Callable[[list[Record]], object],
) -> int:
    """Write one tier's report. Shared schema across exact/almost/potential
    so the three CSVs can be compared or concatenated directly."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    ordered = sorted(groups, key=group_sort_key)
    with _open_for_write(out_path) as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "group_id",
                "size_bytes",
                "normalized_name",
                "side",
                "source",
                "file_name",
                "file_path",
            ]
        )
        for gid, members in enumerate(ordered, start=1):
            for r in sorted(
                members, key=lambda r: (r.side, r.source, r.path)
            ):
                writer.writerow(
                    [
                        gid,
                        r.size,
                        normalize_name(r.name),
                        r.side,
                        r.source,
                        r.name,
                        r.path,
                    ]
                )
                rows += 1
    return rows


def remove_catalog_entries(file: Path, targets: set[tuple[int, str]]) -> int:
    """Rewrite a Linux-format catalog ``file``, dropping every line whose
    parsed ``(size, path)`` is in ``targets``. Writes a ``.bak`` copy of
    the original alongside it (only if one doesn't already exist) before
    the first rewrite. Returns the number of lines removed."""
    if not targets:
        return 0
    encoding = _detect_text_encoding(file)
    with file.open(encoding=encoding, errors="replace") as fh:
        lines = fh.readlines()

    kept: list[str] = []
    removed = 0
    for raw in lines:
        line = raw.rstrip("\r\n")
        m = _LINUX_LINE_RE.match(line) if line.strip() else None
        if m and (int(m.group(1)), m.group(2)) in targets:
            removed += 1
            continue
        kept.append(raw)

    if removed:
        backup = file.with_suffix(file.suffix + ".bak")
        if not backup.exists():
            backup.write_bytes(file.read_bytes())
        with file.open("w", encoding=encoding, newline="") as fh:
            fh.writelines(kept)
    return removed
