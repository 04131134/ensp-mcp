# BlueprintLearner

## 位置
`mcpensp1/agent/blueprint_learner.py`

## 职责
从一次成功的设备命令执行历史中提炼可复用、可回滚的配置蓝图，并以 `template` 类别写入 `KnowledgeStore`。

## 核心接口
`learn_from_success(task_id, execution_log, device_info, topology_data)` 接收命令、输出和视图记录，返回新建或合并后的蓝图；没有配置命令时返回 `None`。

## 提炼规则
- 过滤 `display`、`show`、`ping`、`tracert`、`dir` 等查询命令。
- 根据执行视图补齐系统视图、接口视图等必要进入命令。
- 将拓扑中接口地址参数化；例如 `GE0/0/1` 的地址 `10.0.0.1/24` 替换为 `{ip_interface_GE0/0/1}`，并保存拓扑路径来源。
- 为地址、OSPF、VLAN 等配置生成反向回滚命令。
- 用规范化命令序列哈希去重；相同蓝图成功时增加成功次数并合并适用设备型号。
