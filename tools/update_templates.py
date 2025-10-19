"""Script to apply deterministic safety edits to backend/templates JSON files.

Rules implemented (per developer memory):
- Convert 'action' nodes that contain inline code/template (have 'language' and 'code' or 'template') -> type 'transform'. Preserve original config in data.config.body.original_config.
- Convert generic split-like nodes (label contains 'SplitInBatches' or config has 'batch_size' and 'input_path') to type 'SplitInBatches' and preserve original config in data.config.body.original_config.
- Convert 'email' nodes -> 'http' nodes that POST to https://example.com/placeholder. Put original email config under data.config.body.original_config.
- For LLM nodes missing a user-visible 'prompt' (no 'prompt' key) or using 'prompt_template', add minimal safe prompt "You are a helpful assistant. Answer concisely." and store original config under data.config.body.original_config.
- For http nodes with a concrete absolute URL (contains 'https://' and does NOT contain '{{') or lacking 'url', set url to https://example.com/placeholder and preserve original config under data.config.body.original_config.

The script edits files in-place and prints filenames changed.
"""
import json
from pathlib import Path

TEMPLATES_DIR = Path('backend/templates')
PLACEHOLDER = 'https://example.com/placeholder'
SAFE_PROMPT = 'You are a helpful assistant. Answer concisely.'

changed_files = []

def preserve_original_config(cfg):
    # returns a body dict with original_config copy
    return { 'body': { 'original_config': cfg.copy() } }

for p in sorted(TEMPLATES_DIR.glob('*.json')):
    with p.open('r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except Exception:
            # skip non-json or invalid
            continue
    orig_data = json.dumps(data, sort_keys=True)

    modified = False
    if isinstance(data, dict) and 'graph' in data and isinstance(data['graph'], dict):
        nodes = data['graph'].get('nodes') or []
        for node in nodes:
            ntype = node.get('type')
            d = node.get('data') or {}
            cfg = d.get('config') or {}

            # 1) split: detect action node representing SplitInBatches
            if ntype == 'action' and (d.get('label','').lower().find('splitinbatches')!=-1 or ('batch_size' in cfg and 'input_path' in cfg)):
                # turn into SplitInBatches
                node['type'] = 'SplitInBatches'
                # preserve original config under body.original_config
                if 'body' not in cfg:
                    cfg = cfg.copy()
                    cfg['body'] = { 'original_config': cfg.copy() }
                    # but above duplicates; instead make proper original
                    # store a clean original copy
                    orig_cfg = d.get('config', {}).copy()
                    cfg = d.get('config', {}).copy()
                    cfg['body'] = { 'original_config': orig_cfg }
                    node['data']['config'] = cfg
                modified = True
                continue

            # 2) action nodes with inline code/template -> transform
            if ntype == 'action' and isinstance(cfg, dict) and ('language' in cfg and ('code' in cfg or 'template' in cfg)):
                node['type'] = 'transform'
                # preserve original config
                orig_cfg = cfg.copy()
                # ensure body exists and contains original_config
                if 'body' not in cfg:
                    cfg = cfg.copy()
                    cfg['body'] = { 'original_config': orig_cfg }
                    node['data']['config'] = cfg
                else:
                    # if body exists, ensure original_config preserved
                    if not isinstance(cfg.get('body'), dict) or 'original_config' not in cfg.get('body'):
                        cfg = cfg.copy()
                        b = cfg.get('body', {}).copy() if isinstance(cfg.get('body'), dict) else {}
                        b['original_config'] = orig_cfg
                        cfg['body'] = b
                        node['data']['config'] = cfg
                modified = True
                continue

            # 3) email -> http placeholder
            if ntype == 'email':
                orig_cfg = cfg.copy()
                node['type'] = 'http'
                new_cfg = {
                    'method': 'POST',
                    'url': PLACEHOLDER,
                    'body': { 'original_config': orig_cfg }
                }
                node['data']['config'] = new_cfg
                modified = True
                continue

            # 4) llm nodes missing prompt or using prompt_template
            if ntype == 'llm':
                # if prompt absent or using prompt_template key
                if not isinstance(cfg, dict):
                    cfg = {}
                if 'prompt' not in cfg or 'prompt_template' in cfg:
                    orig_cfg = cfg.copy()
                    # set prompt if missing
                    new_cfg = cfg.copy()
                    new_cfg['prompt'] = SAFE_PROMPT
                    # preserve original under body.original_config
                    b = new_cfg.get('body', {}) if isinstance(new_cfg.get('body'), dict) else {}
                    if 'original_config' not in b:
                        b['original_config'] = orig_cfg
                    new_cfg['body'] = b
                    node['data']['config'] = new_cfg
                    modified = True
                continue

            # 5) http nodes with concrete absolute URLs (contains 'https://' and no '{{') or missing url
            if ntype == 'http':
                if not isinstance(cfg, dict):
                    cfg = {}
                url = cfg.get('url')
                if (not url) or (isinstance(url, str) and url.startswith('https://') and '{{' not in url and '}}' not in url):
                    orig_cfg = cfg.copy()
                    new_cfg = cfg.copy()
                    new_cfg['url'] = PLACEHOLDER
                    # preserve original config under body.original_config
                    b = new_cfg.get('body', {}) if isinstance(new_cfg.get('body'), dict) else {}
                    if 'original_config' not in b:
                        b['original_config'] = orig_cfg
                    new_cfg['body'] = b
                    node['data']['config'] = new_cfg
                    modified = True
                continue

        if modified:
            data['graph']['nodes'] = nodes

    new_data = json.dumps(data, indent=2, ensure_ascii=False)
    if modified and new_data != orig_data:
        with p.open('w', encoding='utf-8') as f:
            f.write(new_data + '\n')
        changed_files.append(str(p))

if changed_files:
    print('Modified files:')
    for c in changed_files:
        print(c)
else:
    print('No changes made.')

if __name__ == '__main__':
    pass
