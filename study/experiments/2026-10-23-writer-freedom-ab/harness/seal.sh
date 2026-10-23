#!/bin/zsh
# usage: seal.sh <A|B> <chapter> <brief_file> <skills_file_or_EMPTY> <out_prompt>
set -e
ARM=$1; CH=$2; BRIEF=$3; SKILLS=$4; OUT=$5
if [ "$ARM" = "A" ]; then
  CODE=/Users/chang/Desktop/Code/zhanghui/.worktrees/wf-code-A/.claude/plugins/zhanghui
  BOOK=/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/book_A
  EXTRA=""
else
  CODE=/Users/chang/Desktop/Code/zhanghui/.claude/plugins/zhanghui
  BOOK=/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/book_B
  EXTRA="--lean-input"
fi
ARGS=(--chapter "$CH" --brief-file "$BRIEF" --scene-design --reader-pull --format prompt)
[ "$SKILLS" != "EMPTY" ] && ARGS+=(--skills-file "$SKILLS")
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" runtime attach-creative-brief "${ARGS[@]}" $EXTRA > "$OUT"
echo "sealed $ARM ch$CH -> $OUT ($(wc -c < "$OUT") bytes)"
