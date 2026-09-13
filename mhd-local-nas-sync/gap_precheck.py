"""Pre-check NAS-YuData and macbook lists for internal duplicates.

Runs before gap_analysis.py's 3-source cross-check. Checks each source
on its own:
  - confirmed duplicate: same (size, normalized filename) appears more than once
  - suspected duplicate: same size, different filename

Usage:
    python gap_precheck.py
"""
import csv
import os
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gap_analysis import MACBOOK_DIR, NAS_DIR, OUTPUTS_DIR, gb, load_dir

SOURCES = [
    ("NAS-YuData", NAS_DIR),
    ("macbook", MACBOOK_DIR),
]


def find_confirmed_duplicates(records):
    groups = defaultdict(list)
    for r in records:
        groups[r.key].append(r)
    return {key: recs for key, recs in groups.items() if len(recs) > 1}


def find_suspected_duplicates(records):
    by_size = defaultdict(list)
    for r in records:
        by_size[r.size].append(r)
    return {
        size: recs
        for size, recs in by_size.items()
        if len({r.norm_name for r in recs}) > 1
    }


def write_groups_csv(out_path, groups):
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["group_id", "size_bytes", "filename", "path"])
        for group_id, key in enumerate(sorted(groups), start=1):
            for r in groups[key]:
                writer.writerow([group_id, r.size, r.filename, r.path])


def main():
    today = date.today().isoformat()
    run_dir = os.path.join(OUTPUTS_DIR, f"{today}-precheck")
    os.makedirs(run_dir, exist_ok=True)

    summary_rows = []
    for label, dir_path in SOURCES:
        records = load_dir(dir_path)
        confirmed = find_confirmed_duplicates(records)
        suspected = find_suspected_duplicates(records)

        confirmed_files = sum(len(recs) for recs in confirmed.values())
        confirmed_redundant = confirmed_files - len(confirmed)
        confirmed_wasted_gb = gb(sum(key[0] * (len(recs) - 1) for key, recs in confirmed.items()))

        suspected_files = sum(len(recs) for recs in suspected.values())
        suspected_gb = gb(sum(size * len(recs) for size, recs in suspected.items()))

        write_groups_csv(os.path.join(run_dir, f"{label}_duplicates_confirmed.csv"), confirmed)
        write_groups_csv(os.path.join(run_dir, f"{label}_duplicates_suspected.csv"), suspected)

        summary_rows.append((f"{label}_confirmed (同名同size，确定重复)", len(confirmed), confirmed_files, confirmed_redundant, confirmed_wasted_gb))
        summary_rows.append((f"{label}_suspected (同size不同名，疑似重复)", len(suspected), suspected_files, "", suspected_gb))

    with open(os.path.join(run_dir, "summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "group_count", "file_count", "redundant_file_count", "total_size_gb"])
        writer.writerows(summary_rows)

    print(f"Done. Pre-check report written to {run_dir}")
    for row in summary_rows:
        print(f"  {row[0]}: {row[1]} groups, {row[2]} files, {row[4]} GB")


if __name__ == "__main__":
    main()
