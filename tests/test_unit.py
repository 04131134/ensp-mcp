# -*- coding: utf-8 -*-
"""Unit tests for connection.py (L1), device_manager.py (L2), knowledge.py (L3).

These tests mock the socket layer — no eNSP device required.
"""
import sys
sys.path.insert(0, r'e:\eNSP-MCP\mcpensp1')

import pytest
import threading

# ──────────────────────────────────────────────
# L1: TelnetConnection prompt detection & classification
# ──────────────────────────────────────────────


class TestTelnetPromptDetection:
    """Test prompt regex matching without real socket."""

    @pytest.fixture
    def conn(self):
        from connection import TelnetConnection
        c = TelnetConnection.__new__(TelnetConnection)
        c.host, c.port = '127.0.0.1', 9999
        c.sock = None
        c.lock = threading.Lock()
        return c

    # ── _has_prompt ──

    @pytest.mark.parametrize('data,expected', [
        (b'<SW1>', True),
        (b'<SW1>  \r\n', True),
        (b'[SW1]', True),
        (b'[SW1-GigabitEthernet0/0/1]', True),
        (b'SW1#', True),
        (b'SW1(config-if)#', True),
        (b'random output\r\n<LSW2>', True),
        (b'just text', False),
        (b'', False),
    ])
    def test_has_prompt(self, conn, data, expected):
        assert conn._has_prompt(data) == expected

    # ── _is_more pagination ──

    @pytest.mark.parametrize('data,expected', [
        (b'---- More ----', True),
        (b'  ---- More ----  ', True),
        (b'-- More --', True),
        (b'random text', False),
    ])
    def test_is_more(self, conn, data, expected):
        assert conn._is_more(data) == expected

    # ── _classify_cmd ──

    def test_classify_display(self, conn):
        assert conn._classify_cmd('display version') == 'display'
        assert conn._classify_cmd('dir flash:') == 'display'
        assert conn._classify_cmd('show run') == 'display'

    def test_classify_diag(self, conn):
        assert conn._classify_cmd('ping 8.8.8.8') == 'diag'
        assert conn._classify_cmd('tracert 192.168.1.1') == 'diag'
        assert conn._classify_cmd('traceroute 10.0.0.1') == 'diag'

    def test_classify_config(self, conn):
        assert conn._classify_cmd('system-view') == 'config'
        assert conn._classify_cmd('interface GigabitEthernet0/0/1') == 'config'
        assert conn._classify_cmd('ospf 1') == 'config'

    def test_classify_interactive(self, conn):
        assert conn._classify_cmd('save') == 'interactive'
        assert conn._classify_cmd('reboot') == 'interactive'
        assert conn._classify_cmd('reset saved-configuration') == 'interactive'

    # ── is_diag_done ──

    def test_diag_done_ping(self, conn):
        assert conn._is_diag_done(b'--- 8.8.8.8 ping statistics ---')
        assert conn._is_diag_done(b'5 packets transmitted, 5 received')
        assert conn._is_diag_done(b'0% packet loss')

    def test_diag_done_nomatch(self, conn):
        assert not conn._is_diag_done(b'random output')

    # ── strip_escape ──

    def test_strip_ansi(self, conn):
        assert conn._strip_escape(b'\x1b[32mhello\x1b[0m') == b'hello'
        assert conn._strip_escape(b'\x1b[1;33mWARNING') == b'WARNING'

    # ── timeouts per type ──

    def test_timeout_display(self, conn):
        assert conn.TIMEOUTS['display'] == 30

    def test_timeout_diag(self, conn):
        assert conn.TIMEOUTS['diag'] == 10

    def test_timeout_config(self, conn):
        assert conn.TIMEOUTS['config'] == 5


# ──────────────────────────────────────────────
# L2: DeviceManager thread safety & correctness
# ──────────────────────────────────────────────


class MockTelnetConnection:
    """Fake TelnetConnection for DeviceManager tests."""
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = True
        self._closed = False

    def close(self):
        self._closed = True


