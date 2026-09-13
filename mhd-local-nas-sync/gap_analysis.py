"""Compare macbook / NAS-YuData / 4TB-HD file lists and report backup gaps.

Usage:
    python gap_analysis.py
"""
import csv
import glob
import os
import re
from collections import defaultdict
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MACBOOK_DIR = os.path.join(BASE_DIR, "inputs", "macbook")
NAS_DIR = os.path.join(BASE_DIR, "inputs", "NAS-YuData")
HD_DIR = os.path.join(BASE_DIR, "inputs", "4TB-HD")
STATE_DIR = os.path.join(BASE_DIR, "state")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")

LINE_RE = re.compile(r"(\d+)\s*bytes\s+(.+)")
JUNK_FILENAMES = {".ds_store", "desktop.ini", "thumbs.db"}


class Record:
    __slots__ = ("size", "path", "filename", "norm_name")

    def __init__(self, size, path):
        self.size = size
        self.path = path
        self.filename = os.path.basename(path)
        self.norm_name = self.filename.strip().lower()

    @property
    def key(self):
        return (self.size, self.norm_name)


def parse_line(line):
    m = LINE_RE.search(line)
    if not m:
        return None
    size = int(m.group(1))
    path = m.group(2).strip()
    if not path:
        return None
    record = Record(size, path)
    if record.norm_name in JUNK_FILENAMES:
        return None
    return record


def load_dir(dir_path):
    records = []
    for txt_path in sorted(glob.glob(os.path.join(dir_path, "*.txt"))):
        with open(txt_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                record = parse_line(line)
                if record:
                    records.append(record)
    return records


def keys_of(records):
    return {r.key for r in records}


def first_path_by_key(records):
    result = {}
    for r in records:
        result.setdefault(r.key, r.path)
    return result


def gb(size_bytes):
    return round(size_bytes / 1024 ** 3, 2)


def load_rejected_ledger():
    path = os.path.join(STATE_DIR, "rejected_ledger.csv")
    keys = set()
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                keys.add((int(row["size_bytes"]), row["norm_name"]))
    return keys


def update_rejected_ledger(current_macbook_records, nas_keys):
    os.makedirs(STATE_DIR, exist_ok=True)
    snapshot_path = os.path.join(STATE_DIR, "macbook_snapshot.csv")
    ledger_path = os.path.join(STATE_DIR, "rejected_ledger.csv")

    current_keys = keys_of(current_macbook_records)
    current_paths = first_path_by_key(current_macbook_records)

    newly_rejected = []
    if os.path.exists(snapshot_path):
        with open(snapshot_path, newline="", encoding="utf-8") as f:
            prev_rows = list(csv.DictReader(f))
        prev_keys = {(int(row["size_bytes"]), row["norm_name"]) for row in prev_rows}
        prev_paths = {(int(row["size_bytes"]), row["norm_name"]): row["path"] for row in prev_rows}
        disappeared = prev_keys - current_keys
        existing_ledger_keys = load_rejected_ledger()
        for key in disappeared - nas_keys - existing_ledger_keys:
            newly_rejected.append((key[0], key[1], prev_paths[key], date.today().isoformat()))

    if newly_rejected:
        write_header = not os.path.exists(ledger_path)
        with open(ledger_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["size_bytes", "norm_name", "last_known_path", "rejected_on"])
            writer.writerows(newly_rejected)

    with open(snapshot_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["size_bytes", "norm_name", "path"])
        for key, path in current_paths.items():
            writer.writerow([key[0], key[1], path])

    return len(newly_rejected)


def write_path_list(out_path, keys, path_by_key):
    with open(out_path, "w", encoding="utf-8-sig") as f:
        for key in sorted(keys):
            f.write(path_by_key[key] + "\n")


def suspected_renames(label_a, unmatched_a, label_b, unmatched_b):
    by_size_b = defaultdict(list)
    for r in unmatched_b:
        by_size_b[r.size].append(r)

    pairs = []
    for r in unmatched_a:
        for candidate in by_size_b.get(r.size, []):
            pairs.append((label_a, r.path, label_b, candidate.path, r.size))
    return pairs


def main():
    macbook_records = load_dir(MACBOOK_DIR)
    nas_records = load_dir(NAS_DIR)
    hd_records = load_dir(HD_DIR)

    macbook_keys = keys_of(macbook_records)
    nas_keys = keys_of(nas_records)
    hd_keys = keys_of(hd_records)

    hd_paths = first_path_by_key(hd_records)
    macbook_paths = first_path_by_key(macbook_records)

    rejected_added = update_rejected_ledger(macbook_records, nas_keys)
    rejected_keys = load_rejected_ledger()

    b_macbook_not_in_nas = macbook_keys - nas_keys
    c_already_backed_up = hd_keys & nas_keys
    pending_4tb = hd_keys - macbook_keys - nas_keys - rejected_keys

    today = date.today().isoformat()
    run_dir = os.path.join(OUTPUTS_DIR, f"{today}-gap-analysis")
    os.makedirs(run_dir, exist_ok=True)

    write_path_list(os.path.join(run_dir, "4tb_pending.txt"), pending_4tb, hd_paths)
    write_path_list(os.path.join(run_dir, "macbook_pending_upload.txt"), b_macbook_not_in_nas, macbook_paths)
    write_path_list(os.path.join(run_dir, "already_backed_up.txt"), c_already_backed_up, hd_paths)

    rename_pairs = []
    hd_unmatched = [r for r in hd_records if r.key not in macbook_keys]
    macbook_unmatched_vs_hd = [r for r in macbook_records if r.key not in hd_keys]
    rename_pairs += suspected_renames("4TB-HD", hd_unmatched, "macbook", macbook_unmatched_vs_hd)

    hd_unmatched_vs_nas = [r for r in hd_records if r.key not in nas_keys]
    nas_unmatched_vs_hd = [r for r in nas_records if r.key not in hd_keys]
    rename_pairs += suspected_renames("4TB-HD", hd_unmatched_vs_nas, "NAS-YuData", nas_unmatched_vs_hd)

    macbook_unmatched_vs_nas = [r for r in macbook_records if r.key not in nas_keys]
    nas_unmatched_vs_macbook = [r for r in nas_records if r.key not in macbook_keys]
    rename_pairs += suspected_renames("macbook", macbook_unmatched_vs_nas, "NAS-YuData", nas_unmatched_vs_macbook)

    with open(os.path.join(run_dir, "suspected_renames.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["source_a", "path_a", "source_b", "path_b", "size_bytes"])
        writer.writerows(rename_pairs)

    summary_rows = [
        ("4tb_pending (真正待处理，需复制到暂存区)", len(pending_4tb), gb(sum(k[0] for k in pending_4tb))),
        ("macbook_pending_upload (待上传到NAS)", len(b_macbook_not_in_nas), gb(sum(k[0] for k in b_macbook_not_in_nas))),
        ("already_backed_up (4TB已在NAS，无需处理)", len(c_already_backed_up), gb(sum(k[0] for k in c_already_backed_up))),
        ("suspected_renames (疑似改名/移动，待人工确认)", len(rename_pairs), gb(sum(p[4] for p in rename_pairs))),
        ("rejected_ledger_new_entries (本次新记录的淘汰文件)", rejected_added, ""),
    ]
    with open(os.path.join(run_dir, "summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "file_count", "total_size_gb"])
        writer.writerows(summary_rows)

    print(f"Done. Report written to {run_dir}")
    for row in summary_rows:
        print(f"  {row[0]}: {row[1]} files, {row[2]} GB")


if __name__ == "__main__":
    main()
