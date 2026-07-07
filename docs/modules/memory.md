# Memory（MemoryStore）

## 位置
`mcpensp1/agent/memory.py`

## 职责
Agent 的长期记忆系统。持久化存储实验执行经验、成功/失败模式、可复用命令模板。支持去重和相似度检测。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| `persist_path` | `str` | 持久化文件路径 |

## 输出

| 方法 | 返回值 |
|------|--------|
| `add(entry)` | `str` (entry_id) |
| `recall(query, category, limit)` | `List[MemoryEntry]` |
| `get_lessons(limit)` | `List[MemoryEntry]` |
| `get_error_patterns(limit)` | `List[MemoryEntry]` |
| `get_success_patterns(limit)` | `List[MemoryEntry]` |
| `get_reusable_commands(device_type, limit)` | `List[MemoryEntry]` |
| `summarize_for_prompt(query, limit)` | `str` |
| `ingest_reflection(reflection)` | `int` (条目数) |
| `get_stats()` | `Dict` |
| `export_for_sharing()` | `Dict` |

## 数据结构
```python
class MemoryEntry:
    id: str
    category: str           # success / error / lesson / template
    content: str
    device_type: str
    command: Optional[str]
    importance: float       # 0.0 ~ 1.0
    timestamp: str
    reuse_count: int
```

## 依赖
- 文件系统（JSON 持久化）
- `reflection.ReflectionEntry` — 反思输入

## 禁止事项
- ❌ 不允许重复记录完全相同的条目
- ❌ 不允许在持久化失败时静默丢失数据
- ❌ 不允许跨实验混淆记忆条目

## 调用关系
```
AgentRuntime → MemoryStore
    ├── add() ← 记录每次命令执行
    ├── recall() ← 查询相关记忆
    ├── ingest_reflection() ← 反思引擎输出
    └── get_stats() ← MCP agent_memory_stats
```
