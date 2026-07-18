# ConfigMethodStore

## 位置
`mcpensp1/config_method_store.py`

## 职责
配置方法库：以 JSON 文件形式持久化"标准配置流程"（配置方法），支持按类别组织、检索、增改、使用成功率统计，并为 MCP 工具 `config_method_*` 提供数据支撑。每条配置方法包含步骤命令、验证命令、排错案例等结构化字段。

## 核心方法

| 方法 | 说明 |
|------|------|
| `get_method(method_id)` | 按 ID 获取单条配置方法 |
| `list_methods(category=None)` | 列出全部方法（可按类别过滤） |
| `search_methods(keyword)` | 关键词搜索配置方法 |
| `add_method(method_data)` | 新增配置方法（含 id/name/category/steps 等字段） |
| `update_method(method_id, updates)` | 更新方法（如补充成功经验、成功率） |
| `record_usage(method_id, success=True)` | 记录一次使用及成败，更新使用统计 |
| `get_method_commands(method_id)` | 返回该方法的步骤命令列表 |
| `get_method_steps(method_id)` | 返回结构化步骤（含命令/说明） |
| `get_verification_commands(method_id)` | 返回验证命令列表 |
| `get_troubleshooting(method_id)` | 返回排错案例列表 |
| `export_methods_summary()` | 导出方法摘要文本 |

## 依赖
- 服务层 `services.py` / MCP 工具 `config_method_*` — 间接调用本类
- 文件系统：配置方法 JSON 持久化于 `kb/` 目录（由构造参数 `kb_folder` 指定）

## 数据流
MCP 工具 `config_method_list/get/search/add/update/steps` → `ConfigMethodStore` → `kb/` 下 JSON 文件；`record_usage` 在方法被成功应用后更新成功率与使用次数。

## 另见
- `docs/modules/knowledge.md` —— 结构化命令知识库
