---
name: feedback-never-delete-outputs
description: Never rm -rf or overwrite output folders without listing them first; processed results are valuable
metadata:
  node_type: memory
  type: feedback
  originSessionId: 4cf4b682-f1bb-4232-b1a4-c9ab87c30ad4
  modified: 2026-11-16T22:33:57.782Z
---

Do not delete or overwrite files in `outputs/` (or anywhere the user keeps processing results) without listing the folder and confirming first.

**Why:** In history-files-merge I ran `rm -rf outputs/txt` (plus reports/images) to re-run a script and wiped two processed txt files from an earlier round. The user said "you should not delete them, they are the processing result from previous round". The original `.doc` sources were temporarily missing, so the results could not be regenerated.

**How to apply:** Before any delete or overwrite, `ls` the target. Let scripts overwrite only the files they generate in that run, and make them refuse or skip existing files that are not their own. If a result becomes superseded (for example a txt whose page became an HTML report), list it and ask before removing. The user may also reorganise outputs (rename, move, merge, delete folders) between my turns, so re-list before assuming a file is still there. See [[history-files-merge-playbook]].
