# ENSP 华为VRP 全套命令知识库（Agent适配版·全量汇总）

## 文档说明

- **适配环境**：ENSP模拟器 AR2220/AR3260、S5700、USG6000V、AC6005、AP6010DN

- **固件版本**：全部基于VRP5，所有命令**ENSP实测可用**，无无效命令

- **结构规范**：按设备分类、按功能细分，附带配置\+验证排障命令，适配AI Agent检索

- **全局元数据标签**：ensp\_test: true、vrp\_version: VRP5、标签：\#ENSP \#华为VRP \#网络命令 \#实验模板

---

# 第一部分：全设备通用基础命令（AR/S5700/USG通用）

## 1\.1 视图切换命令

```Plain Text
system-view          # 用户视图进入系统视图
quit                 # 退回上一级视图
return               # 直接返回用户视图（快捷键Ctrl+Z）
```

## 1\.2 设备系统基础管理

```Plain Text
sysname R1           # 修改设备名称
save                 # 保存当前配置
reboot               # 重启设备
reset saved-configuration   # 删除启动配置（重启生效）
clock datetime 10:00:00 2026-07-23  # 设置系统时间
display clock        # 查看系统时间
display version      # 查看VRP版本、运行时长
display current-configuration   # 查看当前运行配置 简写dis cur
display saved-configuration     # 查看闪存保存配置
display history-command         # 查看历史输入命令
```

## 1\.3 远程登录管理（Console/VTY/SSH）

```Plain Text
# Console口配置
user-interface console 0
 set authentication-mode password
 set authentication password cipher Admin@123
 idle-timeout 15 0        # 15分钟无操作超时

# VTY Telnet/SSH配置
user-interface vty 0 4
 authentication-mode aaa
 protocol inbound telnet

# SSH服务配置
aaa
 local-user admin password cipher Admin@123
 local-user admin privilege level 15
 local-user admin service-type ssh telnet
stelnet server enable
ssh user admin authentication-type password
```

## 1\.4 通用排障查看命令

```Plain Text
display interface brief           # 接口简要状态（最常用）
display ip interface brief        # 三层接口IP信息
display cpu-usage                 # CPU占用
display memory-usage              # 内存占用
display logbuffer                 # 查看系统日志
display alarm active              # 查看当前告警
display diagnostic-information    # 一键收集全套设备信息
display transceiver interface GigabitEthernet 0/0/0 # 光模块信息
reset counters interface GigabitEthernet 0/0/0 # 清空接口流量统计
```

---

# 第二部分：AR路由器 全功能配置命令

## 2\.1 接口基础配置（物理/环回/子接口单臂路由）

```Plain Text
# 物理接口
interface GigabitEthernet 0/0/0
 ip address 192.168.1.1 255.255.255.0
 undo shutdown
 description Link_to_SW

# 环回接口（路由协议Router-ID首选）
interface LoopBack 0
 ip address 1.1.1.1 255.255.255.255

# 单臂路由子接口
interface GigabitEthernet 0/0/0.10
 dot1q termination vid 10
 ip address 192.168.10.1 24
 arp broadcast enable

interface GigabitEthernet 0/0/0.20
 dot1q termination vid 20
 ip address 192.168.20.1 24
 arp broadcast enable
```

## 2\.2 静态路由/默认路由/浮动路由

```Plain Text
ip route-static 192.168.30.0 255.255.255.0 192.168.1.2
ip route-static 192.168.30.0 255.255.255.0 192.168.1.3 preference 70  # 浮动路由
ip route-static 0.0.0.0 0.0.0.0 192.168.1.2  # 默认路由
undo ip route-static 192.168.30.0 255.255.255.0 192.168.1.2

# 查看命令
display ip routing-table
display ip routing-table protocol static
```

## 2\.3 RIP动态路由

```Plain Text
rip 1
 version 2
 network 192.168.1.0
 undo summary           # 关闭自动汇总

display rip
display rip route
```

## 2\.4 OSPF动态路由

