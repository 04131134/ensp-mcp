# eNSP MCP Server — 知识库驱动的设备配置工具

## 核心理念

这个工具的目标是：**通过持续积累经验，让AI仅靠本地知识库就能完成eNSP模拟器的所有设备配置，无需联网。**

知识库不是一次性产物，而是随每次实验持续增长的经验库。每次实验后提取新发现的命令、排障经验、最佳实践，写入知识库，使AI工具越来越熟练。

---

## ⚠️ 操作规范（每次配置前必须遵守）

### 规则一：配置前检测视图类型

**发送任何命令前，必须先检测设备当前处于哪种视图：**

| 视图 | 提示符格式 | 可执行命令 |
|------|-----------|-----------|
| **用户视图** | `<设备名>` 以 `>` 结尾 | `display`、`save`、`ping`、`system-view`、`undo t m` |
| **系统视图** | `[设备名]` 以 `]` 结尾 | `interface`、`vlan`、`ospf`、`vrrp`、`ip address` 等配置命令 |

**检测方法：** 读取终端提示符
- 包含 `<` 和 `>` → 用户视图
- 包含 `[` 和 `]` → 系统视图

**错误视图下发送命令会报 `Unrecognized command` 错误！**

```
# 正确流程
1. 读取提示符 → 确定当前视图
2. 如果需要系统视图但当前在用户视图 → 发送 system-view
3. 如果需要用户视图但当前在系统视图 → 发送 return 或 quit
4. 发送目标命令
```

### 规则二：配置前关闭日志

**所有设备配置前的第一条命令必须是：**

```
undo terminal monitor
```

简写 `undo t m`。不执行此命令，设备日志会不断弹出，干扰命令输入和输出解析。

### 规则三：配置后保存

**所有设备配置完成后必须执行 `save` 命令保存配置。**

---

## 知识库架构

### 四层知识体系

```
┌─────────────────────────────────────────┐
│  第1层：操作规范 (best_practices)        │ ← 永远适用的规则
├─────────────────────────────────────────┤
│  第2层：设备命令库 (user/system_view)    │ ← 按设备型号×视图×主题分类
├─────────────────────────────────────────┤
│  第3层：实验经验 (experiences)           │ ← 每次实验后积累
├─────────────────────────────────────────┤
│  第4层：运行时记录 (global/devices_kb)   │ ← 每次命令执行自动记录
└─────────────────────────────────────────┘
```

### 知识库文件

| 文件 | 说明 | 增长方式 |
|------|------|---------|
| `kb/structured_commands_kb.json` | 结构化经验知识库 | 每次实验后手动/API写入 |
| `kb/global_kb.json` | 运行时命令记录 | 每次执行命令自动记录 |
| `kb/devices_kb.json` | 设备维度命令历史 | 每次执行命令自动记录 |

### 结构化知识库内容

`structured_commands_kb.json` 包含：

| 字段 | 说明 |
|------|------|
| `meta` | 版本、实验计数、已记录实验列表 |
| `best_practices` | 操作规范（视图检测、undo t m、保存等） |
| `user_view_commands` | `<>` 用户视图命令，按设备型号分类 |
| `system_view_commands` | `[]` 系统视图命令，按设备型号×配置主题分类 |
| `experiments` | 实验经验记录（新命令、教训、排障案例） |
| `troubleshooting` | 排障知识库 |
| `config_order` | 推荐配置顺序 |

### 支持的设备型号

| 型号 | 类型 | 用户视图 | 系统视图主题 |
|------|------|---------|-------------|
| S5700 | 核心/汇聚交换机 | 17条命令 | 基础、VLAN端口、VLANIF、VRRP、MSTP、DHCP、OSPF、LACP |
| S3700 | 接入层交换机 | 5条命令 | 基础、端口配置、上行口配置 |
| USG6000V | 防火墙 | 10条命令 | 接口配置、安全区域、安全策略、OSPF路由、静态路由、AAA账户 |
| AR2220 | 路由器 | 8条命令 | 接口配置、静态路由、环回接口 |
| AC6605 | 无线控制器 | 8条命令 | 基础配置、WLAN安全、SSID、VAP、AP组、AP注册 |

---

## AI Agent 使用流程

### 标准配置流程

```
1. 扫描设备 → GET /api/devices/scan?start=2000&end=2024
2. 连接设备 → POST /api/devices/connect {path, name}
3. 获取命令建议 → GET /api/kb/suggest?model=LSW1
4. 检测视图 → 发送空命令或读取提示符
5. 关闭日志 → send_command("undo t m")
6. 进入系统视图 → send_command("system-view")
7. 按知识库建议逐条配置
8. 保存 → send_command("save")
9. 记录经验 → POST /api/kb/experience
```

### 配置前：获取命令建议

```
GET /api/kb/suggest?model=LSW1
```

返回该设备型号在用户视图和系统视图下的所有可用命令，按主题分组。

### 配置中：检测视图

