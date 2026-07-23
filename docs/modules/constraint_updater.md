# ConstraintUpdater

## 位置
`mcpensp1/agent/constraint_store.py` 和 `mcpensp1/agent/constraint_updater.py`

## 职责
将错误分类结果转化为设备能力约束、蓝图修正或错误统计记忆。`ConstraintStore` 每次写入均先读取当前 JSON 文件，写入同目录临时文件并以原子替换提交，防止中断损坏约束文件。

## 核心接口
`ConstraintUpdater.update_from_error(error_record)` 返回约束是否已记录、已更新的蓝图数量和是否写入记忆。

## 更新规则
- `device_not_supported`：存储错误分类器提供的命令约束；若记录额外提供 `device_model` 或 `device_info.model`，从匹配命令模式的蓝图中移除该型号。
- `context_error`：当记录提供 `failed_command` 与 `required_view` 或 `view_entry_command` 时，为命中蓝图增加视图前置条件并补齐进入命令。
- 其他错误：仅写入 `MemoryStore` 的错误类别，用于后续统计。

约束与记忆都会保存时间戳和可选的 `task_id`。由于错误分类器的基础返回结构不含设备型号、任务标识和缺失视图，调用方需要在需要精确更新蓝图时追加这些可选上下文字段。
