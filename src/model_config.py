"""Chat model construction, env-driven so no provider/key is hardcoded.

Mirrors mcp_client.py's pattern: read from environment with a sane default,
raise loudly if something required is missing, never fall back silently to
a different provider than the one asked for.
"""

from __future__ import annotations

import os

from agentscope.credential import DashScopeCredential, OpenAICredential
from agentscope.model import ChatModelBase, DashScopeChatModel

from ._llm_compat import ToolChoiceRelaxingModel, ToolReplyAdjacencyFormatter

#: model name defaults, one per provider; override with DMS_LLM_MODEL.
_DEFAULT_MODEL = {
    "dashscope": "qwen-max",
    "openai": "gpt-4.1",
}


def build_chat_model(provider: str | None = None) -> ChatModelBase:
    """Build the chat model used by every agent in this package.

    Provider and model are read from env (`DMS_LLM_PROVIDER`, `DMS_LLM_MODEL`),
    the API key from the provider-specific env var below. Raises a clear
    `RuntimeError` rather than silently picking a different provider when the
    key is missing - callers should treat that as "stop and report", same as
    `mcp_client.require_available()`.
    """
    provider = (provider or os.environ.get("DMS_LLM_PROVIDER", "dashscope")).lower()
    model_name = os.environ.get("DMS_LLM_MODEL", _DEFAULT_MODEL.get(provider, ""))

    if provider == "dashscope":
        api_key = _require_env("DASHSCOPE_API_KEY")
        return DashScopeChatModel(
            credential=DashScopeCredential(api_key=api_key),
            model=model_name,
        )
    if provider == "openai":
        api_key = _require_env("OPENAI_API_KEY")
        return ToolChoiceRelaxingModel(
            credential=OpenAICredential(api_key=api_key, base_url=os.environ.get("OPENAI_BASE_URL")),
            model=model_name,
            formatter=ToolReplyAdjacencyFormatter(),
        )
    raise RuntimeError(
        f"Unknown DMS_LLM_PROVIDER '{provider}'. Supported: dashscope, openai."
    )


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set; required for the configured DMS_LLM_PROVIDER")
    return value
