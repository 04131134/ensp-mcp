# eNSP MCP Server — 知识库驱动的设备配置工具

## 核心理念

**通过持续积累经验，让AI仅靠本地知识库就能完成eNSP模拟器的所有设备配置，无需联网。**

知识库不是一次性产物，而是随每次实验持续增长的经验库。每次实验后提取新发现的命令、排障经验、最佳实践，写入知识库，使AI工具越来越熟练。

---

## 功能总览

| 功能类别 | 功能 | 说明 |
|---------|------|------|
| **设备管理** | 扫描/连接/断开/重命名 | Telnet连接eNSP设备，自动识别型号 |
| **命令执行** | 单条/批量/分组发送 | 支持自动视图切换、自动undo t m、Y/N自动应答 |
| **配置管理** | 快照/对比/回滚 | 配置前自动快照，支持diff对比和一键回滚 |
| **知识库** | 结构化命令库 | 5种设备型号，200+命令，按视图/主题分类 |
| **经验积累** | 实验经验/排障案例 | 每次实验后记录新命令、教训、排障案例 |
| **智能建议** | 上下文感知推荐 | 分析已执行命令，推荐下一步配置操作 |
| **配置模板** | 7种模板自动生成 | VLAN/VRRP/MSTP/DHCP/OSPF/LACP/WLAN |
| **知识搜索** | 全文搜索+命令帮助 | 搜索命令、排障经验、实验记录 |
| **实验报告** | 自动生成Markdown报告 | 汇总设备配置、执行统计、知识库数据 |
| **拓扑引擎** | 解析/路径查找 | 支持.topo文件，自动提取设备名和连线 |
| **心跳监控** | 自动检测+重连 | 定期ping检测，断线自动重连 |
| **WebSocket** | 实时终端 | 浏览器实时终端输出，支持多设备标签页 |
| **Web UI** | 9个Tab暗色主题+CSP安全 | 结构化命令/操作规范/实验经验/排障/配置顺序/运行时/搜索/配置模板/实验报告 |
| **MCP协议** | 39个AI工具 | 供AI Agent直接调用，覆盖全部功能 |

---

## 操作规范（每次配置前必须遵守）

### 规则一：配置前检测视图类型

| 视图 | 提示符格式 | 可执行命令 |
|------|-----------|-----------|
| **用户视图** | `<设备名>` 以 `>` 结尾 | `display`、`save`、`ping`、`system-view`、`undo t m` |
| **系统视图** | `[设备名]` 以 `]` 结尾 | `interface`、`vlan`、`ospf`、`vrrp`、`ip address` 等 |

> **批量命令模式下自动检测视图并切换，无需手动处理。**

### 规则二：配置前关闭日志

```
undo terminal monitor
```

> **批量命令模式下自动在第一条命令前执行 `undo t m`。**

### 规则三：配置后保存

所有设备配置完成后必须执行 `save` 命令保存配置。

---

## API 端点总览（46个）

### 设备管理（12个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices/scan?start=2000&end=2024` | 扫描端口范围 |
| POST | `/api/devices/connect` | 连接设备 `{port}` |
| POST | `/api/devices/disconnect` | 断开设备 `{path}` |
| GET | `/api/devices` | 已连接设备列表 |
| POST | `/api/devices/command` | 发送单条命令 `{path, command}` |
| POST | `/api/devices/batch-command` | **批量发送命令** `{path, commands[], wait, auto_view, auto_undo_tm}` |
| POST | `/api/devices/group-command` | **分组命令** `{paths[], command}` |
| POST | `/api/devices/rename` | 重命名设备 |
| POST | `/api/devices/fetch-name` | 从设备获取真实主机名 |
| POST | `/api/devices/suggest-next` | **上下文感知建议** `{path}` |
| GET | `/api/devices/heartbeat` | 心跳状态 |
| GET | `/api/health` | 健康检查 |

### 配置快照（4个）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/devices/snapshot` | **创建快照** `{path, label}` |
| GET | `/api/devices/snapshots?path=` | **快照列表** |
| GET | `/api/devices/snapshot/<id>` | **获取快照内容** |
| POST | `/api/devices/diff` | **配置对比** `{snapshot1, snapshot2}` 或 `{config1, config2}` |
| POST | `/api/devices/rollback` | **回滚配置** `{path, snapshot_id}` |

