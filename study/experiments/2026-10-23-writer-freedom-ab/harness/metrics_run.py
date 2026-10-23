#!/usr/bin/env python3
import sys, json
from pathlib import Path
sys.path.insert(0,'/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab')
import metrics
base=Path(sys.argv[1]); ch=sys.argv[2]
report={}
for arm in ('A','B'):
    p=base/f'draft_{arm}.md'
    text=p.read_text(encoding='utf-8')
    report[arm]={
      'hanzi':metrics.count_words(text),
      'paragraphs':len([x for x in text.split('\n\n') if x.strip()]),
      'dialogue_ratio':metrics.dialogue_ratio(text),
      'emotion_words':metrics.hits(text,metrics.EMOTION_WORDS),
      'body_templates':metrics.hits(text,metrics.BODY_TEMPLATES),
      'explain_markers':metrics.hits(text,metrics.EXPLAIN_MARKERS),
      'other_mind':metrics.hits(text,metrics.OTHER_MIND),
      'diagnose':metrics.diagnose(p),
    }
(base/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
