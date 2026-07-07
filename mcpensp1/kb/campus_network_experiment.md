# 校园网综合设计实训 - 实验经验库

## 一、实验拓扑概述

### 设备清单 (13台)
| 设备 | 型号 | 端口 | 角色 |
|------|------|------|------|
| LSW1 | S5700 | 2008 | 核心交换机1 (VRRP Master: VLAN10/101) |
| LSW2 | S5700 | 2015 | 核心交换机2 (VRRP Master: VLAN20/30/40) |
| LSW3 | S5700 | 2007 | 汇聚交换机1 (连接AP1) |
| LSW4 | S5700 | 2016 | 汇聚交换机2 (连接AP2) |
| LSW5 | S3700 | 2002 | 接入交换机 (PC3-VLAN10, PC4-VLAN20) |
| LSW6 | S3700 | 2003 | 接入交换机 (PC5-VLAN10, PC6-VLAN20) |
| LSW7 | S3700 | 2004 | 接入交换机 (PC7-VLAN30, PC8-VLAN40) |
| LSW8 | S3700 | 2006 | 接入交换机 (PC9-VLAN30, PC10-VLAN40) |
| LSW9 | S3700 | 2014 | 服务器接入 (Server2/3, DNS) |
| LSW10 | S3700 | 2011 | 接入交换机 (PC1/PC2-VLAN521) |
| AC1 | AC6605 | 2010 | 无线控制器 |
| AP1 | AP3030DN | 2000 | FIT AP (连接LSW3 GE0/0/3) |
| AP2 | AP3030DN | 2001 | FIT AP (连接LSW4 GE0/0/5) |
| FW1 | USG6000V | 2009 | 防火墙 |
| AR1 | AR3260 | 2013 | 路由器 |

### VLAN规划
| VLAN | 网段 | 用途 | 网关 |
|------|------|------|------|
| 10 | 192.168.1.0/24 | 教学楼有线 | 192.168.1.254 |
| 20 | 192.168.2.0/24 | 图书馆有线 | 192.168.2.254 |
| 30 | 192.168.3.0/24 | 宿舍楼有线 | 192.168.3.254 |
| 40 | 192.168.4.0/24 | 办公楼有线 | 192.168.4.254 |
| 100 | 192.168.100.0/24 | AP管理VLAN | 192.168.100.1 (AC) |
| 101 | 192.168.101.0/24 | 无线用户VLAN | 192.168.101.254 |
| 520 | 192.168.50.0/24 | 服务器区 | - |
| 521 | 201.1.1.0/24 | 外部用户 | 201.1.1.254 |

### 物理连接拓扑
```
AC1 GE0/0/19 ──trunk── LSW1 GE0/0/19
                         │
LSW1 GE0/0/1 ──trunk── FW1 GE1/0/0 (DMZ)
LSW1 GE0/0/2 ──trunk── LSW3 GE0/0/1
LSW1 GE0/0/3 ──trunk── LSW4 GE0/0/1
LSW1 GE0/0/10-11 ══Eth-Trunk1══ LSW2 GE0/0/10-11
                         │
LSW2 GE0/0/1 ──trunk── FW1 GE1/0/1
LSW2 GE0/0/2 ──trunk── LSW3 GE0/0/2
LSW2 GE0/0/3 ──trunk── LSW4 GE0/0/3
                         │
LSW3 GE0/0/3 ──trunk pvid 100── AP1
LSW3 GE0/0/4 ──trunk── LSW5
LSW3 GE0/0/5 ──trunk── LSW6
LSW3 GE0/0/10-11 ══Eth-Trunk1══ LSW4 GE0/0/10-11
                         │
LSW4 GE0/0/4 ──access VLAN30── (PC)
LSW4 GE0/0/5 ──trunk pvid 100── AP2
LSW4 GE0/0/2 ──trunk── LSW7
LSW4 GE0/0/3 ──trunk── LSW8
                         │
AR1 GE0/0/0 ── FW1 GE1/0/1 (200.1.1.0/24)
AR1 GE0/0/1 ── LSW10 (201.1.1.0/24)
FW1 GE1/0/2 ── LSW9 (192.168.50.0/24)
```