### 知识库 — 结构化命令（8个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kb/structured` | 完整结构化知识库 |
| GET | `/api/kb/structured/<type>` | 按设备型号过滤 |
| GET | `/api/kb/suggest?model=LSW1` | 命令建议 |
| POST | `/api/kb/scan` | 扫描设备返回建议 `{path}` |
| GET | `/api/kb/config-order` | 推荐配置顺序（20步） |
| GET | `/api/kb/search?q=关键词` | **知识库全文搜索** |
| GET | `/api/kb/help?cmd=命令` | **命令帮助查询** |
| POST | `/api/kb/detect-view` | 视图检测 `{prompt}` |

### 知识库 — 配置模板（3个）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/kb/template` | **生成配置模板** `{type, params}` |
| GET | `/api/kb/templates` | **模板列表** |
| 支持类型 | vlan/vrrp/mstp/dhcp/ospf/lacp/wlan | 7种常用配置模板 |

### 知识库 — 经验与规范（4个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kb/best-practice` | 操作规范 |
| POST | `/api/kb/best-practice` | 添加新规范 |
| GET | `/api/kb/experience` | 实验经验列表 |
| POST | `/api/kb/experience` | 记录实验经验 |
| GET | `/api/kb/troubleshooting` | 排障知识库 |
| POST | `/api/kb/lab-report` | **自动生成实验报告** `{name, paths[]}` |

### 知识库 — 运行时（6个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kb/commands` | 全局命令记录 |
| GET | `/api/kb/catalog` | 命令目录 |
| GET | `/api/kb/devices` | 设备维度记录 |
| GET | `/api/kb/capabilities` | 设备能力矩阵 |
| GET | `/api/kb/stats` | 知识库统计 |
| POST | `/api/kb/reload` | 重新加载知识库 |

### 拓扑（5个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/topology` | 拓扑摘要 |
| POST | `/api/topology` | 保存拓扑 |
| POST | `/api/topology/file` | 上传.topo文件 |
| GET | `/api/topology/path` | 路径查找 |
| GET | `/api/topology/device/<id>` | 设备连接信息 |

---

## MCP 工具（39个）

供 AI Agent 通过 MCP 协议调用：

### 设备操作
`scan_devices` · `connect_device` · `send_command` · `disconnect_device` · `get_connected_devices` · `rename_device` · `fetch_device_name` · `batch_command` · `group_command`

### 配置管理
`snapshot_config` · `list_snapshots` · `get_snapshot` · `diff_snapshots` · `rollback_config`

### 智能建议
`suggest_commands` · `suggest_next_steps` · `scan_device_commands` · `detect_device_view` · `get_command_help`

### 知识库
`get_structured_kb` · `get_command_catalog` · `get_device_capabilities` · `get_device_history` · `get_kb_commands` · `get_kb_stats` · `search_kb` · `reload_kb`

### 经验与规范
`get_best_practices` · `get_experiences` · `record_experience` · `get_troubleshooting_kb` · `get_config_order` · `generate_lab_report`

### 配置模板
`generate_config_template` · `list_templates`

### 拓扑
`get_topology` · `save_topology` · `find_topology_path` · `get_topology_device`

---

## 新增功能详解

### 1. 批量命令（自动视图切换 + 自动 undo t m）

一次发送多条命令，自动处理视图切换和日志关闭：

```json
POST /api/devices/batch-command
{
  "path": "127.0.0.1:2012",
  "commands": ["vlan batch 10 20 30", "interface Vlanif10", "ip address 192.168.1.100 255.255.255.0"],
  "auto_view": true,
  "auto_undo_tm": true,
  "wait": 0.1
}
```

返回每条命令的执行结果、成功/失败统计、总耗时。

### 2. 配置快照 + 对比 + 回滚

```json
// 创建快照
POST /api/devices/snapshot  {"path": "127.0.0.1:2012", "label": "before-change"}

// 对比两个快照
POST /api/devices/diff  {"snapshot1": "LSW1_20260616_100000_before-change", "snapshot2": "LSW1_20260616_110000_after-change"}

// 回滚到指定快照
POST /api/devices/rollback  {"path": "127.0.0.1:2012", "snapshot_id": "LSW1_20260616_100000_before-change"}
```

### 3. 上下文感知建议

分析设备已执行的命令，按设备角色（SW1/SW2/FW/AR/AC等）匹配配置阶段，推荐下一步：

```json
POST /api/devices/suggest-next  {"path": "127.0.0.1:2012"}
```

