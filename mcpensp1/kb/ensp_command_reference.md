# 华为 eNSP 操作命令大全（知识库参考文档）

> 本文件为《华为eNSP操作命令大全》的完整副本，作为 eNSP-MCP 知识库的单一可信来源。
> 生成时间：2026-07-20

Agent 可通过 `config_method_search` / `search_kb` 检索结构化知识，
也可直接阅读本文件获取完整命令说明。

---

================================================================================
                    华为eNSP模拟器 设备操作规范与命令大全
================================================================================

目录：
一、eNSP设备类型总览
二、VRP系统基础操作规范
三、通用基础配置命令
四、交换机配置命令
五、路由器配置命令
六、防火墙（USG）配置命令
七、无线AC+AP配置
八、查看与排障命令大全
九、操作注意事项与常见问题
十、命令速查缩写表
十一、VRP通用路由平台 特征特性（补充）
十二、防火墙（USG6000V）登录特征与注意事项（补充）

================================================================================
一、eNSP设备类型总览
================================================================================

1.1 路由器（AR系列）
- 型号：AR1220、AR2220、AR3260 等
- 功能：路由转发、NAT、VPN、DHCP、ACL、广域网接入
- 操作系统：VRP（Versatile Routing Platform）通用路由平台

1.2 交换机（S系列）
- 型号：S3700、S5700、S7700、CE6800/CE12800（数据中心级）
- 功能：VLAN划分、STP生成树、链路聚合、三层交换、堆叠

1.3 防火墙（USG系列）
- 型号：USG5500、USG6000V
- 功能：安全区域划分、安全策略、NAT、VPN、入侵防御

1.4 无线设备
- AC控制器：AC6005、AC6605（管理AP，最大支持1024台）
- AP接入点：AP6010DN、AP4050DN 等（提供无线信号覆盖）

1.5 其他设备
- 终端设备：PC、Server、Client
- 网络工具：Cloud（桥接物理网卡）、Hub、Frame Relay交换机

================================================================================
二、VRP系统基础操作规范
================================================================================

2.1 命令视图层级

用户视图 <Huawei>：登录后默认进入，查看运行状态、测试连通性、保存配置
系统视图 [Huawei]：用户视图下输入 system-view，全局配置、进入其他功能视图
接口视图 [Huawei-GigabitEthernet0/0/1]：系统视图下 interface g0/0/1，接口配置
协议视图 [Huawei-ospf-1]：系统视图下 ospf 1，路由协议配置
VLAN视图 [Huawei-vlan10]：系统视图下 vlan 10，VLAN配置

2.2 视图切换快捷键

Tab          自动补全命令或参数
Ctrl+Z       从任意视图直接返回用户视图（同 return 命令）
Ctrl+C       终止当前正在执行的命令
quit         返回上一级视图
?            查看当前视图可用命令或参数帮助

2.3 命令缩写规则
- 命令不区分大小写，实操均用小写
- 支持缩写：display→dis，system-view→sys，interface→int
- 缩写必须唯一，如 "d c" 会提示命令模糊

2.4 基础操作规范

# 进入系统视图（所有配置的入口）
<Huawei> system-view
[Huawei]

# 修改设备名称（建议含位置/功能标识）
[Huawei] sysname Core-SW1
[Core-SW1]

# 设置时区（北京时间）
[Huawei] clock timezone BJ add 08:00:00

# 保存配置（重要！设备重启后配置不丢失）
<Huawei> save

================================================================================
三、通用基础配置命令
================================================================================

3.1 接口配置

# 进入接口视图（缩写：int g0/0/1）
[Huawei] interface GigabitEthernet 0/0/1

# 配置IP地址和掩码
[Huawei-GigabitEthernet0/0/1] ip address 192.168.1.1 255.255.255.0
# 或用掩码长度
[Huawei-GigabitEthernet0/0/1] ip address 192.168.1.1 24

# 开启/关闭接口
[Huawei-GigabitEthernet0/0/1] undo shutdown   # 开启
[Huawei-GigabitEthernet0/0/1] shutdown        # 关闭

# 配置接口描述
[Huawei-GigabitEthernet0/0/1] description To_Router_G0/0/0

# 配置速率和双工模式
[Huawei-GigabitEthernet0/0/1] negotiation auto          # 启用自协商
[Huawei-GigabitEthernet0/0/1] auto speed 100            # 限制最高协商速率100M
[Huawei-GigabitEthernet0/0/1] auto duplex full          # 优先全双工
[Huawei-GigabitEthernet0/0/1] speed 100                 # 强制100Mbps
[Huawei-GigabitEthernet0/0/1] duplex full               # 强制全双工

3.2 远程管理配置

