# 架构规则

## 模块分层

```
┌─────────────────────────────────────┐
│          MCP 协议层                  │  mcp_server.py
│          (52+ tools)                │
├─────────────────────────────────────┤
│          服务层                      │  services.py
│     (KB查找/配置方法/拓扑查询)       │
├─────────────────────────────────────┤
│          领域层                      │
│  ┌──────────┬──────────┬─────────┐ │
│  │ Agent    │ Command  │ Topology│ │
│  │ Runtime  │ Executor │ Engine  │ │
│  └──────────┴──────────┴─────────┘ │
├─────────────────────────────────────┤
│          基础设施层                  │
│  ┌──────────┬──────────┬─────────┐ │
│  │ Device   │ Telnet   │ Heartbeat│ │
│  │ Manager  │ Conn     │ Monitor  │ │
│  └──────────┴──────────┴─────────┘ │
├─────────────────────────────────────┤
│          知识层                      │
│  ┌──────────┬──────────┬─────────┐ │
│  │ Knowledge│ KB JSON  │ Config  │ │
│  │ Base     │  Files   │ Methods │ │
│  └──────────┴──────────┴─────────┘ │
└─────────────────────────────────────┘
```

## 核心规则

### 依赖方向

- **上层可依赖下层，下层不可依赖上层**
- `mcp_server → services → domain → infra`
- Agent 模块可调用 CommandExecutor，但不能反向

### 单例模式

以下对象在进程内全局唯一，不允许创建第二个实例：

- `DeviceManager` — 设备连接池
- `KnowledgeBase` — 知识库
- `TopologyEngine` — 拓扑图
- `ConfigMethodStore` — 配置方法

### 线程安全

- `DeviceManager` 使用 `threading.Lock` 保护并发访问
- TelnetConnection 内部使用 asyncio + threading 桥接
- heartbeat 独立线程运行，通过 DeviceManager 获取状态

### 数据隔离

- 静态知识：`mcpensp1/kb/` 目录下的 JSON/MD 文件
- 动态知识：MemoryStore / KnowledgeStore 运行时积累
- 配置快照：`mcpensp1/kb/snapshots/` 目录

## 禁止事项

- ❌ 在 mcp_server 中直接操作 TelnetConnection
- ❌ 在 CommandExecutor 中直接操作设备连接（应通过 DeviceManager）
- ❌ 在多个模块中创建 KnowledgeBase 实例
- ❌ 在 Agent 模块中直接读写磁盘 KB 文件（应通过 MemoryStore/KnowledgeStore）
