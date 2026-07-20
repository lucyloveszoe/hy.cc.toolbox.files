# 子项目 v2：Three-tier duplicate scan + 4TB catalog pruning

Extension of the v1 tool-box (documented in `CLAUDE.md`). Three new
scripts, one new shared module. **None of the 5 v1 scripts, `dup_common.py`,
or `CLAUDE.md` were modified** — this is purely additive.

All three v2 scripts assume their input folders contain **Linux-format
catalog dumps** (`<size> bytes <path>` lines, same as v1's `linux.nas` /
`linux.mac` folders) — not S3 listings, and not real folders scanned
directly from disk. If `local` / `nas` / `4tb` ever contain S3-format
catalogs instead, these scripts need a `parse_fn=parse_s3_catalog` swap
(not currently wired up).

## Key Decisions & Reasoning

Decisions made while scoping this extension, and why — kept here so the
"why" survives even after the code is forgotten:

1. **`local` / `nas` / `4tb` are catalog-dump folders, not real folders
   to scan.** `C:\tmp\files-list2` mirrors v1's `C:\tmp\files-list`
   convention (a root holding several catalog-folder siblings), and the
   user confirmed all three use the Linux `<size> bytes <path>` format —
   so these scripts always call `load_records(..., parse_fn=parse_linux_catalog)`
   (the default), never the S3 parser or `load_records_from_filesystem`.
2. **Three new scripts + one new shared module; zero edits to the 5 v1
   scripts, `dup_common.py`, or `CLAUDE.md`.** Explicit user choice, so
   v1 stays stable/production and v2 is purely additive — anyone can
   diff this whole feature by looking only at the new files.
3. **The three tiers are a mutually-exclusive "waterfall"**, not
   overlapping independent categories. Explicit user choice — it means
   concatenating `exact.csv` + `almost.csv` + `potential.csv` accounts
   for every grouped record exactly once, instead of the same file
   showing up in more than one report.
