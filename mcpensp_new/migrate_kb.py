# -*- coding: utf-8 -*-
"""One-time migration from legacy KB JSON files to new knowledge.jsonl format.

Run once:
    cd mcpensp_new
    python migrate_kb.py

This reads the old global_kb.json, devices_kb.json, and structured_commands_kb.json
from ../mcpensp1/kb/ and writes them into kb/knowledge.jsonl.

It also copies config_methods/*.json as-is (same format).
"""
from __future__ import annotations

import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
OLD_KB = os.path.join(HERE, '..', 'mcpensp1', 'kb')
NEW_KB = os.path.join(HERE, 'kb')


def migrate_global_kb() -> int:
    """Migrate global_kb.json commands to knowledge entries."""
    path = os.path.join(OLD_KB, 'global_kb.json')
    if not os.path.exists(path):
        print('[SKIP] global_kb.json not found')
        return 0

    from core.knowledge import KnowledgeEntry, KnowledgeService
    ks = KnowledgeService(NEW_KB)

    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    count = 0
    for cmd_rec in data.get('commands', []):
        if not isinstance(cmd_rec, dict):
            continue
        entry = KnowledgeEntry(
            category='command',
            title=cmd_rec.get('command', '')[:100],
            content={'output_preview': cmd_rec.get('output_preview', '')[:500]},
            device_type=cmd_rec.get('device_type', 'unknown'),
            tags=[cmd_rec.get('category', 'general'),
                  cmd_rec.get('device_type', 'unknown')],
            success=cmd_rec.get('success', True),
            command=cmd_rec.get('command', ''),
            output_preview=cmd_rec.get('output_preview', '')[:500],
            risk=cmd_rec.get('risk', 'medium'),
            use_count=cmd_rec.get('use_count', 1),
            confidence=0.9 if cmd_rec.get('success', True) else 0.3,
        )
        ks.add(entry)
        count += 1

    print(f'[OK] Migrated {count} commands from global_kb.json')
    return count


def migrate_structured_kb() -> int:
    """Migrate structured_commands_kb.json experiences."""
    path = os.path.join(OLD_KB, 'structured_commands_kb.json')
    if not os.path.exists(path):
        print('[SKIP] structured_commands_kb.json not found')
        return 0

    from core.knowledge import KnowledgeEntry, KnowledgeService
    ks = KnowledgeService(NEW_KB)

    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    count = 0

    for exp in data.get('experiences', []):
        if not isinstance(exp, dict):
            continue
        cmds = []
        for c in exp.get('new_commands_learned', []):
            if isinstance(c, dict):
                cmds.append(c.get('cmd', ''))
        entry = KnowledgeEntry(
            category='experience',
            title=exp.get('experiment', '')[:100],
            content={
                'commands': cmds,
                'lessons': exp.get('lessons_learned', []),
                'features': exp.get('features_implemented', []),
            },
            device_type=exp.get('device_type', 'unknown'),
            tags=['experience', 'migrated'],
            success=True,
            use_count=1,
            confidence=0.85,
        )
        ks.add(entry)
        count += 1

    for problem_name, tc_data in data.get('troubleshooting', {}).items():
        if not isinstance(tc_data, dict):
            continue
        entry = KnowledgeEntry(
            category='troubleshoot',
            title=str(problem_name)[:100],
            content={
                'symptom': tc_data.get('symptom', tc_data.get('problem', '')),
                'cause': tc_data.get('cause', tc_data.get('root_cause', '')),
                'solution': tc_data.get('solution', []),
            },
            tags=['troubleshoot', 'migrated'],
            confidence=0.8,
        )
        ks.add(entry)
        count += 1

    print(f'[OK] Migrated {count} entries from structured_commands_kb.json')
    return count


def copy_config_methods() -> int:
    """Copy config_methods/*.json as-is."""
    src = os.path.join(OLD_KB, 'config_methods')
    dst = os.path.join(NEW_KB, 'config_methods')
    if not os.path.isdir(src):
        print('[SKIP] config_methods/ not found')
        return 0

    os.makedirs(dst, exist_ok=True)
    count = 0
    for fname in os.listdir(src):
        if fname.endswith('.json'):
            shutil.copy2(os.path.join(src, fname), os.path.join(dst, fname))
            count += 1
    print(f'[OK] Copied {count} config method files')
    return count


def main() -> None:
    os.makedirs(NEW_KB, exist_ok=True)
    total = 0
    total += migrate_global_kb()
    total += migrate_structured_kb()
    total += copy_config_methods()
    print(f'\n==== Migration complete: {total} total entries ====')


if __name__ == '__main__':
    main()
