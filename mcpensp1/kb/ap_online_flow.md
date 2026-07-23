# 华为 AC+AP 完整上线流程 (FIT AP)

## 一、完整上线流程图

```
AP 上电
  │
  ├─ 1. 硬件初始化 (加载 VRP, 检测端口)
  │
  ├─ 2. 发送 DHCP Discover (管理 VLAN)
  │     └─ AC 侧需要: DHCP 池 + Vlanif + dhcp select
  │
  ├─ 3. 收到 DHCP Offer → 获取 IP + 网关 + Option 43 (AC地址)
  │     └─ 关键: DHCP Pool 必须存在, Vlanif 必须配 dhcp select
  │
  ├─ 4. AP 发现 AC (三种方式)
  │     ├─ a. DHCP Option 43 (推荐, 自动)
  │     ├─ b. DNS 解析 (AC 域名)
  │     └─ c. 静态配置 (手动)
  │     └─ 关键: AC 必须配 capwap source interface
  │
  ├─ 5. CAPWAP Discovery
  │     └─ AP → AC: Discovery Request (UDP 5246)
  │     └─ AC → AP: Discovery Response
  │
  ├─ 6. CAPWAP Join
  │     └─ AP → AC: Join Request
  │     └─ AC → AP: Join Response (认证检查)
  │     └─ 关键: ap auth-mode 必须匹配
  │
  ├─ 7. 配置下载
  │     └─ AC 下发: radio, vap-profile, ssid, security
  │     └─ 关键: ap-group 必须绑定正确的 vap-profile
  │
  ├─ 8. CAPWAP 隧道建立
  │     └─ AP ↔ AC: 控制隧道 + 数据隧道
  │
  └─ 9. SSID 广播
        └─ AP 开始广播 wlan-2024
```

## 二、AC 侧必须配置的命令 (按顺序)

```
# 1. 基础网络
vlan batch 100 to 101
interface Vlanif100
 ip address 192.168.100.1 255.255.255.0
 dhcp select global          ← 关键: AP 通过 DHCP 获取 IP

# 2. DHCP 池 (AP 管理网段)
ip pool vlan100
 gateway-list 192.168.100.1
 network 192.168.100.0 mask 255.255.255.0
 dns-list 192.168.0.1

# 3. CAPWAP 源接口 (AP 发现 AC 的关键)
capwap source interface Vlanif100   ← 最容易遗漏的命令!

# 4. AP 认证模式
ap auth-mode no-auth    ← 允许所有 AP 加入

# 5. WLAN 配置
wlan
 traffic-profile name default
 security-profile name sec
  security wpa-wpa2 psk pass-phrase YourPassword aes
 ssid-profile name ssid
  ssid wlan-2024
 vap-profile name vap
  service-vlan vlan-id 101      ← 用户 VLAN
  ssid-profile ssid
  security-profile sec

# 6. AP 分组 (绑定 VAP)
ap-group name ap
 radio 0
  vap-profile vap wlan 1
 radio 1
  vap-profile vap wlan 1

# 7. 手动注册 AP (可选, 用于指定 AP 加入特定组)
ap-id 1 ap-mac xxxx-xxxx-xxxx
 ap-name ap1
 ap-group ap
```

## 三、常见 AP 不上线原因排查

| 序号 | 检查项 | 命令 | 预期结果 |
|------|--------|------|----------|
| 1 | AP 端口是否 UP | display interface GE0/0/x | Physical: UP |
| 2 | AP 端口 VLAN 是否正确 | display vlan xxx | AP 端口在管理 VLAN |
| 3 | 管理 VLAN 是否存在 | display vlan 100 | VLAN 100 存在 |
| 4 | AC Vlanif IP | display ip interface brief | 192.168.100.1/24 UP |
| 5 | DHCP 是否开启 | display dhcp enable | DHCP: ON |
| 6 | DHCP 池是否存在 | display ip pool | 有 vlan100 池 |
| 7 | Vlanif 是否配 dhcp select | display this (在 Vlanif 下) | dhcp select global |
| 8 | capwap source interface | display current-configuration \| include capwap | 有配置 |
| 9 | AP 是否获取 IP | display arp all \| include 192.168.100 | 有 AP 的 ARP |
| 10 | AP 认证模式 | display ap auth-mode | no-auth |
| 11 | AP 分组是否正确 | display ap-group | 有 ap-group 且绑定了 vap |
| 12 | AP 是否注册 | display ap all | 有 AP 条目 |

## 四、本次实验的修复记录

### 修复 1: 缺少 capwap source interface
- 问题: AC 没有配置 capwap source interface Vlanif100
- 影响: AP 无法发现 AC, 完全无法上线
- 修复: `capwap source interface Vlanif100`

### 修复 2: VLAN 100 缺少 DHCP 池
- 问题: LSW1 没有创建 vlan100 的 DHCP 池
- 影响: AP 无法获取 IP 地址
- 修复: `ip pool vlan100` + gateway + network + dns

### 修复 3: Vlanif100 缺少 dhcp select global
- 问题: LSW1 的 Vlanif100 没有配置 dhcp select global
- 影响: 即使有 DHCP 池, AP 也无法通过 DHCP 获取 IP
- 修复: `dhcp select global`

### 修复 4: LSW1 到 LSW3 的 trunk 缺失
- 问题: LSW1 的 GE0/0/1 (连接 LSW3) 没有配为 trunk
- 影响: VLAN 100 无法在 LSW1 和 LSW3 之间传递
- 修复: `port link-type trunk` + `port trunk allow-pass vlan 2 to 4094`

### 修复 5: AP 未手动注册到 AC
- 问题: AP 没有通过 ap-id/ap-mac 手动注册
- 影响: AP 即使获取 IP 也可能不被 AC 识别
- 修复: 使用 ap-id + ap-mac + ap-group 注册

