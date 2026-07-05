# eNSP-MCP 渐进式重构方案

> 两轮对抗式审查后修正的最终版本。核心原则：不搞大爆炸重写，每步可独立验证、可独立回滚。
>
> 制定日期：2026-07-06 | **状态：Phase 0/1/2/2.5/3 已完成 ✅**

---

## 0. 问题全景

### 已确认的核心问题

| 优先级 | 问题 | 影响 |
|--------|------|------|
| P0 | `AGENT_SYSTEM_PROMPT`（mcp_server.py:19-98）中文乱码 | Agent 无法理解工作指令 |
| P0 | `names` 未定义（app.py:864）应为 `device_names` | 知识自动记录静默失败 |
| P0 | `analysis['kb_references']` 未初始化（agent/recovery.py:113） | 自动恢复 KeyError |
| P1 | `app.py` 3616 行单体 God Object | 无法维护、无法独立测试 |
| P1 | `mcp_server.py` 是空壳 HTTP 代理 | 两层服务依赖、延迟翻倍、故障面大 |
| P1 | 全局变量 + 多锁、获取顺序不统一 | 潜在死锁、数据竞争 |
| P2 | `knowledge.py` 与 `app.py` 内嵌 KnowledgeBase 完全重复 | 死代码 900 行 |
| P2 | Telnet 读取用固定超时而非提示符检测 | 响应截断或超时；ping 等诊断命令缺失特殊处理 |
| P2 | 心跳用 `select.select()` 查可写性而非发探测命令 | 断连检测不准 |
| P2 | `agent/routes.py` 的 `_require_auth` 是空操作 | Agent API 无认证 |
| P3 | 测试覆盖率约 0% | 无回归保障 |
| P3 | Agent System Prompt 硬编码在 Python 里 | 不可迭代、乱码不可见 |
| P3 | 根目录/mcpensp1 内散落 20+ 临时文件 | 项目卫生差 |
| P3 | Agent 子系统（12 文件,~3300行）与核心模块通过回调耦合 | 重构时容易遗漏 |

### 目标架构

**当前：**

```
MCP Server (空壳代理,517行) ──HTTP──> Flask (God Object,3616行) ──Telnet──> eNSP
```

**目标：**

```
MCP Server (唯一运行时进程)
    │
    ├── DeviceManager ──> TelnetConnectionPool ──> eNSP
    ├── CommandExecutor
    ├── KnowledgeStore
    └── AgentRuntime

Flask Web UI (可选调试器,只读)
    └── HTTP GET ──> DeviceManager 状态查询端点
```

MCP Server 是唯一的运行时进程。Flask 降级为可选的只读调试面板：需要时手动启动 `python app.py`，只能查询设备状态和历史日志，不写入。

---

## Phase 0: 安全网 ✅ 已完成

**目标：在动任何代码之前建立可验证的基线。工期 0.5 天。**

### 0.1 冒烟测试

为 4 个核心链路写集成测试脚本：

- `scan_devices` → 扫描到的设备列表
- `connect_device` → 连接成功、设备信息获取
- `send_command` → 发送单条命令、返回输出
- `batch_command` → 批量发送命令、返回结果

记录成功请求/响应对作为回归基准。同时记录失败场景作为预期错误行为。

**风险提示：冒烟测试依赖 eNSP 设备在线运行。设备不在线时本 Phase 可降级为纯代码审查。**

### 0.2 Git 分支策略

```
main        —— 当前可用状态，禁止直接 push
refactor/p0 —— Phase 1~7 的重构分支
```

合入 main 前跑完整冒烟测试。

### 0.3 基线备份

```bash
# 备份整个 mcpensp1/ 目录
cp -r e:/eNSP-MCP/mcpensp1 e:/eNSP-MCP/_baseline_20260706/

# 备份根目录工具和知识库
cp e:/eNSP-MCP/ensp_utils.py e:/eNSP-MCP/_baseline_20260706/
cp -r e:/eNSP-MCP/mcpensp1/kb e:/eNSP-MCP/_baseline_20260706/kb_backup/
```

### 验证标准

- 冒烟测试脚本可通过真实 eNSP 执行（设备在线时）
- Git 分支就绪

