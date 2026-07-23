# -*- coding: utf-8 -*-
"""
知识优先检索系统 - Knowledge First

原则：
1. 知识库能回答时，禁止外部搜索
2. 知识优先级：Memory > Knowledge Base > Best Practice > Template > Troubleshooting > External
3. 自动学习：每次执行后更新知识库
4. 知识类型：命令、经验、模板、排障、最佳实践、配置顺序、验证方法、设备能力、协议知识、依赖关系
"""
from __future__ import annotations
import json
import os
import re
import hashlib
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from .types import KnowledgeRecord

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """可成长知识库存储"""

    RECORD_CATEGORIES = {
        'command': '命令记录',
        'experience': '实验经验',
        'template': '实验模板',
        'troubleshoot': '排障案例',
        'best_practice': '最佳实践',
        'config_order': '配置顺序',
        'verify_method': '验证方法',
        'device_capability': '设备能力',
        'protocol': '协议知识',
        'dependency': '依赖关系',
        'success_case': '成功案例',
        'failure_case': '失败案例',
    }

    def __init__(self, persist_path: str):
        self._path = persist_path
        self._records: Dict[str, KnowledgeRecord] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._load()
        logger.info('[KnowledgeStore] 加载 %d 条知识记录', len(self._records))

    def _load(self):
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            valid_fields = set(KnowledgeRecord.__dataclass_fields__)
            for rec_data in data.get('records', []):
                filtered = {k: v for k, v in rec_data.items() if k in valid_fields}
                rec = KnowledgeRecord(**filtered)
                self._records[rec.record_id] = rec
        except Exception as e:
            logger.warning('[KnowledgeStore] 加载失败: %s', e)

    def _save(self):
        if not self._dirty:
            return
        try:
            os.makedirs(os.path.dirname(self._path) or '.', exist_ok=True)
            data = {
                'version': '3.0',
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'total_records': len(self._records),
                'records': [r.to_dict() for r in self._records.values()],
            }
            import tempfile
            fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(self._path) or '.', suffix='.tmp'
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self._path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            self._dirty = False
        except Exception as e:
            logger.error('[KnowledgeStore] 保存失败: %s', e)

    def add(self, record: KnowledgeRecord) -> str:
        """添加知识记录"""
        with self._lock:
            existing = self._find_similar(record)
            if existing:
                # 合并更新
                existing.usage_count += record.usage_count
                existing.success_count += record.success_count
                existing.failure_count += record.failure_count
                existing.confidence = max(existing.confidence, record.confidence)
                existing.tags = list(set(existing.tags + record.tags))
                existing.last_used = datetime.now(timezone.utc).isoformat()
                record_id = existing.record_id
            else:
                self._records[record.record_id] = record
                record_id = record.record_id
            self._dirty = True
            self._save()
            return record_id

    def update(self, record: KnowledgeRecord) -> None:
        """更新一条已存在的知识记录并持久化。"""
        with self._lock:
            if record.record_id not in self._records:
                raise KeyError(f"未知知识记录: {record.record_id}")
            self._records[record.record_id] = record
            self._dirty = True
            self._save()

    def search(
        self,
        query: str = "",
        category: Optional[str] = None,
        device_type: Optional[str] = None,
        protocol: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> List[KnowledgeRecord]:
        """搜索知识库"""
        with self._lock:
            candidates = list(self._records.values())

        if category:
            candidates = [r for r in candidates if r.category == category]
        if device_type:
            candidates = [r for r in candidates if r.device_type.lower() == device_type.lower()]
        if protocol:
            candidates = [r for r in candidates if protocol.lower() in r.protocol.lower()]
        if min_confidence > 0:
            candidates = [r for r in candidates if r.confidence >= min_confidence]

        if query:
            query_lower = query.lower()
            query_tokens = set(query_lower.split())
            scored = []
            for r in candidates:
                text = f"{r.title} {json.dumps(r.content, ensure_ascii=False)} {' '.join(r.tags)}".lower()
                match_score = sum(2 if t in text else 0 for t in query_tokens)
                # 标题完全匹配加分
                if query_lower in r.title.lower():
                    match_score += 5
                # 成功率加分
                success_bonus = r.success_rate * 2
                # 使用频率加分
                usage_bonus = min(r.usage_count * 0.1, 3)
                total = match_score + success_bonus + usage_bonus + r.confidence
                scored.append((total, r))
            scored.sort(key=lambda x: -x[0])
            candidates = [r for _, r in scored]
        else:
            candidates.sort(key=lambda r: (-r.confidence, -r.usage_count, r.created_at))

        return candidates[:limit]

    def query_for_task(self, task_description: str, device_type: str = "") -> Dict[str, List[KnowledgeRecord]]:
        """为任务执行知识优先检索，返回分类结果"""
        results: Dict[str, List[KnowledgeRecord]] = {}

        # 1. 搜索最佳实践
        bp = self.search(query=task_description, category='best_practice', device_type=device_type, limit=5)
        if bp:
            results['best_practices'] = bp

        # 2. 搜索成功案例
        sc = self.search(query=task_description, category='success_case', device_type=device_type, limit=5)
        if sc:
            results['success_cases'] = sc

        # 3. 搜索实验模板
        tmpl = self.search(query=task_description, category='template', device_type=device_type, limit=5)
        if tmpl:
            results['templates'] = tmpl

        # 4. 搜索配置顺序
        order = self.search(query=task_description, category='config_order', device_type=device_type, limit=5)
        if order:
            results['config_orders'] = order

        # 5. 搜索排障案例
        ts = self.search(query=task_description, category='troubleshoot', device_type=device_type, limit=5)
        if ts:
            results['troubleshooting'] = ts

        # 6. 搜索相关命令
        cmds = self.search(query=task_description, category='command', device_type=device_type, limit=10)
        if cmds:
            results['commands'] = cmds

        # 7. 搜索验证方法
        vm = self.search(query=task_description, category='verify_method', limit=5)
        if vm:
            results['verify_methods'] = vm

        return results

    def record_success(
        self,
        commands: List[str],
        device_type: str,
        experiment_type: str,
        context: Dict[str, Any],
    ):
        """记录成功实验经验"""
        # 成功案例
        self.add(KnowledgeRecord(
            category='success_case',
            title=f"{experiment_type} 实验成功",
            content={
                'commands': commands,
                'context': context,
                'experiment_type': experiment_type,
            },
            device_type=device_type,
            tags=[experiment_type, 'success'],
            confidence=0.9,
            source='learned',
        ))

    def record_failure(
        self,
        failed_command: str,
        error_message: str,
        device_type: str,
        experiment_type: str,
        fix_commands: Optional[List[str]] = None,
    ):
        """记录失败案例和排障方法"""
        self.add(KnowledgeRecord(
            category='failure_case',
            title=f"失败: {failed_command[:50]}",
            content={
                'failed_command': failed_command,
                'error_message': error_message,
                'experiment_type': experiment_type,
                'fix_commands': fix_commands or [],
            },
            device_type=device_type,
            tags=[experiment_type, 'failure', 'troubleshoot'],
            confidence=0.7,
            source='learned',
        ))

        # 如果有修复方案，同时记录排障案例
        if fix_commands:
            self.add(KnowledgeRecord(
                category='troubleshoot',
                title=f"排障: {error_message[:40]}",
                content={
                    'symptom': error_message,
                    'cause': failed_command,
                    'solution': fix_commands,
                },
                device_type=device_type,
                tags=[experiment_type, 'auto-fix'],
                confidence=0.8,
                source='learned',
            ))

    def record_best_practice(self, title: str, content: Dict[str, Any], tags: List[str] = None):
        """记录最佳实践"""
        self.add(KnowledgeRecord(
            category='best_practice',
            title=title,
            content=content,
            tags=tags or [],
            confidence=0.9,
            source='learned',
        ))

    def record_config_order(self, experiment_type: str, steps: List[Dict[str, Any]], device_type: str = "huawei"):
        """记录配置顺序"""
        self.add(KnowledgeRecord(
            category='config_order',
            title=f"{experiment_type} 配置顺序",
            content={'steps': steps, 'experiment_type': experiment_type},
            device_type=device_type,
            tags=[experiment_type, 'config-order'],
            confidence=0.85,
            source='learned',
        ))

    def record_verify_method(self, protocol: str, commands: List[str], expected: str, device_type: str = "huawei"):
        """记录验证方法"""
        self.add(KnowledgeRecord(
            category='verify_method',
            title=f"{protocol} 验证方法",
            content={'commands': commands, 'expected': expected},
            device_type=device_type,
            protocol=protocol,
            tags=[protocol, 'verify'],
            confidence=0.9,
            source='learned',
        ))

    def record_experiment_template(
        self,
        name: str,
        description: str,
        phases: List[Dict[str, Any]],
        device_type: str = "huawei",
    ):
        """记录实验模板"""
        self.add(KnowledgeRecord(
            category='template',
            title=name,
            content={'description': description, 'phases': phases},
            device_type=device_type,
            tags=['template'],
            confidence=0.8,
            source='learned',
        ))

    def get_stats(self) -> Dict[str, Any]:
        """获取知识库统计"""
        with self._lock:
            by_cat: Dict[str, int] = {}
            for r in self._records.values():
                by_cat[r.category] = by_cat.get(r.category, 0) + 1
            return {
                'total_records': len(self._records),
                'by_category': by_cat,
                'avg_confidence': sum(r.confidence for r in self._records.values()) / len(self._records) if self._records else 0,
                'total_usage': sum(r.usage_count for r in self._records.values()),
            }

    def _find_similar(self, record: KnowledgeRecord) -> Optional[KnowledgeRecord]:
        """查找相似的知识记录"""
        content_str = json.dumps(record.content, sort_keys=True, ensure_ascii=False)
        content_hash = hashlib.md5(content_str.encode()).hexdigest()[:12]
        for r in self._records.values():
            if r.category != record.category:
                continue
            existing_str = json.dumps(r.content, sort_keys=True, ensure_ascii=False)
            existing_hash = hashlib.md5(existing_str.encode()).hexdigest()[:12]
            if content_hash == existing_hash:
                return r
        return None

    def summarize_for_prompt(self, task_description: str, device_type: str = "") -> str:
        """生成供 Agent Prompt 使用的知识摘要"""
        results = self.query_for_task(task_description, device_type)
        if not results:
            return "知识库中暂无相关知识，将基于通用网络知识执行。"

        lines = ["## 知识库检索结果\n"]
        for cat, records in results.items():
            label = self.RECORD_CATEGORIES.get(cat, cat)
            lines.append(f"### {label}")
            for r in records[:3]:
                lines.append(f"- **{r.title}** (置信度: {r.confidence:.0%}, 成功率: {r.success_rate:.0%})")
                if r.category == 'config_order' and 'steps' in r.content:
                    steps = r.content['steps']
                    lines.append(f"  步骤: {' → '.join(s.get('name', '') for s in steps)}")
                elif r.category == 'troubleshoot' and 'solution' in r.content:
                    lines.append(f"  解决方案: {', '.join(r.content['solution'])}")
            lines.append("")

        return '\n'.join(lines)

    def export_for_sharing(self) -> Dict[str, Any]:
        """导出可共享的知识数据"""
        with self._lock:
            return {
                'version': '3.0',
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'records': [r.to_dict() for r in self._records.values()],
            }

    def import_shared(self, data: Dict[str, Any]) -> int:
        """导入共享知识"""
        count = 0
        for rec_data in data.get('records', []):
            try:
                rec = KnowledgeRecord(**rec_data)
                self.add(rec)
                count += 1
            except Exception as e:
                logger.warning('[KnowledgeStore] 导入失败: %s', e)
        return count
