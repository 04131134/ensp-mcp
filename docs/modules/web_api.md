# Flask Web API

## 位置
`mcpensp1/app.py`（`app` Flask 实例）+ `mcpensp1/agent/routes.py`（由 `init_agent_runtime(app, ...)` 在导入时注册）

## 职责
eNSP-MCP 的 Web 控制台后端。所有对外 HTTP 接口与 SocketIO 事件均在此暴露，供前端 Dashboard（静态资源 `static/app.js`）调用。**注意**：AI Agent 不直接走 REST，AI 交互统一经 MCP 协议（`mcp_server.py`）；此处接口是给人/前端用的。

## 通用约定
- 基础路径：`http://127.0.0.1:5000`（本地 eNSP 配套 Web 服务）
- 请求/响应均为 JSON；成功响应统一包裹为 `{"success": true, ...}`，失败为 `{"success": false, "error": "..."}`（见 `command_executor.md` 返回契约）
- 查询参数走 query string，写操作走 JSON body
- 本文件由运行时 `app.url_map` 探测生成，并由 `tests/test_web_api_doc.py` 守护：新增/删除路由或文档漂移会导致该测试失败

## Dashboard
| Method | Path | 说明 |
|--------|------|------|
| GET | / | Web 控制台主页（设备连接、命令下发、知识库浏览） |

## Health
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/health | 健康检查，返回服务运行状态 |

## Devices（设备连接与命令）
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/devices | 列出当前已连接设备及其状态 |
| GET | /api/devices/scan | 扫描 2000–2050 端口发现 eNSP 设备 |
| POST | /api/devices/connect | 连接指定端口设备，自动识别型号/主机名。body: `{"port": int}` |
| POST | /api/devices/command | 向设备发送单条命令。body: `{"path": str, "command": str}` |
| POST | /api/devices/disconnect | 断开设备连接。body: `{"path": str}` |
| POST | /api/devices/fetch-name | 从设备获取真实主机名。body: `{"path": str}` |
| GET | /api/devices/heartbeat | 设备保活/心跳状态 |
| POST | /api/devices/rename | 重命名设备。body: `{"path": str, "name": str}` |
| POST | /api/devices/batch-command | 批量下发命令，自动视图切换 / `undo t m`。body: `{"path", "commands": [], "wait", "auto_view", "auto_undo_tm"}` |
| POST | /api/devices/group-command | 向多台设备发送相同命令。body: `{"paths": [], "command": str}` |
| POST | /api/devices/verify | 验证设备配置/状态。body: `{"path": str, ...}` |

## Knowledge Base（知识库）
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/kb/commands | 知识库命令列表 |
| GET | /api/kb/catalog | 命令目录（按类别/风险/设备类型） |
| GET | /api/kb/capabilities | 设备能力矩阵 |
| GET | /api/kb/stats | 知识库统计信息 |
| GET | /api/kb/suggest | 按型号推荐命令。query: `model`, `view_type` |
| GET | /api/kb/structured | 结构化知识库（按拓扑/型号分类）。query: `model`, `view_type` |
| GET | /api/kb/devices | 按设备的命令历史/能力 |
| GET | /api/kb/devices/<path:p> | 指定设备的命令记录 |
| GET | /api/kb/troubleshooting | 排错知识库。query: `symptom` |
| GET | /api/kb/help | 查询特定命令帮助。query: `cmd` |
| GET | /api/kb/search | 知识库全文搜索。query: `q`, `limit` |
| POST | /api/kb/scan | 扫描历史设备识别型号并推荐命令。body: `{"path": str}` |
| POST | /api/kb/detect-view | 探测设备当前视图（用户 `< >` / 系统 `[ ]`）。body: `{"prompt": str}` |
| POST | /api/kb/reload | 重新加载结构化知识库（外部修改 KB 文件后） |
| POST | /api/kb/auto-extract | 自动提取设备命令序列并归纳实验记录。body: `{"path": str}` |
| GET | /api/kb/experience | 获取实验经验记录。query: `experiment` |
| POST | /api/kb/experience | 记录实验经验。body: `{"experiment", "date", "topology", "features_implemented", "new_commands_learned", "lessons_learned", "troubleshooting_cases"}` |
| GET | /api/kb/best-practice | 获取最佳实践规范。query: `priority`, `applies_to` |
| POST | /api/kb/best-practice | 记录最佳实践。body: `{"priority", "applies_to", ...}` |
| POST | /api/kb/lab-report | 生成实验报告（Markdown）。body: `{"name": str, "paths": []}` |

