# Web API 文档对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 eNSP-MCP 的 Flask Web API 编写 `docs/modules/web_api.md`，使全部 HTTP 路由与 SocketIO 事件在文档中均有准确、可验证的对应条目。

**Architecture:** 以运行时探测（Flask `app.url_map` + 解析 `app.py` 的 `@socketio.on`）得到真实端点清单作为唯一事实源，按业务域分组写入文档；新增一个文档覆盖测试，断言每个运行时端点都出现在文档中，从根上防止文档再次漂移（此前静态扫描漏掉了 `init_agent_runtime` 在启动时注册的 23 个 agent 路由，必须以运行时清单为准）。

**Tech Stack:** Python 3.12（`python312/` 解释器）、Flask `app.url_map` / test_client、pytest、grep。

## Global Constraints

- 不删除任何公开接口（AGENTS.md 最高约束）。
- 纯文档/测试改动，不修改 `app.py` 等业务逻辑；每次修改后跑 `python312/python.exe -m pytest tests/` 确认基线（当前 223 passed, 3 skipped）。
- 模块以顶层方式导入：运行测试时 `pythonpath=mcpensp1`（pyproject 已配置，`tests` 自动包含）。
- 小步提交，单次 ≤10 个文件；工作在 `codex/fix-command-reliability` 分支，不直推 main。
- 文档内跨文件引用使用相对路径。

---

### Task 1: 编写会失败的文档覆盖测试

**Files:**
- Create: `tests/test_web_api_doc.py`

**Interfaces:**
- Consumes: `app` Flask 实例（顶层导入 `from app import app`）、`app.py` 源码路径 `mcpensp1/app.py`
- Produces: 无（纯校验，供后续任务驱动）

- [ ] **Step 1: 编写测试**

```python
# tests/test_web_api_doc.py
import re
import pytest

from app import app as flask_app

DOC_PATH = "docs/modules/web_api.md"


def _runtime_http_paths():
    """从运行时 url_map 取全部 HTTP 路径（已去除 <var> 转换器）。"""
    paths = set()
    for rule in flask_app.url_map.iter_rules():
        norm = re.sub(r"<[^>]+>", "", rule.rule)
        paths.add(norm)
    return paths


def _socketio_events():
    """从 app.py 源码解析 @socketio.on("name") 事件名（静态声明，可靠）。"""
    src = open("mcpensp1/app.py", encoding="utf-8").read()
    return set(re.findall(r'@socketio\.on\("([^"]+)"\)', src))


def test_all_http_routes_documented():
    doc = open(DOC_PATH, encoding="utf-8").read()
    missing = sorted(p for p in _runtime_http_paths() if p not in doc)
    assert not missing, f"未文档化的 HTTP 路由: {missing}"


def test_all_socketio_events_documented():
    doc = open(DOC_PATH, encoding="utf-8").read()
    missing = sorted(e for e in _socketio_events() if e not in doc)
    assert not missing, f"未文档化的 SocketIO 事件: {missing}"
```

- [ ] **Step 2: 运行测试，确认失败（文档尚不存在）**

Run: `python312/python.exe -m pytest tests/test_web_api_doc.py -v`
Expected: FAIL，`FileNotFoundError`（读 `docs/modules/web_api.md` 失败）或 `未文档化的 HTTP 路由: [...]`

- [ ] **Step 3: 暂存测试（不提交）**

```bash
git add tests/test_web_api_doc.py
```

---

### Task 2: 运行时探测并固化端点清单

**Files:**
- Create (临时，执行后删除): `tests/_dump_routes.py`

**Interfaces:**
- Consumes: `app` Flask 实例、`mcpensp1/app.py` 源码
- Produces: 终端输出的完整端点清单（后续 Task 3 的录入源）

- [ ] **Step 1: 编写探测脚本**

```python
# tests/_dump_routes.py
import re
from app import app as flask_app

print("=== HTTP ROUTES (method  path) ===")
rows = []
for rule in sorted(flask_app.url_map.iter_rules(), key=lambda r: r.rule):
    methods = ",".join(sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS")))
    rows.append(f"{methods:18} {rule.rule}")
print("\n".join(rows))

print("\n=== SOCKETIO EVENTS ===")
src = open("mcpensp1/app.py", encoding="utf-8").read()
events = re.findall(r'@socketio\.on\("([^"]+)"\)', src)
print("\n".join(sorted(events)))
```