## 二、关键配置要点

### 1. 核心交换机配置顺序
```
1. sysname + undo info-center enable
2. vlan batch (创建所有VLAN)
3. stp instance + stp region-configuration (MSTP)
4. drop illegal-mac alarm + dhcp enable
5. ip pool (DHCP地址池)
6. interface Vlanif (IP + VRRP + dhcp select)
7. interface Eth-Trunk (聚合链路)
8. interface GigabitEthernet (trunk/access端口)
9. ospf (路由协议)
```

### 2. 汇聚交换机配置顺序
```
1. sysname + undo info-center enable
2. vlan batch
3. stp region-configuration (必须和核心交换机一致!)
4. interface Eth-Trunk
5. interface GigabitEthernet (上行trunk + 下行trunk/access + AP口)
```

### 3. 接入交换机配置顺序
```
1. sysname + undo info-center enable
2. vlan batch
3. interface Ethernet (access口 + 上行trunk口)
```

## 三、踩坑记录 (CRITICAL)

### 坑1: LSW1误配Vlanif100导致AP无法获取DHCP
- **错误**: 在LSW1上配置了Vlanif100 (192.168.100.254/24) + dhcp select global
- **后果**: LSW1和AC1同时响应DHCP请求，AP获取到错误网关，无法上线
- **正确做法**: LSW1不需要Vlanif100！AP管理VLAN的网关只在AC上
- **教训**: 一个VLAN只能有一个DHCP服务器，检查是否有冲突

### 坑2: AP端口必须配置 trunk pvid vlan
- **错误**: AP口只配了trunk，没配pvid
- **后果**: AP发送的untagged帧被分到VLAN1，不是VLAN100
- **正确做法**: `port trunk pvid vlan 100` + `port trunk allow-pass vlan 2 to 4094`
- **教训**: FIT AP发送的是untagged帧，必须通过pvid指定管理VLAN

### 坑3: 缺少 ap auth-mode no-auth
- **错误**: AC没有配置AP认证模式
- **后果**: AP注册到AC后状态为idle，无法上线
- **正确做法**: 在wlan视图下执行 `ap auth-mode no-auth`
- **教训**: AP上线三要素: capwap source + dhcp + auth-mode

### 坑4: 端口从access改为trunk需要先重置
- **错误**: 直接执行 `port link-type trunk` 报错 "Please renew the default config"
- **原因**: 华为交换机不允许直接从access改为trunk
- **正确做法**: 
  ```
  undo port default vlan    # 先清除access VLAN
  undo port link-type       # 重置端口类型
  port link-type trunk      # 设置新类型
  port trunk allow-pass vlan 2 to 4094
  ```

### 坑5: Eth-Trunk成员端口被意外移除
- **错误**: 修复端口时误将GE0/0/10从Eth-Trunk移除
- **后果**: LSW1-LSW2之间的聚合链路断开，VRRP和OSPF全部失效
- **正确做法**: 修改端口前先检查是否是Eth-Trunk成员 (`display this`)
- **教训**: 操作端口前必须用 `display this` 查看当前配置

### 坑6: 接入交换机上行口必须配trunk
- **错误**: 接入交换机的上行口(连接汇聚交换机)没有配trunk
- **后果**: 下行PC的VLAN标签无法传递到核心交换机
- **正确做法**: 上行口配置 `port link-type trunk` + `port trunk allow-pass vlan 2 to 4094`

### 坑7: 防火墙(USG6000V)登录流程特殊
- **错误**: 用普通方式登录防火墙失败
- **正确流程**: 
  1. 发送回车唤醒
  2. 输入用户名: admin
  3. 输入密码: Admin@123 (初始) 或修改后的密码
  4. 首次登录需要修改密码
- **教训**: USG6000V的登录流程和普通交换机不同，需要特殊处理

### 坑8: OSPF silent-interface阻止邻居建立
- **错误**: 所有Vlanif都配置了silent-interface
- **后果**: OSPF不在这些接口发送Hello包，无法建立邻居
- **正确做法**: silent-interface只用于不需要建立OSPF邻居的接口(如连接终端的接口)
- **例外**: 如果通过Vlanif建立OSPF邻居，不能配置silent-interface

