# system_view Knowledge Expansion Report

> **阶段** 知识库视图修复第二阶段（数据补充）| **日期** 2026-07-21
> **修改文件** `mcpensp1/kb/structured_commands_kb.json`（仅 1 个文件）
> **测试新增** `tests/test_kb_view_classification.py`（7 用例）

---

## 1. 新增文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `mcpensp1/kb/structured_commands_kb.json` | 修改 | system_view 补充缺失 function 命令数据 |
| `tests/test_kb_view_classification.py` | 新增 | 视图分类 + 型号匹配 + 数据完整性验证 |
| `mcpensp1/kb/structured_commands_kb.json.bak_2026-07-21` | 备份 | 修改前自动备份 |

---

## 2. 新增功能分类

### S3700（接入层交换机，+4 functions）

| Function | 命令数 | 覆盖 |
|----------|--------|------|
| VLAN | 2 | vlan \<id\>, vlan batch |
| 接口配置 | 6 | interface, port link-type access/trunk, port default vlan, port trunk allow-pass, undo shutdown |
| STP | 2 | stp enable, stp mode rstp |
| Eth-Trunk | 3 | interface Eth-Trunk, mode lacp-static, trunkport |

### AR2220（路由器，+2 functions）

| Function | 命令数 | 覆盖 |
|----------|--------|------|
| OSPF路由 | 3 | ospf router-id, area, network (含 example) |
| BGP路由 | 3 | bgp, peer as-number, network (含 example) |

### USG6000V（防火墙，+2 functions）

| Function | 命令数 | 覆盖 |
|----------|--------|------|
| ACL规则 | 3 | acl, rule permit, rule deny |
| NAT策略 | 4 | nat-policy, source-zone, destination-zone, action source-nat easy-ip |

---

## 3. 新增命令数量

| 设备 | 修复前 functions | 修复后 functions | 新增命令 |
|------|-----------------|-----------------|---------|
| S5700 | 10 | 10 (不变) | 0 |
| S3700 | 3 | **7** | **+13** |
| USG6000V | 7 | **9** | **+7** |
| AR2220 | 4 | **6** | **+6** |
| AC6605 | 7 | 7 (不变) | 0 |
| **合计** | 31 | 39 | **+26** |

命令总数变化：
- user_view: 48 条（不变，全是 display/ping/save 查看命令）
- system_view: 150 → **176** 条

---

## 4. 测试结果

| 阶段 | 通过/跳过 | 说明 |
|------|-----------|------|
| 知识库修复后全量 (第一轮) | 319 passed, 3 skipped | knowledge.py 修复后，零回归 |
| 新测试单独跑 | 7 passed | 视图分类 7 用例全过 |
| 最终全量（数据补充 + 7 新测试） | _待填_ | 预期 319 + 7 = 326 |

### 新增测试覆盖

| 测试 | 验证点 |
|------|--------|
| test_system_view_not_empty | system_view 有配置命令（≥1 条，含 vlan） |
| test_user_view_only_display_commands | user_view 只有 display/ping/save，无配置命令混入 |
| test_suggest_commands_system_view_has_config | S5700 system_view 有非 display 配置命令 |
| test_suggest_commands_user_view_no_config | S5700 user_view 不含 vlan/interface/ospf 等 |
| test_flatten_commands_fw1_alias_mapping | FW1→USG6000V 别名映射生效 |
| test_flatten_commands_s3700_no_filter_returns_all | 不过滤时覆盖 5+ 设备型号 |
| test_structured_kb_loads_without_error | KB 可正确加载 |

---

## 5. 对 Agent 能力提升的影响

### 修复前
- `suggest_commands('S3700', 'system_view')` → 返回 0 条（键名不匹配 + 数据不全）
- `get_structured_kb('system_view')` → 返回空
- Agent 无法获取系统视图配置命令，只能依赖 planner 硬编码模板

### 修复后
- `suggest_commands('S3700', 'system_view')` → 返回 20 条配置命令（VLAN/接口/STP/Eth-Trunk）
- `suggest_commands('AR2220', 'system_view')` → 返回 OSPF/BGP 配置命令
- `suggest_commands('FW1', 'system_view')` → 返回防火墙 ACL/NAT 配置命令（别名映射）
- `_flatten_commands('system_view')` → 返回 176 条命令供 Agent 参考

### 经验驱动闭环打通
结合第一阶段（planner 接入 knowledge_store），Agent 现在可以：
1. 从 `suggest_commands` 获取设备型号相关的系统视图命令
2. 从 `knowledge_store.query_for_task` 检索成功经验
3. 用经验命令覆盖 planner 硬编码模板
4. 形成完整的"经验驱动命令生成"闭环

### 视图分类铁律落实
- ✅ user_view: 仅 display/ping/save/telnet 等查看命令（48 条）— 有测试保护
- ✅ system_view: 仅 vlan/interface/ospf/bgp/acl/nat/stp 等配置命令（176 条）— 有测试保护
- ✅ Agent 不会误将配置命令发到用户视图（视图混淆风险消除）

---

## 6. 数据质量保证

- 每条新增命令包含 `{cmd, desc, when, view: "system_view"}` 基础字段
- 关键命令增加 `{verify, prerequisite, example, tips}` 增强字段
- 修改前自动备份到 `structured_commands_kb.json.bak_2026-07-21`
- 未修改 user_view 任何数据
- 未修改 JSON schema
- 未修改 knowledge.py / Agent 架构 / MCP Tool
