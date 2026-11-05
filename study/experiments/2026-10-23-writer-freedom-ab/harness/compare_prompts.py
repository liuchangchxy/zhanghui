#!/usr/bin/env python3
"""Quantify what the two Writer prompts actually differ in."""
import re, sys, json
from pathlib import Path

def sections(text):
    out=[]
    for part in re.split(r'\n(?=## )', text):
        out.append((part.splitlines()[0][:40], len(part)))
    return out

def facts(text):
    """Pull the distinctive tokens that must survive in both arms."""
    probes = ['2016年3月17日','临潮07','TX-2015','TX-2015-086','市海事局','《临港市志》',
              '旧报库','地方志办公室','差异说明','清点单','钥匙交接册','梁沐','老周','郑培']
    return {p: p in text for p in probes}

def stats(text):
    return {
        'chars': len(text),
        'raw_json_event_lines': sum(len(l)+1 for l in text.splitlines() if l.startswith('- {"')),
        'path_dump_lines': sum(len(l)+1 for l in text.splitlines() if 'story_craft.' in l),
        'cbn_labels': sum(text.count(t) for t in ('CBN','CPNs','CEN')),
        'progress_obligation': text.count('Progress Obligation'),
        'scene_four_q': text.count('【场景设计四问】'),
        'reader_three_q': text.count('【追读设计三问】'),
    }

ch = sys.argv[1]
d = Path(f'/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/ch{ch}')
a = (d/'prompt_A.txt').read_text(); b = (d/'prompt_B.txt').read_text()
rep = {'chapter': ch, 'A': stats(a), 'B': stats(b),
       'sections_A': sections(a), 'sections_B': sections(b),
       'facts_A': facts(a), 'facts_B': facts(b)}
(d/'prompt_compare.json').write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: rep[k] for k in ('chapter','A','B')}, ensure_ascii=False, indent=2))
missing = [k for k,v in rep['facts_B'].items() if v is False]
print('facts missing in B:', missing)