### 坑9: trunk端口的allow-pass vlan必须包含所有需要的VLAN
- **错误**: trunk口只允许了个别VLAN
- **后果**: 某些VLAN的流量无法通过
- **正确做法**: 核心/汇聚交换机之间的trunk口建议 `allow-pass vlan 2 to 4094`
- **注意**: 接入交换机的上行口也要允许所有需要的VLAN

### 坑10: display current-configuration输出太长被截断
- **错误**: 直接执行display current-configuration，API返回不完整
- **原因**: 配置太长，需要多次按空格翻页
- **正确做法**: 使用 `display current-configuration | include xxx` 过滤
- **备选**: 循环按空格直到没有More提示

## 四、验证命令速查

### 核心交换机验证
```bash
display vlan brief                    # VLAN是否创建
display port vlan                     # 端口VLAN分配
display ip interface brief            # Vlanif接口状态
display vrrp brief                    # VRRP主备状态
display ospf peer brief               # OSPF邻居
display stp brief                     # STP状态
display ip pool                       # DHCP地址池
display eth-trunk 1                   # 聚合链路状态
```

### AC验证
```bash
display ap all                        # AP注册状态和IP
display vap all                       # VAP广播状态
display radio all                     # 射频状态
display current-configuration | include capwap  # CAPWAP源
display current-configuration | include ap-group # AP分组
```

### 防火墙验证
```bash
display ip interface brief            # 接口状态
display firewall zone table           # 安全区域
display ospf peer brief               # OSPF邻居
display security-policy               # 安全策略
display ip routing-table              # 路由表
```

## 五、配置模板

### 核心交换机1 (LSW1) 完整配置
```shell
system-view
sysname SW1
undo info-center enable
vlan batch 10 20 30 40 100 to 101 520
stp instance 1 root primary
stp instance 2 root secondary
drop illegal-mac alarm
dhcp enable
stp region-configuration
 region-name huawei
 revision-level 16
 instance 1 vlan 10 100 to 101
 instance 2 vlan 20 30 40
 active region-configuration
# DHCP地址池
ip pool vlan10
 gateway-list 192.168.1.254
 network 192.168.1.0 mask 255.255.255.0
 dns-list 192.168.0.1
ip pool vlan20
 gateway-list 192.168.2.254
 network 192.168.2.0 mask 255.255.255.0
 dns-list 192.168.0.1
ip pool vlan30
 gateway-list 192.168.3.254
 network 192.168.3.0 mask 255.255.255.0
 dns-list 192.168.0.1
ip pool vlan40
 gateway-list 192.168.4.254
 network 192.168.4.0 mask 255.255.255.0
 dns-list 192.168.0.1
ip pool vlan101
 gateway-list 192.168.101.254
 network 192.168.101.0 mask 255.255.255.0
 dns-list 192.168.0.1
# VRRP接口
interface Vlanif10
 ip address 192.168.1.100 255.255.255.0
 vrrp vrid 10 virtual-ip 192.168.1.254
 vrrp vrid 10 priority 120
 dhcp select global
interface Vlanif20
 ip address 192.168.2.100 255.255.255.0
 vrrp vrid 20 virtual-ip 192.168.2.254
 dhcp select global
interface Vlanif30
 ip address 192.168.3.100 255.255.255.0
 vrrp vrid 30 virtual-ip 192.168.3.254
 dhcp select global
interface Vlanif40
 ip address 192.168.4.100 255.255.255.0
 vrrp vrid 40 virtual-ip 192.168.4.254
 dhcp select global
interface Vlanif101
 ip address 192.168.101.100 255.255.255.0
 vrrp vrid 101 virtual-ip 192.168.101.254
 vrrp vrid 101 priority 120
 dhcp select global
# 聚合链路
interface Eth-Trunk1
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
 mode lacp-static
# AC上行口
interface GigabitEthernet0/0/19
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
# 上行到LSW3
interface GigabitEthernet0/0/2
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
# 上行到LSW4
interface GigabitEthernet0/0/3
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
# 到FW1
interface GigabitEthernet0/0/1
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
# Eth-Trunk成员
interface GigabitEthernet0/0/10
 eth-trunk 1
interface GigabitEthernet0/0/11
 eth-trunk 1
# OSPF
ospf 1 router-id 1.1.1.1
 silent-interface Vlanif10
 silent-interface Vlanif20
 silent-interface Vlanif30
 silent-interface Vlanif40
 silent-interface Vlanif101
 area 0.0.0.0
  network 192.168.0.0 0.0.255.255
return
```