Telnet配置：
[Huawei] user-interface vty 0 4
[Huawei-ui-vty0-4] authentication-mode password
[Huawei-ui-vty0-4] set authentication password cipher Huawei@123
[Huawei-ui-vty0-4] protocol inbound telnet
[Huawei-ui-vty0-4] user privilege level 3

SSH配置（推荐，更安全）：
# 生成RSA密钥对
[Huawei] rsa local-key-pair create

# 配置VTY接口
[Huawei] user-interface vty 0 4
[Huawei-ui-vty0-4] authentication-mode aaa
[Huawei-ui-vty0-4] protocol inbound ssh

# 创建本地用户
[Huawei] aaa
[Huawei-aaa] local-user admin password cipher Huawei@123
[Huawei-aaa] local-user admin privilege level 15
[Huawei-aaa] local-user admin service-type ssh

================================================================================
四、交换机配置命令
================================================================================

4.1 VLAN配置

# 创建VLAN
[Switch] vlan 10
[Switch-vlan10] description Finance_Department
[Switch-vlan10] quit

# 批量创建VLAN
[Switch] vlan batch 10 20 30

# Access端口配置（接入终端）
[Switch] interface GigabitEthernet 0/0/1
[Switch-GigabitEthernet0/0/1] port link-type access
[Switch-GigabitEthernet0/0/1] port default vlan 10

# Trunk端口配置（交换机互联）
[Switch] interface GigabitEthernet 0/0/24
[Switch-GigabitEthernet0/0/24] port link-type trunk
[Switch-GigabitEthernet0/0/24] port trunk allow-pass vlan 10 20 30
# 放行所有VLAN
[Switch-GigabitEthernet0/0/24] port trunk allow-pass vlan all

# Hybrid端口配置
[Switch-GigabitEthernet0/0/1] port link-type hybrid
[Switch-GigabitEthernet0/0/1] port hybrid pvid vlan 10
[Switch-GigabitEthernet0/0/1] port hybrid untagged vlan 10
[Switch-GigabitEthernet0/0/1] port hybrid tagged vlan 20 30

4.2 VLANIF三层接口

# 创建VLANIF接口并配置IP（作为VLAN网关）
[Switch] interface Vlanif 10
[Switch-Vlanif10] ip address 192.168.10.254 255.255.255.0
[Switch-Vlanif10] description Gateway_VLAN10

4.3 STP生成树

# 全局开启STP（默认开启）
[Switch] stp enable

# 配置STP模式（默认MSTP）
[Switch] stp mode stp       # 普通STP
[Switch] stp mode rstp      # RSTP快速生成树
[Switch] stp mode mstp      # MSTP多生成树

# 配置根桥（优先级越小越优先，默认32768）
[Switch] stp priority 4096
# 或直接指定为根桥
[Switch] stp root primary

# 配置边缘端口（接入终端的端口，加速收敛）
[Switch-GigabitEthernet0/0/1] stp edged-port enable

4.4 链路聚合（Eth-Trunk）

# 创建Eth-Trunk接口
[Switch] interface Eth-Trunk 1

# 配置聚合模式
[Switch-Eth-Trunk1] mode manual load-balance   # 手动模式
[Switch-Eth-Trunk1] mode lacp-static           # LACP静态模式

# 将物理接口加入聚合组
[Switch] interface GigabitEthernet 0/0/1
[Switch-GigabitEthernet0/0/1] eth-trunk 1
[Switch] interface GigabitEthernet 0/0/2
[Switch-GigabitEthernet0/0/2] eth-trunk 1

# 配置Trunk放行VLAN
[Switch-Eth-Trunk1] port link-type trunk
[Switch-Eth-Trunk1] port trunk allow-pass vlan all

4.5 LACP优先级配置
# 设备LACP优先级（越小越优先，默认32768）
[Switch] lacp priority 1

================================================================================
五、路由器配置命令
================================================================================

5.1 静态路由

# 配置静态路由
[Router] ip route-static 192.168.20.0 255.255.255.0 192.168.1.2
# 或用出接口
[Router] ip route-static 192.168.20.0 24 GigabitEthernet 0/0/0

# 默认路由（0.0.0.0匹配所有网络）
[Router] ip route-static 0.0.0.0 0.0.0.0 202.103.0.1

5.2 RIP协议

# 启用RIP进程
[Router] rip 1
[Router-rip-1] version 2           # 使用RIP v2
[Router-rip-1] undo summary        # 关闭自动汇总
[Router-rip-1] network 192.168.1.0 # 宣告直连网段
[Router-rip-1] network 10.0.0.0

5.3 OSPF协议

# 启用OSPF进程，配置Router ID
[Router] ospf 1 router-id 1.1.1.1