返回：
- `completed_topics`: 已完成的配置主题
- `current_phase`: 当前阶段
- `next_steps`: 推荐的下一步命令列表
- `progress`: 完成进度（如 "3/9"）

### 4. 知识库全文搜索

```json
GET /api/kb/search?q=VRRP&limit=10
```

搜索结构化命令库、排障知识库、实验经验，按相关度排序返回。

### 5. 配置模板生成

```json
POST /api/kb/template
{
  "type": "vrrp",
  "params": {"vlan_id": "10", "ip": "192.168.1.100", "mask": "255.255.255.0", "vrid": "10", "vip": "192.168.1.254", "priority": "120"}
}
```

支持 7 种模板：`vlan` · `vrrp` · `mstp` · `dhcp` · `ospf` · `lacp` · `wlan`

### 6. 实验报告自动生成

```json
POST /api/kb/lab-report  {"name": "校园网综合设计实训"}
```

自动汇总所有设备的配置历史、命令执行统计、知识库数据，生成 Markdown 格式报告。

### 7. Y/N 自动应答

`send_cmd` 自动检测 `[Y/N]` 或 `(Y/N)` 提示并回复 `y`，支持 `save`、`ap-group`、`security wpa2` 等命令。

---

## 知识库架构

### 四层知识体系

```
第1层：操作规范 (best_practices)        ← 永远适用的规则
第2层：设备命令库 (user/system_view)    ← 按设备型号×视图×主题分类
第3层：实验经验 (experiences)           ← 每次实验后积累
第4层：运行时记录 (global/devices_kb)   ← 每次命令执行自动记录
```

### 支持的设备型号

| 型号 | 类型 | 系统视图主题 |
|------|------|-------------|
| S5700 | 核心/汇聚交换机 | 基础、VLAN、VLANIF、VRRP、MSTP、DHCP、OSPF、LACP |
| S3700 | 接入层交换机 | 基础、端口配置、上行口配置 |
| USG6000V | 防火墙 | 接口、安全区域、安全策略、OSPF、静态路由、AAA |
| AR2220 | 路由器 | 接口、静态路由、环回接口 |
| AC6605 | 无线控制器 | 基础、WLAN安全、SSID、VAP、AP组、AP注册 |

### 推荐配置顺序（20步）

1. 所有设备: undo t m → system-view → undo info-center enable
2. 所有交换机: 创建VLAN
3. SW1/SW2: MSTP区域配置
4. SW1/SW2: DHCP地址池
5. SW1/SW2: VLANIF接口 + VRRP
6. SW1/SW2: 端口配置
7. SW1/SW2: LACP链路聚合
8. LSW3/LSW4: 汇聚交换机配置
9. LSW5~LSW8: 接入交换机配置
10. LSW9/LSW10: 服务器区/外网区
11. FW1: 接口 + 区域
12. FW1: 安全策略
13. FW1: OSPF + 路由
14. AR1: 接口 + 路由
15. SW1/SW2: OSPF
16. AC1: 基础配置
17. AC1: WLAN配置
18. AC1: AP注册
19. AP端口: trunk配置
20. 保存所有设备

---

## 快速开始

```bash
pip install -r requirements.txt
python app.py
```

服务地址：http://127.0.0.1:5000

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENSP_SECRET_KEY` | Flask密钥 | 随机生成 |
| `ENSP_API_KEY` | API认证密钥 | 空（不认证） |
| `CORS_ORIGINS` | CORS来源 | `http://127.0.0.1:5000` |
| `HEARTBEAT_INTERVAL` | 心跳间隔(秒) | `30` |
| `HEARTBEAT_RECONNECT` | 最大重连次数 | `3` |

## 项目结构

```
mcpensp1/
├── app.py                          # 主服务器（2477行，46个API路由）
├── mcp_server.py                   # MCP服务器（39个工具）
├── mcp.json                        # MCP配置
├── requirements.txt                # 依赖
├── README.md                       # 本文档
├── kb/                             # 知识库数据
│   ├── structured_commands_kb.json # 结构化经验知识库（核心）
│   ├── global_kb.json              # 运行时命令记录（300+条）
│   ├── devices_kb.json             # 设备维度命令历史
│   └── snapshots/                  # 配置快照存储
├── static/
│   └── app.js                      # Web UI逻辑
├── templates/
│   └── index.html                  # Web UI页面
└── uploads/                        # 拓扑文件上传
```