---

## Phase 1: 修确定性 Bug + 编码修复 ✅ 已完成

**目标：不动架构，修复已知 Bug。工期 1 天。**

### 1.1 必修 Bug

| # | Bug | 文件:行 | 修复 |
|---|-----|---------|------|
| 1 | `names` 未定义 | app.py:864 | `names.get(...)` → `device_names.get(...)` |
| 2 | `analysis['kb_references']` KeyError | agent/recovery.py:113 | 访问前检查 `'kb_references' in analysis`，缺失时设空列表 |
| 3 | `_require_auth` 空操作 | agent/routes.py:35-39 | 读取 `X-API-Key` header 并校验，接入 `ENSP_API_KEY` 环境变量 |
| 4 | MCP 裸 except 无日志 | mcp_server.py:466 | 添加 `logger.exception("Unhandled tool call error")` |

### 1.2 编码修复

**注意：不是全文件编码损坏。** 实际只有 `AGENT_SYSTEM_PROMPT`（mcp_server.py:19-98）和 `heartbeat.py` 两条 WebSocket 推送消息是乱码。`app.py` 的 `COMMAND_CATALOG` 中文正确。

| # | 文件:行 | 内容 | 修复方式 |
|---|---------|------|----------|
| 1 | mcp_server.py:19-98 | `AGENT_SYSTEM_PROMPT` 中文乱码 | 重写为正确 UTF-8 中文，同时外部化 |
| 2 | heartbeat.py:48,117 | WebSocket 推送消息乱码 | `宸叉柇寮€` → `已断开`、`已恢复愬姛` → `已恢复成功` |

### 1.3 同步外部化 Agent System Prompt

```
mcpensp1/prompts/
└── v3/
    └── system.md    # 完整 UTF-8 Markdown
```

```python
def _load_prompt(version: str = "v3") -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", version, "system.md")
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

AGENT_SYSTEM_PROMPT = _load_prompt()
```

### 验证标准

- 4 个 Bug 不再复现
- `AGENT_SYSTEM_PROMPT` 在 MCP 客户端中正常显示中文
- `heartbeat.py` 推送消息正常

---

## Phase 2: 拆 app.py ✅ 已完成

**目标：把 3616 行拆为独立模块。工期 8-10 天。**

### 2.1 拆分目标

```
mcpensp1/
├── device_manager.py     # 设备连接/断开/心跳/命名（~400行）
├── knowledge_store.py    # 统一知识库（~500行）
├── command_executor.py   # send_command/batch_command/COMMAND_CATALOG（~300行）
├── topology.py           # 已有文件（适配 DeviceManager 引用）
├── heartbeat.py          # 已有文件（适配 DeviceManager 引用）
├── connection.py         # 已有文件（~200行，基本不动）
├── app.py                # 瘦身后仅 Flask 路由 + WebSocket（~800行）
└── mcp_server.py         # Phase 3 改造
```

### 2.2 提取顺序（每步可独立验证）

**Step 1: 提取 `device_manager.py`（3-4 天）**

把以下内容收进 `DeviceManager` 类：

- 模块级变量：`devices`, `device_names`, `device_types`, `topo_names`, `device_role_counters`
- 模块级锁：`devices_lock`, `name_lock`, `device_role_lock`
- 方法：`connect_device`, `disconnect_device`, `rename_device`, `fetch_device_name`, `scan_devices` 辅助逻辑

**锁策略**：`DeviceManager` 内部用两把锁而非一把。

```python
class DeviceManager:
    def __init__(self):
        self._devices: dict[str, TelnetConnection] = {}
        self._names: dict[str, str] = {}
        self._types: dict[str, str] = {}
        self._state_lock = threading.Lock()   # 保护设备列表增删查
        # 不设 IO 锁——调用方各自管理 I/O 并发

    def list_all(self) -> dict[str, TelnetConnection]:
        """返回设备快照——不持锁期间可安全遍历"""
        with self._state_lock:
            return dict(self._devices)

    def connect(self, port: int) -> tuple[str, TelnetConnection]: ...
    def disconnect(self, path: str) -> bool: ...
    def get(self, path: str) -> TelnetConnection | None: ...
```

