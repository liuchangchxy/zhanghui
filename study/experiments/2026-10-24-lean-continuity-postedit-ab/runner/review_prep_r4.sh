#!/bin/zsh
# usage: review_prep_r4.sh <chapter> <draft_file>
set -e
CH=$1; DRAFT=$2
CODE=/Users/chang/Desktop/Code/zhanghui/.claude/plugins/zhanghui
BOOK=/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/book_B
OUT=/Users/chang/Desktop/Code/zhanghui/.tmp/hf-ab/ch$CH/r4
PAD=$(printf "%04d" $CH)
cp "$DRAFT" "$BOOK/.webnovel/tmp/chapter_${PAD}_working.md"
FP=$(python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" runtime status --chapter "$CH" --format json | python3 -c 'import sys,json;print(json.load(sys.stdin)["package_fingerprint"])')
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" runtime ingest-draft --chapter "$CH" --package-fingerprint "$FP" --draft-file "$BOOK/.webnovel/tmp/chapter_${PAD}_working.md" --format json > "$OUT/ingest_B.json"
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" runtime reviewer-context --chapter "$CH" --format json > "$OUT/reviewer_context_B.json"
python3 - "$OUT" <<'PY'
import json,sys
from pathlib import Path
out=Path(sys.argv[1])
d=json.loads((out/'ingest_B.json').read_text())
print(json.dumps({k:d.get(k) for k in ('ok','draft_id','draft_fingerprint','review_subject_fingerprint','status')},ensure_ascii=False))
PY
