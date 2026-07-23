# Reflection（ReflectionEngine）

## 位置
`mcpensp1/agent/reflection.py`

## 职责
实验结束后自动总结：分析成功/失败原因、提取可复用经验、推荐最佳实践、生成知识更新建议。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| `result` | `ExperimentResult` | 实验执行结果 |

## 输出
- `ReflectionEntry`：what_went_well / what_went_wrong / lessons_learned / optimization_suggestions / knowledge_updates / summary

## 依赖
- `agent/types.py` — 数据结构
- `agent/error_library.py` — 错误原因查询（v3.1，可选注入）

## 禁止事项
- ❌ 不允许遗漏失败节点的分析
- ❌ 不允许因果分析异常破坏 reflect 主流程

## 调用关系
```
AgentRuntime.execute_task()
    └── ReflectionEngine.reflect(result) → ReflectionEntry
          ├── 遍历 plan.nodes 总结成功/失败
          ├── 遍历 verification_results 学习
          ├── _analyze_failure_causes() → 因果分析（v3.1，第二阶段 Step9）
          ├── _extract_lessons() → 经验教训
          ├── _suggest_knowledge_updates() → 知识更新建议
          └── _generate_summary() → 摘要
```

## v3.1 增强（第二阶段 Step9：因果分析）

### 修复的问题
- 反思从"纯字符串拼接"升级为"结构化因果分析"
- 失败节点关联 error_library，输出 `{cause, fix, confidence}` 而非泛化"检查依赖和视图"

### 新增接口（向后兼容，可选注入）

| 接口 | 说明 | 默认 |
|------|------|------|
| `set_error_library(lib)` | 注入 ErrorLibrary，启用失败节点因果分析 | None（回退原行为） |
| `causal_reflection: bool` | 开关：是否做因果分析 | True |

### 因果分析流程
`reflect` 在验证结果学习后、经验提取前调用 `_analyze_failure_causes`：
1. 遍历 plan 中 `status=failed` 的节点
2. 从 `node.result['error']` 提取错误文本
3. 调 `error_library.lookup(error_text)` 查询原因与修复建议
4. 命中则追加结构化因果到 `what_went_wrong` 和 `optimization_suggestions`
5. 任一步异常静默跳过该节点（不破坏 reflect 主流程）

### 接入方式
`AgentRuntime.__init__` 自动注入（try/except 容错）：
```python
from .error_library import ErrorLibrary
self.reflection.set_error_library(ErrorLibrary(kb/errors/huawei_errors.json))
```
注入失败时 log warning，reflection 回退原有字符串拼接行为。