4. **4TB catalog-line removal is direct, no interactive dry-run step**
   — explicit user choice ("edit catalog .txt lines directly, no
   preview needed"). A `.bak` copy of each touched catalog file is
   still written before the first rewrite, as a low-cost, non-interactive
   safety net — this doesn't contradict "no preview," it's just cheap
   insurance in case a same-size-and-name match turns out to be a false
   positive.
5. **`4tb-prune-v2.py` also writes an audit CSV (`<prefix>-pruned.csv`)**
   that wasn't explicitly requested. Added because the script performs
   an in-place, destructive rewrite of the user's catalog files —
   an audit trail of exactly what was deleted from where felt necessary
   for a script that mutates files without a preview step. Flagging
   this addition here rather than silently scope-creeping it in.
6. **Output directory defaults to `C:\tmp\files-list2\outputs`** for
   all three v2 scripts (v1 scripts default `--output-dir` to `.`,
   the current directory). Changed because the request explicitly said
   "write into outputs/..." relative to the fixed default root, so
   hardcoding it there means the defaults just work without an extra
   flag on every run.

## What's new vs. v1

v1's `exact.csv` / `potential.csv` used two categories: same size, or
similar name with a *different* size. v2 adds a third, in-between
category and makes all three **mutually exclusive** (a "waterfall" — see
below) instead of computing size-match and name-match independently:

| Tier | Definition |
|------|------------|
| `exact` | same byte size **and** fuzzy-matched (normalized) name |
| `almost` | same byte size only — not already claimed by `exact` |
| `potential` | fuzzy-matched name only, size differs — not already claimed by `exact` or `almost` |

**Waterfall rule**: every record lands in at most one tier. `exact` is
computed first and claims its members; `almost` is computed from
whatever's left; `potential` gets the final leftovers. This keeps the
three CSVs non-overlapping — concatenating them reproduces every
grouped record exactly once. (v1's `exact.csv`/`potential.csv` have no
such rule since they're only two independent categories that can't
collide by construction: same size vs. different size.)

The name-matching logic itself (`normalize_name`, `is_too_generic`, the
optional `--fuzzy` `SequenceMatcher` pass) is unchanged from v1 — see
`CLAUDE.md` for the full stripping-pattern list and generic-name filter.

## How to Run

```powershell
cd files-crosscheck
.\venv\Scripts\Activate.ps1

# (1) Single folder, 3-tier scan — run once per folder
python local-dup-match-v2.py                                    # folder=local, prefix=local
python local-dup-match-v2.py C:\tmp\files-list2\nas --prefix nas # folder=nas,   prefix=nas

# (2) Cross-compare local vs nas, 3-tier scan, pairs only
python cross-dup-match-v2.py                                     # defaults: local vs nas -> loc2nas-*
python cross-dup-match-v2.py D:\a D:\b --prefix a2b

# (3) Cross-compare local vs 4tb, EXACT tier only, then prune 4tb's catalog lines
python 4tb-prune-v2.py                                           # defaults: local vs 4tb
python 4tb-prune-v2.py D:\local D:\4tb --prefix loc2tb
```

Default root for all three: `C:\tmp\files-list2`, with subfolders
`local\`, `nas\`, `4tb\` each holding one or more `*.txt` Linux-format
catalogs. Default `--output-dir` for all three: `C:\tmp\files-list2\outputs`.

## 功能要求

1. **`local-dup-match-v2.py`** — 3-tier duplicate scan inside **one**
   catalog folder (same script used for both `local` and `nas` — just
   change the `folder` argument and `--prefix`).
   - `folder` positional arg, default `C:\tmp\files-list2\local`.
   - `--prefix` default: the folder's own name (e.g. `local`, `nas`).
   - Writes `<prefix>-exact.csv`, `<prefix>-almost.csv`,
     `<prefix>-potential.csv`.
   - No cross-side requirement (single folder — groups can be within
     the same catalog file or across catalog files in that folder).

2. **`cross-dup-match-v2.py`** — 3-tier duplicate scan across **two**
   catalog folders. A group is reported only when its members span
   **both** folders (single-side matches are dropped, same convention
   as v1's `-cross` scripts).
   - `folder_a` / `folder_b` positional args, default `local` / `nas`.
   - `--prefix` default `loc2nas`.
   - Writes `<prefix>-exact.csv`, `<prefix>-almost.csv`,
     `<prefix>-potential.csv` — same schema as (1), but every row's
     `side` column shows which of the two folders it came from, so a
     group's two (or more) rows form the "pair".

3. **`4tb-prune-v2.py`** — cross-compare `local` vs `4tb`, but only
   *acts on* the **`exact`** tier (same size + fuzzy-matched name).
   - Positional args are `local_folder` / `tb4_folder` (default
     `local` / `4tb` under the root); side labels in every output row
     are the **hardcoded literals `"local"` and `"4tb"`**, not derived
     from the folder's actual name — unlike `cross-dup-match-v2.py`,
     which uses `folder.name`. Pass whatever paths you like; the report
     always calls them `local` and `4tb`.
   - For every exact-duplicate group: the `local`-side member(s) are
     left alone; every `4tb`-side member's line is **deleted** from its
     catalog `.txt` file (rewritten in place; a `<file>.txt.bak` backup
     of the original is written alongside it the first time that file
     is touched — never overwritten once it exists).
   - Writes one audit report, `<prefix>-pruned.csv` (default prefix
     `loc2tb`), with an `action` column (`kept` for local rows,
     `removed` for 4tb rows) so every deletion is traceable after the
     fact.
   - `find_tiered_duplicates()` still computes `almost` and `potential`
     internally (it always returns all three), but this script discards
     them (`_almost`, `_potential`) — they are never written or acted
     on. Only `exact` matches trigger a removal, since same size *and*
     same name is the strongest signal available without content hashes.

## Output CSV Schema

### `<prefix>-exact.csv` / `<prefix>-almost.csv` / `<prefix>-potential.csv`

Same 7-column schema across all three tiers (unlike v1, where
`exact.csv` and `potential.csv` had different columns):

| Column | Meaning |
|--------|---------|
| `group_id` | 1-based per file. `exact`/`almost` sorted by descending `size_bytes`; `potential` sorted alphabetically by `normalized_name` |
| `size_bytes` | Byte size of this entry |
| `normalized_name` | Output of `normalize_name(file_name)` (same normalization as v1) |
| `side` | Folder-level label (folder name; or `local`/`nas`/`4tb` for the cross scripts) |
| `source` | Catalog filename within that folder |
| `file_name` | Basename of the entry |
| `file_path` | Full path from the catalog line |

### `<prefix>-pruned.csv` (4tb-prune-v2.py only)

8 columns — same as above with one extra (`action`), inserted right
after `normalized_name`:

`group_id, size_bytes, normalized_name, action, side, source, file_name, file_path`

| Column | Meaning |
|--------|---------|
| `action` | `kept` (local side, catalog line untouched) or `removed` (4tb side, catalog line deleted) |

`group_id` here is 1-based sorted by descending `size_bytes` over the
`exact`-tier groups only (`almost`/`potential` never reach this report).

## Decision Logic — `find_tiered_duplicates` (`dup_common_v2.py`)

1. Build name-clusters exactly like v1's potential-duplicate pass
   (normalized-name bucket, plus optional `--fuzzy` `SequenceMatcher`
   pass for singletons) — but **without** v1's "must differ in size"
   filter, since here that filter is what separates `exact` from
   `potential`.
2. **exact**: within each name-cluster, sub-bucket by `size_bytes`; any
   sub-bucket with ≥ 2 members is an `exact` group. Claim those records.
3. **almost**: among records not claimed by step 2, bucket by
   `size_bytes` alone; any bucket with ≥ 2 members is an `almost` group.
   Claim those records.
4. **potential**: for each original name-cluster from step 1, keep only
   the members not claimed by steps 2–3; if ≥ 2 remain, that's a
   `potential` group.
5. `require_cross_side` (always `True` for the two cross scripts,
   always `False` for the single-folder script) drops any tier's group
   that doesn't span ≥ 2 distinct `side` values — applied as a final
   filter, same as v1's cross-side rule. Note: dropping a cross-side-
   failing group does **not** demote its records to a lower tier; they
   simply don't appear in any of the three reports for that run.

## Catalog Line Removal — `remove_catalog_entries` (`dup_common_v2.py`)

Used only by `4tb-prune-v2.py`. For a given catalog file and a set of
`(size, path)` targets:

1. Detects encoding the same way v1 does (`dup_common._detect_text_encoding`).
2. Re-parses the file line by line with the same Linux-format regex
   used for loading, and drops any line whose `(size, path)` is in the
   target set — matched by content, not line number, so it's safe even
   if the file has been re-sorted or re-generated between scans.
3. If anything was removed: writes `<file>.<ext>.bak` (only if that
   backup doesn't already exist) with the original bytes, then
   rewrites the catalog file with the matching lines dropped.
4. This only ever touches the `.txt` catalog file — never the actual
   file on the 4TB drive, and never `local`'s catalog.

## Restrictions (same spirit as v1)

- **Never touches real files.** All three v2 scripts, like v1's
  catalog-based scripts, only read and (for `4tb-prune-v2.py`) rewrite
  `.txt` catalog text — never the NAS, 4TB drive, or any cloud storage.
- **Same byte size + fuzzy name is still a heuristic, not a verdict.**
  `4tb-prune-v2.py` deletes catalog lines based on this heuristic with
  no content hash to confirm — treat the `.bak` files as your undo
  path if a match turns out to be a false positive.
- **Catalog file format must be Linux-style.** These scripts default to
  `parse_linux_catalog` for every folder; an S3-format catalog folder
  would need code changes to use here.

## Exit Codes

Same as v1: `0` success, `2` bad folder argument / folders equal,
`3` output CSV locked by another process (e.g. Excel).
