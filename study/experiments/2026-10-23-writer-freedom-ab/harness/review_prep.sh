#!/bin/zsh
# usage: review_prep.sh <A|B> <chapter> <draft_file>
set -e
ARM=$1; CH=$2; DRAFT=$3
if [ "$ARM" = "A" ]; then CODE=/Users/chang/Desktop/Code/zhanghui/.worktrees/wf-code-A/.claude/plugins/zhanghui; BOOK=/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/book_A
else CODE=/Users/chang/Desktop/Code/zhanghui/.claude/plugins/zhanghui; BOOK=/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/book_B; fi
OUT=/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/ch$CH
FP=$(python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" runtime status --chapter "$CH" --format json | python3 -c 'import sys,json;print(json.load(sys.stdin)["package_fingerprint"])')
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" runtime ingest-draft --chapter "$CH" --package-fingerprint "$FP" --draft-file "$DRAFT" --format json > "$OUT/ingest_$ARM.json"
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" runtime reviewer-context --chapter "$CH" --format json > "$OUT/reviewer_context_$ARM.json"
echo "prepared $ARM ch$CH"