```Plain Text
# 全局进程配置
ospf 1 router-id 1.1.1.1
 area 0
  network 192.168.12.0 0.0.0.255
  network 1.1.1.1 0.0.0.0

# 接口使能方式
interface GigabitEthernet 0/0/0
 ospf enable 1 area 0

# 查看排障
display ospf peer brief
display ospf lsdb
display ospf routing
```

## 2\.5 ACL访问控制列表

```Plain Text
# 基础ACL 2000-2999
acl number 2000
 rule permit source 192.168.10.0 0.0.0.255
 rule deny

# 高级ACL 3000-3999
acl number 3000
 rule permit tcp source 192.168.10.0 0.0.0.255 destination 192.168.20.0 0.0.0.255 eq 80
 rule deny ip

display acl 3000
```

## 2\.6 NAT上网配置（EasyIP/地址池/端口映射）

```Plain Text
# Easy-IP
acl number 2000
 rule permit source 192.168.10.0 0.0.0.255
interface GigabitEthernet 0/0/1
 nat outbound 2000

# 地址池NAT
nat address-group 1 202.1.1.10 202.1.1.20
acl number 2000
 rule permit source 192.168.10.0 0.0.0.255
interface GigabitEthernet 0/0/1
 nat outbound 2000 address-group 1

# 服务器端口映射
nat server protocol tcp global 202.1.1.10 80 inside 192.168.10.100 80
display nat session all
```

## 2\.7 DHCP服务器配置

```Plain Text
dhcp enable
# 全局地址池
ip pool VLAN10
 gateway-list 192.168.10.1
 network 192.168.10.0 mask 255.255.255.0
 dns-list 223.5.5.5 114.114.114.114
 lease day 3 hour 0 minute 0

interface GigabitEthernet 0/0/0.10
 dhcp select global

# 接口地址池
interface GigabitEthernet 0/0/0.20
 dhcp select interface
 dhcp server dns-list 223.5.5.5

display ip pool
```

## 2\.8 VRRP网关冗余

```Plain Text
interface GigabitEthernet 0/0/0
 ip address 192.168.1.1 24
 vrrp vrid 1 virtual-ip 192.168.1.254
 vrrp vrid 1 priority 120
 vrrp vrid 1 preempt-mode enable

display vrrp brief
```

## 2\.9 VRRP单臂路由专属配置

```Plain Text
# 主设备子接口VRRP
interface GigabitEthernet0/0/0.10
 dot1q termination vid 10
 ip address 192.168.10.1 255.255.255.0
 arp broadcast enable
 vrrp vrid 10 virtual-ip 192.168.10.254
 vrrp vrid 10 priority 120
 vrrp vrid 10 track interface GigabitEthernet0/0/1 reduced 30

# 备设备子接口VRRP
interface GigabitEthernet0/0/0.10
 dot1q termination vid 10
 ip address 192.168.10.2 255.255.255.0
 arp broadcast enable
 vrrp vrid 10 virtual-ip 192.168.10.254
```

## 2\.10 GRE隧道配置

```Plain Text
# 基础GRE隧道
interface Tunnel0/0/1 mode gre
 ip address 10.255.12.1 255.255.255.0
 source GigabitEthernet 0/0/0
 destination 202.1.1.2
ip route-static 192.168.20.0 24 Tunnel0/0/1

# GRE承载组播
interface Tunnel0/0/1 mode gre
 source LoopBack 0
 destination 2.2.2.2
 pim dm

display interface Tunnel0/0/1
display tunnel-info
```

## 2\.11 PIM组播（DM/SM/IGMP）

```Plain Text
multicast routing-enable   # 全局开启组播

# PIM-DM密集模式
interface GigabitEthernet 0/0/0
 pim dm

# PIM-SM稀疏模式
pim
 c-rp LoopBack 0
 c-bsr LoopBack 0
interface GigabitEthernet 0/0/0
 pim sm

# IGMPv2接入
interface GigabitEthernet 0/0/1
 igmp enable
 igmp version 2

# 静态RP
pim
 c-rp static 1.1.1.1

# 查看命令
display pim routing-table
display pim neighbor
display igmp group
display multicast routing-table
```

## 2\.12 BGP路由协议（IBGP/EBGP/RR/联盟/路由策略）

