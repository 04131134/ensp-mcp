# ViewRouter（视图感知命令路由）

## 位置
`mcpensp1/view_router.py`

## 职责
华为 VRP 设备的视图感知命令路由。将每条命令映射到所需视图（用户视图 / 系统视图），从 prompt 探测当前视图，必要时自动切换，并提供 VRP 冷却保护（连续 3 次 `quit`/`return` 后等待 3 秒，避免视图切换拥塞）。

## 核心能力
1. `classify(cmd)` 命令分类：根据前缀判断命令应在系统视图还是用户视图执行；导航命令（`system-view`/`quit`/`return`/`exit`）单独归类为 `navigation`。默认归入 `system`。
2. `detect_view(conn)` 视图探测：优先读取连接对象的 `current_view` 属性，否则返回 `unknown`。
3. `ensure_view(conn, path, required_view)` 视图确保：当前视图不符时自动发送 `system-view` 进入系统视图，或 `return` 回到用户视图。
4. `before_command(conn, path, cmd)` 命令前置处理：分类 + 冷却计数 + 自动视图切换，在命令下发前调用。
5. VRP 冷却保护（`_handle_cooldown`）：连续 3 次 `quit`/`return` 后 `time.sleep(3)`，并重置计数。

## 关键设计
- `SYSTEM_VIEW_PREFIXES`：必须在系统视图执行的命令前缀（`interface`/`vlan`/`ospf`/`bgp`/`dhcp`/`undo`/`ip address`/`aaa` 等）。
- `USER_VIEW_PREFIXES`：必须在用户视图执行的命令前缀（`display`/`show`/`ping`/`save`/`system-view` 等）。
- `NAVIGATION_COMMANDS`：导航命令集合。
- 全局单例 `view_router = ViewRouter()`，由 `app.py` 与 `command_executor.py` 直接使用。

## 接入状态
✅ 已接入运行链路：视图判断与自动切换由 `app.py`、`command_executor.py` 通过 `view_router` 单例真实调用，非摆设代码。
