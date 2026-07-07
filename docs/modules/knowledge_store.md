# KnowledgeStore

## 位置
`mcpensp1/agent/knowledge_store.py`

## 职责
Agent 的增长知识库：记录配置成功/失败经验、最佳实践、验证方法、配置顺序、实验模板。随实验积累自动增长。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| `persist_path` | `str` | 持久化文件路径 |

## 输出

| 方法 | 返回值 |
|------|--------|
| `add(record)` | `str` (record_id) |
| `search(query, category, device_type, limit)` | `List[KnowledgeRecord]` |
| `query_for_task(task, device_type)` | `Dict` |
| `record_success(task, commands, device_type)` | `None` |
| `record_failure(task, commands, error, device_type)` | `None` |
| `record_best_practice(title, content, tags)` | `None` |
| `record_config_order(type, steps, device_type)` | `None` |
| `record_verify_method(protocol, commands, expected, device_type)` | `None` |
| `get_stats()` | `Dict` |
| `summarize_for_prompt(task, device_type)` | `str` |

## 与 KnowledgeBase 的区别

| 维度 | KnowledgeBase | KnowledgeStore |
|------|-------------|----------------|
| 数据来源 | 静态 JSON/MD 文件 | Agent 运行时积累 |
| 更新方式 | 手动编辑 | 自动写入 |
| 内容 | 通用知识（命令目录、最佳实践） | 个性化经验（成功/失败模式） |
| 增长性 | 相对稳定 | 持续增长 |

## 依赖
- 文件系统（JSON 持久化）
- `agent/types.py` — 数据结构

## 禁止事项
- ❌ 不允许与 KnowledgeBase 的职责混淆
- ❌ 不允许在持久化失败时丢弃数据
- ❌ 不允许在 record_success 时写入空命令列表

## 调用关系
```
AgentRuntime → KnowledgeStore
    ├── record_success() ← 命令执行成功
    ├── record_failure() ← 命令执行失败
    ├── search() ← 查询相关经验
    └── summarize_for_prompt() ← 生成提示上下文
```
