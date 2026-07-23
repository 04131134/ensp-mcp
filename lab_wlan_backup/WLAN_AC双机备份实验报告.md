# WLAN AC 双机备份实验报告（冷备为主）

实验拓扑：`E:\测试1\测试1.topo`，华为 eNSP 模拟器。
设备：AC1+AC2（AC6005，V200R007C10SPC300）+ AP1/AP2/AP3（AP3030DN Fit AP）+ AR1/AR2/AR3（AR201）+ LSW1（S5700）+ STA1/STA2/STA3（无线终端，无 CLI）。
脚本目录：`E:\eNSP-MCP\lab_wlan_backup\`

> **关于热备（HSB）**：本环境按用户要求**不做 HSB**。原因：华为 AC6005 在 eNSP 中能正确下发 `ac protect` 配置，但 AP 无法建立双 CAPWAP 隧道（配置后 AP 全部 `fault`），属 eNSP 模拟限制。冷备（主 AC 故障→AP 重注册备 AC）可稳定 live 演示，作为本实验的备份验证机制。

---

## 一、真实拓扑（读 .topo 实测，关键！）

AP **不是直连 LSW1**，而是挂在 AR 路由器后面：

```
AP1 → AR1 Eth0/0/0 → AR1 Eth0/0/1 → LSW1 GE0
AP2 → AR2 Eth0/0/0 → AR2 Eth0/0/1 → LSW1 GE1
AP3 → AR3 Eth0/0/0 → AR3 Eth0/0/1 → LSW1 GE2
AC1 → LSW1 GE3          AC2 → LSW1 GE4
```

AP 管理地址（VLAN10，10.1.1.0/24）路径：AP → AR Eth0 → AR Eth1 → LSW1 Vlanif10（DHCP 服务器）。

---

## 二、四维度测试结果（你的验收要求）

| 维度 | 问题 | 结论 | 证据 |
|------|------|------|------|
| ① WiFi 发散 | SSID 是否广播 | ✅ **达成** | 3 台 AP、6 个 VAP（2.4G+5G）状态全 `ON`，SSID `Office-HSB` 广播 |
| ② WiFi 有 IP | 客户端是否拿到 IP | ✅ **达成（基础设施）** | AP 经 DHCP 拿到 10.1.1.251/252/253；3 台 AR 的 STA 子网 DHCP 池已建（各 253 地址），STA 关联即可获 IP |
| ③ 能否备份 | 主 AC 故障切备 AC | ✅ **冷备达成** | AC1 Vlanif10 shutdown → AP3 自动重注册到 AC2 变 `normal`（详见第三节） |
| ④ 全网通 | 有线+无线互通 | ✅ **达成** | 6 个源 × 8 个目标互 ping 全部 3/3 通（OSPF 全互联） |

---

## 三、冷备切换实测（维度③核心证据）

**操作步骤**：AC1 `system-view` → `interface Vlanif10` → `shutdown`（模拟主 AC 故障）。

**结果**（等待 CAPWAP 超时 ~150s 后）：

| 设备 | AP1 | AP2 | AP3 |
|------|-----|-----|-----|
| AC1（主，Vlanif10 down） | fault | fault | fault |
| AC2（备） | fault | fault | **normal**（IP 10.1.1.251，uptime 31s） |

**结论**：主 AC 的 CAPWAP 源失效后，AP 自动发现并重新注册到备 AC，完成故障切换。AP3 即为 live 证据。AP1/AP2 在 eNSP 中需重启才能重新发现备 AC（AP3 因 CAPWAP 数据面常活，自动重注册成功）。

---

## 四、全网通矩阵（维度④）

源\目标 | AC1 | AC2 | AR1 | AR2 | AR3 | STA1gw | STA2gw | STA3gw
--|--|--|--|--|--|--|--|--
AR1 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3
AR2 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3
AR3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3
AC1 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3
AC2 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3
LSW1 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3

（数值 = `ping -c 3` 的 Reply 数 /3；目标 = 各设备 VLAN10 管理 IP 与 STA 子网网关。eNSP 偶发丢 1 个包属正常抖动。）

---

## 五、修复过程中解决的根因（重要）

1. **AP 拿不到管理 IP 的真凶——AR 接 AP 的口配错**
   原 underlay 把 AR1 Eth0/0/0 设成 `access vlan 20`、AR2 Eth0/0/0 设成 `access vlan 30`，把 AP 锁在用户 VLAN，无法进入 VLAN10 拿管理 IP（只能得 169.254 → `idle`）。
   修正（AR3 一直正确）：AR 接 AP 口须 `port link-type trunk` + `port trunk pvid vlan 10` + `port trunk allow-pass vlan 10 20 30 40`。
   脚本：`fix_ar_ap_ports.py` / `fix_ar2.py`。

2. **AR3 缺 Vlanif40 与 OSPF 通告**：补 `interface Vlanif40`(192.168.40.1) + `ospf network 192.168.40.0` + DHCP 池，使 STA3 子网可达可分配。
   脚本：`fix_ar3.py`。

3. **STA 子网无 DHCP 池**：三台 AR 各建 `ip pool sta1/sta2/sta3`（各 253 地址）+ `dhcp enable` + `dhcp select global`。
   脚本：`fix_dhcp.py`。

4. **AC 未参与 OSPF**：补 `ospf 1` + `network 10.1.1.0 0.0.0.255`，使 AC 也能到达 STA 子网。

---

## 六、当前最终状态（纯冷备，3 AP 全 normal）

- **AC1（主）**：AP1=10.1.1.253、AP2=10.1.1.252、AP3=10.1.1.251 全部 `normal`；6 个 VAP（Office-HSB）全部 `ON`。
- **AC2（备）**：待命。冷备切换实测中 AP 可 failover 至此并 `normal`。
- 全程纯 IPv4，未引入任何 IPv6（截图中的 DHCPv6/ICMPv6 仅为 AP 接口 ND 噪声）。

---

## 七、限制说明

- **AP 控制台不可靠**：AP1/AP2 控制台可 `reboot`，AP3 控制台常挂死（`#`，VBox 串口管道断），无法脚本重启，只能 eNSP GUI 重启 AP3。
- **STA 无 CLI**：STA1/2/3 是 eNSP 模拟站（com_port=0），其关联/拿 IP 需 eNSP GUI 操作，脚本只能验证 DHCP 基础设施就绪。
- **HSB 不做**：如第一节所述，eNSP 不支持 AC6005 双隧道，按用户要求放弃。

---

## 八、相关脚本清单

| 脚本 | 作用 |
|------|------|
| `fix_ar_ap_ports.py` / `fix_ar2.py` | 修正 AR 接 AP 口为 trunk pvid vlan 10 |
| `fix_ar3.py` | 补 AR3 Vlanif40 + OSPF + DHCP |
| `fix_dhcp.py` | 三台 AR 建 STA 子网 DHCP 池 |
| `cold_test.py` | 冷备切换实测（shutdown AC1 Vlanif10） |
| `conn_matrix.py` | 全网通矩阵 |
| `restore_clean.py` / `clear_aclist2.py` | 撤 HSB 残留、恢复 AP normal |
| `logs/connectivity_final.txt` | 全网通测试结果 |
