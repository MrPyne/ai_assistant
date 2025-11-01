import os, json
excluded_dirs={'.git','venv','env','.venv','node_modules','build','dist','__pycache__'}
root='.'
result={}
for dirpath,dirnames,filenames in os.walk(root):
    if any(p in excluded_dirs for p in dirpath.split(os.sep)):
        continue
    for fn in filenames:
        if not fn.endswith('.py'):
            continue
        fp=os.path.join(dirpath,fn)
        try:
            with open(fp,'rb') as f:
                data=f.read().splitlines()
            total=len(data)
        except Exception as e:
            total=None
        result[fp]=total
out=sorted(result.items(), key=lambda x:(-(x[1] or 0), x[0]))
print(json.dumps(out))