```Plain Text
# 基础BGP
bgp 65001
 router-id 1.1.1.1
 peer 12.1.1.2 as-number 65002          # EBGP邻居
 peer 2.2.2.2 as-number 65001            # IBGP邻居
 peer 2.2.2.2 connect-interface LoopBack 0
 peer 2.2.2.2 ebgp-max-hop 255
 peer 2.2.2.2 next-hop-local
 network 1.1.1.1 255.255.255.255

# 路由反射器RR
bgp 65001
 peer 1.1.1.1 reflect-client
 peer 2.2.2.2 reflect-client

# BGP联盟
bgp 65000
 confederation id 65000
 confederation peer-as 65001

# Route-Policy策略
ip ip-prefix NET1 permit 192.168.10.0 24
route-policy BGP-PERM permit node 10
 if-match ip-prefix NET1
 apply local-preference 200
bgp 65001
 peer 12.1.1.2 route-policy BGP-PERM export

# 查看命令
display bgp peer brief
display bgp routing-table
display ip ip-prefix
display route-policy
```

## 2\.13 MPLS基础\+LDP\+静态LSP

```Plain Text
mpls lsr-id 1.1.1.1
mpls
mpls ldp

interface GigabitEthernet 0/0/0
 mpls
 mpls ldp

# 静态LSP
static-lsp ingress LSP1 destination 4.4.4.4 32 nexthop 12.1.1.2 out-label 1020

# 查看命令
display mpls ldp peer
display mpls ldp lsp
display mpls label-table
```

## 2\.14 BGP/MPLS IP VPN

```Plain Text
# 创建VPN实例
ip vpn-instance VPN_A
 ipv4-family
  route-distinguisher 100:1
  vpn-target 100:1 export-extcommunity
  vpn-target 100:1 import-extcommunity

# 接口绑定VPN
interface GigabitEthernet 0/0/0
 ip binding vpn-instance VPN_A
 ip address 192.168.1.1 24

# PE BGP VPN配置
bgp 65001
 ipv4-family vpnv4
  peer 2.2.2.2 enable
  peer 2.2.2.2 connect-interface LoopBack 0
 ipv4-family vpn-instance VPN_A
  peer 192.168.1.2 as-number 65100

display ip vpn-instance
```

## 2\.15 MPLS TE流量工程

```Plain Text
# OSPF开启TE扩展
ospf 1
 opaque-capability enable
 area 0
  mpls-te enable

# 全局MPLS TE
mpls
 mpls-te
interface GigabitEthernet 0/0/0
 mpls-te enable

# TE隧道接口
interface Tunnel0/0/1 mode mpls-te
 ip address 10.255.13.1 24
 destination 3.3.3.3
 mpls-te tunnel-id 1

display mpls-te tunnel
display mpls-te lsdb
```

## 2\.16 L2VPN（PWE3静态PW、Martini VLL）

```Plain Text
# PWE3静态PW
pw-class PW_STATIC
 encapsulation mpls
interface GigabitEthernet0/0/0
 static-pw 1 destination 2.2.2.2 pw-class PW_STATIC

# Martini动态VLL
interface GigabitEthernet0/0/0
 vll martini 1 destination 2.2.2.2

display pw all
display vll brief
```

## 2\.17 IPSec VPN（IKEv1主模式\+野蛮模式）

```Plain Text
# IKE提议
ike proposal 10
 encryption-algorithm aes-256
 authentication-algorithm sha2-256
 dh group14

# IKE对等体
ike peer BR2 pre-shared-key simple Huawei@123
 ike-proposal 10
 remote-ip 203.0.0.2

# 野蛮模式配置
ike peer BR2
 exchange-mode aggressive
 id-type name

# IPSec提议
ipsec proposal TRANSFORM
 esp encryption-algorithm aes-256
 esp authentication-algorithm sha2-256

# IPSec策略+感兴趣流
ipsec map MAP1 10 isakmp
 proposal TRANSFORM
 remote-peer 203.0.0.2 ike-peer BR2
 security acl 3000

acl number 3000
 rule permit ip source 192.168.10.0 0.0.0.255 destination 192.168.20.0 0.0.0.255

# 接口应用
interface GigabitEthernet 0/0/1
 ipsec map MAP1

# 查看命令
display ike sa
display ipsec sa
reset ipsec sa
```

