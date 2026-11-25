#!/bin/zsh
# Extract + process the unique 141 zips. Skips byte-identical copies (md5 checked 2026-11-24):
#   141-all==Report_141_II, a141==Report_141_VI, Report_141_V==y141  -> keep Report_141_II/VI/V names out, process 141-all, a141, y141? (see SKIP)
SP=${1:?scratch dir}
SKIP=(Report_141_II Report_141_VI y141 141_html_01)
cd /Users/hany/Documents/cc.self/hy.cc.toolbox.files/history-files-merge
source venv/bin/activate
for z in inputs/*.zip; do
  n=$(basename "$z" .zip)
  (( ${SKIP[(Ie)$n]} )) && { echo "skip $n"; continue; }
  [ -d outputs/$n ] && { echo "exists $n"; continue; }
  echo "== $n $(date +%T)"
  python3 -I session_tools_2026.11.19/extract_zip.py "$z" "$SP/ex/$n" | tail -1 || continue
  python process_html_posts.py "$SP/ex/$n" -o outputs/$n | tail -1
  python add_summary_output.py outputs/$n 2>&1 | tail -1
done
echo BATCH_DONE