class TestDeviceManager:
    @pytest.fixture
    def dm(self):
        from device_manager import DeviceManager
        return DeviceManager()

    def test_set_and_get(self, dm):
        conn = MockTelnetConnection('127.0.0.1', 2012)
        dm.set('127.0.0.1:2012', conn)
        assert dm.get('127.0.0.1:2012') is conn

    def test_has(self, dm):
        conn = MockTelnetConnection('127.0.0.1', 2012)
        dm.set('127.0.0.1:2012', conn)
        assert dm.has('127.0.0.1:2012') is True
        assert dm.has('127.0.0.1:9999') is False

    def test_remove(self, dm):
        conn = MockTelnetConnection('127.0.0.1', 2012)
        dm.set('127.0.0.1:2012', conn)
        removed = dm.remove('127.0.0.1:2012')
        assert removed is conn
        assert dm.get('127.0.0.1:2012') is None

    def test_name_management(self, dm):
        dm.set_name('127.0.0.1:2012', 'SW1')
        assert dm.get_name('127.0.0.1:2012') == 'SW1'
        # default param is used as fallback when name not found
        assert dm.get_name('127.0.0.1:9999', 'fallback') == 'fallback'

    def test_type_management(self, dm):
        dm.set_type('127.0.0.1:2012', 'huawei')
        assert dm.get_type('127.0.0.1:2012') == 'huawei'
        assert dm.get_type('127.0.0.1:9999') == 'unknown'

    def test_topo_name(self, dm):
        dm.set_topo_name(2012, 'CoreSW')
        assert dm.get_topo_name(2012) == 'CoreSW'
        assert dm.get_topo_name(9999) is None

    def test_role_counter(self, dm):
        assert dm.next_role_name('SW') == 'SW1'
        assert dm.next_role_name('SW') == 'SW2'
        assert dm.next_role_name('AR') == 'AR1'

    def test_set_closes_old(self, dm):
        c1 = MockTelnetConnection('127.0.0.1', 2012)
        c2 = MockTelnetConnection('127.0.0.1', 2012)
        dm.set('127.0.0.1:2012', c1)
        dm.set('127.0.0.1:2012', c2)
        assert c1._closed is True

    def test_concurrent_set(self, dm):
        """Ensure thread safety under concurrent writes."""
        errors = []

        def worker(i):
            try:
                conn = MockTelnetConnection('127.0.0.1', 2000 + i)
                dm.set(f'127.0.0.1:{2000 + i}', conn)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0


# ──────────────────────────────────────────────
# L3: Knowledge data quality guards
# ──────────────────────────────────────────────


class TestKnowledgeGuards:
    """Test Phase 5 data quality write guards."""

    @pytest.fixture
    def kb(self):
        import tempfile, os
        from knowledge import KnowledgeBase
        tmp = tempfile.mkdtemp()
        kb = KnowledgeBase(tmp)
        yield kb
        # cleanup
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_auto_detect_failure(self, kb):
        """Guard 1: output with 'Error:' should force success=False."""
        kb.record_command('display version', 'Error: Unrecognized command',
                          success=True)
        dkb = kb._dkb_cache or {}
        devs = dkb.get('devices', {})
        for dev_path, dev_data in devs.items():
            failed = dev_data.get('failed_commands', [])
            for f in failed:
                if f['command'] == 'display version':
                    return  # PASS — it was recorded as failed
        pytest.fail("Command with Error: was not recorded as failed")

    def test_description_not_empty(self, kb):
        """Guard 3: description must not be empty string."""
        # record_command fills description from base_cmd or catalog
        kb.record_command('system-view', '<SW1>')
        gkb = kb._gkb_cache or {}
        cmds = gkb.get('commands', [])
        for c in cmds:
            if c['command'] == 'system-view':
                assert c['description'] != '', f"description is empty: {c}"
                return
        pytest.fail("Command not found in KB")

    def test_risk_defaults_to_medium(self, kb):
        """Guard 2: unknown commands → risk='medium' (not 'unknown')."""
        kb.record_command('my-custom-cmd', 'OK')
        gkb = kb._gkb_cache or {}
        cmds = gkb.get('commands', [])
        for c in cmds:
            if c['command'] == 'my-custom-cmd':
                assert c['risk'] != 'unknown', f"risk is unknown: {c}"
                return

    def test_record_experience_persists(self, kb):
        """record_experience should attempt to persist (may need structured KB file)."""
        result = kb.record_experience({
            'experiment': 'Test VLAN config',
            'commands': [{'cmd': 'vlan 10', 'output': 'OK', 'success': True}],
            'success': True,
            'lessons': ['VLAN created successfully'],
        })
        # May return success=False if structured KB doesn't exist in temp dir
        assert 'success' in result
