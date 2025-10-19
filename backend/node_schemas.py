from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class BaseNodeConfig(BaseModel):
    """Base class for node config schemas. Keep lightweight to remain compatible
    with existing free-form configs. Specific node types may extend this."""
    # Keep original raw config to allow round-tripping and conservative migrations
    original_config: Optional[Dict[str, Any]] = Field(None, description="Original config as provided by user")


class HTTPRequestConfig(BaseNodeConfig):
    method: Optional[str] = Field("GET")
    url: Optional[str] = None
    headers: Optional[Dict[str, Any]] = None
    body: Optional[Any] = None


class LLMConfig(BaseNodeConfig):
    prompt: Optional[str] = None
    provider_id: Optional[int] = None
    model: Optional[str] = None


class SendEmailConfig(BaseNodeConfig):
    to: Optional[str] = None
    from_: Optional[str] = Field(None, alias="from")
    subject: Optional[str] = None
    body: Optional[str] = None
    provider_id: Optional[int] = None


class SlackMessageConfig(BaseNodeConfig):
    channel: Optional[str] = None
    text: Optional[str] = None
    provider_id: Optional[int] = None


class DBQueryConfig(BaseNodeConfig):
    provider_id: Optional[int] = None
    query: Optional[str] = None


class TransformConfig(BaseNodeConfig):
    language: Optional[str] = Field("jinja")
    template: Optional[str] = None


class WaitConfig(BaseNodeConfig):
    seconds: Optional[int] = Field(60)


class CronTriggerConfig(BaseNodeConfig):
    cron: Optional[str] = Field("0 * * * *")
    timezone: Optional[str] = Field("UTC")
    enabled: Optional[bool] = Field(True)


class HTTPTriggerConfig(BaseNodeConfig):
    capture_headers: Optional[bool] = Field(False)


class SplitConfig(BaseNodeConfig):
    input_path: Optional[str] = Field("input")
    batch_size: Optional[int] = Field(10)
    mode: Optional[str] = Field("serial")
    concurrency: Optional[int] = Field(4)
    fail_behavior: Optional[str] = Field("stop_on_error")
    max_chunks: Optional[int] = None


# Utility to fetch a JSON schema for a friendly label. This is intentionally
# conservative (keeps many fields optional) so existing workflows continue to
# validate. The canonical schemas can be tightened in follow-up work with a
# migration path.
_NODE_SCHEMA_MAP = {
    "HTTP Request": HTTPRequestConfig,
    "LLM": LLMConfig,
    "Send Email": SendEmailConfig,
    "Slack Message": SlackMessageConfig,
    "DB Query": DBQueryConfig,
    "Transform": TransformConfig,
    "Wait": WaitConfig,
    "Cron Trigger": CronTriggerConfig,
    "HTTP Trigger": HTTPTriggerConfig,
    "SplitInBatches": SplitConfig,
    "Loop": SplitConfig,
    "Parallel": SplitConfig,
}


def get_node_json_schema(label: str) -> Dict[str, Any]:
    """Return a JSON Schema (as dict) for the given node label, if known.
    Falls back to a permissive empty-object schema when unknown.
    """
    cls = _NODE_SCHEMA_MAP.get(label)
    if not cls:
        return {"type": "object"}
    return cls.schema()


def canonicalize_graph(graph: Any) -> Any:
    """Conservative migration helper: ensure each node's config preserves
    the original raw config under `original_config` and avoid mutating the
    original_config if already present. This helper attempts to be totally
    non-destructive for unknown fields.
    """
    try:
        # nodes may be a dict with 'nodes' or a list of nodes
        nodes = None
        if graph is None:
            return None
        if isinstance(graph, dict):
            nodes = graph.get('nodes')
        elif isinstance(graph, list):
            nodes = graph
        else:
            return graph

        if nodes is None:
            return graph

        def _canon_node(n: Any):
            try:
                if not isinstance(n, dict):
                    return n
                # react-flow style: config under data.config
                data = n.get('data') or {}
                cfg = None
                if isinstance(data, dict):
                    cfg = data.get('config')
                # fallback: node itself may be a config object
                if cfg is None and isinstance(n, dict) and 'type' in n and 'config' not in n:
                    cfg = n

                if isinstance(cfg, dict):
                    # avoid copying original_config into itself
                    if 'original_config' not in cfg:
                        # shallow copy excluding any nested original_config
                        copy = {k: v for k, v in cfg.items() if k != 'original_config'}
                        cfg['original_config'] = dict(copy)
                return n
            except Exception:
                return n

        out_nodes = []
        for el in nodes:
            out_nodes.append(_canon_node(el))

        if isinstance(graph, dict):
            g2 = dict(graph)
            g2['nodes'] = out_nodes
            return g2
        return out_nodes
    except Exception:
        return graph


__all__ = [
    "BaseNodeConfig",
    "HTTPRequestConfig",
    "LLMConfig",
    "SendEmailConfig",
    "SlackMessageConfig",
    "DBQueryConfig",
    "TransformConfig",
    "WaitConfig",
    "CronTriggerConfig",
    "HTTPTriggerConfig",
    "SplitConfig",
    "get_node_json_schema",
]
