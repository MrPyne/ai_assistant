import os
from types import SimpleNamespace

import pytest

from backend.llm_utils import is_live_llm_enabled
from backend.adapters.openai_adapter import OpenAIAdapter
from backend.adapters.ollama_adapter import OllamaAdapter


def make_provider(config=None):
    return SimpleNamespace(config=config or {}, workspace_id=1)


def test_is_live_llm_enabled_defaults_false(monkeypatch):
    # Ensure env vars are unset
    for k in ["ENABLE_LIVE_LLM", "LIVE_LLM", "ENABLE_OPENAI", "ENABLE_OLLAMA"]:
        monkeypatch.delenv(k, raising=False)

    assert is_live_llm_enabled() is False
    assert is_live_llm_enabled("openai") is False
    assert is_live_llm_enabled("ollama") is False


def test_is_live_llm_enabled_global_opt_in(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_LLM", "true")
    assert is_live_llm_enabled() is True
    assert is_live_llm_enabled("openai") is True
    assert is_live_llm_enabled("ollama") is True


def test_is_live_llm_enabled_provider_fallbacks(monkeypatch):
    monkeypatch.delenv("ENABLE_LIVE_LLM", raising=False)
    monkeypatch.setenv("ENABLE_OPENAI", "true")
    monkeypatch.delenv("ENABLE_OLLAMA", raising=False)

    assert is_live_llm_enabled("openai") is True
    assert is_live_llm_enabled("ollama") is False


def test_openai_adapter_returns_mock_when_disabled(monkeypatch):
    # Ensure global and provider env opts are unset
    for k in ["ENABLE_LIVE_LLM", "LIVE_LLM", "ENABLE_OPENAI"]:
        monkeypatch.delenv(k, raising=False)

    provider = make_provider({"model": "gpt-test"})
    adapter = OpenAIAdapter(provider, db=None)

    resp = adapter.generate("Hello world")
    assert isinstance(resp, dict)
    assert "text" in resp
    assert resp["text"].startswith("[mock] OpenAIAdapter")
    assert "meta" in resp and isinstance(resp["meta"], dict)
    meta = resp["meta"]
    assert "usage" in meta and isinstance(meta["usage"], dict)
    assert "prompt_tokens" in meta["usage"]
    assert "model" in meta and meta["model"] == "gpt-test"


def test_ollama_adapter_returns_mock_when_disabled(monkeypatch):
    for k in ["ENABLE_LIVE_LLM", "LIVE_LLM", "ENABLE_OLLAMA"]:
        monkeypatch.delenv(k, raising=False)

    provider = make_provider({"model": "llama-test"})
    adapter = OllamaAdapter(provider, db=None)

    resp = adapter.generate("Hello world")
    assert isinstance(resp, dict)
    assert "text" in resp
    assert resp["text"].startswith("[mock] OllamaAdapter")
    assert "meta" in resp and isinstance(resp["meta"], dict)
    meta = resp["meta"]
    assert "model" in meta and meta["model"] == "llama-test"