```
POST /api/kb/detect-view
Body: {"prompt": "<LSW1>"}
→ {"view": "user_view", "can_commands": "display/save/ping/system-view"}
```

### 配置后：记录经验

```
POST /api/kb/experience
Body: {
  "experiment": "实验名称",
  "date": "2026-06-16",
  "topology": "拓扑描述",
  "features_implemented": ["VRRP", "OSPF"],
  "new_commands_learned": [
    {"cmd": "新命令", "device": "S5700", "desc": "命令说明"}
  ],
  "lessons_learned": ["教训1", "教训2"],
  "troubleshooting_cases": [
    {"problem": "问题", "root_cause": "原因", "solution": "解决方案", "diagnosis_cmd": "诊断命令"}
  ]
}
```

新命令会自动加入对应设备型号的「经验积累」主题下。

---

## API 端点总览

### 设备管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices/scan?start=2000&end=2024` | 扫描端口范围内的设备 |
| POST | `/api/devices/connect` | 连接设备 `{path, name}` |
| POST | `/api/devices/disconnect` | 断开设备 `{path}` |
| GET | `/api/devices` | 已连接设备列表 |
| POST | `/api/devices/command` | 发送命令 `{path, command}` |
| GET | `/api/devices/command/history` | 命令执行历史 |

### 知识库 — 结构化命令

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kb/structured` | 完整结构化知识库 |
| GET | `/api/kb/structured/<type>` | 按设备型号过滤 |
| GET | `/api/kb/suggest?model=LSW1` | 命令建议 |
| POST | `/api/kb/scan` | 扫描设备返回建议 `{path}` |
| GET | `/api/kb/config-order` | 推荐配置顺序（20步） |

### 知识库 — 经验与规范

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kb/best-practice` | 操作规范（?priority=critical） |
| POST | `/api/kb/best-practice` | 添加新规范 `{rule, detail, priority}` |
| GET | `/api/kb/experience` | 实验经验列表 |
| POST | `/api/kb/experience` | 记录实验经验 |
| GET | `/api/kb/troubleshooting` | 排障知识库 |

### 知识库 — 运行时

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kb/commands` | 全局命令记录 |
| GET | `/api/kb/catalog` | 命令目录（76条预置命令） |
| GET | `/api/kb/devices` | 设备维度记录 |
| GET | `/api/kb/capabilities` | 设备能力矩阵 |
| GET | `/api/kb/stats` | 知识库统计 |
| POST | `/api/kb/reload` | 重新加载知识库 |
| POST | `/api/kb/detect-view` | 视图检测 `{prompt}` |

### 拓扑

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/topology` | 拓扑摘要 |
| POST | `/api/topology` | 保存拓扑 |
| POST | `/api/topology/file` | 上传.topo文件 |
| GET | `/api/topology/path` | 路径查找 |
| GET | `/api/topology/neighbor` | 邻居查询 |

---

## 知识库增长机制

### 自动增长（运行时）
每次通过 `/api/devices/command` 执行命令，自动记录到 `global_kb.json` 和 `devices_kb.json`。

### 手动增长（实验后）
每次实验完成后，调用 `POST /api/kb/experience` 记录：
- 本次实验发现了哪些新命令
- 踩了哪些坑（教训）
- 遇到了什么问题、怎么解决的（排障案例）

新命令会自动归入对应设备型号的「经验积累」主题。

### 目标
随着实验次数增加，知识库覆盖所有eNSP设备的所有命令，AI仅靠本地知识库即可完成任何拓扑的配置。

---

## API端点（33个）

| 类别 | 数量 | 端点 |
|------|------|------|
| 设备管理 | 7 | scan/connect/command/disconnect/devices/rename/fetch-name |
| 结构化KB | 6 | structured/suggest/scan/config-order/troubleshooting/reload |
| 经验规范 | 4 | experience(POST/GET)/best-practice(POST/GET) |
| 运行时KB | 6 | commands/catalog/devices/capabilities/stats/detect-view |
| 拓扑 | 5 | topology(GET/POST/file/path/device) |
| 其他 | 5 | heartbeat/health + WebSocket |

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
| `CORS_ORIGINS` | CORS来源 | `http://127.0.0.1:5000` |
| `HEARTBEAT_INTERVAL` | 心跳间隔(秒) | `15` |
| `HEARTBEAT_RECONNECT` | 最大重连次数 | `3` |

## 项目结构

```
mcpensp1/
├── app.py                          # 主服务器（知识库+心跳+拓扑+18个KB API）
├── mcp_server.py                   # MCP服务器
├── mcp.json                        # MCP配置
├── requirements.txt                # 依赖
├── README.md                       # 本文档
├── kb/                             # 知识库数据
│   ├── structured_commands_kb.json # 结构化经验知识库（核心）
│   ├── global_kb.json              # 运行时命令记录
│   └── devices_kb.json             # 设备维度命令历史
├── templates/
│   └── index.html                  # Web UI
└── uploads/
```
