# eNSP 配置方法库使用指南

## 概述

配置方法库用于存储**网络配置的标准流程和方法论**，而非某次实验的具体参数。

**核心思想**：记录"如何配置 OSPF"的标准步骤，而不是"这次实验的 OSPF 配置了什么参数"。

## 目录结构

```
mcpensp1/kb/config_methods/
├── _index.json           # 索引文件
├── ospf_basic.json       # OSPF 基础配置方法
├── vlan_config.json      # VLAN 配置方法
├── static_route.json     # 静态路由配置方法
└── ...                   # 更多配置方法
```

## 配置方法数据结构

每个配置方法 JSON 文件包含以下字段：

```json
{
  "id": "ospf_basic",                    // 唯一标识符
  "name": "OSPF基础配置",                 // 方法名称
  "category": "routing",                 // 分类
  "device_types": ["路由器", "三层交换机"], // 适用设备
  "description": "配置OSPF路由协议",      // 描述
  "prerequisites": ["已配置接口IP"],      // 前置条件
  "steps": [                             // 配置步骤
    {
      "step": 1,
      "name": "进入系统视图",
      "commands": ["system-view"],
      "notes": []
    },
    {
      "step": 2,
      "name": "创建OSPF进程",
      "commands": ["ospf [process-id]", "router-id [router-id]"],
      "notes": ["process-id 默认为1"]
    }
  ],
  "verification": [                      // 验证命令
    "display ospf peer brief",
    "display ip routing-table protocol ospf"
  ],
  "common_errors": [                     // 常见问题
    {
      "error": "邻居无法建立",
      "cause": "区域ID不匹配",
      "solution": "检查两端 area-id"
    }
  ],
  "tips": ["使用 display ospf peer brief 查看状态"],  // 技巧
  "related_methods": ["static_route"],   // 相关方法
  "usage_count": 0,                      // 使用次数
  "success_rate": 0.0                    // 成功率
}
```

## 分类说明

| 分类 | 说明 | 示例 |
|------|------|------|
| routing | 路由协议配置 | OSPF、静态路由、RIP |
| switching | 交换配置 | VLAN、STP、LACP |
| security | 安全配置 | ACL、防火墙策略 |
| wireless | 无线配置 | WLAN、AP管理 |
| services | 网络服务 | DHCP、NAT、VRRP |
| management | 管理配置 | Telnet、SNMP、NTP |

## MCP 工具

### 1. 列出配置方法

```
config_method_list(category="routing")
```

返回指定分类或所有配置方法的列表。

### 2. 获取配置方法详情

```
config_method_get(method_id="ospf_basic")
```

返回完整的配置方法信息，包括步骤、验证命令、常见问题等。

### 3. 搜索配置方法

```
config_method_search(keyword="OSPF")
```

根据关键词搜索配置方法。

### 4. 添加新配置方法

```
config_method_add(method_data={
    "id": "rip_basic",
    "name": "RIP基础配置",
    "category": "routing",
    "steps": [...]
})
```

添加新的配置方法到知识库。

### 5. 获取配置步骤命令

```
config_method_steps(method_id="ospf_basic")
```

返回按步骤顺序排列的命令列表，可直接用于执行。

## 持续收录新配置方法

### 方式一：手动添加

通过 MCP 工具 `config_method_add` 添加新的配置方法。

### 方式二：从实验中学习

当完成一次成功的实验后，系统可以：
1. 提取实验中的命令序列
2. 分析命令的执行顺序和依赖关系
3. 生成标准配置方法并保存

### 配置方法编写规范

1. **步骤要清晰**：每步只做一件事
2. **命令用占位符**：如 `[vlan-id]`、`[ip-address]`
3. **添加注意事项**：说明命令的关键参数
4. **包含验证命令**：如何检查配置是否成功
5. **记录常见问题**：方便后续排查

## 示例：添加新配置方法

```json
{
  "id": "dhcp_server",
  "name": "DHCP服务器配置",
  "category": "services",
  "device_types": ["路由器", "三层交换机"],
  "description": "配置DHCP服务器为终端自动分配IP地址",
  "prerequisites": [
    "设备已配置接口IP地址",
    "DHCP功能已启用"
  ],
  "steps": [
    {
      "step": 1,
      "name": "进入系统视图",
      "commands": ["system-view"],
      "notes": []
    },
    {
      "step": 2,
      "name": "启用DHCP功能",
      "commands": ["dhcp enable"],
      "notes": ["全局启用DHCP"]
    },
    {
      "step": 3,
      "name": "创建地址池",
      "commands": [
        "ip pool [pool-name]",
        "network [ip-address] mask [mask]",
        "gateway-list [gateway-ip]",
        "dns-list [dns-ip]",
        "lease day [days]"
      ],
      "notes": ["lease 默认为1天"]
    },
    {
      "step": 4,
      "name": "接口启用DHCP",
      "commands": [
        "interface [port]",
        "dhcp select global"
      ],
      "notes": []
    },
    {
      "step": 5,
      "name": "退出并保存",
      "commands": ["return", "save"],
      "notes": []
    }
  ],
  "verification": [
    "display ip pool",
    "display ip pool name [pool-name]"
  ],
  "common_errors": [
    {
      "error": "终端无法获取IP",
      "cause": "地址池配置错误或接口未启用DHCP",
      "solution": "检查地址池网段和接口DHCP模式"
    }
  ],
  "tips": [
    "使用 display ip pool 查看地址分配情况"
  ],
  "related_methods": ["vlanif_ip"]
}
```
