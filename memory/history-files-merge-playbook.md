---
name: history-files-merge-playbook
description: "Where the processing rules for the history-files-merge data sets are documented, the layout the user wants, and lessons from three data sets"
metadata:
  node_type: memory
  type: project
  originSessionId: 4cf4b682-f1bb-4232-b1a4-c9ab87c30ad4
  modified: 2026-11-16T22:34:01.720Z
---

The full processing logic for the `history-files-merge` tool (`.doc` and saved-web-page clean-up, outputs layout, verification checklist, script gaps) is in `history-files-merge/PROCESSING_RULES.md`. The user plans to process other data sets the same way, so read it first.

Layout the user chose: `outputs/txt`, `outputs/reports` (HTML linking to images), `outputs/images` (only images referenced by a report, flat), `outputs/images.only` (images no report uses), plus summary and manifest CSVs.

**Why:** Written down at the end of the first data set (`inputs/2008_10_17_sss.Report`, finished 2026-11-16). `DOC_PROCESSING_RULES.md` in the same folder is the older, superseded version.

**How to apply:** For a new data set, follow PROCESSING_RULES.md sections 3–6 and check the script-gap table in section 7 (some steps were done by hand). Pair this with [[feedback-never-delete-outputs]].

**Second data set (2026-11-16, `hk9394`, `mcjt`, `Peep`, `russian`):** done and recorded in PROCESSING_RULES.md section 10. User decisions: `hk9394` and `Peep` are both reports (user wanted title/author context kept; I had wrongly called them image-only) (don't judge "image-only" from the absence of `pid` tables, inspect the text first); reports carry an `[image missing]` marker for unsaved images. Superseded duplicates in `images.only/Peep` and `images.only/hk9394` were deleted with the user's OK (hash-checked first). Nothing pending.

**Third data set (2026-11-16, 19 loose `.doc` files + `txt.done` clean-up):** recorded in PROCESSING_RULES.md sections 3.A, 4.1, 11. Lessons to apply next time:
- `.doc` noise differs per file (spaced garbage, spam phrases like `军团,招财进宝…`, `bbs.maichun.org` + garbage, compact garbage). Scan each file before choosing rules; do not assume the maichun watermark.
- Image check: textutil's html `<img>` count misses Word `INCLUDEPICTURE` pictures. They are embedded in the binary; carve them (`carve_doc_images.py`, `FFD8FF`/`89PNG`/`GIF8`) into `outputs/images/<stem>/` and link relatively. Remote URLs are dead.
- Text-only `.doc` -> `outputs/txt` (`doc_to_txt.py`); with images -> `outputs/reports/*.html` (`doc_to_html.py`). Skip `~$*.doc` lock files.
- Merged txt files: manifest per file (`<stem>.manifest.csv`: no, title, start/end line, chars). Split posts on the forum header (`title` line followed by `作者: xxx`) plus `【买春地址】`-style fields; inside author-marked posts do not split on fields (duplicate titles, `一/二/三` sections).
- Series (same author, numbered titles) go to `txt.done/series/<series>.txt` + `<series>.manifest.csv`, and the range is removed from the source txt only after a line-by-line equality check and a duplicate scan. User said no need to keep the pre-removal backup.


**Fourth data set (2026-11-16, `FZForum`, `maichun`, `Wet168`):** recorded in PROCESSING_RULES.md sections 3.B, 4.2, 5.1, 5.2, 12. Lessons: audit `images.only/` against source pages (avatars excluded) because renamed-folder duplicates, broken-name files and `font-size:0` image wrappers hide real post images; loose `.txt` may be GBK (convert to UTF-8); per-folder merge keeps originals and writes `<folder>/<folder>.txt` + manifest.

**2026-11-18 session (mcu, report-folder merges, txt routing, 2010_07 de-dup):** recorded in PROCESSING_RULES.md sections 22–26. Key lessons: merge report folders by dry run (exact / near / new), compare near copies against the target only, check sibling folders before copying (a report moved earlier was re-added once), copy then delete the source only on request after a text+byte check; de-dup via a scratchpad quarantine; when the answer follows from the rules, state the default and proceed (the user rejected two multiple-choice prompts and wanted the next instruction followed). See [[feedback-never-delete-outputs]].

**2026-11-18/19 later work (audits, near-duplicates, txt library, loose images):** PROCESSING_RULES.md sections 27-38 and the project scripts `merge_report_folders.py` (audit/near/dedupe/merge/remove-source/repoint/fix-fake), `audit_txt_library.py`, `dedupe_loose_images.py`. Section 38 lists current data locations, the final audit numbers and the open items (70 near pairs kept on purpose, 5 category-vs-locations duplicate stories, 98 shared-picture groups). Habits that held: dry run first, quarantine instead of delete, byte-check before any delete, re-scan every CSV after any move or rename, state the default and proceed when the rules decide, ask only on a real choice. All scratchpad backups were deleted on request. See [[feedback-never-delete-outputs]].

**2026-11-19 GoChina zips (24 zips, saved forum pages):** PROCESSING_RULES.md section 39. Per zip: extract to scratchpad, `process_html_posts.py` into `outputs/<zip>/`, `add_summary_output.py`, audit; then consolidate into `outputs/GoChina.consolidated` and `dedupe` (quarantine). Seven new layout adapters were added; first run without them left 198 pages unsupported, so run one zip first, fix adapters, then re-run all. 4 duplicate groups held for the user (images differ in bytes). See [[feedback-never-delete-outputs]].

**2026-11-19 finishing the GoChina library in `~/Downloads/data.done`:** PROCESSING_RULES.md section 40. Base-vs-source de-dup (hash/normalized text + `cmp` before delete), golden txt + manifest, golden image folder, reports sync by signature (text md5 + image hash sequence), near-duplicates with identical images = label differences, flat layout B (`<set>_summary.csv`, `<set>_images_manifest.csv`, `<set>/`, `<set>/images/<set>/`, names `<folder>__<name>`). Key traps: write `src` raw with html.escape, never percent-encoded (the audit does not unquote); sharing identical images breaks `images_copied` (recount); the user moves files between steps, so re-list state first; never `find /`. See [[feedback-never-delete-outputs]].
