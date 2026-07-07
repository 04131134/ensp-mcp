# CommandGenerator（命令生成器）

## 位置
`mcpensp1/agent/command_generator.py`

## 职责
根据当前 CLI 视图状态和 Planner 输出的 Action，自动生成完整的 CLI 命令序列（含视图导航命令）。

## Action 类型
```python
Action("configure_interface", params={"ifname": "GigabitEthernet0/0/1", "ip_address": "10.0.0.1"})
Action("configure_vlan", params={"vlan_id": "10"})
Action("display", params={"commands": ["display version"]})
```

## 核心能力
- 自动补全 `system-view` / `quit` / `return`
- Action → CLI 命令映射
- 自动返回值用户视图（可选）
- 批量 Action 顺序生成

## 依赖
- `cli_state.CLIState` — 当前视图状态

## 禁止事项
- 不允许 Planner 直接生成 CLI 字符串
