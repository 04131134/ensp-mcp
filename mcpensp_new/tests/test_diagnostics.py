# -*- coding: utf-8 -*-
"""Tests for ErrorDiagnostics — pattern matching."""
from __future__ import annotations

from core.diagnostics import diagnose, diagnose_result


def test_unrecognized_command():
    d = diagnose('Error: Unrecognized command found at ^ position.')
    assert d['confidence'] > 0.4
    assert any('unrecognized command' in p['pattern'] for p in d['matched_patterns'])


def test_vlan_not_exist():
    d = diagnose('Error: The VLAN does not exist.')
    assert any('vlan does not exist' in p['pattern'] for p in d['matched_patterns'])


def test_wrong_parameter():
    d = diagnose('Error: Wrong parameter found at ^ position.')
    assert any('wrong parameter' in p['pattern'] for p in d['matched_patterns'])


def test_no_match():
    d = diagnose('Some unknown random error text.')
    assert d['confidence'] == 0.2
    assert d['matched_patterns'] == []


def test_diagnose_result_all_success():
    results = [
        {'command': 'system-view', 'output': 'ok', 'success': True},
        {'command': 'ospf 1', 'output': 'ok', 'success': True},
    ]
    d = diagnose_result(results)
    assert d['has_errors'] is False


def test_diagnose_result_with_failures():
    results = [
        {'command': 'ospf', 'output': 'Error: Unrecognized command', 'success': False},
        {'command': 'display version', 'output': 'Huawei...', 'success': True},
    ]
    d = diagnose_result(results)
    assert d['has_errors'] is True
    assert d['failed_count'] == 1
