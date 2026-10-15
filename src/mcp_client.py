"""Construction helpers for the two MCP servers this project depends on.

Both servers are spawned as stdio subprocesses by this process; neither one
launches or reconnects the browser itself (design doc §9.2; CLAUDE.md 人工
前置). JSReverser-Strong-MCP attaches over CDP to a browser the human has
already opened and logged into; this process only talks MCP to it over
stdio.

No substitutes accepted for either server (design doc §9.2): not a generic
"similar" browser-automation MCP, not Playwright. Call `require_available()`
at startup and stop if it fails - do not fall back to launching or
reconnecting a browser some other way.
"""

from __future__ import annotations

import os

from agentscope.mcp import MCPClient, StdioMCPConfig

#: Tools that would navigate or reload the page. Login sessions here are
#: single-point and non-reproducible (CLAUDE.md 数据捕获规则 8): "已登录会话
#: 下绝不 navigate_page/刷新页面". Disabling them here removes them from
#: list_tools()/get_tool_schemas(), so the LLM is never shown a schema for
#: them and cannot emit a tool_call naming them.
#:
#: CAVEAT (verified empirically 2026-09-17 against agentscope==2.0.8):
#: MCPClient.disable_tools only filters list_tools()/list_raw_tools(). A
#: direct client.get_tool("navigate_page") by name still succeeds. The
#: safety guarantee therefore depends on orchestrator code never calling
#: get_tool() with an explicit tool name for anything - only ever
#: registering the filtered list_tools() output into a Toolkit. Do not
#: "helpfully" add a get_tool() convenience call anywhere in this project.
NAVIGATION_TOOLS = ("navigate_page", "new_page")

JSREVERSER_NAME = "jsreverser"
ANNOTATOR_NAME = "image-annotator"


def qualify(client_name: str, tool_name: str) -> str:
    """The name a *live* MCP tool actually has once surfaced through
    `MCPClient.list_tools()`/`Toolkit`, not the bare server-side name.

    AgentScope renames every tool to `mcp__{client_name}__{tool_name}` to
    satisfy LLM providers' tool-name character rules (see
    `agentscope/tool/_adapters.py` `MCPTool.__init__`). `enable_tools`/
    `disable_tools` on `MCPClient` are the exception - those filter against
    the MCP server's raw tool list, so they still take bare names. Anything
    that compares against a `list_tools()` result or a live `tool_call.name`
    (e.g. `require_available()` below, `BrowserQueueMiddleware`) must go
    through this to match.
    """
    return f"mcp__{client_name}__{tool_name}"


JSREVERSER_COMMAND = os.environ.get("DMS_JSREVERSER_NODE", "/usr/local/opt/node@24/bin/node")
JSREVERSER_SCRIPT = os.environ.get(
    "DMS_JSREVERSER_SCRIPT",
    "/Users/apple/work-zone/tools/mcp/JSReverser-Strong-MCP/build/src/index.js",
)
ANNOTATOR_COMMAND = os.environ.get("DMS_ANNOTATOR_NODE", "node")
ANNOTATOR_SCRIPT = os.environ.get(
    "DMS_ANNOTATOR_SCRIPT",
    "/Users/apple/work-zone/tools/mcp/image-annotator-mcp-main/server.js",
)


def jsreverser_client(enable_tools: list[str] | None = None) -> MCPClient:
    """Client for JSReverser-Strong-MCP with page navigation locked out.

    `enable_tools`, when given, further restricts the surface to that list
    (e.g. Discovery gets a smaller set than a table agent doing drill-downs).
    """
    return MCPClient(
        name=JSREVERSER_NAME,
        is_stateful=True,
        mcp_config=StdioMCPConfig(
            type="stdio_mcp",
            command=JSREVERSER_COMMAND,
            args=[JSREVERSER_SCRIPT, "--autoConnect"],
        ),
        enable_tools=enable_tools,
        disable_tools=list(NAVIGATION_TOOLS),
    )


def annotator_client() -> MCPClient:
    """Client for image-annotator. JSReverser has no red-box capability."""
    return MCPClient(
        name=ANNOTATOR_NAME,
        is_stateful=True,
        mcp_config=StdioMCPConfig(
            type="stdio_mcp",
            command=ANNOTATOR_COMMAND,
            args=[ANNOTATOR_SCRIPT],
        ),
    )


async def require_available() -> None:
    """Phase-0-equivalent check: both servers must connect and list tools.

    Raises on the first failure. Callers should treat any exception here as
    "stop and report", per CLAUDE.md's 人工前置: MCP 未安装/不可用时不自己
    启动或重连浏览器，也不用其它 MCP 顶替。
    """
    jsr = jsreverser_client()
    await jsr.connect()
    try:
        tools = {t.name for t in await jsr.list_tools()}
        if qualify(JSREVERSER_NAME, "list_pages") not in tools:
            raise RuntimeError("JSReverser-Strong-MCP: list_pages tool not found")
    finally:
        await jsr.close()

    ann = annotator_client()
    await ann.connect()
    try:
        tools = {t.name for t in await ann.list_tools()}
        if qualify(ANNOTATOR_NAME, "get_image_dimensions") not in tools:
            raise RuntimeError("image-annotator: get_image_dimensions tool not found")
    finally:
        await ann.close()
