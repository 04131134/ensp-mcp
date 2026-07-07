# PromptParser（设备 Prompt 解析器）

## 位置
`mcpensp1/agent/prompt_parser.py`

## 职责
根据设备实际返回的 prompt 字符串判断当前视图。不相信 AI 的猜测，以设备输出为准。

## 支持的 Prompt 模式
- `<Huawei>` → USER
- `[Huawei]` → SYSTEM
- `[Huawei-GigabitEthernet0/0/1]` → INTERFACE
- `[Huawei-vlan10]` → VLAN
- `[Huawei-ospf-1]` → OSPF
- `[Huawei-ospf-1-area-0.0.0.0]` → AREA
- `[Huawei-acl-adv-3000]` → ACL
- `[Huawei-bgp]` → BGP
- `[Huawei-rip-1]` → RIP

## 核心接口
| 方法 | 说明 |
|------|------|
| `parse(prompt)` | 解析 prompt → {view, params, confidence} |
| `parse_quick(prompt)` | 快速解析，只返回 CLIView 枚举 |
| `detect_from_output(output)` | 从多行命令输出中检测 prompt |
| `is_valid_prompt(prompt)` | 验证是否为合法 prompt |

## 依赖
- `kb/cli/view_rules.json` — 视图规则文件

## 禁止事项
- 不允许修改规则文件后不调用 reload_rules
