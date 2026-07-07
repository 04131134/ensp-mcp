# Learning

## 位置
`mcpensp1/agent/learning.py`

## 职责
从实验执行结果中自动学习，更新知识库和记忆系统。实现知识的持续积累和复用。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| `result` | `ExperimentResult` | 实验执行结果 |
| `reflection` | `ReflectionEntry` | 反思结果 |

## 输出
- 写入 MemoryStore：成功模式、失败模式、可复用命令
- 写入 KnowledgeStore：配置经验、最佳实践、故障案例

## 核心流程
```
LearningEngine:
    1. 解析 ExperimentResult + ReflectionEntry
    2. 提取成功命令序列 → MemoryStore (success_patterns)
    3. 提取失败模式 → MemoryStore (error_patterns)
    4. 提取可复用模板 → MemoryStore (templates)
    5. 更新 KnowledgeStore（record_success/record_failure）
    6. 更新实验中学习的经验 → record_experience
```

## 依赖
- `memory.MemoryStore` — 长期记忆
- `knowledge_store.KnowledgeStore` — 增长知识库
- `reflection.ReflectionEngine` — 反思结果

## 禁止事项
- ❌ 不允许重复记录完全相同的经验
- ❌ 不允许遗漏反思中的重要教训
- ❌ 不允许跨实验混淆知识记录

## 调用关系
```
AgentRuntime.execute_task()
    └── LearningEngine.learn_from_result(result, reflection)
        ├── MemoryStore.add() → 成功/失败模式
        ├── KnowledgeStore.record_success()
        ├── KnowledgeStore.record_failure()
        └── KnowledgeStore.record_best_practice()
```