# 进入区域视图并宣告网段（反掩码）
[Router-ospf-1] area 0
[Router-ospf-1-area-0.0.0.0] network 192.168.1.0 0.0.0.255
[Router-ospf-1-area-0.0.0.0] network 10.0.0.0 0.0.0.255

# 接口方式启用OSPF
[Router-GigabitEthernet0/0/0] ospf enable 1 area 0

# 配置OSPF接口开销
[Router-GigabitEthernet0/0/0] ospf cost 10

5.4 BGP协议

# 启用BGP进程，指定本地AS号
[Router] bgp 100
[Router-bgp] router-id 1.1.1.1

# 配置IBGP对等体
[Router-bgp] peer 10.1.2.2 as-number 100
[Router-bgp] peer 10.1.2.2 connect-interface LoopBack 0

# 配置EBGP对等体
[Router-bgp] peer 202.103.0.2 as-number 200

# 进入IPv4单播地址族
[Router-bgp] ipv4-family unicast
[Router-bgp-af-ipv4] undo synchronization

# 宣告本地网络
[Router-bgp-af-ipv4] network 192.168.1.0 255.255.255.0

# IBGP下一跳改为本地
[Router-bgp-af-ipv4] peer 10.1.2.2 next-hop-local

5.5 DHCP服务

全局地址池方式：
# 全局开启DHCP
[Router] dhcp enable

# 创建地址池
[Router] ip pool VLAN10
[Router-ip-pool-VLAN10] network 192.168.10.0 mask 255.255.255.0
[Router-ip-pool-VLAN10] gateway-list 192.168.10.254
[Router-ip-pool-VLAN10] dns-list 8.8.8.8 114.114.114.114
[Router-ip-pool-VLAN10] lease day 7 hour 0 minute 0
[Router-ip-pool-VLAN10] excluded-ip-address 192.168.10.1 192.168.10.10

# 接口应用全局地址池
[Router-Vlanif10] dhcp select global

接口地址池方式：
[Router-GigabitEthernet0/0/0] dhcp select interface
[Router-GigabitEthernet0/0/0] dhcp server dns-list 8.8.8.8
[Router-GigabitEthernet0/0/0] dhcp server lease day 3

DHCP中继：
[Router] dhcp enable
[Router-Vlanif10] dhcp select relay
[Router-Vlanif10] dhcp relay server-ip 192.168.100.1

5.6 NAT配置

Easy IP（PAT端口地址转换）：
# 配置ACL匹配内网网段
[Router] acl number 2000
[Router-acl-basic-2000] rule permit source 192.168.1.0 0.0.0.255

# 在外网接口配置NAT
[Router-GigabitEthernet0/0/1] nat outbound 2000

NAT Server（端口映射/发布服务器）：
# 映射内网服务器到公网
[Router-GigabitEthernet0/0/1] nat server protocol tcp global 202.103.0.10 www inside 192.168.1.100 www

5.7 ACL访问控制列表

基本ACL（2000-2999，基于源IP）：
[Router] acl number 2000
[Router-acl-basic-2000] rule 5 permit source 192.168.1.0 0.0.0.255
[Router-acl-basic-2000] rule 10 deny source any

# 在接口应用
[Router-GigabitEthernet0/0/0] traffic-filter inbound acl 2000

高级ACL（3000-3999，基于五元组）：
[Router] acl number 3000
[Router-acl-adv-3000] rule permit tcp source 192.168.1.0 0.0.0.255 destination 10.0.0.0 0.0.0.255 destination-port eq 80
[Router-acl-adv-3000] rule deny ip source any destination any

5.8 VRRP配置

# 主设备配置
[Switch-Vlanif10] vrrp vrid 10 virtual-ip 192.168.10.254
[Switch-Vlanif10] vrrp vrid 10 priority 120      # 优先级，默认100
[Switch-Vlanif10] vrrp vrid 10 preempt-mode timer delay 20  # 抢占模式

# 备设备配置
[Switch-Vlanif10] vrrp vrid 10 virtual-ip 192.168.10.254
[Switch-Vlanif10] vrrp vrid 10 priority 100

================================================================================
六、防火墙（USG）配置命令
================================================================================

6.1 安全区域配置

默认安全区域优先级：
- trust: 85（内网）
- untrust: 5（外网）
- dmz: 50（服务器区）
- local: 100（防火墙自身）

# 将接口加入安全区域
[USG] firewall zone trust
[USG-zone-trust] add interface GigabitEthernet 1/0/1

[USG] firewall zone untrust
[USG-zone-untrust] add interface GigabitEthernet 1/0/0

[USG] firewall zone dmz
[USG-zone-dmz] add interface GigabitEthernet 1/0/2

6.2 安全策略配置

