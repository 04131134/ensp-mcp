# Verifier（SemanticVerifier）

## 位置
`mcpensp1/agent/verifier.py`

## 职责
对设备配置结果进行语义级验证，自动执行验证命令并解析输出，判断配置是否达到预期状态。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| `command_executor` | `Callable` | 命令执行回调 `(path, cmd) -> dict` |

## 输出
```python
VerificationResult:
    check_name: str           # 检查项名称
    passed: bool              # 是否通过
    details: List[Dict]       # 详细结果
    raw_output: str           # 原始输出
    summary: str              # 人类可读摘要
```

## 支持的验证类型

| 方法 | 验证内容 |
|------|---------|
| `verify_interfaces()` | 接口状态（up/down）、IP 配置 |
| `verify_vlans()` | VLAN 是否存在、端口归属 |
| `verify_routing()` | 路由表正确性 |
| `verify_ospf()` | OSPF 邻居关系 |
| `verify_stp()` | STP 状态 |
| `verify_acl()` | ACL 规则匹配 |
| `verify_connectivity()` | 网络连通性（ping） |
| `verify_custom()` | 自定义验证规则 |

## 依赖
- `command_executor.CommandExecutor` — 执行验证命令
- 内置解析器（`_parse_ip_brief`, `_parse_vlan`, `_parse_ospf_peer` 等）

## 禁止事项
- ❌ 不允许验证失败时返回 passed=True
- ❌ 不允许跳过验证类型的输出解析
- ❌ 不允许直接修改解析器而不更新测试

## 调用关系
```
AgentRuntime._execute_verify_node() → SemanticVerifier
    ├── verify_interfaces() → display ip interface brief → _parse_ip_brief()
    ├── verify_vlans() → display vlan → _parse_vlan()
    ├── verify_ospf() → display ospf peer → _parse_ospf_peer()
    └── verify_connectivity() → ping → 检查丢包率
```
