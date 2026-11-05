#!/bin/zsh
# usage: pack.sh <chapter>
set -e
CH=$1
DIR=/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/ch$CH
python3 - "$CH" <<'PY'
import sys, json
from pathlib import Path
ch=sys.argv[1]
dir=Path(f'/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/ch{ch}')
tmpl=Path('/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/judge_template.md').read_text().replace('{CH}', ch)
task=Path(dir/'judge_task.md').read_text()
tmpl=tmpl.replace('{TASK}', task.strip())
(dir/'judge_packet_template.md').write_text(tmpl, encoding='utf-8')
print('template ready', ch)
PY
cd "$DIR" && python3 -X utf8 /Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/make_blind.py --drafts drafts --out . --template judge_packet_template.md --seed $((20261023 + CH))
