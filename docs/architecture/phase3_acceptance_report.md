# eNSP-MCP 第三阶段验收报告：接口映射自动推理优化

> **阶段** 第三阶段（Step7）| **执行日期** 2026-07-20 | **基线** 255 passed / 3 skipped（第二阶段后）
> **遵守规则** 最高优先级开发原则（小步、可回滚、≤10 文件、每步测试、不破坏现有功能）
> **核心铁律** 工作记忆："永远不信任 .topo 的 srcIndex，下接口命令前必跑 display interface brief"

---

## 1. 修改文件列表（共 6 个，符合 ≤10 约束）

### 源代码（3 个）
| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `mcpensp1/interface_resolver.py` | **新建** | 型号感知接口映射 + display 校验 + 多源推理 |
| `mcpensp1/app.py` | 改动 | `_build_interface_map` 加 model 参数委托新模块；L1282 传 `dev.get("model")`；`_resolve_interface` 委托 |
| `mcpensp1/knowledge.py` | 删除 | 移除 L586-606 死代码副本 `_build_interface_map`/`_resolve_interface` |

### 测试（1 个新增）
| 文件 | 用例数 | 覆盖 |
|------|--------|------|
| `tests/test_interface_resolver.py` | 28 | 四类设备 + 回退 + 异常 + display 校验 + 多源推理 + 多接口类型 |

### 文档（2 个）
| 文件 | 改动 |
|------|------|
| `docs/modules/interface_resolver.md` | **新建**（AGENTS.md 要求新模块必须有文档） |
| `docs/modules/topology.md` | 未改动（topology.py 本身不涉及接口映射，无需更新） |

---

## 2. 修改原因

### 问题（第一阶段报告 P0 风险）
- `app.py:174-194` 的 `_build_interface_map` 不接收 model 参数，**所有设备统一用 `0/0/{idx}` idx 从 1 起**
- `knowledge.py:586-606` 有完全相同的死代码副本（无人调用，维护改错风险）
- 导致子卡设备 AR3260/USG6000V 的 srcIndex=0 被错误映射为 G0/0/1（应为 G0/0/0）
- 与工作记忆铁律"永远不信任 .topo 的 srcIndex"直接冲突

### 修复
1. **新建 `interface_resolver.py`**：型号感知映射
   - 盒式设备（S5700/S3700/AC6605）：端口 1 起始 → srcIndex=N → G0/0/(N+1)
   - 子卡设备（AR3260/USG6000V）：端口 0 起始 → srcIndex=N → G0/0/N
   - model=None 默认盒式（向后兼容旧行为）
   - `InterfaceResolver` 类提供可选 display interface brief 校验（工作记忆铁律的运行时实现）
2. **app.py 改动**：
   - `_build_interface_map(dev_element, model=None)` 加可选 model 参数，委托新模块
   - L1282 调用点 `_build_interface_map(dev)` → `_build_interface_map(dev, dev.get("model"))`
   - `_resolve_interface` 委托新模块（签名不变）
   - 旧函数名保留为 thin wrapper（向后兼容，其他调用点不受影响）
3. **knowledge.py 删除死代码**：移除 L586-606 重复副本，加注释标明去向

### 影响范围
- 仅 .topo 文件解析路径（`/api/topology/file` 上传）的接口名生成
- 旧函数签名兼容（model 可选），未传 model 时行为与旧代码完全一致
- 不影响已连接设备的命令执行

---

## 3. 测试结果

| 阶段 | 通过/跳过 | 回归 | 新增 |
|------|-----------|------|------|
| 基线（第二阶段后） | 255 passed, 3 skipped | — | — |
| 新测试单独跑 | 28 passed | — | 28 全过 |
| 全量（全部改完 + 28 新测试） | **283 passed, 3 skipped** | **0 回归** | **+28 全过** |

✅ **255 → 283，零回归，28 个新测试全部通过，3 skipped 不变**

