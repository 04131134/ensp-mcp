# Transaction（事务管理器）

> ⚠️ **状态：未接入运行链路（实验性 / 候选能力）**
> 本模块代码已实现，但 `AgentRuntime` **从未实例化或使用 `TransactionManager`**，全仓仅测试引用。因此文档中的“事务性执行 / 回滚（Snapshot → Execute → Verify → Commit → Rollback）”**当前并未生效**——执行失败不会自动回滚。本文档描述的是设计意图，非已上线功能。如需启用，须在 `runtime.py` 的 `execute_task` 中包裹事务（属于架构增强，非缺陷修复）。

## 位置
`mcpensp1/agent/transaction.py`

## 职责
配置操作的事务性执行框架。Snapshot → Execute → Verify → Commit → Rollback。

## 事务状态机
INIT → SNAPSHOTTING → EXECUTING → VERIFYING → COMMITTING → COMPLETED / FAILED

## 核心接口
| 方法 | 说明 |
|------|------|
| `run(tx, executor_fn)` | 执行完整事务流程 |
| `run_batch(txs, executor_fn)` | 批量事务执行 |
| `rollback(tx_id, rollback_fn)` | 手动回滚 |
| `get_status(tx_id)` | 查询事务状态 |

## 依赖
- `CommandExecutor`（外部注入）— 命令执行
- `snapshot_provider`（外部注入）— 快照保存

## 禁止事项
- 不允许在无回滚方案时执行破坏性操作
