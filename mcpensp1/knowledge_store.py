# -*- coding: utf-8 -*-
"""Knowledge Store - unified knowledge base for eNSP-MCP.

Provides a single KnowledgeBase class imported from knowledge.py,
with proper integration to DeviceManager for device metadata.
"""
from __future__ import annotations
import os, json, re, hashlib, tempfile, logging, threading, time
from datetime import datetime, timezone

from knowledge import KnowledgeBase

logger = logging.getLogger(__name__)

# Re-export KnowledgeBase as KnowledgeStore for clarity
KnowledgeStore = KnowledgeBase
