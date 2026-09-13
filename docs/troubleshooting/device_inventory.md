# eNSP-MCP 实机设备清单（终端联调）

- 生成时间：2026-07-20 17:33:14  
- 后端：http://127.0.0.1:5000  
- 扫描端口：17（2000–2016）  
- **成功连接：15 / 17**  
- 失败端口：2005, 2012

## 已连接设备

| 端口 | eNSP 标签 | 型号 | VRP 版本 | 运行主机名(Sysname) | 连接 |
|-----:|----------|------|---------|-------------------|------|
| 2000 | AP1 | AP3030DN FIT | 5.160 | Huawei | OK |
| 2001 | AP2 | AP3030DN FIT | 5.160 | Huawei | OK |
| 2002 | lsw5 | S3700 | 5.110 | lsw5 | OK |
| 2003 | lsw6 | S3700 | 5.110 | lsw6 | OK |
| 2004 | lsw7 | S3700 | 5.110 | lsw7 | OK |
| 2006 | lsw8 | S3700 | 5.110 | lsw8 | OK |
| 2007 | lsw3 | S5700 | 5.110 | lsw3 | OK |
| 2008 | lsw1 | S5700 | 5.110 | lsw1 | OK |
| 2009 | USG6000V1 | USG6000V1 | 5.170 | USG6000V1 | OK |
| 2010 | AC1 | AC6605 | 5.160 | ac1 | OK |
| 2011 | SW1 | S3700 | 5.110 | Huawei | OK |
| 2013 | AR1 | AR3200 | 5.130 | ar1 | OK |
| 2014 | lsw9 | S3700 | 5.110 | lsw9 | OK |
| 2015 | lsw2 | S5700 | 5.110 | lsw2 | OK |
| 2016 | lsw4 | S5700 | 5.110 | lsw4 | OK |

## 未连接端口

- **端口 2005**：`FAIL: Connection failed: ConnectionRefusedError: [WinError 10061] 由于目标计算机积极拒绝，无法连接。`
- **端口 2012**：`FAIL: Connection failed: ConnectionRefusedError: [WinError 10061] 由于目标计算机积极拒绝，无法连接。`

## 说明

- 端口 2005、2012 不在拓扑 `E:\测试\测试.topo` 中（未启动 / Cloud 设备），连接被拒绝，属预期。
- FW1（USG6000V，端口 2009）首登强制改密已修复：默认 `admin/Admin@123` → 改密为 `Huawei@123`，现已正常登录并返回 `display version`。
- 运行主机名(Sysname)取自 `display version` 输出末尾的 CLI 提示符；AP1/AP2/SW1 仍为默认 `Huawei`（未配置 sysname），AC1/AR1 的 VRP 主机名为小写 `ac1`/`ar1`。
- 原始逐设备 `display version` 全文见 `device_test_report.json` 的 `VersionOutput` 字段。
