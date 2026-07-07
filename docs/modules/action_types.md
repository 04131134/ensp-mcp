# ActionTypes（内部统一 AST）

## 位置
`mcpensp1/agent/action_types.py`

## 职责
定义内部统一 AST 数据结构。不在内部保存 CLI 字符串，CLI 仅由 Generator 生成。

## 数据结构
- **ActionType**：18 种 Action 类型枚举
- **ProtocolObject**：协议描述（协议名/参数）
- **ConfigObject**：单次配置操作（目标/设备/验证/前置条件）
- **ActionNode**：依赖图节点（状态/重试/超时）
- **ActionPlan**：完整执行计划（节点列表/协议对象/元信息）

## 依赖
无外部依赖（纯数据结构）

## 禁止事项
- 不允许在 AST 中保存 CLI 字符串
- 不允许绕过 Generator 直接拼接命令
