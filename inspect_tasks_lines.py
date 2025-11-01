import sys
p='backend/tasks.py'
with open(p, 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i,l in enumerate(lines, start=1):
    if 'LLM node' in l or "elif isinstance(ntype, str) and ntype.lower() == 'llm'" in l or 'elif isinstance(ntype, str) and ntype.lower() == \'llm\'' in l or "# LLM node" in l:
        print(i, l.strip())
# also find SplitInBatches
for i,l in enumerate(lines, start=1):
    if 'SplitInBatches' in l or "SplitInBatches'" in l or "SplitInBatches" in l:
        print(i, l.strip())
# find HTTP node
for i,l in enumerate(lines, start=1):
    if "# HTTP node" in l or "HTTP node" in l and i>200:
        print(i, l.strip())

# find start of process_run
for i,l in enumerate(lines, start=1):
    if l.strip().startswith('def process_run('):
        print('process_run starts at', i)
    if l.strip().startswith('def execute_workflow('):
        print('execute_workflow starts at', i)
