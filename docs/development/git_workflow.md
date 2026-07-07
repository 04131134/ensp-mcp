# Git 工作流

## 分支命名

| 前缀 | 用途 | 示例 |
|------|------|------|
| `codex/` | Codex AI 开发分支 | `codex/safety-net`, `codex/refactor-kb` |
| `feature/` | 功能开发 | `feature/snapshot-diff` |
| `fix/` | Bug 修复 | `fix/telnet-timeout` |
| `refactor/` | 重构 | `refactor/p0` |

## 开发流程

```
1. 从 main（或最新稳定分支）创建 codex/ 分支
        ↓
2. 运行 pytest tests/ 确认基线通过
        ↓
3. 小步修改（每步 ≤ 10 个核心文件）
        ↓
4. 每步运行 pytest tests/
        ↓
5. 提交（格式见下方）
        ↓
6. 推送并创建 PR
        ↓
7. Code Review → 合并
```

## 提交规范

### 格式

```
<类型>: <简短描述>

<详细说明>
- 修改了哪些文件
- 为什么修改
- 对兼容性的影响
- 如何回滚
- 测试结果
```

### 类型

| 前缀 | 含义 |
|------|------|
| `安全网:` | 安全网/基线建立 |
| `知识库:` | 文档/知识库新增 |
| `feat:` | 新功能 |
| `fix:` | Bug 修复 |
| `refactor:` | 重构 |
| `test:` | 测试补充 |
| `docs:` | 文档更新 |
| `chore:` | 杂项 |

### 示例

```
安全网: 补充回归测试 — command_executor(4) + knowledge(5) + heartbeat(3) + mcp_server(3) = 15条
```

## 修改前检查清单

- [ ] 是否在非 main 分支？
- [ ] 是否已阅读 AGENTS.md？
- [ ] 是否已阅读相关 docs/ 文档？
- [ ] 是否已运行 pytest tests/ 确认基线？
- [ ] 本次修改是否 ≤ 10 个核心文件？

## 提交前检查清单

- [ ] pytest tests/ 全部通过？
- [ ] 新增功能有对应测试？
- [ ] 公开接口无删除/重命名？
- [ ] 文档已同步更新？

## 回滚方式

```bash
# 回滚到上一个提交
git revert HEAD

# 回滚整个分支
git checkout main
```

## 禁止事项

- ❌ 直接 push 到 main/master
- ❌ 提交不写说明
- ❌ 跳过测试直接合并
- ❌ 一次提交修改超过 10 个核心文件
