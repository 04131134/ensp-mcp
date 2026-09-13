# eNSP-MCP 实机联调问题排查报告（2026-07-20）

## 背景

- **项目**：eNSP-MCP —— 一个 Python 编写的 MCP 服务器，用于驱动华为 eNSP 网络模拟器。
- **目标**：用户在 `E:\测试\测试.topo` 打开拓扑并启动 15 台设备，要求驱动 eNSP-MCP 后端对**真实运行中的设备**做端到端测试，最终产出一份可用的设备清单。
- **调用链路**：AI Client → MCP Server（`mcp_server.py`，stdio）→ Flask Web UI（`app.py`，`http://127.0.0.1:5000`）→ 通过 Telnet 连接本地 eNSP 设备控制台（`127.0.0.1:2000+`，每台设备一个端口）。
- **用户明确要求**：遇到 eNSP 相关问题，先**检索华为 eNSP 的运行特性 / 网上的解决办法**，不要靠猜。（后续正是用 raw socket 直接探针设备控制台 + 参考开源项目 `ensp-cli-mcp` 确认行为的。）

---

## 问题一：`/api/devices/connect` 对所有设备返回失败

### 现象
- `POST /api/devices/connect {"port": N}` 对每一台设备都返回 `{"success": false, "error": "Connection failed"}`。
- 但 `GET /api/devices/scan` 正常，能扫到 14 个在线的设备控制台（端口 2000–2004、2006–2011、2013–2016）。
- 矛盾点：**能扫到设备，却连不上任何一台**。

### 排查过程
- 用独立脚本 `_diag4.py` 复刻 `connect_device` 函数的本体逻辑，结果**连接成功**（拿到 `name=AP1, device_type=huawei`）。
- 这说明：连接逻辑本身没问题，故障出在 `connect_device` 函数外层，**异常被 `except` 吞掉了**。

### 根因（已定位）
- `app.py` 的 `connect_device()` 内部第 386 行调用了 `TelnetConnection('127.0.0.1', port)`，但 `TelnetConnection` 这个符号**从未被 import 进 `app.py`**（只有 `device_manager.py` 导入过它）。
- 该 `NameError` 被 `connect_device` 的兜底 `except Exception` 捕获，并被**泛化成一句 "Connection failed"** 返回给前端。
- 为什么 scan 正常、connect 必败？因为 `scan` 走的是 `dm.scan_devices`，根本不碰 `TelnetConnection`；只有 `connect` 才会实例化 `TelnetConnection`，于是被 `NameError` 命中。

### 可能的原因 / 延伸分析
- **重构遗漏**：很可能是某次代码拆分 / 重构时，把 `TelnetConnection` 的使用加进了 `app.py`，却忘了补对应的 `import` 语句。
- **静默失败反模式**：`connect_device` 的 `except` 只返回一句字符串，既不抛栈、也不记日志，导致这个 `NameError` 在没有任何报错的情况下被完全掩盖。
- **表象误导**：因为扫描能成功，很容易让人误判成"eNSP 设备没起来"或"端口被占"，而真实原因是纯代码层的符号缺失。

### 修复
- 在 `app.py` 导入区新增 `from connection import TelnetConnection`。
- 同时把兜底 `except` 改为**暴露真实异常**：返回 `Connection failed: <异常类型>: <信息>` 并加 `logger.exception`（便于排错，但不向前端吐完整 traceback）。

---

## 问题二：`/api/devices/command` 对所有"已连接"设备返回失败

### 现象
- 问题一修好后，连接全部成功，但发 `display version` 等只读命令时，所有设备都返回 `{"success": false, "error": "Command execution failed"}`，且 `output` 为空。
- `GET /api/devices` 显示 14 台设备都 `alive: true`（心跳机制没有杀连接），所以不是"连上又掉了"。

### 排查过程
- 真实异常**不在 stdout**：我把 stdout/stderr 重定向到了 `server_run.log`，但 Python 对重定向的文件默认是**块缓冲**，长驻进程不会刷新，所以那里看不到错误。
- 真正报错在 `mcpensp1/server_debug.log` —— 该 logger 配置了 file handler，会**实时 flush**。日志实锤：
  ```
  Command failed for 127.0.0.1:2000: name 'view_router' is not defined
  ```