## Topology（拓扑）
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/topology | 获取拓扑摘要 |
| POST | /api/topology | 保存/更新拓扑数据。body: `{"data": {"nodes", "links"}}` |
| GET | /api/topology/path | 查找两设备间最短路径。query: `start`, `end` |
| GET | /api/topology/device/<path:nid> | 获取设备的连接与端口信息 |
| POST | /api/topology/file | 上传拓扑文件。body: 文件或多部分表单 |

## Config Methods（配置方法库）
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/config-methods/list | 列出配置方法（可选按类别）。query: `category` |
| GET | /api/config-methods/get/<method_id> | 获取指定方法的详情（步骤/验证/注意事项） |
| GET | /api/config-methods/search | 搜索配置方法。query: `keyword` |
| GET | /api/config-methods/steps/<method_id> | 获取方法的步骤命令列表（可直接执行） |
| GET | /api/config-methods/summary | 配置方法摘要 |
| POST | /api/config-methods/add | 新增配置方法。body: `{"method_data": {"id","name","category","steps",...}}` |
| POST | /api/config-methods/update/<method_id> | 更新方法（补充成功经验、成功率等）。body: `{"updates": {...}}` |

## Experiments（实验）
| Method | Path | 说明 |
|--------|------|------|
| GET | /api/experiments | 列出实验 |
| POST | /api/experiments | 创建实验。body: `{"goal", "experiment_type", ...}` |
| GET | /api/experiments/<exp_id> | 实验详情 |
| POST | /api/experiments/<exp_id>/plan | 生成 DAG 执行计划 |
| POST | /api/experiments/<exp_id>/verify | 验证实验结果 |
| GET | /api/experiments/dependency-graph | 实验依赖图 |

## Agent Runtime（AI Agent 子系统）
由 `init_agent_runtime` 在启动时注册，对应 `mcp_server.py` 的 `agent_*` MCP 工具。
| Method | Path | 说明 |
|--------|------|------|
| POST | /api/agent/plan | 生成 DAG 执行计划（配置前推荐）。body: `{"goal", "experiment_type"}` |
| POST | /api/agent/execute | 一键闭环实验执行（推荐）。body: `{"request", "device_paths", "experiment_type", "constraints"}` |
| GET | /api/agent/status | Agent 运行时状态与统计 |
| GET | /api/agent/status/<experiment_id> | 指定实验的状态 |
| GET | /api/agent/reflection/<experiment_id> | 实验反思结果 |
| POST | /api/agent/learning/daily-review | 记忆每日复盘与优化 |
| GET | /api/agent/memory | 长期记忆查询 |
| GET | /api/agent/memory/lessons | 实验经验教训 |
| GET | /api/agent/memory/errors | 错误案例 |
| GET | /api/agent/memory/commands | 记忆中的命令 |
| GET | /api/agent/memory/templates | 记忆模板 |
| GET | /api/agent/memory/stats | 记忆统计 |
| GET | /api/agent/memory/export | 导出记忆 |
| POST | /api/agent/memory/import | 导入记忆。body: 记忆数据 |
| GET | /api/agent/knowledge/search | 搜索增长知识库。query: `query`, `category`, `device_type`, `limit` |
| GET | /api/agent/knowledge/stats | 知识统计 |
| GET | /api/agent/knowledge/success-cases | 成功案例 |
| GET | /api/agent/knowledge/failure-cases | 失败案例 |
| GET | /api/agent/knowledge/troubleshooting | 历史排错案例 |
| GET | /api/agent/knowledge/best-practices | 网络配置最佳实践 |
| GET | /api/agent/knowledge/templates | 知识模板 |
| GET | /api/agent/knowledge/export | 导出知识 |
| POST | /api/agent/knowledge/import | 导入知识。body: 知识数据 |

## SocketIO 事件
前端经 WebSocket 实时交互，事件与上方 Devices 的 HTTP 操作一一对应：
| 事件 | 说明 | 典型 payload |
|------|------|-------------|
| `connect` | 客户端建立连接 | — |
| `scan` | 扫描设备端口 | — |
| `get_connected_devices` | 获取已连接设备列表 | — |
| `connect_device` | 连接设备 | `{"port": int}` |
| `send_command` | 发送命令 | `{"path": str, "command": str}` |
| `disconnect_device` | 断开设备 | `{"path": str}` |
| `rename_device` | 重命名设备 | `{"path": str, "name": str}` |
| `fetch_device_name` | 获取设备名 | `{"path": str}` |

## 另见
- `docs/modules/command_executor.md` —— 命令执行与返回契约
- `docs/modules/knowledge.md` —— 结构化命令知识库
- `docs/architecture/system.md` —— 系统架构概述