- [ ] **Step 2: 运行探测，保存输出**

Run: `python312/python.exe tests/_dump_routes.py > /tmp/web_api_inventory.txt 2>&1`
Expected: 终端/文件出现约 50+ 条 HTTP 路由（含 `init_agent_runtime` 启动时注册的 `/api/agent/*` 等）与 8 个 SocketIO 事件。

- [ ] **Step 3: 删除临时脚本**

```bash
rm tests/_dump_routes.py
```

> 注：若 `from app import app` 触发过重副作用（心跳线程/socketio 监听），参考既有 `tests/test_kb_search_endpoint.py` 的惰性导入与 `app.test_client()` 用法，将导入移入测试函数内并加上 fixture 收尾。

---

### Task 3: 编写 docs/modules/web_api.md

**Files:**
- Create: `docs/modules/web_api.md`

**Interfaces:**
- Consumes: Task 2 生成的 `/tmp/web_api_inventory.txt`
- Produces: 含每个端点路径的文档（使 Task 1 测试通过）

- [ ] **Step 1: 按业务域分组录入**

以 Task 2 输出为准，逐条录入。每个域一个小节，每条格式：

```markdown
### <域> (devices / kb / topology / config-methods / experiments / agent / health)

| Method | Path | 说明 | 参数 | 响应 |
|--------|------|------|------|------|
| GET | /api/devices | 列出已连接设备 | — | 200: 设备数组 |
| POST | /api/devices/connect | 连接设备 | body: {port} | 200/4xx |
```

- 必须覆盖 Task 2 输出的**每一个** HTTP 路径与 **每一个** SocketIO 事件名（测试按子串匹配，写入含 `<var>` 的原始路径即可，如 `/api/experiments/<exp_id>`）。
- SocketIO 事件单独成节：`## SocketIO 事件`，列出 8 个事件名及触发时机。

- [ ] **Step 2: 运行 Task 1 测试，确认通过**

Run: `python312/python.exe -m pytest tests/test_web_api_doc.py -v`
Expected: PASS（两条测试均绿）

---

### Task 4: 交叉引用与收尾

**Files:**
- Modify: `docs/modules/knowledge.md`（在"另见"追加一行）

**Interfaces:**
- Consumes: 新建的 `docs/modules/web_api.md`
- Produces: 相关知识文档互链

- [ ] **Step 1: 在 knowledge.md 另见区补充 Web API 文档链接**

在 `docs/modules/knowledge.md` 末尾"## 另见"列表中追加：

```markdown
- `docs/modules/web_api.md` —— Flask Web API（HTTP 路由 + SocketIO 事件）
```

- [ ] **Step 2: 跑全量测试确认基线**

Run: `python312/python.exe -m pytest tests/ -q`
Expected: 224 passed, 3 skipped（原 223 + 新增 1 个覆盖测试文件中的 2 用例 → 实际 +2，以运行结果为准），无失败。

---

### Task 5: 提交

**Files:**
- `docs/modules/web_api.md`、`tests/test_web_api_doc.py`、`docs/modules/knowledge.md`

- [ ] **Step 1: 提交（单提交，≤10 文件）**

```bash
git add docs/modules/web_api.md tests/test_web_api_doc.py docs/modules/knowledge.md
git commit -m "docs: 新增 Flask Web API 文档（web_api.md）并加文档覆盖测试"
```

- [ ] **Step 2: 确认状态干净**

Run: `git status --short`
Expected: 无未提交改动（除本分支既有的未 push 提交外）

---

## 范围外（不在本计划）

- `static/app.js` 中 6 处悬空 fetch 调用（404/405，指向 v2.4 已移除的路由）属于**前端死代码**，是代码问题不是文档问题；建议另立计划清理前端或补回对应后端路由。
- 此前已修复的 5 处文档不匹配（工具数、`AGENTS.md` 目录树、`command_executor` 返回契约、`config_method_store` 死链）已在 `fca1419`/`fc8c860` 提交，不重复处理。

## Self-Review 要点

- 覆盖度：每个 Task 2 探测到的运行时端点都有 Task 3 文档条目 + Task 1 测试守护，无遗漏。
- 无占位符：测试与探测脚本均为完整可执行代码。
- 一致性：`from app import app`、路径 `mcpensp1/app.py`、`docs/modules/web_api.md` 在 Task 1/2/3 中命名一致。
