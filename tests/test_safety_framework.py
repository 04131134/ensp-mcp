# -*- coding: utf-8 -*-
"""安全执行框架单元测试 — ErrorLibrary / CapabilityManager / PlanReviewer / Transaction"""
from __future__ import annotations
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════
# ErrorLibrary 测试
# ═══════════════════════════════════════════════════════════

class TestErrorLibrary:
    """测试错误库查询。"""

    @pytest.fixture
    def lib(self):
        from mcpensp1.agent.error_library import ErrorLibrary
        return ErrorLibrary()

    def test_lookup_exact_match(self, lib):
        """精确匹配错误消息。"""
        result = lib.lookup("Error: The VLAN already exists")
        assert result["found"] is True
        assert result["matched_id"] == "E004"
        assert result["auto_recoverable"] is True
        assert result["confidence"] == "exact"

    def test_lookup_partial_match(self, lib):
        """关键词部分匹配。"""
        result = lib.lookup("Error: The VLAN already exists in config")
        assert result["found"] is True
        assert result["confidence"] == "exact"

    def test_lookup_not_found(self, lib):
        """未知错误返回 not found。"""
        result = lib.lookup("Error: Something completely unknown happened")
        assert result["found"] is False
        assert result["confidence"] == "none"

    def test_lookup_by_id(self, lib):
        """按 ID 查询。"""
        result = lib.lookup_by_id("E008")
        assert result is not None
        assert "router-id" in result["cause"]

    def test_lookup_by_invalid_id(self, lib):
        """无效 ID 返回 None。"""
        result = lib.lookup_by_id("E999")
        assert result is None

    def test_is_recoverable(self, lib):
        """快速判断可恢复性。"""
        assert lib.is_recoverable("Error: The interface is shut down") is True
        assert lib.is_recoverable("Error: Unrecognized command found") is False

    def test_get_fix(self, lib):
        """获取修复建议。"""
        fix = lib.get_fix("Error: The BGP peer does not exist")
        assert "先配置 peer 命令" in fix

    def test_search_by_category(self, lib):
        """按类别搜索。"""
        results = lib.search_by_category("connection")
        assert len(results) >= 2
        assert all(e["category"] == "connection" for e in results)

    def test_list_categories(self, lib):
        """列出类别。"""
        cats = lib.list_categories()
        assert "ospf" in cats
        assert "connection" in cats


# ═══════════════════════════════════════════════════════════
# CapabilityManager 测试
# ═══════════════════════════════════════════════════════════

class TestCapabilityManager:
    """测试设备能力管理器。"""

    @pytest.fixture
    def cm(self):
        from mcpensp1.agent.capability_manager import CapabilityManager
        return CapabilityManager()

    def test_get_s5700_capabilities(self, cm):
        """S5700 能力查询。"""
        caps = cm.get_model_capabilities("S5700")
        assert caps is not None
        assert caps["type"] == "switch"
        assert "ospf" in caps["protocols"]

    def test_get_unknown_model(self, cm):
        """未知设备型号返回 None。"""
        caps = cm.get_model_capabilities("UnknownDevice")
        assert caps is None

    def test_check_ospf_on_switch(self, cm):
        """S5700 应支持 OSPF。"""
        result = cm.check_protocol("S5700", "ospf")
        assert result["supported"] is True
        assert result["required_view"] == "OSPF"

    def test_check_ospf_on_s3700(self, cm):
        """S3700 不应支持 OSPF。"""
        result = cm.check_protocol("S3700", "ospf")
        assert result["supported"] is False

    def test_check_bgp_on_router(self, cm):
        """AR2220 应支持 BGP。"""
        result = cm.check_protocol("AR2220", "bgp")
        assert result["supported"] is True

    def test_check_wlan_on_ac(self, cm):
        """AC6605 应支持 WLAN。"""
        result = cm.check_protocol("AC6605", "wlan")
        assert result["supported"] is True

    def test_check_wlan_on_switch(self, cm):
        """S5700 不应支持 WLAN。"""
        result = cm.check_protocol("S5700", "wlan")
        assert result["supported"] is False

    def test_model_alias_normalization(self, cm):
        """型号别名标准化。"""
        caps = cm.get_model_capabilities("switch")
        assert caps is not None
        assert caps["type"] == "switch"

    def test_get_supported_protocols(self, cm):
        """获取支持的协议列表。"""
        protos = cm.get_supported_protocols("USG6000V")
        assert "security-policy" in protos
        assert "nat" in protos

    def test_suggest_model_for_protocol(self, cm):
        """推荐支持协议的设备。"""
        models = cm.suggest_model_for_protocol("wlan")
        assert "AC6605" in models

    def test_check_commands_blocks_dangerous(self, cm):
        """检查命令时应拦截危险命令。"""
        result = cm.check_commands("S5700", ["reboot", "display version"])
        assert result["all_supported"] is False
        assert len(result["blocked"]) == 1

    def test_check_commands_all_safe(self, cm):
        """安全命令应全部通过。"""
        result = cm.check_commands("S5700", ["display version", "vlan 10"])
        assert result["all_supported"] is True

    def test_get_device_type(self, cm):
        """获取设备类型。"""
        assert cm.get_device_type("S5700") == "switch"
        assert cm.get_device_type("AR2220") == "router"
        assert cm.get_device_type("USG6000V") == "firewall"