### 根因（已定位）
- `send_command()` 内部引用了 `view_router`（命令视图分类 / 视图检测 / 视图切换）和 `check_command_error`（命令错误回显检测），但这两个符号定义在 `view_router.py` 中，**从未被 import 进 `app.py`**。
- 真实 `NameError` 被 `send_command` 的兜底 `except Exception` 吞成一句 "Command execution failed"。

### 可能的原因 / 延伸分析
- **同样属于"import 缺失 + 吞异常"**：`view_router` 是后端命令处理的核心模块，但作为 Flask 入口层的 `app.py` 漏掉了它的 import。
- **表象极易误判**：这是"连接成功、命令却全失败"，非常像"设备断链"或"命令通道坏了"，实际上只是代码层的 `NameError`。
- **共性风险**：问题一和问题二本质是同一条：函数体引用了未 import 的模块级符号，异常被兜底 `except` 吞掉。这强烈暗示代码里可能还有类似的遗漏。

### 修复
- 在 `app.py` 导入区新增 `from view_router import view_router, check_command_error`。
- 重启后端后，`display version` 正常返回 507 字符的 VRP 输出（AP3030DN，VRP 5.160），命令通道打通。

---

## 问题三：防火墙（USG6000V，端口 2009）登录挂死 / 超时

### 现象
- 14 台非防火墙设备 connect / command 全部正常后，**唯独 FW1 / USG6000V（端口 2009）始终超时**（单次 > 40s，整批扫描被它拖住）。

### 用户纠正与关键信息
- 用户明确：防火墙默认凭证是 **账户 `admin`，密码 `Admin@123`**（代码原先硬编码成了 `Admin@1234`，多了一个 `4`）。
- 用户给出了**精确的首登强制改密序列**：
  ```
  Username: admin
  Password: Admin@123            ← 输入默认密码
  The password needs to be changed. Change now? [Y/N]: y
  Please enter old password: Admin@123   ← 旧密码仍是 Admin@123
  Please enter new password: Huawei@123  ← 设置新密码（需符合复杂度）
  Please confirm new password: Huawei@123
  ```

### 排查过程（用 raw socket 探针 `_fw_probe.py` 直连设备控制台）
- 用 `n` 回答 "Change now?" 时，设备走到 `Please Press ENTER.` —— 说明这台设备**强制要求首登改密**。
- 旧代码的登录流程：回答 `y` 后，对 `old → new → confirm` 三次输入都发了**同一个 `Admin@123`**，并且**漏掉了最后的 confirm 提示** → 设备侧一直卡在等待 confirm，客户端 40s 超时挂死。

### 根因（已定位）
1. **密码常量错误**：硬编码为 `Admin@1234`，与真实默认密码 `Admin@123` 不符。
2. **改密流程不完整**：`handle_firewall_login` 没有正确区分 old / new / confirm 三次输入，且漏掉了 confirm 提示。
3. **缺少进入 CLI 的最后一步**：设备改密完成后会打印 `Please Press ENTER.`，旧代码没有发一个 `\r\n` 去应答它，于是进不了 CLI 提示符。

### 可能的原因 / 延伸分析
- **这是华为 eNSP 的"运行特性"，不是 bug**：USG6000V 等安全设备故障默认密码存在安全策略，首登必须改密。这正是用户要求"先检索 eNSP 运行特性、别靠猜"的原因 —— 直接探针设备控制台 + 参考开源项目 `ensp-cli-mcp`（其 `execute` 也做了 VRP 提示符检测与首登处理）即可确认。
- 代码原先假设"密码就能直接登录"，完全没有考虑首登改密这个分支，导致对安全设备的适配缺失。

### 修复
- 重写 `connection.py` 的 `handle_firewall_login(username='admin', password='Admin@123', new_password='Huawei@123')`：
  1. 先试 `password`，若被再次要求 Password 则回退 `new_password`（重连韧性）；
  2. 遇到 `[Y/N]` 发 `y\r\n`；
  3. 遇到 `old password` 依次发 `Admin@123`(旧) → `Huawei@123`(新) → `Huawei@123`(确认)；
  4. 末尾 `sock.send(b'\r\n')` 应答 `Please Press ENTER.`，进入 CLI。
