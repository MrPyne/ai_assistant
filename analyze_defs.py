import ast, json, sys

def analyze(path):
    with open(path, 'r', encoding='utf-8') as f:
        src = f.read()
    tree = ast.parse(src)
    lines = src.splitlines()
    defs = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            # find end lineno by scanning body nodes
            end = start
            if hasattr(node, 'end_lineno') and node.end_lineno is not None:
                end = node.end_lineno
            else:
                # fallback: walk to find max lineno
                maxln = start
                for n in ast.walk(node):
                    if hasattr(n, 'lineno'):
                        maxln = max(maxln, getattr(n, 'lineno'))
                end = maxln
            defs.append({'type': type(node).__name__, 'name': getattr(node, 'name', '<anon>'), 'start': start, 'end': end, 'lines': end - start + 1})
    total = len(lines)
    return {'path': path, 'total_lines': total, 'defs': defs}

if __name__ == '__main__':
    paths = sys.argv[1:]
    out = []
    for p in paths:
        out.append(analyze(p))
    print(json.dumps(out, indent=2))
