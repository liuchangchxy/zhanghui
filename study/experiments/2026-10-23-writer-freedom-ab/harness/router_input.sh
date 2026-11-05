#!/bin/zsh
# usage: router_input.sh <A|B> <chapter> <brief_file> <out_json>
set -e
ARM=$1; CH=$2; BRIEF=$3; OUT=$4
if [ "$ARM" = "A" ]; then CODE=/Users/chang/Desktop/Code/zhanghui/.worktrees/wf-code-A/.claude/plugins/zhanghui; BOOK=/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/book_A
else CODE=/Users/chang/Desktop/Code/zhanghui/.claude/plugins/zhanghui; BOOK=/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/book_B; fi
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" writing-skills input --chapter "$CH" --brief-file "$BRIEF" --format json > "$OUT"
echo "input $ARM ch$CH -> $OUT"
