# -*- coding: utf-8 -*-
"""
Agent Runtime 集成引导模块

将 Agent Runtime 集成到现有 Flask 应用中，保持所有现有 API 兼容。
新增能力通过扩展方式添加，不替换任何现有功能。
"""
from __future__ import annotations
import os
import logging
from typing import Any, Dict, Optional

import json
import hashlib
from .types import KnowledgeRecord
import json
import hashlib
from .types import KnowledgeRecord

def _migrate_legacy_kb(knowledge_store, kb_folder):
    """Migrate data from legacy knowledge.py JSON files into KnowledgeStore."""
    migration_flag = os.path.join(os.path.dirname(knowledge_store._path), '.kb_migrated')
    if os.path.exists(migration_flag):
        logger.info('[Migration] Already migrated, skipping')
        return 0
    
    imported = 0
    
    global_kb_path = os.path.join(kb_folder, 'global_kb.json')
    if os.path.exists(global_kb_path):
        try:
            with open(global_kb_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for cmd_rec in data.get('commands', []):
                record_id = hashlib.md5(cmd_rec.get('command', '').encode()).hexdigest()[:12]
                if record_id in knowledge_store._records:
                    continue
                rec = KnowledgeRecord(
                    record_id=record_id,
                    category='command',
                    title=cmd_rec.get('command', ''),
                    content={
                        'description': cmd_rec.get('description', ''),
                        'output_preview': cmd_rec.get('output_preview', ''),
                        'risk': cmd_rec.get('risk', 'safe'),
                    },
                    device_type=cmd_rec.get('device_type', 'huawei'),
                    tags=[cmd_rec.get('category', 'general')],
                    confidence=0.9 if cmd_rec.get('success', True) else 0.3,
                    source='migrated',
                )
                knowledge_store.add(rec)
                imported += 1
            logger.info('[Migration] Imported %d commands from global_kb.json', imported)
        except Exception as e:
            logger.warning('[Migration] global_kb.json failed: %s', e)

    struct_kb_path = os.path.join(kb_folder, 'structured_commands_kb.json')
    if os.path.exists(struct_kb_path):
        try:
            with open(struct_kb_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for topic, cases in data.get('troubleshooting', {}).items():
                if isinstance(cases, list):
                    for case in cases:
                        rid = hashlib.md5(('ts:' + str(case)).encode()).hexdigest()[:12]
                        if rid not in knowledge_store._records:
                            title_val = case.get('symptom', case.get('problem', topic))[:100] if isinstance(case, dict) else str(case)[:100]
                            knowledge_store.add(KnowledgeRecord(
                                record_id=rid,
                                category='troubleshoot',
                                title=title_val,
                                content=case if isinstance(case, dict) else {'text': str(case)},
                                tags=['troubleshoot', topic],
                                confidence=0.8,
                                source='migrated',
                            ))
                            imported += 1

            for exp in data.get('experiences', []):
                rid = hashlib.md5(('exp:' + exp.get('experiment', '')).encode()).hexdigest()[:12]
                if rid not in knowledge_store._records:
                    knowledge_store.add(KnowledgeRecord(
                        record_id=rid,
                        category='experience',
                        title=exp.get('experiment', '')[:100],
                        content=exp,
                        tags=['experience'],
                        confidence=0.85,
                        source='migrated',
                    ))
                    imported += 1

            for order in data.get('config_order', []):
                rid = hashlib.md5(('order:' + str(order)).encode()).hexdigest()[:12]
                if rid not in knowledge_store._records:
                    title_val = order.get('topic', '')[:100] if isinstance(order, dict) else str(order)[:100]
                    knowledge_store.add(KnowledgeRecord(
                        record_id=rid,
                        category='config_order',
                        title=title_val,
                        content=order if isinstance(order, dict) else {'text': str(order)},
                        tags=['config_order'],
                        confidence=0.9,
                        source='migrated',
                    ))
                    imported += 1
        except Exception as e:
            logger.warning('[Migration] structured_commands_kb.json failed: %s', e)

    if imported > 0:
        knowledge_store._dirty = True
        knowledge_store._save()
    
    try:
        with open(migration_flag, 'w') as f:
            f.write('migrated')
    except Exception:
        pass
    
    logger.info('[Migration] Total imported: %d records', imported)
    return imported


logger = logging.getLogger(__name__)

# 全局 Agent Runtime 实例
_agent_runtime = None


def init_agent_runtime(app, command_executor, device_scanner=None):
    """
    初始化 Agent Runtime 并注册路由

    Args:
        app: Flask 应用实例
        command_executor: 命令执行函数 (path, command) -> dict
        device_scanner: 设备扫描函数 (可选)
    Returns:
        AgentRuntime 实例
    """
    global _agent_runtime
    from .runtime import AgentRuntime
    from .routes import register_agent_routes

    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'agent_data')
    os.makedirs(data_dir, exist_ok=True)

    _agent_runtime = AgentRuntime(
        data_dir=data_dir,
        command_executor=command_executor,
        device_scanner=device_scanner,
    )

    # Migrate legacy knowledge base data into KnowledgeStore
    try:
        kb_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kb')
        if os.path.isdir(kb_folder):
            _migrate_legacy_kb(_agent_runtime.knowledge, kb_folder)
    except Exception as _mig_err:
        logger.warning('[Bootstrap] KB migration skipped: %s', _mig_err)

    register_agent_routes(app, _agent_runtime)

    logger.info('[Bootstrap] Agent Runtime v3.0 已集成到 Flask 应用')
    return _agent_runtime


def get_agent_runtime():
    """获取全局 Agent Runtime 实例"""
    return _agent_runtime
