# -*- coding: utf-8 -*-
"""Shared service singletons for eNSP-MCP.

Both app.py (Flask) and mcp_server.py (MCP stdio) import from here
to share the same knowledge base, topology engine, and config methods.
"""
from __future__ import annotations
import os

from knowledge import KnowledgeBase
from topology import TopologyEngine
from config_method_store import ConfigMethodStore

# ---- Shared singletons ----

_KB_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kb')

kb = KnowledgeBase(_KB_FOLDER)
topo_engine = TopologyEngine()
config_methods = ConfigMethodStore(_KB_FOLDER)
