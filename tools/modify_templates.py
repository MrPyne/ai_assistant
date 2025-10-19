import json,glob,os
ROOT='backend/templates'
files=glob.glob(os.path.join(ROOT,'*.json'))
modified=[]
for fp in files:
    with open(fp,'r',encoding='utf-8') as f:
        try:
            data=json.load(f)
        except Exception as e:
            print('skip',fp,'err',e)
            continue
    changed=False
    graph=data.get('graph')
    if not isinstance(graph,dict):
        continue
    nodes=graph.get('nodes',[])
    for n in nodes:
        t=n.get('type')
        d=n.setdefault('data',{})
        cfg=d.get('config',{}) or {}
        label=d.get('label','')
        # Normalize split/batch action -> SplitInBatches node type
        if t=='action':
            if (label and 'split' in label.lower()) or isinstance(cfg,dict) and (cfg.get('batch_size') or cfg.get('input_path')):
                if n.get('type')!='SplitInBatches':
                    n['type']='SplitInBatches'
                    # ensure config exists
                    n['data']['config']=cfg
                    changed=True
            else:
                # map generic action to http worker call
                newcfg={'method':'POST','url':'https://internal.api/worker/execute','headers':{'Content-Type':'application/json'},'body':{}}
                if isinstance(cfg,dict):
                    if cfg.get('language') or 'code' in cfg or 'template' in cfg:
                        newcfg['body']={'language':cfg.get('language'),'code':cfg.get('code'),'template':cfg.get('template'),'original_config':cfg}
                    else:
                        newcfg['body']={'task': label or 'action', 'original_config': cfg}
                else:
                    newcfg['body']={'task': label or 'action', 'original_config': cfg}
                n['type']='http'
                n['data']['config']=newcfg
                changed=True
        elif t=='email':
            # convert email node to http calling mail API placeholder
            newcfg={'method':'POST','url':'https://example.mail/send','headers':{'Content-Type':'application/json'},'body':{}}
            if isinstance(cfg,dict):
                newcfg['body']={'to':cfg.get('to'),'subject':cfg.get('subject'),'body':cfg.get('body'),'original_config':cfg}
            else:
                newcfg['body']={'original_config':cfg}
            n['type']='http'
            n['data']['config']=newcfg
            changed=True
        elif t=='llm':
            # ensure prompt-like keys exist
            if isinstance(cfg,dict):
                if not (cfg.get('prompt') or cfg.get('prompt_template') or (cfg.get('model') and cfg.get('prompt'))):
                    # set a safe default prompt preserving prior config
                    cfg['prompt']=cfg.get('prompt') or cfg.get('prompt_template') or 'Provide a concise response based on: {{ input }}'
                    n['data']['config']=cfg
                    changed=True
            else:
                n['data']['config']={'prompt':'Provide a concise response based on: {{ input }}'}
                changed=True
    if changed:
        with open(fp,'w',encoding='utf-8') as f:
            json.dump(data,f,indent=2,ensure_ascii=False)
        modified.append(fp)
print('modified',len(modified),'files')
for m in modified:
    print(m)
