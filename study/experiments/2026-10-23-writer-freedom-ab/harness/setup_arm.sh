#!/bin/zsh
set -e
ARM=$1
CODE=$2
BOOK=$3
CH=$4
GOAL=$5
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" story-system "$GOAL" --genre 悬疑 --chapter "$CH" --persist --emit-runtime-contracts --format both > "$BOOK/.webnovel/tmp/story_system_${CH}.out" 2>&1
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" write-gate --chapter "$CH" --stage prewrite > "$BOOK/.webnovel/tmp/write_gate_${CH}.json" 2>&1
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" runtime prepare --chapter "$CH" --format json > "$BOOK/.webnovel/tmp/runtime_prepare_${CH}.json" 2>&1
python3 -X utf8 "$CODE/scripts/webnovel.py" --project-root "$BOOK" runtime governed-context --chapter "$CH" --format json > "/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/gov_${ARM}_${CH}.json" 2>"/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/gov_${ARM}_${CH}.err"
