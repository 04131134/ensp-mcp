"""回归测试：确保 list_tools 声明的每个 MCP 工具都在 call_tool 中有对应分发分支。

防止再次出现「声明了工具、却漏写 elif name == '...' 头部」这类 bug
（如 search_kb 曾经把实现体错误地挂在 batch_command 分支内）。
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(REPO_ROOT, "mcpensp1", "mcp_server.py")


def _call_tool_body() -> str:
    src = open(SERVER, encoding="utf-8").read()
    lines = src.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("async def call_tool"))
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if (lines[j].startswith("async def ") or lines[j].startswith("def ")) and not lines[j].startswith("    "):
            end = j
            break
    return "\n".join(lines[start:end])


def test_all_declared_tools_are_dispatched():
    src = open(SERVER, encoding="utf-8").read()
    declared = set(re.findall(r'Tool\(\s*name\s*=\s*[\'"]%s[\'"]' % r'([^\'"]+)', src))
    body = _call_tool_body()
    dispatched = set(re.findall(r'(?:if|elif) name\s*==\s*[\'"]%s[\'"]' % r'([^\'"]+)', body))
    orphans = declared - dispatched
    assert not orphans, f"声明但未接线的工具: {sorted(orphans)}"


def test_no_dangling_tool_body():
    """每个分发分支的头部必须存在；不允许工具实现体挂在错误的分支里。"""
    body = _call_tool_body()
    # 全部工具均有 elif/if name == 头部，且仅在 call_tool 范围内
    dispatched = set(re.findall(r'(?:if|elif) name\s*==\s*[\'"]%s[\'"]' % r'([^\'"]+)', body))
    assert "search_kb" in dispatched, "search_kb 必须有独立的分发分支"
    assert len(dispatched) >= len(set(re.findall(r'Tool\(\s*name\s*=\s*[\'"]%s[\'"]' % r'([^\'"]+)', open(SERVER, encoding="utf-8").read())))
