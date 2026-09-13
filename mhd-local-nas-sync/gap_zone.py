"""Cross-check file lists across zone-* folders under inputs/zones/.

Same compare logic as gap_analysis.py's pairwise diff (size + normalized
filename), applied to every pair of zone folders found, instead of the
fixed macbook/NAS/4TB-HD sources.

Usage:
    python gap_zone.py
"""
import csv
import glob
import itertools
import os
from datetime import date

from gap_analysis import (
    BASE_DIR,
    OUTPUTS_DIR,
    first_path_by_key,
    gb,
    keys_of,
    load_dir,
    suspected_renames,
    write_path_list,
)

ZONES_DIR = os.path.join(BASE_DIR, "inputs", "zones")


def discover_zones():
    return sorted(d for d in glob.glob(os.path.join(ZONES_DIR, "*")) if os.path.isdir(d))


def main():
    zone_dirs = discover_zones()
    if len(zone_dirs) < 2:
        print(f"Need at least 2 zone folders under {ZONES_DIR}, found {len(zone_dirs)}.")
        return

    zones = {os.path.basename(d): load_dir(d) for d in zone_dirs}

    today = date.today().isoformat()
    run_dir = os.path.join(OUTPUTS_DIR, f"{today}-zone-gap")
    os.makedirs(run_dir, exist_ok=True)

    summary_rows = []
    for name_a, name_b in itertools.combinations(sorted(zones), 2):
        records_a, records_b = zones[name_a], zones[name_b]
        keys_a, keys_b = keys_of(records_a), keys_of(records_b)
        paths_a, paths_b = first_path_by_key(records_a), first_path_by_key(records_b)

        only_a = keys_a - keys_b
        only_b = keys_b - keys_a
        in_both = keys_a & keys_b

        pair_prefix = f"{name_a}_vs_{name_b}"
        write_path_list(os.path.join(run_dir, f"{pair_prefix}_only_in_{name_a}.txt"), only_a, paths_a)
        write_path_list(os.path.join(run_dir, f"{pair_prefix}_only_in_{name_b}.txt"), only_b, paths_b)
        write_path_list(os.path.join(run_dir, f"{pair_prefix}_in_both.txt"), in_both, paths_a)

        unmatched_a = [r for r in records_a if r.key not in keys_b]
        unmatched_b = [r for r in records_b if r.key not in keys_a]
        rename_pairs = suspected_renames(name_a, unmatched_a, name_b, unmatched_b)

        with open(os.path.join(run_dir, f"{pair_prefix}_suspected_renames.csv"), "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["source_a", "path_a", "source_b", "path_b", "size_bytes"])
            writer.writerows(rename_pairs)

        summary_rows.append((f"{pair_prefix}_only_in_{name_a}", len(only_a), gb(sum(k[0] for k in only_a))))
        summary_rows.append((f"{pair_prefix}_only_in_{name_b}", len(only_b), gb(sum(k[0] for k in only_b))))
        summary_rows.append((f"{pair_prefix}_in_both", len(in_both), gb(sum(k[0] for k in in_both))))
        summary_rows.append((f"{pair_prefix}_suspected_renames", len(rename_pairs), gb(sum(p[4] for p in rename_pairs))))

    with open(os.path.join(run_dir, "summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "file_count", "total_size_gb"])
        writer.writerows(summary_rows)

    print(f"Done. Zone gap report written to {run_dir}")
    for row in summary_rows:
        print(f"  {row[0]}: {row[1]} files, {row[2]} GB")


if __name__ == "__main__":
    main()
