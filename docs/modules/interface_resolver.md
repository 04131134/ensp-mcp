# InterfaceResolver（接口映射自动推理）

## 位置
`mcpensp1/interface_resolver.py`

## 职责
根据设备型号规则 + .topo 拓扑数据 + 可选 display 校验，自动推理 srcIndex → 真实接口名。
解决旧 `_build_interface_map` 对所有设备统一用 1 起始、无法区分盒式/子卡设备的问题。

## 背景（工作记忆铁律）
> 永远不信任 .topo 的 srcIndex，下接口命令前必跑 `display interface brief`

旧实现（app.py L174-194）固定拼 `{name}0/0/{idx}` idx 从 1 起，导致：
- 盒式设备 S5700（端口 1 起始）：srcIndex=0 → G0/0/1 ✓
- 子卡设备 AR3260（端口 0 起始）：srcIndex=0 → G0/0/1 ✗（应为 G0/0/0）

## 设备型号规则

| 设备类型 | 型号示例 | 端口起始 | srcIndex=N → |
|---------|---------|---------|--------------|
| 盒式（交换机/AC） | S5700/S3700/AC6605 | 1 | G0/0/(N+1) |
| 子卡（路由器/防火墙） | AR3260/USG6000V | 0 | G0/0/N |

## 输入

### 模块级函数
| 函数 | 参数 | 说明 |
|------|------|------|
| `build_interface_map(dev_element, model=None)` | dev XML 元素 + 型号 | 构建 srcIndex→接口名映射 |
| `resolve_interface(iface_map, index)` | 映射表 + 索引 | 查表解析，回退 Index{index} |

### InterfaceResolver 类
| 方法 | 说明 |
|------|------|
| `__init__(command_executor=None)` | 可选注入命令执行器，启用 display 校验 |
| `build_map(dev_element, model)` | 委托 build_interface_map |
| `resolve(iface_map, index)` | 委托 resolve_interface |
| `verify_by_display(device_path, interface_name)` | display interface brief 校验接口存在 |
| `resolve_with_verification(dev, model, index, device_path)` | 多源推理主入口 |

## 输出
- `build_interface_map` → `{srcIndex: interface_name}`
- `resolve_interface` → 接口名字符串（回退 `Index{index}`）
- `resolve_with_verification` → `{interface, model, is_module, verified, source}`

## 多源推理链
```
resolve_with_verification
  ├── 1. 型号规则映射（build_interface_map）
  │     ├── 盒式 → 端口 1 起始
  │     └── 子卡 → 端口 0 起始
  ├── 2. 查表解析（resolve_interface）
  │     └── 查不到 → Index{index}（source='fallback'）
  └── 3. display 校验（可选，需 device_path + executor）
        └── verify_by_display → True/False/None
```

## 依赖
- 无外部依赖（纯 Python + xml.etree）
- `command_executor` 可选注入（用于运行时 display 校验）

## 禁止事项
- ❌ 不允许 model=None 时改变旧行为（必须默认盒式 1 起始，向后兼容）
- ❌ 不允许 display 校验异常破坏推理主流程（必须返回 None 静默跳过）
- ❌ 不允许删除回退 `Index{index}`（保证查不到时不抛异常）

## 调用关系
```
app.py (_build_interface_map / _resolve_interface thin wrapper)
    └── interface_resolver
          ├── build_interface_map(dev, model)  ← .topo 解析时
          └── InterfaceResolver.verify_by_display  ← 运行时校验（可选）
```

## v3.2 引入（第三阶段 Step7）
- 新建本模块，替代 app.py/knowledge.py 两份重复的 `_build_interface_map` 死代码
- app.py 的 `_build_interface_map`/`_resolve_interface` 改为 thin wrapper 委托本模块
- knowledge.py 的死代码副本已删除
- 型号规则基于工作记忆实战经验：S5700/S3700/AC6605 盒式 1 起始 vs AR3260/USG6000V 子卡 0 起始
