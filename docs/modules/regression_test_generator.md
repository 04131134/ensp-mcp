# RegressionTestGenerator

## 位置
`mcpensp1/agent/regression_test_generator.py`

## 职责
将设备能力约束转换为可由 pytest 收集的真实 eNSP 设备回归测试，输出到 `tests/regression/`。

## 核心接口
`generate_test(constraint)` 要求约束包含 `command_pattern`、`device_model` 和 `alternative`，返回生成测试的绝对路径。生成文件名为 `test_<设备型号>_<短哈希>.py`，同一约束重复生成时覆盖同一文件。

## 设备执行约定
生成测试使用 `device_fixture` 和应用层 `send_command`。为目标型号设置环境变量 `ENSP_REGRESSION_<型号>_PATH`，值为 `127.0.0.1:<Telnet端口>`；例如 `ENSP_REGRESSION_AC6005_PATH=127.0.0.1:2001`。未设置时测试跳过，已设置但格式错误或连接失败时测试失败。

原命令必须传输成功且 `cmd_success` 为假，替代命令必须传输成功且 `cmd_success` 为真。生成的测试带有 `regression_device` 标记。
