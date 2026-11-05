#!/bin/zsh
# usage: pack_r4.sh <chapter>
set -e
CH=$1
DIR=/Users/chang/Desktop/Code/zhanghui/.tmp/hf-ab/ch$CH/r4
python3 - "$CH" <<'PY'
import sys
from pathlib import Path
ch=sys.argv[1]
root=Path('/Users/chang/Desktop/Code/zhanghui/.tmp/hf-ab')
tmpl=(root/'r4_judge_template.md').read_text().replace('{CH}', ch)
task=(root/f'ch{ch}'/'judge_task.md').read_text()
(root/f'ch{ch}'/'r4'/'judge_packet_template.md').write_text(tmpl.replace('{TASK}', task.strip()), encoding='utf-8')
print('template ready', ch)
PY
cd "$DIR" && python3 -X utf8 /Users/chang/Desktop/Code/zhanghui/.tmp/hf-ab/make_blind.py --drafts /Users/chang/Desktop/Code/zhanghui/.tmp/hf-ab/ch$CH/drafts_r4 --out "$DIR" --template "$DIR/judge_packet_template.md" --seed $((20261026 + CH))