**关键设计决策**：心跳 `_check_all` 通过 `list_all()` 获取设备快照后释放锁，再逐个 ping。探测期间不持有 DeviceManager 锁，避免阻塞用户操作。只有修改设备状态时短暂持锁。

**适配清单（Step 1 完成后需要同步改的文件）：**

| 文件 | 原来引用方式 | 改为 |
|------|------------|------|
| `heartbeat.py._check_all` | `devices_lock` + `devices` dict | `dm.list_all()` 返回快照副本 |
| `heartbeat.py._ping` | `devices[path]` 复制 | `dm.replace(path, new_conn)` |
| `topology.py` | `devices` / `device_names` | `dm.get(path)` / `dm.get_name(path)` |
| `app.py` 所有路由 | 直接操作 `devices` dict | `dm.xxx()` 方法调用 |

**Step 2: 提取 `command_executor.py`（2 天）**

```python
class CommandExecutor:
    def __init__(self, device_manager: DeviceManager, knowledge_store: KnowledgeStore):
        self.dm = device_manager
        self.kb = knowledge_store

    def send_command(self, path: str, command: str) -> dict: ...
    def batch_command(self, path: str, commands: list[str], **opts) -> dict: ...
```

`COMMAND_CATALOG` 从 `app.py` 模块级全局变量移入此模块。

**Step 3: 统一知识库为 `knowledge_store.py`（1 天）**

- 保留 `app.py` 内嵌的 `KnowledgeBase` 类
- 删除 `knowledge.py`
- 修复 `_auto_record_knowledge` 中的 `names` → `device_names`

**Step 4: 瘦身 `app.py`（1-2 天）**

删除所有已被移出的类定义和函数。`app.py` 只保留：
- Flask 应用初始化 + CORS/认证中间件
- 所有 `@app.route` 路由函数（调用上述模块）
- SocketIO 事件处理（调用上述模块）
- `__main__` 启动逻辑

**Step 5: Agent 子系统适配（1-2 天）**

这是最容易被遗漏的一步。`agent/` 目录 12 个文件与核心模块有深层回调耦合：

- `agent/bootstrap.py`：`init_agent_runtime()` 创建 `AgentRuntime` 实例，注入一个 `command_executor` 回调函数。当前这个回调是 `app.py` 中的 `send_command` 裸函数。改为接收 `CommandExecutor` 实例。
- `agent/routes.py`：405 行独立的 Flask 路由，有自己的 `_require_auth` 装饰器。路由函数改为调用 `CommandExecutor` + `KnowledgeStore`。
- `agent/knowledge_store.py`：与 `app.py` 的 `KnowledgeBase` 是两套独立实现。评估能否统一到新的 `knowledge_store.py`，或保留桥接层。

### 验证标准

- `app.py` < 1000 行
- 每个抽出模块可独立 `import`
- 冒烟测试与 Phase 0 基线一致
- `knowledge.py` 已删除
- Agent 子系统相关 API 可正常调用

---

## Phase 2.5: async/sync 桥接 ✅ 已完成

**目标：TelnetConnection 同时支持同步和异步调用，避免同步阻塞 MCP 的 asyncio 事件循环。工期 1 天。**

### 改造内容

`connection.py` 新增异步接口：

```python
class TelnetConnection:
    def send_cmd(self, cmd: str) -> str:
        """同步接口——保持向后兼容（Flask 线程使用）"""
        ...  # 现有实现不变

    async def send_cmd_async(self, cmd: str) -> str:
        """异步接口——供 MCP Server 调用，不阻塞事件循环"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.send_cmd, cmd)
```

### 验证标准

- 同步 `send_cmd` 行为不变
- `send_cmd_async` 不阻塞 MCP 事件循环

---

## Phase 3: MCP Server 直连 ✅ 已完成

**目标：MCP 工具不再通过 HTTP 转发，直接调用核心模块。工期 3-4 天。**

### 3.1 架构决策

MCP Server 是唯一的运行时进程。Flask Web UI 从核心依赖降级为可选的只读调试器：

- 日常使用场景：只启动 MCP Server，通过 TRAE/Cursor/Claude Desktop 交互
- 调试场景：手动启动 `python app.py`，打开浏览器查看设备状态（只读）