## 五、关键命令速查

```bash
# AP 上线排查三板斧
display ap all                          # 查看 AP 注册状态
display ap-sysname ap-name              # 查看 AP 系统名
display ap-group                        # 查看 AP 分组

# DHCP 排查
display ip pool vlan100                 # 查看 DHCP 池
display arp all | include 192.168.100   # 查看 AP 是否获取 IP

# CAPWAP 排查
display capwap source interface         # 查看 CAPWAP 源接口
display ap online-record all            # 查看 AP 上线记录

# WLAN 状态
display vap-profile name vap            # 查看 VAP 配置
display ssid-profile name ssid          # 查看 SSID 配置
display radio-profile                   # 查看射频配置
```

## 六、实际实验补充 (2026-06-27 校园网实训)

### 关键发现: AC使用dhcp select interface而非dhcp select global

在实际实验中，AC的Vlanif100配置为:
```
interface Vlanif100
 ip address 192.168.100.1 255.255.255.0
 dhcp select interface    ← 使用接口DHCP，不需要ip pool
```

这种方式更简单，AC直接用自己的接口IP作为网关和DHCP服务器。

### 关键发现: LSW1不应配置Vlanif100

最初错误地在LSW1上也配置了Vlanif100 (192.168.100.254/24)，导致:
- LSW1和AC同时响应DHCP请求
- AP获取到错误的网关地址
- AP无法通过CAPWAP发现AC

**解决方案**: 删除LSW1的Vlanif100，让AC独占AP管理VLAN的三层接口。

### 关键发现: ap auth-mode必须在wlan视图下配置

```
# 错误: 在系统视图下执行
[AC] ap auth-mode no-auth
Error: Unrecognized command

# 正确: 在wlan视图下执行
[AC] wlan
[AC-wlan-view] ap auth-mode no-auth
Warning: It is insecure to configure none authentication mode.
```

### AP上线时间
- AP获取IP: 约10-30秒
- CAPWAP发现+Join: 约10-20秒
- 配置下载+SSID广播: 约5-10秒
- **总计: 约30-60秒**

### 验证AP上线的完整流程
```bash
# 1. 检查AP注册状态
display ap all
# 期望: State=nor (normal), IP有地址

# 2. 检查VAP广播
display vap all
# 期望: Status=ON, SSID正确

# 3. 检查射频
display radio all
# 期望: 2.4G和5G都显示 ST=on
```

## 七、AC6005 双机备份实战补充 (2026-07-21)

本次实验用 **AC6005 + AP3030DN**，与六节的 AC6605 校园网实训有本质差异，关键纠正如下：

### 1. type-id 因平台而异（最重要！）
- AC6005: `display ap-type all` → **45 = AP3030DN**, 56 = AP6050DN
- AC6605: 56 = AP3030DN
- 错配 type-id 的后果：AP 卡 `idle`/`fault`、射频 `Total:0`，CAPWAP 建链但射频起不来
- **铁律：每台 AC 上线前先 `display ap-type all` 取真实 id**

### 2. 真实拓扑：AP 挂在 AR 后，不是直连交换机
```
AP → AR Eth0/0/0 → AR Eth0/0/1 → LSW1 GE0/0/x → AC
```
- 接 AP 的口是 **路由器 AR 的口**（不是交换机口）
- AR 接 AP 口配置（漏配/错配会让 AP 永远拿不到管理 IP）：
  ```
  interface Ethernet0/0/0
   port link-type trunk
   port trunk pvid vlan 10
   port trunk allow-pass vlan 10 20 30 40
  ```
- 曾被错配成 `access vlan 20/30`，把 AP 锁在用户 VLAN → 只能 169.254.x.x → idle。修正为 trunk pvid vlan 10 后 AP 立即 normal。

### 3. AC6005 的 HSB(ac protect) 在 eNSP 不支持双隧道
- 配置必须在 **wlan 视图** 下做（system-view 下报 Wrong parameter）
- 全局：`ac protect enable` / `ac protect priority 0` / `ac protect protect-ac <对端IP>`
- AP 级：`ap-id N` 视图内 `ac-list <对端IP>`（弹 [Y/N] 须回大写 YES）；**无** `ap protect enable` 子命令，也**无** `ac source ip`
- 模拟限制：配置能正确下发（`display ac protect` 全对），但 AP 重启后全 `fault`，建不了双 CAPWAP 隧道 → **eNSP AC6005 不做 HSB**
- 残留 `ac-list` 会让 AP 持续 fault，须先 YES 清 [Y/N] 提示再 `undo ac-list`（不带 IP）

### 4. 冷备 failover（实测可用，推荐）
- 两台 AC 独立配相同 WLAN，AP 双归属
- 主 AC `interface Vlanif10` → `shutdown` 后，AP 约 **150~160s** 内切到备 AC 并 `normal`（射频 up、VAP ON）
- 验证命令：主备都 `display ap all`，切完后备 AC 上 State 变 normal

### 5. 瘦 AP 限制
- AP 控制台 `port link-type` / `ip address` 均 Unrecognized
- AP 管理 IP 只能从 DHCP 自动获取，且必须处在管理 VLAN（本实验 VLAN10）
- AP 拿不到 IP 只能从交换机/路由器侧修（把接 AP 的口划进管理 VLAN），AP 侧无法自救

### 6. 无线 STA 子网 DHCP
- 用户 VLAN（本实验 20/30/40）的网关在各 AR 上，需补 `interface Vlanif<x>` + `ip pool sta` + `dhcp select global`，并 `ospf` 通告该网段，否则 STA 拿不到 IP、全网不通
```
