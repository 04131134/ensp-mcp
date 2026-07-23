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

## v3.1 增强（第二阶段：数据质量修复）

### 修复的问题
1. **device_type 硬编码 'huawei'** → 改为 `_infer_device_type(result)` 推断
2. **record_verify_method 传空 commands=[]** → 改为 `_extract_verify_commands(vr)` 提取

### 新增接口

| 接口 | 说明 |
|------|------|
| `DEFAULT_DEVICE_TYPE = 'huawei'` | 模块级常量，eNSP 平台默认设备类型（消除魔法字符串散落） |
| `_infer_device_type(result)` | 从实验结果推断设备类型，当前默认 huawei，预留多厂商扩展口 |
| `_extract_verify_commands(vr)` | 从 VerificationResult.evidence 提取命令，兜底用 check_name |

### verify_method 命令提取规则
1. 优先取 `vr.evidence['command']`（字符串）
2. 其次取 `vr.evidence['commands']`（列表）
3. 兜底用 `vr.check_name`（保证非空，不再是 `[]`）