# ═══════════════════════════════════════════════════════════
# PlanReviewer 测试
# ═══════════════════════════════════════════════════════════

class TestPlanReviewer:
    """测试计划审核器。"""

    @pytest.fixture
    def reviewer(self):
        from mcpensp1.agent.plan_reviewer import PlanReviewer
        return PlanReviewer()

    def test_approve_safe_plan(self, reviewer):
        """安全计划应通过审核。"""
        plan = {
            "nodes": [
                {"id": "1", "commands": ["display version", "display vlan"]},
            ]
        }
        report = reviewer.review(plan, "S5700")
        assert report["approved"] is True
        assert report["score"] == 1.0

    def test_block_dangerous_command(self, reviewer):
        """危险命令应被审核拦截。"""
        plan = {
            "nodes": [
                {"id": "1", "commands": ["reboot"]},
            ]
        }
        report = reviewer.review(plan, "S5700")
        assert report["approved"] is False
        assert any(i["type"] == "dangerous_command" for i in report["issues"])

    def test_warn_dangerous_keyword(self, reviewer):
        """包含危险关键词应有警告。"""
        plan = {
            "nodes": [
                {"id": "1", "commands": ["shutdown"]},
            ]
        }
        report = reviewer.review(plan, "S5700")
        assert any(i["severity"] == "warning" for i in report["issues"])

    def test_detect_view_errors(self, reviewer):
        """检测视图权限错误。"""
        plan = {
            "nodes": [
                {"id": "1", "commands": ["interface GigabitEthernet0/0/1"]},
            ]
        }
        report = reviewer.review(plan, "S5700")
        # interface 在 USER 视图不允许
        assert any(i["type"] == "view_error" for i in report["issues"])

    def test_detect_duplicates(self, reviewer):
        """检测重复命令。"""
        plan = {
            "nodes": [
                {"id": "1", "commands": ["vlan 10", "vlan 10"]},
            ]
        }
        report = reviewer.review(plan, "S5700")
        assert any(i["type"] == "duplicate" for i in report["issues"])

    def test_detect_circular_dependency(self, reviewer):
        """检测循环依赖。"""
        plan = {
            "nodes": [
                {"id": "A", "commands": ["cmd1"], "depends_on": ["B"]},
                {"id": "B", "commands": ["cmd2"], "depends_on": ["A"]},
            ]
        }
        report = reviewer.review(plan, "S5700")
        assert any(i["type"] == "circular_dependency" for i in report["issues"])

    def test_block_illegal_delete(self, reviewer):
        """拦截非法删除命令。"""
        plan = {
            "nodes": [
                {"id": "1", "commands": ["undo telnet server"]},
            ]
        }
        report = reviewer.review(plan, "S5700")
        assert any(i["type"] == "illegal_delete" for i in report["issues"])

    def test_review_commands_quick(self, reviewer):
        """快速审核命令列表。"""
        report = reviewer.review_commands(["display version", "vlan 10"], "S5700")
        assert "approved" in report
        assert "total_commands" in report

    def test_generates_suggestions(self, reviewer):
        """生成修复建议。"""
        plan = {
            "nodes": [
                {"id": "1", "commands": ["reboot", "vlan 10", "vlan 10"]},
            ]
        }
        report = reviewer.review(plan, "S5700")
        assert len(report["suggestions"]) > 0


# ═══════════════════════════════════════════════════════════
# TransactionManager 测试
# ═══════════════════════════════════════════════════════════

class TestTransaction:
    """测试事务对象。"""

    def test_transaction_init(self):
        """事务对象初始化。"""
        from mcpensp1.agent.transaction import Transaction, TransactionState
        tx = Transaction("tx-001", "127.0.0.1:2000",
                         commands=["system-view", "vlan 10"],
                         verify_commands=["display vlan 10"])
        assert tx.tx_id == "tx-001"
        assert tx.state == TransactionState.INIT
        assert tx.snapshot_data is None

    def test_transaction_to_dict(self):
        """事务序列化。"""
        from mcpensp1.agent.transaction import Transaction
        tx = Transaction("tx-002", "127.0.0.1:2001",
                         commands=["display version"])
        d = tx.to_dict()
        assert d["tx_id"] == "tx-002"
        assert d["state"] == "init"


