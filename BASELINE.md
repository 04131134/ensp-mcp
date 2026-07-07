# 安全网基线 (Task 0)
# 生成时间: 2026-07-08
# 分支: codex/safety-net
# 测试状态: 97 passed, 4 skipped

--- mcpensp1/mcp_server.py ---
SHA256: 3F8FF2766A2CDE6088CF62A39BF75C78CF2F45764E2B01F56752D2B06E990D91
接口: async list_tools(), 52+ tools, 6 config_method tools
关键回归点: batch_command schema 含 auto_undo_tm + auto_view

--- mcpensp1/knowledge.py ---
SHA256: 76E841197BABA4C39E948E6BF7B6A952A4BA5F24F3E1580DC912277890955F3F
接口: KnowledgeBase(kb_folder), get_stats(), search_experiences(),
      get_best_practices(), get_structured_kb(), get_device_history(),
      get_command_catalog(), _guess_cat(), get_config_guidance()

--- mcpensp1/command_executor.py ---
SHA256: 969F1C3D5CB74083A8933F686CDB9E9BE00847A4A3816D8DF3EFD3D02A1ABC2A
接口: is_blocked_command(cmd), CommandExecutor(knowledge_base)
      send_command(path, cmd), batch_command(path, cmds), send_command_to_group(paths, cmd)

--- mcpensp1/heartbeat.py ---
SHA256: 993F04F5561EF898EAE02D205AA0B1AA3C2367597215349AB43D2FEFDA8C2B4D
接口: HeartbeatMonitor(kb_ref), start(), get_status(path|None)

--- mcpensp1/device_manager.py ---
SHA256: 254FD88D5A9DF2D70490E71F430398290808FCD266B89B71348F0E47B96A4D8D
测试覆盖: test_unit.py:TestDeviceManager (9条)

--- mcpensp1/connection.py ---
SHA256: 59DB040182AF3EDC6F4D04C5830DFAEA3991AB8E6DF1180AD6914A43BA6557F2
接口: TelnetConnection