- 验证：端口 2009 connect → `USG6000V1 (HUAWEI)`；`display version` 返回 589 字符（VRP 5.170 / USG6000V1 V500R005C10SPC300）。

---

## 问题四（次要）：设备清单报告的字段解析错误

### 现象
- 全量扫描脚本（`m4384n`）生成的 `device_test_report.json` 里，`Model` 列全部是 `R`，`Sysname` 列全部是命令回显 `display current-configuration | include sysname`。

### 根因
- 正则过于宽松：
  - 型号提取用了 `\(([^)]+)\)`，结果匹配到了 VRP 版本行的 `(R)`（"VRP (R) software"），而非真正的 `(AP3030DN FIT V200R007C10SPC300)` 这种含型号+版本的组。
  - `sysname` 提取用了 `$_ -match 'sysname'`，结果把**命令自身回显**（命令里就包含 "sysname" 字样）当成了输出，而非真正的 `sysname lsw5` 配置行。

### 修复
- 不需要重打设备，直接复用已保存的 `VersionOutput` 重新解析：
  - 型号：取含 `V<数字>` 的括号组 `(MODEL VVER)`，再剥掉末尾版本号 → 得到 `AP3030DN FIT` / `S3700` / `S5700` / `USG6000V1` / `AC6605` / `AR3200`。
  - 运行主机名(Sysname)：取 `display version` 输出**末尾的 `<prompt>`**（即当前 CLI 主机名）。
- 重写 `device_test_report.json`（并去掉 PowerShell 写入时带上的 UTF-8 BOM）。

---

## 共性根因 / 模式总结（重点）

今天暴露的四处问题，有三处是**同一条根因的不同表现**：

> **「函数体引用了未 import 的模块级符号，且被兜底 `except` 吞掉异常」**
> 已命中：`TelnetConnection`、`view_router` / `check_command_error`、`handle_firewall_login` 的密码逻辑（外加报告脚本的正则）。

带来的核心隐患是**静默失败**：前端永远只看到一句泛化的 "Connection failed" / "Command execution failed"，真实异常（往往是 `NameError`）被完全隐藏。

### 排查方法论（经验）
- 遇到"扫描能成功、连接却全失败"或"连接成功、命令却全失败"或"某类设备整体挂死"时：
  1. **优先看 `mcpensp1/server_debug.log`**（它有会 flush 的 file handler），搜 `Command failed for ...` / `connect_device failed for ...`，那里才是真实异常。
  2. `server_run.log`（stdout 重定向）是块缓冲的，**长驻进程不刷新、看不到实时错误**，别被它误导。
  3. 用"独立脚本复刻函数本体却成功"来快速判定：是连接逻辑坏了，还是异常被 `except` 吞了。
- 涉及设备行为（尤其安全设备的首登改密）时，**直接 raw socket 探针设备控制台**，或查 `ensp-cli-mcp` 等开源参考实现，按华为 eNSP 真实运行特性来写适配，不要脑补。

### 当前状态
- 全量清单已跑通：**15 台连接成功 / 17 端口**（2005、2012 不在拓扑，预期拒绝）。
- 交付物：`device_test_report.json`（含逐设备完整 `display version` 输出）、`device_inventory.md`（可读表格）。
- `app.py` / `connection.py` 修复**已于 2026-07-20 17:55 完成并验证**：

### 最终修复确认（2026-07-20）

| # | 问题 | 修复内容 | 状态 |
|---|------|---------|------|
| 1 | `TelnetConnection` NameError | `app.py` L13: `from connection import TelnetConnection` | ✅ |
| 1b | `connect_device` 吞异常 | `app.py` L412 `logger.exception` + L417 暴露真实异常类型/消息 | ✅ |
| 2 | `view_router` NameError | `app.py` L14: `from view_router import view_router, check_command_error` | ✅ |
| 2b | `send_command` 吞异常 | `app.py` L476 `logger.exception` + L479 暴露真实异常类型/消息 | ✅ |
| 3 | 防火墙首登改密 | `connection.py` L294-384: 完整 old→new→confirm 流程 + `\r\n` 应答 | ✅ |
| 4 | 报告解析错误 | `device_test_report.json`/`device_inventory.md` 重写解析逻辑 | ✅ |

**测试结果**：`pytest tests/` —— **239 passed, 0 failed**
