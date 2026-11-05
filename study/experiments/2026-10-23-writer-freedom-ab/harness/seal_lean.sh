#!/bin/zsh
set -e
CH=$1; BRIEF=$2; SKILLS=$3; OUT=$4
CODE=/Users/chang/Desktop/Code/zhanghui/.claude/plugins/zhanghui
BOOK=/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/book_B
ARGS=(--chapter "$CH" --brief-file "$BRIEF" --scene-design --reader-pull --lean-input --format prompt)
[ "$SKILLS" != "EMPTY" ] && ARGS+=(--skills-file "$SKILLS")
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" runtime attach-creative-brief "${ARGS[@]}" > "$OUT"
echo "sealed B ch$CH -> $OUT ($(wc -c < "$OUT") bytes)"
