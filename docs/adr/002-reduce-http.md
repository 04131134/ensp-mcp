# ADR-002: 减少 HTTP 调用（工具直连模式）

## 状态
已采纳（2025-06）

## 背景
早期架构中 MCP Server 通过 HTTP 调用 Flask Web API 来执行设备操作。这导致：
- 每次命令调用多一次 HTTP 往返（延迟增大）
- Flask 成为单点瓶颈
- 错误传递链路过长（MCP → HTTP → Flask → CommandExecutor）

## 决策
MCP Server 中的工具函数**直接调用 Python 模块**，跳过 HTTP 转发。

## 理由
- **减少延迟**：命令直连比 HTTP 转发快 50-100ms
- **简化调用链**：MCP → CommandExecutor，而非 MCP → HTTP → Flask → CommandExecutor
- **降低耦合**：MCP Server 不再依赖 Flask 运行
- **统一单例**：services.py 提供共享的 KnowledgeBase/TopologyEngine/ConfigMethodStore 单例

## 后果
- 从 45+ 个 HTTP 调用降至 ~10 个（仅前端 Dashboard 保留）
- Flask 降级为纯前端服务
- services.py 成为 MCP 和 Flask 共享的服务层
- 所有工具函数内部需处理错误和返回结构，而非依赖 HTTP 错误码