Flask 的 API 路由改为调用同一套核心模块，但仅保留 GET 类查询端点。

### 3.2 分三批改造（不是一次性）

**批次 1：4 个核心设备工具（1 天）**

```python
# 之前
elif name == "send_command":
    text = await mcp_req("POST", "/api/devices/command", json_data={...})

# 之后
elif name == "send_command":
    conn = dm.get(arguments["path"])
    result = await conn.send_cmd_async(arguments["command"])
    text = json.dumps(result)
```

改造工具：`scan_devices`, `connect_device`, `send_command`, `batch_command`。

验证：MCP Server 不依赖 Flask 进程，单独启动即可完成核心设备操作。

**批次 2：知识库 + 拓扑 + 实验 + 快照工具 ~20 个（1-2 天）**

改造工具：`get_kb_commands`, `search_kb`, `suggest_commands`, `get_best_practices`, `record_experience`, `create_experiment`, `execute_experiment_plan`, `snapshot_config`, `list_snapshots`, `get_snapshot`, `diff_snapshots`, `rollback_config`, `get_topology`, `save_topology`, `find_topology_path`, `get_config_guidance`, `auto_record_experience`, `generate_lab_report`, 等。

**批次 3：Agent Runtime 工具 ~10 个（1-2 天）**

改造工具：`agent_memory_query`, `agent_memory_lessons`, `agent_memory_stats`, `agent_knowledge_search`, `agent_knowledge_best_practices`, `agent_knowledge_troubleshooting`, `agent_plan`, `agent_execute`, `agent_status`, `agent_daily_review`, `config_method_*` 系列。

### 验证标准

- 三批工具全部可用
- MCP Server 单独启动时核心设备操作正常
- 冒烟测试与 Phase 0 基线一致

---

## Phase 4: 修复 Telnet 可靠性

**目标：让 Telnet 读取不再依赖固定超时猜测，正确处理各种命令类型。工期 2-3 天。**

### 4.1 命令分类器

不同命令的响应模式不同：

| 命令类型 | 示例 | 结束标志 | 超时 |
|---------|------|---------|------|
| display | `display current-configuration` | 提示符 + 无 `---- More ----` | 30s |
| diag | `ping`, `tracert` | 统计行 + 提示符 | 10s |
| config | `system-view`, `interface`, `ospf` | 提示符 | 5s |
| interactive | `save`, `reboot`, `reset` | `[Y/N]` 应答 + 提示符 | 10s |

### 4.2 提示符驱动读取

```python
class TelnetConnection:
    # 设备提示符
    PROMPT_PATTERNS = [
        re.compile(rb'<\S+>\s*$'),
        re.compile(rb'\[\S+\]\s*$'),
        re.compile(rb'<\S+>.*\]\s*$'),
    ]

    # 分页标记
    MORE_PATTERN = re.compile(rb'---- More ----')

    # ping/tracert 统计行
    DIAG_DONE_PATTERN = re.compile(rb'--.+packets.+received|packet loss')

    def _has_prompt(self, data: bytes) -> bool:
        lines = data.split(b'\r\n')
        for line in reversed(lines[-4:]):
            stripped = line.strip()
            for pattern in self.PROMPT_PATTERNS:
                if pattern.match(stripped):
                    return True
        return False

    def send_cmd(self, cmd: str) -> str:
        with self.lock:
            cmd_lower = cmd.strip().lower()
            is_diag = cmd_lower.startswith(('ping', 'tracert'))
            is_display = cmd_lower.startswith('display') or cmd_lower.startswith('dir')
            is_interactive = cmd_lower.startswith(('save', 'reboot', 'reset'))

            # 超时策略
            if is_diag:
                deadline = time.time() + 10
            elif is_interactive:
                deadline = time.time() + 10
            else:
                deadline = time.time() + 30

            self._send(cmd)
            chunks = []
            total = 0
            while time.time() < deadline:
                try:
                    self.sock.settimeout(0.2)
                    data = self.sock.recv(65536)
                    if data:
                        chunks.append(data)
                        total += len(data)
                        if total >= 4 * 1024 * 1024:
                            break
                        # 自动翻页
                        if self.MORE_PATTERN.search(b''.join(chunks[-4:])):
                            self.sock.send(b' ')
                            time.sleep(0.15)
                            continue
                        # 诊断命令看到统计行即结束
                        if is_diag and self.DIAG_DONE_PATTERN.search(b''.join(chunks)):
                            break
                        # 其他命令看到提示符即结束
                        if self._has_prompt(b''.join(chunks)):
                            break
                except socket.timeout:
                    if chunks: break
                except OSError:
                    break

            output = self._strip_escape(b''.join(chunks)).decode('gbk', errors='ignore')
            # [Y/N] 自动应答逻辑保留
            ...
            return output
```

