# Transaction（事务管理器）

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