### AC无线控制器完整配置
```shell
system-view
sysname AC
undo info-center enable
vlan batch 100 to 101
dhcp enable
# AAA配置
aaa
 authentication-scheme default
 authentication-scheme radius
  authentication-mode radius
 authorization-scheme default
 accounting-scheme default
 domain default
  authentication-scheme radius
  radius-server default
 domain default_admin
  authentication-scheme default
 local-user admin password irreversible-cipher Admin@1234
 local-user admin privilege level 15
 local-user admin service-type http
# 接口配置
interface Vlanif100
 ip address 192.168.100.1 255.255.255.0
 dhcp select interface
interface GigabitEthernet0/0/19
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
# CAPWAP源接口 (关键!)
capwap source interface Vlanif100
# WLAN配置
wlan
 traffic-profile name default
 security-profile name sec
  security wpa-wpa2 psk pass-phrase YourPassword aes
 security-profile name default
 security-profile name default-wds
 security-profile name default-mesh
 ssid-profile name ssid
  ssid wlan-2024
 ssid-profile name default
 vap-profile name vap
  service-vlan vlan-id 101
  ssid-profile ssid
  security-profile sec
 ap-group name ap
  radio 0
   vap-profile vap wlan 1
  radio 1
   vap-profile vap wlan 1
 ap-group name default
 # AP认证 (关键!)
 ap auth-mode no-auth
 # AP注册
 ap-id 1 type-id 56 ap-mac 00e0-fcdf-4df0 ap-sn 21023544831023634310
  ap-name ap1
  ap-group ap
 ap-id 2 type-id 56 ap-mac 00e0-fc10-43a0 ap-sn 2102354483101965a26c
  ap-name ap2
  ap-group ap
 provision-ap
return
```

### 汇聚交换机 (LSW3) 完整配置
```shell
system-view
sysname SW3
undo info-center enable
vlan batch 10 20 30 40 100 to 101
stp region-configuration
 region-name huawei
 revision-level 16
 instance 1 vlan 10 100 to 101
 instance 2 vlan 20 30 40
 active region-configuration
# Eth-Trunk
interface Eth-Trunk1
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
 mode lacp-static
# 上行到LSW1
interface GigabitEthernet0/0/1
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
# 上行到LSW2
interface GigabitEthernet0/0/2
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
# AP口 (关键: pvid!)
interface GigabitEthernet0/0/3
 port link-type trunk
 port trunk pvid vlan 100
 port trunk allow-pass vlan 2 to 4094
# 下行到接入交换机
interface GigabitEthernet0/0/4
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
interface GigabitEthernet0/0/5
 port link-type trunk
 port trunk allow-pass vlan 2 to 4094
# Eth-Trunk成员
interface GigabitEthernet0/0/10
 eth-trunk 1
interface GigabitEthernet0/0/11
 eth-trunk 1
return
```

