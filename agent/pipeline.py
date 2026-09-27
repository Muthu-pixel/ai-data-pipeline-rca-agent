import asyncio
import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from agent.prompts import SYSTEM_PROMPT
from agent.schemas import RCAReport
from agent.tools import get_table_schema as _get_table_schema
from agent.tools import read_log_file as _read_log_file


@tool("read_log_file", "Reads a pipeline run's log file from disk, given its full path.", {"path": str})
async def read_log_file_tool(args: dict[str, Any]) -> dict[str, Any]:
    text = _read_log_file(args["path"])
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "get_table_schema",
    "Queries SQL Server for a table's real, current column names and types.",
    {"table_name": str},
)
async def get_table_schema_tool(args: dict[str, Any]) -> dict[str, Any]:
    columns = _get_table_schema(args["table_name"])
    return {"content": [{"type": "text", "text": json.dumps(columns)}]}


def _find_cli_path() -> str | None:
    """The claude-agent-sdk wheel doesn't bundle claude.exe on this machine; fall back to
    the native binary the VS Code Claude Code extension already ships, if present."""
    matches = sorted(Path.home().glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"))
    return str(matches[-1]) if matches else None


_opsfix_server = create_sdk_mcp_server(name="opsfix", tools=[read_log_file_tool, get_table_schema_tool])

_OPTIONS = ClaudeAgentOptions(
    system_prompt=SYSTEM_PROMPT,
    mcp_servers={"opsfix": _opsfix_server},
    allowed_tools=["mcp__opsfix__read_log_file", "mcp__opsfix__get_table_schema"],
    output_format={"type": "json_schema", "schema": RCAReport.model_json_schema()},
    cli_path=_find_cli_path(),
)


async def investigate_log_async(log_path: str) -> RCAReport | None:
    """Runs a Claude Agent SDK session that investigates one pipeline log file and
    returns a validated RCAReport, or None if the session didn't produce one."""
    prompt = f"Investigate the pipeline run logged at: {log_path}"
    result: RCAReport | None = None

    messages = query(prompt=prompt, options=_OPTIONS)
    try:
        async for message in messages:
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"[agent] {block.text}")

            elif isinstance(message, ResultMessage):
                if message.subtype == "success" and message.structured_output is not None:
                    result = RCAReport.model_validate(message.structured_output)
                elif message.subtype == "success":
                    print("[pipeline] Session succeeded but produced no structured output")
                else:
                    print(f"[pipeline] Session did not succeed: {message.subtype}")
                break
    finally:
        # query()'s underlying transport can raise on close if we stop iterating
        # early (which we always do, right after the ResultMessage) -- harmless.
        try:
            await messages.aclose()
        except RuntimeError:
            pass

    return result


def investigate_log(log_path: str) -> RCAReport | None:
    return asyncio.run(investigate_log_async(log_path))