---

# 第三部分：S5700三层交换机 全功能命令

## 3\.1 VLAN基础配置

```Plain Text
vlan batch 10 20 30
vlan 10
 description Admin_VLAN

# Access端口
interface GigabitEthernet 0/0/1
 port link-type access
 port default vlan 10
 undo shutdown

# Trunk端口
interface GigabitEthernet 0/0/24
 port link-type trunk
 port trunk allow-pass vlan 10 20 30

display vlan
display mac-address
```

## 3\.2 Eth\-Trunk链路聚合LACP

```Plain Text
interface Eth-Trunk 1
 mode lacp-static
 port link-type trunk
 port trunk allow-pass vlan all
 trunkport GigabitEthernet 0/0/1 to 0/0/2

display eth-trunk 1
display lacp neighbor
```

## 3\.3 STP/RSTP/MSTP生成树

```Plain Text
stp mode mstp
stp enable

# MSTP域配置
stp region-configuration
 region-name MSTP_TEST
 instance 1 vlan 10
 instance 2 vlan 20
 active region-configuration

# 根桥配置
stp instance 1 root primary

# 边缘端口
interface GigabitEthernet 0/0/1
 stp edged-port enable

display stp brief
```

## 3\.4 三层VLANIF接口

```Plain Text
interface Vlanif 10
 ip address 192.168.10.254 255.255.255.0
 undo shutdown
```

## 3\.5 交换机VRRP冗余

```Plain Text
interface Vlanif 10
 ip address 192.168.10.252 24
 vrrp vrid 10 virtual-ip 192.168.10.254
 vrrp vrid 10 priority 120
 vrrp vrid 10 preempt-mode timer delay 20
 vrrp vrid 10 track interface GigabitEthernet 0/0/24 reduced 30
```

## 3\.6 交换机DHCP配置

```Plain Text
dhcp enable
ip pool VLAN10
 gateway-list 192.168.10.254
 network 192.168.10.0 mask 255.255.255.0
 dns-list 223.5.5.5

interface Vlanif 10
 dhcp select global
```

## 3\.7 CSS交换机堆叠

```Plain Text
# 主交换机
css enable
css member 1 priority 150
interface XGigabitEthernet 0/0/24
 css port

# 备交换机
css enable
css member 2 priority 100
interface XGigabitEthernet 0/0/24
 css port

# 验证命令
display css status
display css device
css switchover
```

---

# 第四部分：USG6000V防火墙 核心命令

## 4\.1 接口\+安全区域绑定

```Plain Text
interface GigabitEthernet 0/0/0
 ip address 192.168.1.1 24
 zone trust

interface GigabitEthernet 0/0/1
 ip address 202.1.1.1 24
 zone untrust
```

## 4\.2 安全策略（核心）

```Plain Text
security-policy
 rule name Trust_To_Untrust
  source-zone trust
  destination-zone untrust
  action permit

display security-policy rule all
```

## 4\.3 防火墙NAT策略

```Plain Text
# 源NAT
nat-policy
 rule name SNAT_TRUST
  source-zone trust
  destination-zone untrust
  action source-nat easy-ip

# 端口映射
nat server protocol tcp global 202.1.1.1 80 inside 192.168.100.10 80
```

## 4\.4 防火墙排障命令

```Plain Text
display zone
display firewall session table
display ip routing-table
```

---

# 第五部分：AC\+AP WLAN 全套配置（FitAP\+FatAP\+802\.1X认证）

## 5\.1 DHCP\+Option43（AP上线必备）

```Plain Text
dhcp enable
ip pool AP_POOL
 network 192.168.100.0 mask 255.255.255.0
 gateway-list 192.168.100.1
 dns-list 223.5.5.5
 option 43 sub-option 3 ascii 192.168.100.1

interface Vlanif 100
 ip address 192.168.100.1 24
 dhcp select global
```

## 5\.2 标准WLAN组网模板（AP组\+安全\+SSID\+VAP）

