# CLI 状态机

## 概述

eNSP 设备的命令行接口（CLI）有多层视图结构。CommandExecutor 通过 prompt 检测自动识别当前视图并在必要时自动切换。

## 华为设备视图层级

```
用户视图 <SW1>
    │
    system-view
    ↓
系统视图 [SW1]
    │
    ├── interface GigabitEthernet0/0/1
    │   ↓
    │   接口视图 [SW1-GigabitEthernet0/0/1]
    │
    ├── vlan 10
    │   ↓
    │   VLAN 视图 [SW1-vlan10]
    │
    ├── ospf 1
    │   ↓
    │   OSPF 视图 [SW1-ospf-1]
    │   │
    │   └── area 0
    │       ↓
    │       OSPF 区域视图 [SW1-ospf-1-area-0.0.0.0]
    │
    └── acl 3000
        ↓
        ACL 视图 [SW1-acl-adv-3000]
```

## Prompt 检测规则

| Prompt 模式 | 视图类型 | 示例 |
|------------|---------|------|
| `<NAME>` | 用户视图 | `<SW1>` |
| `[NAME]` | 系统视图 | `[SW1]` |
| `[NAME-xxx]` | 子视图 | `[SW1-GigabitEthernet0/0/1]` |
| `NAME>` | 用户视图（无尖括号） | 某些设备变体 |
| `NAME#` | 特权模式 | `SW1#` |

## 命令分类体系

CommandExecutor 将命令分为 4 类，每类有不同的超时和读取策略：

| 类别 | 特征 | 超时 | 示例 |
|------|------|------|------|
| `display` | 只读查询 | 15s | `display version`, `display current-configuration` |
| `diagnostic` | 网络诊断 | 30s | `ping 10.0.0.1`, `tracert 192.168.1.1` |
| `config` | 配置修改 | 5s | `vlan 10`, `interface GE0/0/1` |
| `interactive` | 交互式命令 | 60s | `system-view` |

## 翻页处理

当检测到 `---- More ----` 提示时，自动发送空格翻页，直到内容读取完毕。

## 安全机制

- 危险命令拦截（`is_blocked_command`）：`reboot`、`format`、`reset saved-configuration` 等被拦截
- `undo t m` 自动管理：配置模式下自动执行 `undo terminal monitor`
- 视图退出保护：命令执行后自动返回用户视图