### 4.3 心跳探测

从 `select.select()` 改为发送回车探测提示符：

```python
def _ping(self, path: str) -> bool:
    conn = self.dm.get(path)
    if not conn or not conn.sock:
        return False
    try:
        conn.sock.send(b'\r\n')
        time.sleep(0.3)
        data = b''
        deadline = time.time() + 3
        conn.sock.settimeout(0.3)
        while time.time() < deadline:
            try:
                chunk = conn.sock.recv(65536)
                if chunk:
                    data += chunk
                    if self._has_prompt(data):
                        return True
            except socket.timeout:
                if data: return True
            except OSError:
                return False
        return len(data) > 0
    except (ConnectionError, OSError):
        return False
```

**注意：心跳探测必须排队。** 通过 `DeviceManager` 的队列机制确保心跳的 `\r\n` 和用户命令不会在 socket 上交错。

```python
class DeviceManager:
    def __init__(self):
        ...
        self._io_lock = threading.Lock()   # 串行化同一连接的 I/O

    def send_command(self, path: str, cmd: str) -> str:
        conn = self._devices.get(path)
        with conn.lock:   # 每连接一把锁，心跳和用户命令串行
            return conn.send_cmd(cmd)
```

### 验证标准

- `display current-configuration` 大量输出不被截断、不因 `---- More ----` 提前中断
- `ping` 命令不超时，在当前 4s 内正常返回
- 手动断开一个设备，心跳在 2 轮内检测到断连
- 冒烟测试中 `send_command` 输出与 Phase 0 基线一致或更完整

---

## Phase 5: 知识库数据质量治理

**目标：清理脏数据、防止新脏数据进入。工期 1 天。**

### 5.1 数据清理

| 文件 | 问题 | 处理方式 |
|------|------|----------|
| `global_kb.json` | 83% 命令 description 为空 | 填充至少一个关键词描述 |
| `global_kb.json` | 100% 命令 risk 为 unknown | 保守策略：只将明确匹配白名单的标记 `safe`，其余默认 `medium` |
| `devices_kb.json` | success 标记与 output 含 Error 矛盾 | 检查 success 判定逻辑，修正错误记录 |
| `config_methods/_index.json` | `methods_count: 6` 实际只有 1 个 | 修正计数 |

### 5.2 数据写入防护

在 `KnowledgeStore.__add_record` 中增加校验：

- `description` 不能为空字符串
- `output` 含 `Error:` 或 `Unrecognized command` 时强制 `success=False`
- `risk` 不允许 `unknown`，必须选 `safe` / `low` / `medium` / `high`
- 不认识的命令默认标记为 `medium`（宁可误报不漏报）

### 5.3 清理前备份

```bash
cp kb/global_kb.json kb/_backup_global_kb.json
cp kb/devices_kb.json kb/_backup_devices_kb.json
```

### 验证标准

- `global_kb.json` 所有命令有非空 description 和有效 risk 值
- `devices_kb.json` 无 success/Error 矛盾记录

---

## Phase 6: 测试覆盖

**目标：核心路径有测试保护。持续进行。**

### 6.1 分层策略

| 层 | 模块 | 测试方式 | 最低覆盖率 |
|----|------|----------|-----------|
| L1 | `connection.py` | Mock socket，测提示符匹配、[Y/N] 应答、分页翻页、编码转换 | 80% |
| L2 | `device_manager.py` | Mock TelnetConnection，测设备生命周期、并发安全、命名规则 | 80% |
| L3 | `knowledge_store.py` | 纯数据操作，测 CRUD、去重、搜索排序、原子写入、数据校验 | 80% |
| L4 | `command_executor.py` | Mock DeviceManager + KnowledgeStore | 60% |
| L5 | 端到端 | 真实 eNSP 设备 | 4 个核心工具 |

