markers=['# HTTP node','# Slack / webhook','# Email node','# LLM node','# SplitInBatches','# Execute sub-workflow','# Switch node','# If','# SplitInBatches / Loop node']
with open('backend/tasks.py','r',encoding='utf-8') as f:
    for i,l in enumerate(f, start=1):
        for m in markers:
            if m in l:
                print(m,'->',i)