# 进入安全策略视图
[USG] security-policy

# 允许内网访问外网
[USG-policy-security] rule name Trust_to_Untrust
[USG-policy-security-rule-Trust_to_Untrust] source-zone trust
[USG-policy-security-rule-Trust_to_Untrust] destination-zone untrust
[USG-policy-security-rule-Trust_to_Untrust] source-address 192.168.1.0 24
[USG-policy-security-rule-Trust_to_Untrust] destination-address any
[USG-policy-security-rule-Trust_to_Untrust] service any
[USG-policy-security-rule-Trust_to_Untrust] action permit

# 允许外网访问DMZ区Web服务器
[USG-policy-security] rule name Untrust_to_DMZ_Web
[USG-policy-security-rule-Untrust_to_DMZ_Web] source-zone untrust
[USG-policy-security-rule-Untrust_to_DMZ_Web] destination-zone dmz
[USG-policy-security-rule-Untrust_to_DMZ_Web] destination-address 172.16.10.10 32
[USG-policy-security-rule-Untrust_to_DMZ_Web] service http
[USG-policy-security-rule-Untrust_to_DMZ_Web] service https
[USG-policy-security-rule-Untrust_to_DMZ_Web] action permit

# 允许管理防火墙（Local区域）
[USG-policy-security] rule name Trust_to_Local_Manage
[USG-policy-security-rule-Trust_to_Local_Manage] source-zone trust
[USG-policy-security-rule-Trust_to_Local_Manage] destination-zone local
[USG-policy-security-rule-Trust_to_Local_Manage] service https
[USG-policy-security-rule-Trust_to_Local_Manage] service ssh
[USG-policy-security-rule-Trust_to_Local_Manage] service icmp
[USG-policy-security-rule-Trust_to_Local_Manage] action permit

6.3 NAT策略配置

# 进入NAT策略视图
[USG] nat-policy

# 内网访问外网PAT
[USG-policy-nat] rule name Inside_NAT
[USG-policy-nat-rule-Inside_NAT] source-zone trust
[USG-policy-nat-rule-Inside_NAT] destination-zone untrust
[USG-policy-nat-rule-Inside_NAT] source-address 192.168.1.0 24
[USG-policy-nat-rule-Inside_NAT] action source-nat easy-ip

# 服务器映射
[USG-policy-nat] rule name Server_Map
[USG-policy-nat-rule-Server_Map] source-zone untrust
[USG-policy-nat-rule-Server_Map] destination-zone dmz
[USG-policy-nat-rule-Server_Map] destination-address 202.103.0.10 32
[USG-policy-nat-rule-Server_Map] service http
[USG-policy-nat-rule-Server_Map] action destination-nat static addr-to-addr 172.16.10.10

================================================================================
七、无线AC+AP配置
================================================================================

7.1 AC基础配置

# 全局开启CAPWAP
[AC] capwap source interface Vlanif 100

# 创建AP组
[AC] wlan
[AC-wlan-view] ap-group name ap-group1

# 配置SSID模板
[AC-wlan-view] ssid-profile name ssid-office
[AC-wlan-ssid-prof-ssid-office] ssid Office-WiFi

# 配置安全模板（WPA2-PSK）
[AC-wlan-view] security-profile name sec-office
[AC-wlan-sec-prof-sec-office] security wpa2 psk pass-phrase Huawei@123 aes

# 配置VAP模板（绑定SSID、安全、VLAN）
[AC-wlan-view] vap-profile name vap-office
[AC-wlan-vap-prof-vap-office] forward-mode tunnel
[AC-wlan-vap-prof-vap-office] service-vlan vlan-id 10
[AC-wlan-vap-prof-vap-office] ssid-profile ssid-office
[AC-wlan-vap-prof-vap-office] security-profile sec-office

# AP组绑定VAP模板
[AC-wlan-view] ap-group name ap-group1
[AC-wlan-ap-group-ap-group1] vap-profile vap-office wlan 1

7.2 AP上线配置

# 手动添加AP（通过MAC地址）
[AC-wlan-view] ap-id 1 ap-mac 00e0-fc12-3456
[AC-wlan-ap-1] ap-name AP-Floor1-01
[AC-wlan-ap-1] ap-group ap-group1

# 或自动发现（需DHCP Option43配置）

================================================================================
八、查看与排障命令大全
================================================================================

8.1 设备状态查看

display version                    dis ver         查看软件版本与硬件信息
display current-configuration      dis cu          查看当前运行配置
display saved-configuration        dis sav         查看已保存配置
display device                     dis dev         查看板卡状态
display interface brief            dis int bri     查看接口状态摘要
display interface g0/0/1           dis int g0/0/1  查看接口详细信息
display ip interface brief         dis ip int bri  查看接口IP状态

