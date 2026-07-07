# DeviceManager

## 位置
`mcpensp1/device_manager.py`

## 职责
全局设备连接池管理。维护所有活跃 TelnetConnection，提供线程安全的增删改查操作。进程内唯一实例（单例模式）。

## 输入
无初始化参数（单例）。

## 输出

| 方法 | 返回值 |
|------|--------|
| `list_all()` | `Dict[str, TelnetConnection]` |
| `get(path)` | `TelnetConnection` 或 `None` |
| `set(path, conn)` | `None` |
| `remove(path)` | `TelnetConnection` 或 `None` |
| `has(path)` | `bool` |
| `get_name(path)` | `str` |
| `set_name(path, name)` | `None` |
| `get_type(path)` | `str` |
| `get_topo_name(port)` | `str` 或 `None` |
| `scan_devices(start, end)` | `List[Dict]` |
| `get_connected_summary()` | `List[Dict]` |
| `next_role_name(role)` | `str` |

## 核心约束

- **线程安全**：使用 `threading.Lock` 保护 `_connections` 字典
- **单例模式**：全局只有一个 DeviceManager 实例
- **自动关闭**：`set()` 时会自动关闭同一 path 的旧连接

## 依赖
- `connection.TelnetConnection` — 连接对象
- `threading.Lock` — 线程安全

## 禁止事项
- ❌ 不允许创建第二个 DeviceManager 实例
- ❌ 不允许在不持有锁时修改 `_connections`
- ❌ 不允许在 Agent 模块中直接操作 TelnetConnection（应通过 DeviceManager）

## 调用关系
```
mcp_server.py → services.py → DeviceManager
command_executor.py → DeviceManager
heartbeat.py → DeviceManager
agent/runtime.py → DeviceManager（通过 _auto_detect_devices）
```
