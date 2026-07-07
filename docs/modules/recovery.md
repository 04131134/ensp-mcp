# Recovery（ReflectionEngine）

## 位置
`mcpensp1/agent/reflection.py`

## 职责
对实验执行结果进行反思，提取经验教训，生成知识更新建议。Recovery 功能嵌入在 AgentRuntime 的计划执行循环中。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| `result` | `ExperimentResult` | 实验执行结果 |

## 输出
```python
ReflectionEntry:
    experiment_id: str
    success: bool
    lessons: List[str]
    knowledge_updates: List[Dict]
    summary: str
    importance: float
```

## 核心方法

| 方法 | 说明 |
|------|------|
| `reflect(result)` | 主入口，生成反思结果 |
| `_extract_lessons(result)` | 从成功/失败中提取教训 |
| `_suggest_knowledge_updates(result)` | 生成知识库更新建议 |
| `_generate_summary(result, reflection)` | 生成可读摘要 |

## Recovery 策略（在 AgentRuntime 中实现）

| 策略 | 说明 |
|------|------|
| `retry` | 重试当前节点，最多 max_rounds 次 |
| `skip` | 跳过当前节点，继续执行 |
| `abort` | 终止整个实验 |

## 依赖
- `planner.DAGPlanner.update_plan_after_failure()` — 失败后更新计划
- `memory.MemoryStore.ingest_reflection()` — 写入反思
- `knowledge_store.KnowledgeStore` — 写入知识更新

## 禁止事项
- ❌ 不允许在反思中遗漏失败节点
- ❌ 不允许生成空的经验教训
- ❌ 不允许在 retry 成功后将失败记录为 success

## 调用关系
```
AgentRuntime.execute_task()
    └── ReflectionEngine.reflect(result)
        ├── _extract_lessons()
        ├── _suggest_knowledge_updates()
        └── _generate_summary()
    └── AgentRuntime._execute_plan_loop() → Recovery 策略
        ├── retry → _execute_config_node/_execute_verify_node
        ├── skip → 继续下一个节点
        └── abort → 终止
```