### 新增测试覆盖维度
- **盒式设备**：S5700/S3700/AC6605 端口 1 起始（3 用例）
- **子卡设备**：AR3260/USG6000V/AR2220 端口 0 起始（3 用例）
- **盒式 vs 子卡差异**：同一 srcIndex 产生不同接口名（核心修复点验证）
- **向后兼容**：model=None 默认盒式
- **resolve_interface**：查表/回退/非法 index/None index（4 用例）
- **型号判定**：_is_module_model/_is_box_model（6 用例）
- **InterfaceResolver 类**：display 校验（未注入/无设备/命中/未命中/异常）（5 用例）
- **多源推理**：resolve_with_verification（rule/module/fallback/display）（4 用例）
- **多接口类型混合**：GE + Eth 分别计数

---

## 4. 性能变化

- 接口映射逻辑从 app.py 内联改为委托 interface_resolver（多一次函数调用，<0.1ms）
- 型号判定 `_is_module_model` 为字符串匹配（O(1)），无显著开销
- display 校验为可选（未注入 executor 时直接返回 None，零开销）
- 全量测试耗时 111.1s vs 基线 111.2s，**无显著变化**

---

## 5. Agent 能力提升

| 能力维度 | 改动前 | 改动后 | 提升 |
|---------|--------|--------|------|
| 接口映射准确率 | 所有设备统一 1 起始 | 型号感知：盒式 1 起始 / 子卡 0 起始 | AR3260/USG6000V 不再错配 |
| 死代码风险 | app.py + knowledge.py 两份重复 | 统一到 interface_resolver | 维护改错风险消除 |
| 运行时校验 | 无 | display interface brief 校验接口存在 | 落实"下命令前必跑 display"铁律 |
| 多源推理 | 单一硬编码规则 | 型号规则 + display 校验 + 回退链 | 推理可解释、可回退 |

### 工作记忆铁律落实
- ✅ "永远不信任 .topo 的 srcIndex" → 型号规则区分盒式/子卡，不再盲目 1 起始
- ✅ "下接口命令前必跑 display interface brief" → `InterfaceResolver.verify_by_display` 提供运行时校验能力
- ✅ "S5700/S3700/AC6605: srcIndex=N → G0/0/(N+1)" → 盒式规则
- ✅ "AR3260/USG6000V: srcIndex=N → G0/0/N" → 子卡规则

---

## 6. 剩余风险

| 风险 | 严重度 | 说明 | 缓解 |
|------|--------|------|------|
| display 校验未接入主流程 | 🟡 中 | .topo 解析时设备未连接，display 校验为可选 API 未自动调用 | InterfaceResolver 已提供能力，后续 agent 执行命令前可调用 |
| 型号规则基于经验未覆盖所有设备 | 🟡 中 | _BOX_MODEL_KEYWORDS/_MODULE_MODEL_KEYWORDS 列表可能不全 | 通用判断兜底（AR/USG/Router/FW 关键词）；model=None 默认盒式 |
| app.py 本地 TopologyEngine 死代码副本 | 🟢 低 | app.py L196-240 与 topology.py 重复，但不在本阶段范围 | 留待后续架构审计（P4） |
| 未处理 G1/0/N 槽位 | 🟢 低 | AR3260 部分接口可能是 GigabitEthernet1/0/0 而非 0/0/0 | 当前按工作记忆主规则处理，边界情况留后续 |

---

## 7. 下一阶段建议

### 第四阶段（稳定性增强，P1，独立可做）
- **Step3**：runtime 接入 command_validator（执行前校验视图）
- **Step4**：runtime 接入 transaction（失败回滚，关键）
- **Step5**：runtime 接入 plan_reviewer（计划审核）
- **Step6**：修 verifier 两个永真判定（verify_acl / verify_connectivity）
- **Step8**：统一异常体系（exceptions.py）

### 本阶段后续增强（可选）
- 让 agent 执行接口命令前自动调 `InterfaceResolver.verify_by_display`（落实铁律）
- 扩展型号规则表，覆盖更多 eNSP 设备型号
- 接入 LLDP/display mac-address 邻居交叉验证

---

## 8. 回滚方案

- **完全回滚**：git revert 本阶段 3 个源文件改动，恢复 app.py/knowledge.py 原始 _build_interface_map
- **部分回滚**：app.py L1282 改回 `_build_interface_map(dev)`（不传 model），退回旧行为
- **行为回滚**：interface_resolver.build_interface_map 的 model 传 None 即等价旧行为

所有改动均向后兼容（model 可选参数，旧调用不传 model 时行为不变）。