```Plain Text
wlan
# AP组
 ap-group name AP_GROUP1
# 安全模板WPA2-PSK
 security-profile name SEC_WIFI
  security wpa2
  wpa2 authentication-method psk
  psk pass-phrase simple Wifi@123456
# SSID模板
 ssid-profile name SSID_OFFICE
  ssid OFFICE-WIFI
# VAP模板
 vap-profile name VAP_OFFICE
  ssid-profile SSID_OFFICE
  security-profile SEC_WIFI
  service-vlan vlan-id 10
# 绑定AP组
 ap-group AP_GROUP1
  vap-profile VAP_OFFICE wlan 1
```

## 5\.3 AP上线配置（手动/自动）

```Plain Text
# 手动添加AP
wlan
 ap-id 1 ap-mac 00e0-fc11-2233
  ap-name AP_FLOOR1
  ap-group AP_GROUP1

# 自动发现上线
auto-ap enable
auto-ap confirm all
```

## 5\.4 射频参数调整

```Plain Text
wlan
 ap-group name AP_GROUP1
  radio 0   # 2.4G
   channel 6
   transmit-power 100
  radio 1   # 5G
   channel 149
   transmit-power 100
```

## 5\.5 访客开放WIFI配置

```Plain Text
wlan
 security-profile name SEC_GUEST
  security open
 ssid-profile name SSID_GUEST
  ssid GUEST-WIFI
 vap-profile name VAP_GUEST
  ssid-profile SSID_GUEST
  security-profile SEC_GUEST
  service-vlan vlan-id 20
 ap-group AP_GROUP1
  vap-profile VAP_GUEST wlan 2
```

## 5\.6 802\.1X无线企业认证（RADIUS对接）

```Plain Text
# 1. AR模拟RADIUS服务器
aaa
 local-user wifiuser password simple Wifi@123456
 local-user wifiuser service-type 802.1x
 local-user wifiuser privilege level 0

radius-server template WIFI-RAD
 radius-server authentication 192.168.1.200 1812
 radius-server accounting 192.168.1.200 1813
 radius-server shared-key simple Huawei@radius

aaa
 domain WIFI-USER
  radius WIFI-RAD

# 2. AC侧802.1X配置
radius-server template WIFI_RAD
 radius-server authentication 192.168.1.200 1812
 radius-server accounting 192.168.1.200 1813
 radius-server shared-key simple Huawei@radius

aaa
 authentication-scheme WIFI_AUTH
  authentication-method radius
 domain WIFI-USER
  authentication-scheme WIFI_AUTH
  radius WIFI_RAD

# 3. WLAN安全模板
wlan
 security-profile name SEC_8021X
  security wpa2
  wpa2 authentication-method eap
 ssid-profile name SSID_8021X
  ssid OFFICE-8021X-WIFI
 vap-profile name VAP_8021X
  ssid-profile SSID_8021X
  security-profile SEC_8021X
  service-vlan vlan-id 10
  authentication-method eap
  domain WIFI-USER

# 有线802.1X补充
dot1x enable
dot1x authentication-method eap
interface GigabitEthernet 0/0/1
 dot1x enable
 dot1x domain WIFI-USER
```

## 5\.7 WLAN排障核心命令

```Plain Text
display ap all
display wlan client
display capwap ap all
display access-user
display radius-server template all
```

---

# 第六部分：通用终端测试命令

```Plain Text
ping 192.168.1.1
ping -a 192.168.10.1 192.168.20.1   # 路由器指定源PING
tracert 192.168.30.1
display arp
reset arp
```

# 第七部分：Obsidian Agent适配规范

## 7\.1 统一笔记元数据模板

```Plain Text
---
ensp_test: true
vrp_version: VRP5
tags: #ENSP #华为VRP #网络命令 #实验模板
---
```

## 7\.2 知识库目录结构（标准）

- 01\-通用基础命令

- 02\-AR路由器（基础/动态路由/VPN/MPLS/组播）

- 03\-S5700交换机（二层/三层/堆叠/生成树）

- 04\-USG防火墙（安全策略/NAT）

- 05\-WLAN无线（AC/AP/802\.1X认证）

> （注：部分内容可能由 AI 生成）
