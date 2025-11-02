import os, json
exts={'.py','.js','.jsx','.ts','.tsx','.go','.java','.rb','.php','.html','.css','.scss'}
exclude_dirs=('node_modules','dist','build','.next','out','vendor','__pycache__','.pytest_cache','.git')
exclude_files=('package-lock.json','yarn.lock','pnpm-lock.yaml')
res=[]
for root,dirs,files in os.walk('.'):
    parts=[p for p in root.split(os.sep) if p]
    if any(d in parts for d in exclude_dirs):
        continue
    for f in files:
        if f in exclude_files: continue
        if '.min.' in f: continue
        _,e=os.path.splitext(f)
        if e.lower() not in exts: continue
        path=os.path.join(root,f)
        try:
            with open(path,'r',encoding='utf-8',errors='ignore') as fh:
                lines=sum(1 for _ in fh)
        except Exception:
            continue
        res.append({'lines':lines,'path':path.replace('\\','/')})
res=[r for r in res if r['lines']>=500]
res.sort(key=lambda x: x['lines'],reverse=True)
with open('.assistant_line_counts.json','w',encoding='utf-8') as fh:
    json.dump(res,fh,indent=2)
print(json.dumps(res))
