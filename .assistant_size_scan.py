import os
import json

entries=[]
for root,dirs,files in os.walk('.'):
    # skip .git and node_modules and __pycache__
    if any(part in ('.git','node_modules') for part in root.split(os.sep)):
        continue
    for f in files:
        p=os.path.join(root,f)
        try:
            s=os.path.getsize(p)
        except Exception:
            s=0
        entries.append((s,p))
entries.sort(reverse=True)
# print top 40
for s,p in entries[:40]:
    print(f"{s}\t{p}")

# also output JSON for parsing
with open('.assistant_size_scan.json','w',encoding='utf-8') as fh:
    json.dump([{'size':s,'path':p} for s,p in entries],fh)
print('\nWROTE .assistant_size_scan.json')
