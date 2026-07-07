# -*- coding: utf-8 -*-
"""
长期记忆系统 - 跨会话记忆持久化

功能：
- 实验结束后自动总结学习要点
- 不同 Agent 实例共享记忆
- 基于重要性和相关性检索
- 自动衰减过时记忆
- 支持按类别/标签/时间检索
"""
from __future__ import annotations
import json
import os
import logging
import threading
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from .types import MemoryEntry, ReflectionEntry

logger = logging.getLogger(__name__)


class MemoryStore:
    """长期记忆存储"""

    CATEGORIES = {
        'lesson': '经验教训',
        'command': '可复用命令',
        'pattern': '配置模式',
        'error': '错误案例',
        'success': '成功案例',
        'template': '可模板化实验',
        'best_practice': '最佳实践',
        'troubleshoot': '排障经验',
        'protocol': '协议知识',
        'device': '设备特性',
    }

    def __init__(self, persist_path: str):
        self._path = persist_path
        self._entries: Dict[str, MemoryEntry] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._load()
        logger.info('[Memory] 加载 %d 条记忆', len(self._entries))

    def _load(self):
        """从磁盘加载记忆"""
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for entry_data in data.get('entries', []):
                entry = MemoryEntry(**entry_data)
                self._entries[entry.entry_id] = entry
        except Exception as e:
            logger.warning('[Memory] 加载失败: %s', e)

    def _save(self):
        """保存记忆到磁盘"""
        if not self._dirty:
            return
        try:
            os.makedirs(os.path.dirname(self._path) or '.', exist_ok=True)
            data = {
                'version': '3.0',
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'total_entries': len(self._entries),
                'entries': [e.to_dict() for e in self._entries.values()],
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
            logger.error('[Memory] 保存失败: %s', e)

    def add(self, entry: MemoryEntry) -> str:
        """添加记忆条目"""
        with self._lock:
            # 去重：相同内容的记忆合并
            existing = self._find_similar(entry.content, entry.category)
            if existing:
                existing.importance = max(existing.importance, entry.importance)
                existing.access_count += 1
                existing.tags = list(set(existing.tags + entry.tags))
                entry_id = existing.entry_id
            else:
                self._entries[entry.entry_id] = entry
                entry_id = entry.entry_id
            self._dirty = True
            self._save()
            return entry_id

    def recall(
        self,
        query: str = "",
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_importance: float = 0.0,
        limit: int = 20,
    ) -> List[MemoryEntry]:
        """检索记忆"""
        with self._lock:
            candidates = list(self._entries.values())

        # 过滤
        if category:
            candidates = [e for e in candidates if e.category == category]
        if tags:
            tag_set = set(tags)
            candidates = [e for e in candidates if tag_set.intersection(e.tags)]
        if min_importance > 0:
            candidates = [e for e in candidates if e.importance >= min_importance]

        # 相关性排序
        if query:
            query_lower = query.lower()
            query_tokens = set(query_lower.split())
            scored = []
            for e in candidates:
                content_lower = e.content.lower()
                # 关键词匹配分
                match_score = sum(1 for t in query_tokens if t in content_lower)
                # 标签匹配分
                tag_score = sum(1 for t in e.tags if t.lower() in query_lower)
                # 综合分
                total = match_score * 2 + tag_score + e.importance * 3 + min(e.access_count * 0.1, 2)
                scored.append((total, e))
            scored.sort(key=lambda x: (-x[0], x[1].created_at))
            candidates = [e for _, e in scored]
        else:
            # 无查询时按重要性和使用频率排序
            candidates.sort(key=lambda e: (-e.importance, -e.access_count, e.created_at))

        # 更新访问计数
        for e in candidates[:limit]:
            e.touch()

        return candidates[:limit]

    def get_lessons(self, limit: int = 50) -> List[MemoryEntry]:
        """获取经验教训"""
        return self.recall(category='lesson', limit=limit)

    def get_error_patterns(self, limit: int = 30) -> List[MemoryEntry]:
        """获取错误模式"""
        return self.recall(category='error', limit=limit)

    def get_success_patterns(self, limit: int = 30) -> List[MemoryEntry]:
        """获取成功模式"""
        return self.recall(category='success', limit=limit)

    def get_reusable_commands(self, device_type: str = "", limit: int = 30) -> List[MemoryEntry]:
        """获取可复用命令"""
        entries = self.recall(category='command', limit=limit)
        if device_type:
            entries = [e for e in entries if device_type.lower() in [t.lower() for t in e.tags]]
        return entries

    def get_templates(self, limit: int = 20) -> List[MemoryEntry]:
        """获取可模板化的实验"""
        return self.recall(category='template', limit=limit)

    def summarize_for_prompt(self, query: str = "", limit: int = 10) -> str:
        """生成供 Agent Prompt 使用的记忆摘要"""
        entries = self.recall(query=query, limit=limit) if query else self.recall(limit=limit)
        if not entries:
            return "暂无相关记忆。"
        lines = ["## 相关记忆（按重要性排序）\n"]
        for i, e in enumerate(entries, 1):
            lines.append(f"{i}. [{self.CATEGORIES.get(e.category, e.category)}] {e.content}")
            if e.tags:
                lines.append(f"   标签: {', '.join(e.tags)}")
        return '\n'.join(lines)

    def ingest_reflection(self, reflection: ReflectionEntry) -> int:
        """从反思结果中提取记忆"""
        count = 0
        for lesson in reflection.lessons_learned:
            self.add(MemoryEntry(
                category='lesson',
                content=lesson,
                tags=['auto-extracted', 'reflection'],
                importance=0.7,
                experiment_id=reflection.experiment_id,
            ))
            count += 1
        for cmd in reflection.recommended_commands:
            self.add(MemoryEntry(
                category='command',
                content=f"推荐命令: {cmd}",
                tags=['recommended', 'verified'],
                importance=0.8,
                experiment_id=reflection.experiment_id,
            ))
            count += 1
        for update in reflection.knowledge_updates:
            self.add(MemoryEntry(
                category=update.get('category', 'lesson'),
                content=update.get('content', ''),
                tags=update.get('tags', ['auto-updated']),
                importance=update.get('importance', 0.6),
                experiment_id=reflection.experiment_id,
            ))
            count += 1
        return count

    def cleanup_stale(self, max_age_days: int = 90, min_importance: float = 0.2):
        """清理过时的低重要性记忆"""
        with self._lock:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
            stale_ids = [
                eid for eid, e in self._entries.items()
                if e.created_at < cutoff and e.importance < min_importance and e.access_count < 2
            ]
            for eid in stale_ids:
                del self._entries[eid]
            if stale_ids:
                self._dirty = True
                self._save()
                logger.info('[Memory] 清理 %d 条过时记忆', len(stale_ids))
            return len(stale_ids)

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        with self._lock:
            by_cat: Dict[str, int] = {}
            for e in self._entries.values():
                by_cat[e.category] = by_cat.get(e.category, 0) + 1
            return {
                'total_entries': len(self._entries),
                'by_category': by_cat,
                'avg_importance': sum(e.importance for e in self._entries.values()) / len(self._entries) if self._entries else 0,
                'total_accesses': sum(e.access_count for e in self._entries.values()),
            }

    def _find_similar(self, content: str, category: str) -> Optional[MemoryEntry]:
        """查找相似的记忆条目"""
        content_lower = content.lower().strip()
        content_hash = hashlib.md5(content_lower.encode()).hexdigest()[:8]
        for e in self._entries.values():
            if e.category != category:
                continue
            existing_hash = hashlib.md5(e.content.lower().strip().encode()).hexdigest()[:8]
            if content_hash == existing_hash:
                return e
        return None

    def export_for_sharing(self) -> Dict[str, Any]:
        """导出可共享的记忆数据"""
        with self._lock:
            return {
                'version': '3.0',
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'entries': [
                    e.to_dict() for e in self._entries.values()
                    if e.importance >= 0.5
                ],
            }

    def import_shared(self, data: Dict[str, Any]) -> int:
        """导入共享的记忆数据"""
        count = 0
        for entry_data in data.get('entries', []):
            try:
                entry = MemoryEntry(**entry_data)
                self.add(entry)
                count += 1
            except Exception as e:
                logger.warning('[Memory] 导入失败: %s', e)
        return count