8.2 交换机查看命令

display vlan                                       查看所有VLAN
display vlan 10                                    查看VLAN 10详细信息
display port vlan                                  查看所有端口VLAN类型和PVID
display port trunk g0/0/24                         查看Trunk端口放行VLAN列表
display mac-address                                查看MAC地址表
display stp                                        查看STP状态
display stp brief                                  查看STP端口角色摘要
display eth-trunk 1                                查看链路聚合状态

8.3 路由查看命令

display ip routing-table                           查看IP路由表
display ospf peer                                  查看OSPF邻居关系
display ospf lsdb                                  查看OSPF链路状态数据库
display ospf interface                             查看OSPF接口信息
display rip 1 neighbor                             查看RIP邻居
display bgp peer                                   查看BGP对等体状态
display bgp routing-table                          查看BGP路由表

8.4 服务查看命令

display dhcp server pool                           查看DHCP地址池
display dhcp server lease                          查看DHCP地址分配
display acl all                                    查看所有ACL配置
display nat session all                            查看NAT会话表
display vrrp                                       查看VRRP状态

8.5 防火墙查看命令

display firewall zone                              查看安全区域
display security-policy rule all                   查看所有安全策略
display session all                                查看会话表
display firewall statistic system                  查看防火墙统计

8.6 连通性测试

# Ping测试
<Huawei> ping 192.168.1.1
<Huawei> ping -a 192.168.1.10 192.168.2.1  # 指定源地址

# Traceroute路由追踪
<Huawei> tracert 8.8.8.8

# 查看ARP表
<Huawei> display arp

================================================================================
九、操作注意事项与常见问题
================================================================================

9.1 安装与环境注意事项

1. 系统要求：仅支持Windows操作系统
2. 依赖软件：需配套安装 VirtualBox、Wireshark、WinPcap
3. 版本兼容：eNSP与VirtualBox版本必须匹配，推荐VirtualBox 5.2.44
4. 安装路径：不能包含中文、空格，建议直接安装在根目录
5. 关闭冲突软件：安装前关闭杀毒软件、360、电脑管家、防火墙
6. 虚拟化冲突：Hyper-V、VMware与VirtualBox可能冲突，需关闭Hyper-V
7. BIOS设置：必须开启VT-x硬件虚拟化

9.2 常见错误代码

错误40：设备启动失败，一直显示####
  原因：VirtualBox版本不兼容/虚拟网卡异常/Hyper-V冲突
  解决方案：1.卸载重装匹配版本VirtualBox 2.关闭Hyper-V和VBS 3.重置虚拟网卡

错误41：设备启动后无法连接
  原因：虚拟网卡IP配置问题
  解决方案：检查VirtualBox Host-Only网卡设置

镜像缺失：设备图标灰色不可拖拽
  原因：设备镜像文件丢失或路径错误
  解决方案：重新安装eNSP，检查设备镜像路径

9.3 配置操作注意事项

1. 配置前保存：重大修改前先备份当前配置 save
2. 视图层级：确认当前所在视图，命令必须在对应视图下执行
3. 接口编号：华为设备接口编号格式 类型 槽位号/子卡号/端口号
4. 反掩码：OSPF network命令使用反掩码
5. VLAN与Trunk：Trunk端口默认只放行VLAN 1，需手动添加其他VLAN
6. 防火墙默认拒绝：USG防火墙默认所有区域间流量都拒绝，必须配置安全策略
7. NAT与安全策略：防火墙做NAT后，仍需配置对应安全策略放通流量

9.4 常见故障排查思路

VLAN不通排查：
  1. 检查接口VLAN配置：display port vlan
  2. 检查Trunk放行VLAN：display port trunk g0/0/24
  3. 检查VLAN是否创建：display vlan 10
  4. 检查VLANIF接口状态：display ip interface Vlanif 10

OSPF邻居起不来排查：
  1. 检查直连连通性：ping 对端IP
  2. 检查OSPF是否在接口启用：display ospf interface
  3. 检查区域号是否一致：display ospf brief
  4. 检查网络类型、Hello时间是否匹配

防火墙不通排查：
  1. 检查接口是否加入正确区域：display firewall zone
  2. 检查安全策略是否放通：display security-policy rule all
  3. 查看会话表是否有会话建立：display session all
  4. 排障时可临时全开策略（用完立即关闭）

9.5 排错通用步骤
1. 物理层：检查接口是否UP、链路是否正常
2. 数据链路层：检查VLAN配置、Trunk放行、MAC地址学习
3. 网络层：检查IP地址、路由表、ARP表
4. 传输层：检查端口是否被ACL/防火墙阻断
5. 应用层：检查服务是否正常运行

