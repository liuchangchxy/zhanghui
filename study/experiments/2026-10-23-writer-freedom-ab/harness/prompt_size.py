#!/usr/bin/env python3
import re,sys
from pathlib import Path
for f in sys.argv[1:]:
    p=Path(f).read_text()
    print('==',Path(f).name,len(p))
    for part in re.split(r'\n(?=## )',p):
        print('  ',len(part),part.splitlines()[0][:44])
