# Knowledge（KnowledgeBase）

## 位置
`mcpensp1/knowledge.py`

## 职责
管理项目的核心知识库：命令目录、最佳实践、排错案例、实验经验、结构化配置知识。是整个系统最核心的知识层组件。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| `kb_folder` | `str` | 知识库目录路径 |

## 输出

| 方法 | 返回值 |
|------|--------|
| `get_stats()` | `{"total": int, "by_category": {...}}` |
| `get_device_history(path)` | `List[Dict]` |
| `get_device_capabilities(path)` | `Dict` |
| `get_global_commands(...)` | `List[Dict]` |
| `get_command_catalog(...)` | `Dict` |
| `search_experiences(query)` | `List[Dict]` |
| `get_best_practices(...)` | `List[Dict]` |
| `get_structured_kb(...)` | `Dict` |
| `get_troubleshooting_cases(query)` | `List[Dict]` |
| `get_config_guidance(topic)` | `Dict` |
| `get_experiences(experiment)` | `Dict` |

## 数据源
- `mcpensp1/kb/best_practices.json`
- `mcpensp1/kb/troubleshooting_cases.json`
- `mcpensp1/kb/config_methods/*.json`
- `mcpensp1/kb/*.md`（实验流程文档）

## 依赖
- 文件系统（JSON/MD 读写）
- `_build_interface_map()` / `_resolve_interface()` — 接口映射辅助

## 禁止事项
- ❌ 不允许直接暴露内部文件路径
- ❌ 不允许在查询中修改知识库文件
- ❌ 不允许 `_guess_cat` 返回非预期类型

## 调用关系
```
mcp_server.py (52+ tools) → services.py → KnowledgeBase
    ├── get_kb_commands → get_global_commands()
    ├── get_kb_stats → get_stats()
    ├── search_kb → search_experiences()
    ├── get_best_practices → get_best_practices()
    ├── get_config_guidance → get_config_guidance()
    └── suggest_commands → get_device_capabilities()
```