================================================================================
十、命令速查缩写表
================================================================================

10.1 常用命令缩写

system-view          sys          进入系统视图
display              dis          查看命令前缀
interface            int          进入接口视图
GigabitEthernet      g            千兆接口缩写
current-configuration cu          当前配置
interface brief      int bri      接口摘要
routing-table        rou          路由表
quit                 q            退出当前视图

10.2 VLAN相关缩写

port link-type access          p l a
port default vlan              p d v
port link-type trunk           p l t
port trunk allow-pass vlan     p t a v

10.3 OSPF相关缩写

ospf 1 router-id 1.1.1.1      ospf 1 r 1.1.1.1
area 0                         a 0
network 192.168.1.0 0.0.0.255  net 192.168.1.0 0.0.0.255

================================================================================
十一、VRP通用路由平台 特征特性（补充）
================================================================================

11.1 VRP版本演进

VRP1（1998-2000）：集中式设计，早期中低端路由器
VRP3（2000-2004）：分布式设计，核心路由器
VRP5（2004年至今）：组件化设计，AR系列路由器、S系列交换机（eNSP主流）
VRP8（2009年至今）：多进程、多CPU、多框架构，NE系列核心路由器、CE数据中心交换机

eNSP中的情况：AR路由器、S交换机运行的是VRP5，CE系列交换机运行VRP8

11.2 VRP5 vs VRP8 核心区别

配置生效方式：
  VRP5：输入命令实时生效，无需提交
  VRP8：配置后需执行 commit 才生效

配置库结构：
  VRP5：运行配置 + 启动配置
  VRP8：候选配置 + 运行配置 + 启动配置

查看当前配置：
  VRP5：display current-configuration
  VRP8：display current-configuration（查看运行）+ display configuration candidate（查看候选）

撤销配置：
  VRP5：undo 直接撤销
  VRP8：undo 后需 commit 才生效

进程模型：
  VRP5：单进程多线程
  VRP8：多进程独立，故障隔离

11.3 VRP系统核心特性

（1）命令行智能补全
- Tab补全：输入命令前缀按Tab自动补全
- 问号帮助：任意位置输入 ? 查看可用参数
- 不区分大小写：System-View 和 system-view 效果相同
- 支持缩写：只要缩写唯一即可识别

（2）多级权限等级
  0级 访问级：ping、tracert、telnet等诊断命令
  1级 监控级：display查看类命令
  2级 配置级：业务配置命令
  3-15级 管理级：系统级、用户管理、文件操作

（3）文件系统管理
# 查看存储设备
<Huawei> dir

# 查看配置文件
<Huawei> display saved-configuration

# 保存配置（将运行配置写入启动配置文件）
<Huawei> save

# 备份配置文件
<Huawei> copy vrpcfg.zip backup.zip

# 查看Flash空间
<Huawei> display flash

（4）配置回滚与对比
# 对比运行配置和启动配置差异
<Huawei> compare configuration

# VRP8支持配置回滚（eNSP的CE设备）
[~CE6800] rollback configuration to file backup.cfg

11.4 VRP操作注意事项

1. 配置即时生效（VRP5）：敲完回车配置就生效了，不是保存才生效，save只是写入启动文件
2. undo撤销原则：几乎所有配置命令前面加 undo 就能撤销，如 undo shutdown 是开启接口
3. 视图层级严格：命令必须在对应视图下执行，在用户视图敲 ip address 会报错
4. 接口编号规则：类型 槽位号/子卡号/端口号，如 GigabitEthernet 0/0/1
5. 掩码两种写法：可以写完整掩码 255.255.255.0，也可以写前缀长度 24
6. 反掩码场景：OSPF的network命令、ACL的source用的是反掩码
7. 日志干扰：配置时经常弹出日志打断输入，可用 undo info-center enable 关闭
8. 中文提示：用户视图下执行 language-mode Chinese 可切换为中文提示

================================================================================
十二、防火墙（USG6000V）登录特征与注意事项（补充）
================================================================================

12.1 四种登录方式

Console口登录：本地直连，无需IP，最基础。首次初始化、密码恢复
Web界面登录：图形化操作，直观易用。日常管理、策略配置（推荐）
SSH登录：加密安全，命令行。远程运维管理
Telnet登录：明文传输，不安全。仅内网实验环境使用

12.2 默认账号与初始密码

默认用户名：admin（固定）
默认密码（Web）：Admin@123（注意首字母大写，含特殊字符）
首次CLI登录：密码为空，Console首次登录直接输用户名，系统强制改密
默认管理IP：192.168.0.1（G0/0/0接口默认地址）
Web默认端口：8443，HTTPS协议，访问地址：https://IP:8443

