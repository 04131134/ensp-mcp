# ADR-004: 建立 CLI 状态机

## 状态
已采纳（2025-06）

## 背景
华为/H3C 设备的 CLI 有多层视图结构（用户视图 → 系统视图 → 接口/VLAN/OSPF 等子视图）。早期实现通过简单的字符串匹配判断视图，存在以下问题：
- 无法区分 `<SW1>`（用户视图）与 `[SW1]`（系统视图）
- 翻页（`---- More ----`）处理不稳定
- 命令超时一刀切，未区分 display 和 config 类命令

## 决策
建立**基于 prompt 检测的 CLI 状态机**，自动识别视图并分类处理命令。

## 核心设计
1. **Prompt 模式库**：正则匹配 `<NAME>`、`[NAME]`、`[NAME-xxx]` 等
2. **命令四分类**：display(15s) / diagnostic(30s) / config(5s) / interactive(60s)
3. **翻页处理**：检测 `---- More ----` 自动空格翻页
4. **视图切换**：`auto_view=True` 时自动 `system-view` / `return`
5. **安全拦截**：`is_blocked_command()` 过滤危险命令

## 理由
- **可靠性**：prompt 驱动读取比固定超时更可靠
- **效率**：display 类命令不需要等 30s
- **安全**：自动拦截误操作的破坏性命令

## 后果
- 提升了 Telnet 交互的稳定性（已在 Phase 4 实现）
- 新增 25 条单元测试覆盖 prompt 检测
- 后续新增设备型号只需扩展 prompt 模式库即可
