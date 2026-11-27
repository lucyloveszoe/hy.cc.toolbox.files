#!/bin/zsh
# Extract every zip in inputs/ into <scratch>/ex/<zip> (section 16 name fix) and process it into outputs/<zip>.
# Usage: batch_extract_process.sh <scratch dir>     (run from anywhere; project path below)
SP=${1:?scratch dir}
cd "$(dirname "$0")/.."
source venv/bin/activate
for z in inputs/*.zip; do
  n=$(basename "$z" .zip)
  echo "== $n"
  python3 -I session_tools_2026.11.19/extract_zip.py "$z" "$SP/ex/$n" || continue
  python process_html_posts.py "$SP/ex/$n" -o outputs/$n
  python add_summary_output.py outputs/$n 2>&1 | tail -1
done
echo BATCH_DONE
