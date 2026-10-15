"""Unit tests for mcp_client.py's `qualify()` - see require_available()'s
regression (2026-09-18): it compared bare server-side tool names against
`MCPClient.list_tools()` results, which AgentScope renames to
`mcp__{client}__{tool}` (agentscope/tool/_adapters.py `MCPTool.__init__`).
The second test pins that contract against the real library so a future
AgentScope upgrade that changes the naming scheme fails loudly here instead
of resurrecting the same bug silently."""

from __future__ import annotations

import mcp.types
from agentscope.tool import MCPTool

from src.mcp_client import ANNOTATOR_NAME, JSREVERSER_NAME, qualify


def test_qualify_prefixes_with_mcp_double_underscore():
    assert qualify("jsreverser", "list_pages") == "mcp__jsreverser__list_pages"


def test_qualify_matches_real_agentscope_mcptool_naming():
    tool = mcp.types.Tool(name="list_pages", description="", inputSchema={"type": "object", "properties": {}})
    wrapped = MCPTool(mcp_name=JSREVERSER_NAME, tool=tool, client_gen=lambda: None)
    assert wrapped.name == qualify(JSREVERSER_NAME, "list_pages")


def test_client_name_constants_are_the_names_require_available_checks():
    assert JSREVERSER_NAME == "jsreverser"
    assert ANNOTATOR_NAME == "image-annotator"
