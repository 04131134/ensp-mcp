# -*- coding: utf-8 -*-
"""Unified Knowledge Base for eNSP-MCP.

Single data model (KnowledgeEntry), single storage file (JSONL append-only),
in-memory index for search. No duplication, no drift between "agent KB" and
"app KB".

Storage:
  kb/knowledge.jsonl  — append-only event stream
  kb/knowledge.idx    — in-memory index snapshot (for fast startup)

Write path:  append line → JSONL  (atomic: write temp + rename)
Read path:   query → search memory index → load full entries on demand
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass(kw_only=True)
class KnowledgeEntry:
    """A single knowledge record."""
    id: str = field(default_factory=lambda: _make_id(str(time.time())))
    category: str = 'command'  # command | experience | template | troubleshoot
                               # success_case | failure_case | best_practice
                               # config_order | verify_method
    title: str = ''
    content: dict = field(default_factory=dict)
    device_type: str = 'unknown'
    device_path: str = ''
    tags: list[str] = field(default_factory=list)
    success: bool | None = None
    command: str = ''
    output_preview: str = ''
    risk: str = 'medium'
    context: dict = field(default_factory=dict)
    use_count: int = 0
    confidence: float = 0.8
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeEntry:
        valid = {k: v for k, v in data.items()
                 if k in cls.__dataclass_fields__}
        return cls(**valid)


def _make_id(*parts: str) -> str:
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class KnowledgeIndex:
    """In-memory search index over knowledge entries."""

    def __init__(self, kb_dir: str) -> None:
        self._dir = kb_dir
        self._entries: dict[str, KnowledgeEntry] = {}
        self._tag_index: dict[str, set[str]] = {}
        self._type_index: dict[str, set[str]] = {}
        self._cat_index: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def add(self, entry: KnowledgeEntry) -> None:
        with self._lock:
            self._entries[entry.id] = entry
            for tag in entry.tags:
                self._tag_index.setdefault(tag, set()).add(entry.id)
            self._type_index.setdefault(entry.device_type, set()).add(entry.id)
            self._cat_index.setdefault(entry.category, set()).add(entry.id)

    def search(self, query: str = '',
               category: str | None = None,
               device_type: str | None = None,
               limit: int = 20) -> list[KnowledgeEntry]:
        with self._lock:
            ids = set(self._entries.keys())
            if category:
                ids &= self._cat_index.get(category, set())
            if device_type:
                ids &= self._type_index.get(device_type, set())

            if query:
                ql = query.lower()
                tokens = set(ql.split())
                scored: list[tuple[float, KnowledgeEntry]] = []
                for eid in ids:
                    e = self._entries[eid]
                    text = f'{e.title} {json.dumps(e.content, ensure_ascii=False)} {" ".join(e.tags)}'.lower()
                    score = sum(2.0 for t in tokens if t in text)
                    if ql in e.title.lower():
                        score += 5.0
                    success_bonus = (e.use_count * 0.1) if e.success else 0
                    score += success_bonus + e.confidence
                    if score > 0:
                        scored.append((score, e))
                scored.sort(key=lambda x: -x[0])
                return [e for _, e in scored[:limit]]

            entries = sorted(
                (self._entries[eid] for eid in ids),
                key=lambda e: (-e.confidence, -e.use_count),
            )
            return entries[:limit]

    def search_by_tag(self, tag: str, limit: int = 20) -> list[KnowledgeEntry]:
        with self._lock:
            ids = self._tag_index.get(tag, set())
            return [self._entries[eid] for eid in list(ids)[:limit]]

    def get_stats(self) -> dict:
        with self._lock:
            cats: dict[str, int] = {}
            for e in self._entries.values():
                cats[e.category] = cats.get(e.category, 0) + 1
            return {
                'total': len(self._entries),
                'by_category': cats,
                'by_device_type': {k: len(v) for k, v in self._type_index.items()},
            }

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [e.to_dict() for e in self._entries.values()]

    def load_snapshot(self, data: list[dict]) -> None:
        with self._lock:
            for d in data:
                e = KnowledgeEntry.from_dict(d)
                self._entries[e.id] = e
                for tag in e.tags:
                    self._tag_index.setdefault(tag, set()).add(e.id)
                self._type_index.setdefault(e.device_type, set()).add(e.id)
                self._cat_index.setdefault(e.category, set()).add(e.id)


class KnowledgeService:
    """Unified knowledge base with JSONL storage + memory index."""

    def __init__(self, kb_dir: str) -> None:
        self._dir = kb_dir
        os.makedirs(kb_dir, exist_ok=True)
        self._jsonl_path = os.path.join(kb_dir, 'knowledge.jsonl')
        self._idx_path = os.path.join(kb_dir, 'knowledge.idx')
        self._index = KnowledgeIndex(kb_dir)
        self._write_lock = threading.Lock()
        self._load_all()
        logger.info('KnowledgeService loaded %d entries', self._index.get_stats()['total'])

    # ── persistence ──────────────────────────────────────────

    def _load_all(self) -> None:
        if os.path.exists(self._idx_path):
            try:
                with open(self._idx_path, encoding='utf-8') as f:
                    data = json.load(f)
                self._index.load_snapshot(data)
                logger.info('Loaded index from %s', self._idx_path)
                return
            except Exception as e:
                logger.warning('Failed to load index: %s, rebuilding…', e)

        if os.path.exists(self._jsonl_path):
            count = 0
            with open(self._jsonl_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = KnowledgeEntry.from_dict(json.loads(line))
                        self._index.add(entry)
                        count += 1
                    except Exception:
                        pass
            logger.info('Rebuilt index from %d JSONL lines', count)
            self._save_index()

    def _save_index(self) -> None:
        data = self._index.snapshot()
        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self._idx_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _append_jsonl(self, entry: KnowledgeEntry) -> None:
        """Atomically append one line to JSONL."""
        line = json.dumps(entry.to_dict(), ensure_ascii=False) + '\n'
        with self._write_lock:
            with open(self._jsonl_path, 'a', encoding='utf-8') as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

    # ── write ────────────────────────────────────────────────

    def add(self, entry: KnowledgeEntry) -> str:
        self._index.add(entry)
        self._append_jsonl(entry)
        # Debounce index save — write at most once per 10 seconds
        now = time.time()
        if not hasattr(self, '_last_idx_save'):
            self._last_idx_save = 0.0
        if now - self._last_idx_save > 10:
            self._save_index()
            self._last_idx_save = now
        return entry.id

    def record_command(self, command: str, result: 'CommandResult',  # noqa: F821
                       device_path: str, device_type: str,
                       context: dict | None = None) -> None:
        """Record a command execution as side-effect. Never raises."""
        try:
            entry = KnowledgeEntry(
                id=_make_id(device_path, str(time.time())),
                category='command',
                title=command.strip(),
                content={'output': result.output[:500]},
                device_type=device_type,
                device_path=device_path,
                tags=[device_type, 'command'],
                success=result.success,
                command=command.strip(),
                output_preview=result.output[:500],
                risk='low' if result.success else 'medium',
                context=context or {},
                use_count=1,
                confidence=0.9 if result.success else 0.5,
            )
            self.add(entry)
        except Exception:
            logger.exception('Failed to record command — non-fatal')

    def record_experience(self, experiment: str, commands: list[str],
                          success: bool, lessons: list[str] | None = None,
                          device_type: str = 'unknown') -> dict:
        """Record experiment experience."""
        try:
            entry = KnowledgeEntry(
                id=_make_id('exp', experiment, str(time.time())),
                category='experience',
                title=experiment,
                content={'commands': commands, 'success': success,
                         'lessons': lessons or []},
                device_type=device_type,
                tags=['experience', 'success' if success else 'failure'],
                success=success,
                use_count=1,
                confidence=0.85 if success else 0.5,
            )
            self.add(entry)
            return {'success': True, 'id': entry.id}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ── read ─────────────────────────────────────────────────

    def search(self, query: str = '',
               category: str | None = None,
               device_type: str | None = None,
               limit: int = 20) -> list[KnowledgeEntry]:
        return self._index.search(query, category, device_type, limit)

    def get_stats(self) -> dict:
        return self._index.get_stats()

    def get_config_guidance(self, topic: str) -> dict:
        """Get comprehensive guidance for a configuration topic."""
        topic_lower = topic.lower()
        guidance = {
            'topic': topic,
            'experiences': [],
            'best_practices': [],
            'troubleshooting': [],
            'commands': [],
        }
        all_exp = self.search(query=topic, category='experience', limit=10)
        for e in all_exp:
            guidance['experiences'].append({
                'title': e.title,
                'commands': e.content.get('commands', [])[:10],
                'lessons': e.content.get('lessons', []),
                'success': e.success,
                'confidence': e.confidence,
            })
        bp = self.search(query=topic, category='best_practice', limit=5)
        for e in bp:
            guidance['best_practices'].append(e.content)
        ts = self.search(query=topic, category='troubleshoot', limit=5)
        for e in ts:
            guidance['troubleshooting'].append({
                'problem': e.title,
                'solution': e.content.get('solution', ''),
            })
        cmds = self.search(query=topic, category='command', limit=15)
        guidance['commands'] = [
            {'command': e.command, 'success': e.success,
             'device_type': e.device_type, 'use_count': e.use_count}
            for e in cmds
        ]
        return guidance
