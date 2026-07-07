# ErrorLibrary（错误查询库）

## 位置
`mcpensp1/agent/error_library.py`

## 职责
收录 28 种华为 CLI 常见错误，提供原因分析和自动恢复建议。Recovery 优先查询 Error Library。

## 错误分类
- connection（连接类）
- syntax（语法类）
- config（配置类）
- ospf/bgp/acl/aaa/dhcp/routing（协议类）
- interface（接口类）

## 核心接口
| 方法 | 说明 |
|------|------|
| `lookup(error_text)` | 查询错误 → {found, cause, fix, auto_recoverable} |
| `is_recoverable(error_text)` | 快速判断是否可自动恢复 |
| `get_fix(error_text)` | 获取修复建议 |
| `search_by_category(category)` | 按类别搜索 |

## 依赖
- `kb/errors/huawei_errors.json` — 错误数据文件

## 禁止事项
- 不允许在 Recovery 中让 AI 猜测错误原因
