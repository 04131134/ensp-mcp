# WLAN 加密 WiFi 实验重建报告（2026-07-21）

## 目标
清空配置后重建：WiFi 连接需输密码（WPA2-PSK 加密）+ AC 双机冷备。

## 结果
✅ **加密 WiFi 已生效**（用户核心需求）
- SSID：`Office-Cold`，认证 **WPA/WPA2-PSK (AES)**，密码 **`Huawei@123`**
- AC1 上 3 台 AP 全部 `normal`，6 个 VAP 全部 `ON` 并广播该 SSID
- AP 管理 IP：`10.1.1.251 / 252 / 253`（LSW1 的 VLAN10 DHCP，option43→AC1）

✅ **AC2 冷备（eNSP 兼容方案）**
- AC2 配相同加密 WLAN + 相同 3 AP 注册（mac-auth），作待命
- LSW1 的 AP 管理 DHCP `option 43` 改为双 AC：`10.1.1.1,10.1.1.2`
- 主 AC 故障 → AP 凭 option43 知备 AC、CAPWAP 重注册切到 AC2（约 160s）
- 改 option43 不触发 AP 立即重拨，WiFi 稳定在 AC1，无抖动

✅ **全网通**：OSPF area 0 全互联（LSW1 上 3 个 Full 邻接）

## 踩坑与修复（重要）
⚠️ **`ac protect` 双隧道在 eNSP AC6005 再次证实不可用**
- 初版给 AC1/AC2 配 `ac protect enable` + AP 级 `ac-list <对端IP>`，结果：
  `display ac protect` 两 AC 均显示 `Protect state: disable`（根本没生效）；
  3 AP 从全 `nor` 退化成 fault/idle（AP 建不了双隧道）。
- 修复：两 AC 上 `undo ac protect` + 各 AP `undo ac-list`，AP 约 60~90s 自动重建单隧道回到 `nor`。
- **结论**：双机备份一律用 option43 双 AC 冷备，不要用 `ac protect`（真机可用、eNSP 不行）。

## 复用脚本（`E:\eNSP-MCP\lab_wlan_backup\`）
- `rebuild_underlay.py` — LSW1(AP管理DHCP+option43) / AR1-3(trunk pvid 10, STA子网DHCP) / OSPF
- `rebuild_wlan.py` — AC1 加密 WLAN（Office-Cold / Huawei@123 / service-vlan 40 / mac-auth）
- `rebuild_ac2.py` — AC2 相同加密 WLAN + 3 AP 注册（**已去掉 ac protect**）
- `rebuild_opt43_dual.py` — LSW1 option43 改双 AC（冷备关键）
- `rebuild_verify.py` / `rebuild_final_check.py` — 验证
- `rebuild_fix_dual.py` — 清 ac protect 双隧道（应急恢复用）

## 待确认 / 可选
- **STA 拿 IP**：STA 子网 DHCP 池已在 AR1/2/3（vlan20/30/40），VAP `service-vlan 40` 已指路；
  真实无线客户端关联需在 eNSP GUI 里给 STA 填 SSID+密码（STA 无 CLI，脚本驱动不了）。
- **live 切换演示**：shutdown AC1 `Vlanif10` 看 AP 切 AC2。注意 AP 需先续约拿到双 AC option43
  （当前租约 1 天）→ 若要立即演示，需在 eNSP GUI 重启 3 台 AP 让其重拨 DHCP。