密码复杂度要求：必须包含大小写字母+数字+特殊字符，长度≥8位

12.3 eNSP中Web登录完整配置步骤

第一步：拓扑准备
- 拖入 USG6000V 防火墙
- 拖入 Cloud 云设备，绑定本地虚拟网卡（如VMnet8）
- 用网线连接防火墙的 G0/0/0 和 Cloud

第二步：命令行基础配置

# 首次登录：用户名admin，密码空，强制改密
Username: admin
Password:          # 直接回车（空密码）
Please enter old password: 
Please enter new password: Huawei@123     # 设置新密码
Please confirm new password: Huawei@123

# 进入系统视图
<USG6000V> system-view

# 关闭日志弹出（可选，避免干扰）
[USG6000V] undo info-center enable

# 切换中文提示（可选）
[USG6000V] quit
<USG6000V> language-mode Chinese
Change language mode, confirm? [Y/N] y

# 配置管理接口IP
[USG6000V] interface GigabitEthernet 0/0/0
[USG6000V-GigabitEthernet0/0/0] ip address 192.168.0.1 24

# 【关键】开启接口的管理服务权限
[USG6000V-GigabitEthernet0/0/0] service-manage enable                # 启用接口管理功能
[USG6000V-GigabitEthernet0/0/0] service-manage https permit          # 允许HTTPS Web管理
[USG6000V-GigabitEthernet0/0/0] service-manage ping permit           # 允许Ping测试连通性
[USG6000V-GigabitEthernet0/0/0] service-manage ssh permit            # 允许SSH登录
[USG6000V-GigabitEthernet0/0/0] quit

# 将接口加入Trust安全区域
[USG6000V] firewall zone trust
[USG6000V-zone-trust] add interface GigabitEthernet 0/0/0
[USG6000V-zone-trust] quit

# 开启Web管理服务（默认已开启）
[USG6000V] web-manager enable
[USG6000V] web-manager security enable port 8443

第三步：浏览器登录
1. 本地电脑网卡设置同网段IP（如 192.168.0.2/24）
2. 打开浏览器，输入：https://192.168.0.1:8443
3. 提示证书不安全 → 点击「高级」→「继续前往」
4. 输入用户名：admin，密码：你设置的密码
5. 登录成功进入Web管理界面

12.4 防火墙登录的核心注意事项

（1）service-manage 机制（最容易踩的坑）
这是防火墙独有的机制，路由器交换机没有！
- 防火墙的接口默认拒绝所有管理流量，即使IP能Ping通也登不上
- 必须在接口视图下显式开启对应服务：service-manage https permit
- 可用 service-manage all permit 全开所有管理服务（仅实验环境用）
- 查看接口管理权限：display service-manage interface GigabitEthernet 0/0/0

（2）安全区域的影响
- 管理接口必须加入 trust 区域才能正常管理
- Local区域代表防火墙自身，所有到防火墙的管理流量目标都是Local区域
- 如果从外网（untrust）管理防火墙，还需要配置安全策略放通到Local的流量

（3）Web登录注意事项
- 必须用 HTTPS，不能用HTTP（默认HTTP被禁用）
- 默认端口 8443，不是443，也不是80
- 首次登录会提示证书风险，属于正常现象，继续访问即可
- 登录超时默认较短，可配置：web-manager timeout 60（单位：分钟）

（4）密码相关
- 首次Console登录密码为空，不是Admin@123
- 系统强制要求修改密码，复杂度不够会报错
- 忘记密码只能通过Console口进入BootROM恢复，eNSP中可直接删除设备重新添加

（5）排障：登不上Web怎么办？
# 1. 先Ping测试连通性
ping 192.168.0.1

# 2. 检查接口IP是否配置正确
display ip interface GigabitEthernet 0/0/0

# 3. 检查接口管理服务是否开启
display service-manage interface GigabitEthernet 0/0/0

# 4. 检查接口是否加入trust区域
display firewall zone trust

# 5. 检查Web服务是否启用
display web-manager

# 6. 实验环境应急方案：全开管理权限
[USG-GigabitEthernet0/0/0] service-manage all permit

12.5 SSH登录配置

# 1. 生成RSA密钥
[USG] rsa local-key-pair create

# 2. 接口允许SSH
[USG-GigabitEthernet0/0/0] service-manage ssh permit

# 3. 配置管理员用户
[USG] aaa
[USG-aaa] manager-user admin
[USG-aaa-manager-user-admin] password cipher Huawei@123
[USG-aaa-manager-user-admin] service-type ssh web
[USG-aaa-manager-user-admin] level 15

12.6 防火墙与路由器交换机的登录差异总结

