# -*- coding: utf-8 -*-
"""Configuration Method Store — verified config step sequences.

Preserved from the original project. Stores standard network configuration
procedures (OSPF, VLAN, DHCP, WLAN, etc.) as structured JSON files.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

CATEGORIES = {
    'routing': '路由协议配置',
    'switching': '交换配置',
    'security': '安全配置',
    'wireless': '无线配置',
    'services': '网络服务',
    'management': '管理配置',
}


class ConfigMethodStore:
    """Store and query standard network configuration procedures."""

    def __init__(self, kb_dir: str) -> None:
        self._dir = os.path.join(kb_dir, 'config_methods')
        os.makedirs(self._dir, exist_ok=True)
        self._index_path = os.path.join(self._dir, '_index.json')
        self._methods: dict[str, dict[str, Any]] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not os.path.isdir(self._dir):
            return
        for fname in os.listdir(self._dir):
            if not fname.endswith('.json') or fname.startswith('_'):
                continue
            try:
                path = os.path.join(self._dir, fname)
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
                mid = data.get('id', fname[:-5])
                self._methods[mid] = data
            except Exception as e:
                logger.warning('Failed to load config method %s: %s', fname, e)
        logger.info('Loaded %d config methods', len(self._methods))

    # ── read ─────────────────────────────────────────────────

    def list(self, category: str = '') -> list[dict]:
        result = []
        for m in self._methods.values():
            if category and m.get('category') != category:
                continue
            result.append({
                'id': m['id'],
                'name': m['name'],
                'category': m.get('category', ''),
                'description': m.get('description', ''),
                'usage_count': m.get('usage_count', 0),
                'success_rate': m.get('success_rate', 0.0),
                'device_types': m.get('device_types', []),
            })
        return sorted(result, key=lambda x: x['name'])

    def get(self, method_id: str) -> dict | None:
        return self._methods.get(method_id)

    def search(self, keyword: str) -> list[dict]:
        kw = keyword.lower()
        result = []
        for m in self._methods.values():
            text = json.dumps(m, ensure_ascii=False).lower()
            if kw in text:
                result.append({
                    'id': m['id'],
                    'name': m['name'],
                    'category': m.get('category', ''),
                    'description': m.get('description', ''),
                    'steps_count': len(m.get('steps', [])),
                    'usage_count': m.get('usage_count', 0),
                    'success_rate': m.get('success_rate', 0.0),
                })
        return sorted(result, key=lambda x: x['name'])

    def get_steps(self, method_id: str) -> list[dict]:
        m = self._methods.get(method_id)
        if not m:
            return []
        return m.get('steps', [])

    def get_commands(self, method_id: str) -> list[str]:
        """Get flat command list from all steps."""
        steps = self.get_steps(method_id)
        cmds: list[str] = []
        for step in steps:
            cmds.extend(step.get('commands', []))
        return cmds

    def get_verification(self, method_id: str) -> list[str]:
        m = self._methods.get(method_id)
        if not m:
            return []
        return m.get('verification', [])

    def get_categories(self) -> dict:
        return dict(CATEGORIES)

    # ── write ────────────────────────────────────────────────

    def add(self, data: dict) -> dict:
        mid = data.get('id')
        if not mid:
            return {'success': False, 'error': '缺少 id 字段'}
        data.setdefault('created_at', datetime.now(timezone.utc).isoformat())
        data.setdefault('updated_at', datetime.now(timezone.utc).isoformat())
        data.setdefault('usage_count', 0)
        data.setdefault('success_rate', 0.0)
        path = os.path.join(self._dir, f'{mid}.json')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._methods[mid] = data
            self._update_index()
            return {'success': True, 'method_id': mid}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def update(self, method_id: str, updates: dict) -> dict:
        m = self._methods.get(method_id)
        if not m:
            return {'success': False, 'error': f'方法不存在: {method_id}'}
        m.update(updates)
        m['updated_at'] = datetime.now(timezone.utc).isoformat()
        path = os.path.join(self._dir, f'{method_id}.json')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
            return {'success': True, 'method_id': method_id}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def record_usage(self, method_id: str, success: bool = True) -> None:
        m = self._methods.get(method_id)
        if not m:
            return
        m['usage_count'] = m.get('usage_count', 0) + 1
        old_rate = m.get('success_rate', 0.0)
        old_count = m.get('usage_count', 1) - 1
        if old_count > 0:
            m['success_rate'] = (old_rate * old_count + (1 if success else 0)) / (old_count + 1)
        else:
            m['success_rate'] = 1.0 if success else 0.0
        m['updated_at'] = datetime.now(timezone.utc).isoformat()
        path = os.path.join(self._dir, f'{method_id}.json')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _update_index(self) -> None:
        index = {
            'version': '1.0',
            'description': 'eNSP配置方法库',
            'categories': CATEGORIES,
            'methods_count': len(self._methods),
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'methods': [
                {'id': m['id'], 'name': m['name'],
                 'category': m.get('category', ''),
                 'description': m.get('description', '')[:100]}
                for m in self._methods.values()
            ],
        }
        with open(self._index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
