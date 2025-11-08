"""Shared provider constants used by backend.routes.providers.

This module was split out to keep the routes file smaller while
preserving the same literal data and simple lookups.
"""

PROVIDER_TYPES = ["openai", "ollama", "s3", "smtp", "gcp", "azure"]

PROVIDER_SCHEMAS = {
    "openai": {
        "title": "OpenAI Provider",
        "type": "object",
        "properties": {"api_key": {"type": "string", "format": "password"}},
        "required": ["api_key"],
    },
    "ollama": {
        "title": "Ollama Provider",
        "type": "object",
        "properties": {"url": {"type": "string"}, "api_key": {"type": "string", "format": "password"}},
    },
    "s3": {
        "title": "S3",
        "type": "object",
        "properties": {
            "access_key_id": {"type": "string"},
            "secret_access_key": {"type": "string", "format": "password"},
            "region": {"type": "string"},
        },
    },
    "smtp": {
        "title": "SMTP",
        "type": "object",
        "properties": {
            "host": {"type": "string"},
            "port": {"type": "integer"},
            "username": {"type": "string"},
            "password": {"type": "string", "format": "password"},
        },
    },
    "gcp": {"title": "GCP", "type": "object", "properties": {"credentials": {"type": "object"}}},
    "azure": {
        "title": "Azure",
        "type": "object",
        "properties": {"tenant_id": {"type": "string"}, "client_id": {"type": "string"}, "client_secret": {"type": "string", "format": "password"}},
    },
}

MODEL_MAP = {
    "openai": [
        "gpt-4",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4o-realtime-preview",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
    ],
    "anthropic": ["claude-3", "claude-2"],
    "cohere": ["command", "command-nightly", "xlarge"],
    "huggingface-inference": ["hf-infer-embed", "huggingface-generic"],
    "ollama": ["ollama-default", "ollama-llama2"],
    "llama2": ["llama2-chat", "llama2-13b"],
    "s3": [],
    "smtp": [],
    "gcp": [],
    "azure": [],
}