特性              路由器/交换机          USG防火墙
接口默认状态      管理流量默认允许        管理流量默认全部拒绝
Web管理           需额外配置HTTP服务      内置Web管理，默认8443端口HTTPS
管理权限控制      通过ACL、VTY控制        通过 service-manage 接口级控制
默认账号          无默认，需自建          内置 admin 管理员账号
登录区域概念      无安全区域概念          受安全区域+安全策略双重控制
密码复杂度        可选要求                强制复杂度要求

12.7 首次登录改密常见问题与解决方案

问题现象：
  Username: admin
  Password:
  The password needs to be changed. Change now? [Y/N]: y
  Please enter old password:
  Error: The password is invalid.
  （密码无效，改密失败，回到登录界面）

原因分析：
  不同版本USG6000V镜像默认密码不同，空密码不一定适用，需尝试对应版本的默认密码

解决方案：

【方法一：默认密码 Admin@123（最常用）】
  完整登录流程：
  Username: admin
  Password: Admin@123          （这里输入默认密码，首字母A大写）
  The password needs to be changed. Change now? [Y/N]: y
  Please enter old password: Admin@123   （旧密码还是 Admin@123）
  Please enter new password: Huawei@123  （设置新密码）
  Please confirm new password: Huawei@123

【方法二：空密码版本】
  登录时密码为空，改密时旧密码也为空：
  Username: admin        （输入用户名回车）
  Password:              （直接回车，空密码）
  The password needs to be changed. Change now? [Y/N]: y
  Please enter old password:    （直接回车，旧密码为空）
  Please enter new password: Huawei@123
  Please confirm new password: Huawei@123

【方法三：重置设备（终极方案）】
  如果以上都不行，清空配置恢复出厂：
  1. eNSP拓扑中右键防火墙 → 停止
  2. 右键防火墙 → 删除配置
  3. 重新启动设备，再尝试方法一或方法二

【密码复杂度强制要求】
  必须同时包含四类字符，缺一类都会报错：
  - 大写字母（如 H）
  - 小写字母（如 uawei）
  - 数字（如 123）
  - 特殊字符（如 @）
  示例：Huawei@123、Admin@1234、Firewall@666

【不同镜像版本默认密码汇总】
  - 旧版镜像：首次登录空密码
  - 新版镜像：Admin@123（首字母大写）
  - 个别版本：admin@123（全小写）
  可挨个尝试，都不行就重置设备

12.8 设备闲置超时机制与解决方案

超时现象：
  长时间不操作键盘，设备会自动断开连接、退出登录
  Console口提示：Configuration console time out, please press any key to log on
  Web界面提示：会话超时，自动跳回登录页
  VTY远程连接：直接断开，需重新连接

各设备默认超时时间：

【Console口（命令行直连）】
  默认超时：5分钟
  影响范围：所有设备（路由器、交换机、防火墙）的Console登录
  配置命令：
  <Huawei> system-view
  [Huawei] user-interface console 0
  [Huawei-ui-console0] idle-timeout 30        # 设置为30分钟超时
  [Huawei-ui-console0] idle-timeout 30 40     # 设置为30分40秒（分钟+秒）
  [Huawei-ui-console0] idle-timeout 0 0       # 设置为永不超时（推荐实验环境用）

【VTY远程登录（Telnet/SSH）】
  默认超时：5分钟
  影响范围：远程Telnet/SSH登录的会话
  配置命令：
  [Huawei] user-interface vty 0 4
  [Huawei-ui-vty0-4] idle-timeout 60          # 设置为60分钟超时
  [Huawei-ui-vty0-4] idle-timeout 0 0         # 永不超时

【防火墙Web界面】
  默认超时：10分钟
  影响范围：USG防火墙的Web管理界面
  配置命令：
  [USG] web-manager timeout 60                # 设置为60分钟
  [USG] web-manager timeout 1440              # 最大值1440分钟（24小时）
  取值范围：1~1440分钟，不能设为0（无法永久不超时）

【交换机Web界面】
  默认超时：10分钟
  配置命令：
  [Switch] web idle-timeout 30                # 设置为30分钟

查看当前超时配置：
  [Huawei] user-interface console 0
  [Huawei-ui-console0] display this           # 查看Console口配置

  [Huawei] display user-interface console 0   # 查看用户界面信息

实验环境建议配置（一劳永逸）：
  # 路由器/交换机配置
  system-view
  user-interface console 0
   idle-timeout 0 0
   quit
  user-interface vty 0 4
   idle-timeout 0 0
   quit

  # 防火墙额外配置Web超时
  web-manager timeout 1440

================================================================================
                              文档结束
================================================================================
提示：以上命令基于华为VRP5/VRP8系统，eNSP中不同设备型号命令可能略有差异
配置完成后务必执行 save 保存，避免设备重启后配置丢失
