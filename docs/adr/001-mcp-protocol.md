# ADR-001: 采用 MCP 协议

## 状态
已采纳（2025）

## 背景
项目需要一个标准化的方式让 AI Agent（Claude/Codex）与 eNSP 网络仿真设备交互。传统 REST API 方式存在以下问题：
- 需要 AI 理解 HTTP 请求/响应格式
- 工具发现和管理不便
- 缺乏类型化的参数定义

## 决策
采用 **MCP（Model Context Protocol）** 作为 AI 与系统的唯一外部协议。

## 理由
- **标准化**：MCP 是 Anthropic 提出的开放协议，Codex/Claude 原生支持
- **工具自描述**：每个工具自带 `name`/`description`/`inputSchema`，AI 可自动发现
- **类型安全**：`inputSchema` 使用 JSON Schema 定义参数类型和必填项
- **零 HTTP 开销**：MCP Server 与 AI Client 通过 stdio 通信，无需额外网络端口

## 后果
- 所有对外接口必须通过 MCP Tool 暴露
- Flask Web API 仅用于前端 Dashboard，不作为 AI 接口
- 新增功能优先实现为 MCP Tool，其次考虑 Web API
- 52+ 个 MCP 工具形成完整的网络自动化能力矩阵