### 6.2 编写优先级

1. `test_knowledge_store.py` — 无外部依赖
2. `test_device_manager.py` — 核心状态管理
3. `test_connection.py` — 协议可靠性
4. `test_command_executor.py` — 命令编排逻辑
5. `test_smoke.py` — 端到端

### 6.3 现有测试

保留 `tests/test_agent_runtime.py` 和 `tests/test_experiment_engine.py`，确认重构后仍通过。

### 验证标准

- L1-L3 运行 `pytest` 全部通过
- 冒烟测试不退化

---

## Phase 7: 项目清理

**目标：删除所有临时文件、死代码、备份目录。工期 0.5 天。**

### 7.1 删除清单

**根目录：**

```
deep_scan.py, scan_campus.py, scan_frontend.py, scan_mcp.py
final_api_test.py
_check_lines.txt, _config_error.txt, _config_output.txt
file_list.csv
```

**mcpensp1/ 内：**

```
check_js.txt, current_html.txt, current_js.txt, current_js2.txt, current_js3.txt
page_content.html
mcp_server.py.bak
server_debug.log
test_caps.py
```

**补丁脚本 + 备份源码：**

```
_patch_app.py, _patch_mcp.py, _patch_mcp_src.py
_experiment_engine_src.py
```

```
backup-website/  backup_20260624/  backup_20260626/
.pytest_cache/
knowledge.py
```

### 7.2 .gitignore 加固

```gitignore
# 日志
*.log

# 备份
backup*/
*.bak

# 补丁脚本
_patch*.py
_experiment_engine_src.py

# Python 嵌入发行版
python312/
```

**不添加 `*.txt` 通配符——避免误伤未来的合法文本文件。**

### 验证标准

- 根目录无 `.py` 脚本（除 `ensp_utils.py`，移到 `mcpensp1/` 内）
- `mcpensp1/` 内无以 `_` 开头的遗留补丁文件
- Git status 无未追踪临时文件

---

## 风险控制

| 风险 | 阶段 | 缓解措施 |
|------|------|---------|
| 拆分过程破坏核心功能 | Phase 2 | 每步后跑冒烟测试；main 分支随时可回退 |
| 双进程内存共享不可能 | Phase 3 | MCP 为唯一运行时，Flask 降为可选只读调试器 |
| 同步 Telnet 阻塞 asyncio | Phase 2.5 | `run_in_executor` 桥接 |
| 心跳探测与命令争夺 socket | Phase 4 | DeviceManager 增加 `_io_lock` 串行化 |
| ping 提示符检测超时 | Phase 4 | 命令分类器 + 统计行匹配 |
| Agent 子系统回调解耦遗漏 | Phase 2 Step 5 | 明确列在拆分步骤中 |
| 知识库清理丢失数据 | Phase 5 | 清理前备份原始 JSON |

---

## 工期估算

| 阶段 | 内容 | 工期 | 状态 |
|------|------|------|------|
| Phase 0 | 安全网 | 0.5 天 | ✅ |
| Phase 1 | 确定性 Bug + 编码修复 + Prompt 外部化 | 1 天 | ✅ |
| Phase 2 | 拆 app.py + Agent 适配 | 8-10 天 | ✅ 部分（核心3模块完成） |
| Phase 2.5 | async/sync 桥接 | 1 天 | ✅ |
| Phase 3 | MCP 直连（分 3 批） | 3-4 天 | ✅ |
| Phase 4 | Telnet 可靠性 | 2-3 天 | ⏳ 待做 |
| Phase 5 | 知识库数据治理 | 1 天 | ⏳ 待做 |
| Phase 6 | 测试覆盖 | 持续 | ⏳ 待做 |
| Phase 7 | 项目清理 | 0.5 天 | ⏳ 待做 |

**已完成工期：约 6-7 天。剩余：约 4-7 天。**
