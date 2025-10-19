"""
Script to normalize backend/templates JSON files to runtime-supported node types.
This script is intended to be run temporarily by the assistant to perform bulk updates and
will be deleted after changes are applied.

Mapping rules applied:
- email -> http POST to https://example.mail/send with to/subject/body preserved in body.
- unknown/generic action nodes -> http POST to https://internal.api/worker/execute. Original config preserved under body.original_config.
- http nodes missing url -> set url to https://internal.api/worker/execute and preserve original body.
- llm nodes missing prompt -> populate prompt from template or a safe placeholder.
- SplitInBatches and other supported nodes left as-is.

Supported node types allowed: input, output, http, llm, If, Switch, SplitInBatches, ExecuteWorkflow, SubWorkflow
"""
import os
import json

TEMPLATES_DIR = os.path.join("backend", "templates")
ALLOWED_TYPES = {"input", "output", "http", "llm", "If", "Switch", "SplitInBatches", "ExecuteWorkflow", "SubWorkflow"}

MAIL_PLACEHOLDER = "https://example.mail/send"
WORKER_PLACEHOLDER = "https://internal.api/worker/execute"

def normalize_node(node):
    ntype = node.get("type")
    data = node.setdefault("data", {})
    config = data.setdefault("config", {})

    # Email nodes -> http to mail placeholder
    if ntype and ntype.lower() == "email":
        node["type"] = "http"
        # Try to preserve common fields
        body = {}
        for k in ("to", "from", "subject", "body", "text", "html"):
            if k in config:
                body[k] = config[k]
        # Preserve entire original config for follow-up
        body.setdefault("original_config", config.copy())
        data["config"] = {
            "method": "POST",
            "url": MAIL_PLACEHOLDER,
            "headers": {"Content-Type": "application/json"},
            "body": body,
        }
        return

    # If node type is allowed, do some light hygiene
    if ntype in ALLOWED_TYPES:
        if ntype == "http":
            # ensure url exists
            if not config.get("url"):
                config.setdefault("method", "POST")
                config.setdefault("url", WORKER_PLACEHOLDER)
                # preserve original config
                if "body" in config:
                    config.setdefault("body", {})
                    config["body"].setdefault("original_config", config.get("body"))
                else:
                    config.setdefault("body", {"original_config": {k: v for k, v in config.items()}})
                # remove keys that are now in body
                for k in list(config.keys()):
                    if k not in ("method", "url", "headers", "body"):
                        # keep headers/body/method/url only
                        pass
        if ntype == "llm":
            # ensure prompt exists
            if not config.get("prompt"):
                # try to derive from common fields
                if "template" in config:
                    config["prompt"] = config.get("template")
                elif "instruction" in config:
                    config["prompt"] = config.get("instruction")
                else:
                    config["prompt"] = "{{input}}\n\nRespond concisely."
        return

    # Generic/unrecognized node types -> convert to http worker call
    # Preserve original type and config
    orig = {"original_type": ntype, "original_config": config.copy()}
    node["type"] = "http"
    data["config"] = {
        "method": "POST",
        "url": WORKER_PLACEHOLDER,
        "headers": {"Content-Type": "application/json"},
        "body": orig,
    }


def process_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            j = json.load(f)
    except Exception as e:
        print(f"Skipping {path}: could not parse JSON: {e}")
        return False

    changed = False
    if isinstance(j, dict) and "graph" in j and isinstance(j["graph"], dict):
        nodes = j["graph"].get("nodes")
        if isinstance(nodes, list):
            for node in nodes:
                before = json.dumps(node, sort_keys=True)
                normalize_node(node)
                after = json.dumps(node, sort_keys=True)
                if before != after:
                    changed = True
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(j, f, indent=2)
        print(f"Updated {path}")
    else:
        print(f"No changes for {path}")
    return changed


def main():
    files = sorted(os.listdir(TEMPLATES_DIR))
    updated = []
    for fn in files:
        if not fn.endswith('.json'):
            continue
        if fn == 'index.json':
            continue
        path = os.path.join(TEMPLATES_DIR, fn)
        if os.path.isfile(path):
            if process_file(path):
                updated.append(fn)
    print("Done. Updated files:", updated)

if __name__ == '__main__':
    main()
