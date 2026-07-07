# Topology（TopologyEngine）

## 位置
`mcpensp1/topology.py`

## 职责
管理网络拓扑图，支持从 JSON 加载、查询邻居、计算最短路径。进程内唯一实例。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| （无） | — | 无参初始化 |

## 输出

| 方法 | 返回值 |
|------|--------|
| `load(data)` | `None` |
| `get_neighbors(nid)` | `List[Dict]` |
| `find_path(start, end)` | `List[str]` 或 `None` |
| `get_device_connections(nid)` | `List[Dict]` |
| `get_summary()` | `Dict` |

## 拓扑数据结构
```json
{
    "nodes": [{"id": "LSW1", "type": "switch", "ports": [...]}, ...],
    "links": [{"source": "LSW1", "target": "LSW2", "port_src": "GE0/0/1", ...}, ...]
}
```

## 依赖
- 无外部依赖（纯内存计算）

## 禁止事项
- ❌ 不允许在不加锁的情况下修改拓扑图
- ❌ 不允许 `find_path` 在无路径时返回非 None
- ❌ 不允许创建第二个 TopologyEngine 实例

## 调用关系
```
mcp_server (get_topology/find_topology_path/save_topology)
    → services.py
    → TopologyEngine
```