class TestTransactionManager:
    """测试事务管理器。"""

    @pytest.fixture
    def tm(self):
        from mcpensp1.agent.transaction import TransactionManager
        return TransactionManager()

    def test_run_successful_transaction(self, tm):
        """成功执行事务。"""
        from mcpensp1.agent.transaction import Transaction

        def mock_exec(path, commands):
            return {"success": True, "results": [{"command": c, "success": True} for c in commands]}

        tx = Transaction("tx-ok", "127.0.0.1:2000",
                         commands=["system-view", "vlan 10"])
        result = tm.run(tx, executor_fn=mock_exec)
        assert result["success"] is True
        assert result["state"] == "completed"

    def test_run_failed_execution(self, tm):
        """执行失败应回滚。"""
        from mcpensp1.agent.transaction import Transaction

        def mock_exec(path, commands):
            return {"success": False, "error": "Command failed"}

        tx = Transaction("tx-fail", "127.0.0.1:2000",
                         commands=["invalid command"])
        result = tm.run(tx, executor_fn=mock_exec)
        assert result["success"] is False
        assert result["rolled_back"] is True

    def test_run_without_executor(self, tm):
        """无执行回调应失败。"""
        from mcpensp1.agent.transaction import Transaction
        tx = Transaction("tx-noexec", "127.0.0.1:2000",
                         commands=["display version"])
        result = tm.run(tx)
        assert result["success"] is False
        assert "未提供命令执行回调" in result.get("error", "")

    def test_run_with_exception_in_executor(self, tm):
        """执行异常应捕获。"""
        from mcpensp1.agent.transaction import Transaction

        def mock_exec(path, commands):
            raise RuntimeError("Connection refused")

        tx = Transaction("tx-exc", "127.0.0.1:2000",
                         commands=["display version"])
        result = tm.run(tx, executor_fn=mock_exec)
        assert result["success"] is False
        assert result["rolled_back"] is True

    def test_run_batch(self, tm):
        """批量事务执行。"""
        from mcpensp1.agent.transaction import Transaction

        def mock_exec(path, commands):
            return {"success": True}

        txs = [
            Transaction("tx-a", "127.0.0.1:2000", commands=["vlan 10"]),
            Transaction("tx-b", "127.0.0.1:2001", commands=["vlan 20"]),
        ]
        results = tm.run_batch(txs, executor_fn=mock_exec)
        assert len(results) == 2
        assert all(r["success"] for r in results)

    def test_get_status(self, tm):
        """查询事务状态。"""
        from mcpensp1.agent.transaction import Transaction

        def mock_exec(path, commands):
            return {"success": True}

        tx = Transaction("tx-stat", "127.0.0.1:2000",
                         commands=["display version"])
        tm.run(tx, executor_fn=mock_exec)
        status = tm.get_status("tx-stat")
        assert status is not None
        assert status["tx_id"] == "tx-stat"

    def test_list_active(self, tm):
        """列出活跃事务。"""
        from mcpensp1.agent.transaction import Transaction

        def mock_exec(path, commands):
            return {"success": True}

        tx = Transaction("tx-act", "127.0.0.1:2000",
                         commands=["display version"])
        tm.run(tx, executor_fn=mock_exec)
        active = tm.list_active()
        # 事务已完成，不应在活跃列表中
        assert "tx-act" not in active

    def test_get_history(self, tm):
        """获取事务历史。"""
        from mcpensp1.agent.transaction import Transaction

        def mock_exec(path, commands):
            return {"success": True}

        tx = Transaction("tx-hist", "127.0.0.1:2000",
                         commands=["display version"])
        tm.run(tx, executor_fn=mock_exec)
        history = tm.get_history()
        assert len(history) >= 1
        assert history[-1]["tx_id"] == "tx-hist"


# ═══════════════════════════════════════════════════════════
# 兼容性测试
# ═══════════════════════════════════════════════════════════

class TestCompatibility:
    """确保新模块不影响现有代码。"""

    def test_all_new_modules_importable(self):
        """所有新模块可独立导入。"""
        from mcpensp1.agent.error_library import ErrorLibrary
        from mcpensp1.agent.capability_manager import CapabilityManager
        from mcpensp1.agent.plan_reviewer import PlanReviewer
        from mcpensp1.agent.transaction import Transaction, TransactionManager
        assert True

    def test_existing_imports_still_work(self):
        """现有模块导入不受影响。"""
        from mcpensp1.command_executor import CommandExecutor
        from mcpensp1.device_manager import DeviceManager
        from mcpensp1.agent.planner import DAGPlanner
        assert True