### 防火墙 (FW1) 完整配置
```shell
# 登录: admin / Admin@1234
system-view
sysname FW
undo info-center enable
# 接口
interface GigabitEthernet1/0/0
 undo shutdown
 ip address 192.168.0.254 255.255.255.0
interface GigabitEthernet1/0/1
 undo shutdown
 ip address 200.1.1.1 255.255.255.0
interface GigabitEthernet1/0/2
 undo shutdown
 ip address 192.168.50.2 255.255.255.0
interface GigabitEthernet1/0/3
 undo shutdown
 ip address 192.168.51.2 255.255.255.0
# 安全区域
firewall zone trust
 set priority 85
 add interface GigabitEthernet1/0/2
 add interface GigabitEthernet1/0/3
firewall zone untrust
 set priority 5
 add interface GigabitEthernet1/0/1
firewall zone dmz
 set priority 50
 add interface GigabitEthernet1/0/0
# OSPF
ospf 1 router-id 3.3.3.3
 default-route-advertise
 area 0.0.0.0
  network 192.168.0.0 0.0.255.255
# 静态路由
ip route-static 0.0.0.0 0.0.0.0 200.1.1.2
# 安全策略
security-policy
 rule name 1
  source-zone trust
  destination-zone dmz
  destination-zone untrust
  action permit
 rule name 2
  source-zone untrust
  destination-zone dmz
  action permit
return
```

## 六、AP上线WiFi完整流程

### 必须满足的5个条件
1. **AP管理VLAN存在** - VLAN 100
2. **AP端口配置正确** - trunk + pvid vlan 100
3. **AC的CAPWAP源配置** - capwap source interface Vlanif100
4. **AP能获取IP** - DHCP (dhcp select interface) 或静态
5. **AP认证模式** - ap auth-mode no-auth

### 验证AP上线的命令
```bash
# 1. 检查AP是否获取IP
display ap all
# 正常: State=nor, IP=192.168.100.xxx

# 2. 检查VAP是否广播
display vap all
# 正常: Status=ON, SSID=wlan-2024

# 3. 检查射频状态
display radio all
# 正常: ST=on, 2.4G和5G都应显示
```

### AP不上线排查顺序
```
1. display ap all → 看State是idle还是fault
   - idle: AP已注册但未上线 → 检查网络连通性
   - fault: AP故障 → 检查硬件
   
2. 检查AP到AC的网络连通性
   - AP口是否trunk pvid 100
   - 汇聚到核心的trunk是否允许VLAN 100
   - AC的Vlanif100是否up
   
3. 检查DHCP
   - AC的Vlanif100是否有dhcp select interface
   - 或者是否有dhcp select global + ip pool
   
4. 检查CAPWAP
   - capwap source interface Vlanif100 是否配置
   
5. 检查认证
   - ap auth-mode no-auth 是否配置
```

## 七、VRRP配置要点

### 主备模式配置
- **Master设备**: vrrp vrid X priority 120 (优先级更高)
- **Backup设备**: 不配置priority (默认100)

### 本次实验VRRP分配
| VLAN | LSW1 | LSW2 |
|------|------|------|
| 10 | Master (priority 120) | Backup |
| 20 | Backup | Master (priority 120) |
| 30 | Backup | Master (priority 120) |
| 40 | Backup | Master (priority 120) |
| 101 | Master (priority 120) | Backup |

### 验证命令
```bash
display vrrp brief
# 期望: LSW1有2个Master+3个Backup, LSW2有3个Master+2个Backup
```

## 八、MSTP配置要点

### 域配置 (所有交换机必须一致!)
```shell
stp region-configuration
 region-name huawei
 revision-level 16
 instance 1 vlan 10 100 to 101
 instance 2 vlan 20 30 40
 active region-configuration
```

### 根桥配置
- **LSW1**: stp instance 1 root primary, stp instance 2 root secondary
- **LSW2**: stp instance 1 root secondary, stp instance 2 root primary

## 九、本次实验配置统计

| 设备 | 命令数 | 成功 | 失败 | 主要失败原因 |
|------|--------|------|------|-------------|
| LSW1 | 71 | 56 | 15 | DHCP池已存在 |
| LSW2 | 69 | 69 | 0 | - |
| LSW3 | 34 | 34 | 0 | - |
| LSW4 | 34 | 34 | 0 | - |
| LSW5-8 | 13×4 | 52 | 0 | - |
| LSW9 | 16 | 16 | 0 | - |
| LSW10 | 13 | 13 | 0 | - |
| AC1 | 52 | 47 | 5 | 确认提示未处理 |
| AR1 | 8 | 8 | 0 | - |
| FW1 | 40 | 40 | 0 | - |
| **总计** | **412** | **369** | **20** | - |
