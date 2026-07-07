# eNSP-MCP

MCP Server for Huawei eNSP network simulator. AI Agent connects via MCP stdio, sends commands to eNSP devices through raw TCP sockets — no intermediate server, no HTTP round-trips.

## Architecture

```
AI Client (Claude / TRAE / Cursor)
        │  MCP stdio
        ▼
mcp_server.py          ── config/tools.yaml → tool definitions
        │
   ┌────┴────┐
   ▼         ▼
core/      core/
commands  knowledge
   │
   ▼
core/devices           ── heartbeat (built-in, async)
   │
   ▼
driver/telnet          ── raw TCP, prompt-driven I/O
   │
   ▼
eNSP device (127.0.0.1:2000-2050)
```

Every layer depends only on the layer below it. No circular imports. No global mutable state outside `DeviceManager`.

### What this is NOT

- No Flask web UI (AI is the only consumer; use structured logs for debugging)
- No Agent runtime on the tool side (AI does the reasoning, tools do the execution)
- No multiple knowledge base implementations (one `KnowledgeService`, one data model)
- No hardcoded tool definitions in Python (they live in `config/tools.yaml`, UTF-8)

## How command execution works

```
AI calls send_command(path="127.0.0.1:2000", command="ospf 1")
        │
        ▼
CommandPipeline.execute(ctx)
        │
   ┌────┴────────────────────────────────────────────┐
   ▼                                                 ▼
BlockDangerousCommands      AutoUndoTerminalMonitor   ExecuteCommand       RecordToKnowledge
  rejects reboot/reset       injects undo t m         sends via TCP         fire-and-forget
  before it reaches hw       before first config      reads until prompt    writes to kb
```

Each device gets a dedicated single-worker `ThreadPoolExecutor`. Heartbeat uses a separate short-lived socket — it never competes with commands for the I/O lock.

## File layout

```
mcpensp_new/
├── mcp_server.py              MCP entry (stdio), loads tools from YAML
├── driver/
│   └── telnet.py              Raw TCP I/O, Transport protocol for testability
├── core/
│   ├── devices.py             DeviceManager — single source of truth for device state
│   ├── commands.py            Pipeline/Middleware pattern for command execution
│   ├── knowledge.py           Unified KB — JSONL append-only + memory index
│   ├── diagnostics.py         Pattern-matched error → cause + suggestion
│   ├── status.py              Device health monitor (TCP + session probe)
│   └── config_methods.py      Verified config step sequences (OSPF, VLAN, DHCP...)
├── config/
│   ├── tools.yaml             26 MCP tool definitions (UTF-8, no garbled text)
│   └── security.yaml          Blocked command list
├── prompts/
│   └── system.md              Agent system prompt
├── kb/
│   └── config_methods/        Standard config procedures (JSON)
├── migrate_kb.py              One-shot migration from old KB format
├── requirements.txt           mcp + pyyaml
└── tests/
    ├── test_telnet.py         18 tests (prompts, classify, execute, is_alive)
    ├── test_commands.py        6 tests (block, undo_tm, pipeline)
    ├── test_knowledge.py       8 tests (CRUD, search, persistence)
    ├── test_diagnostics.py     6 tests (pattern match, batch)
    ├── test_devices.py        23 tests (connect, metadata, topology, scan)
    ├── test_status.py           9 tests (health check, summary)
    └── test_config_methods.py 18 tests (CRUD, search, steps, usage)
```

## Tools (32 total)

| Tool | Description |
|------|-------------|
| `scan_devices` | Scan port range for eNSP devices |
| `connect_device` | Connect, auto-detect name and type |
| `send_command` | Execute one command, returns cmd_success + elapsed_ms + errors |
| `batch_command` | Execute multiple commands on one device |
| `group_command` | Execute same command on multiple devices |
| `disconnect_device` | Close connection and free resources |
| `get_connected_devices` | List all connected devices |
| `check_device_status` | Probe single device health (TCP + session) |
| `check_all_status` | Probe all device health |
| `status_summary` | Aggregate status: total / alive / dead |
| `rename_device` | Set custom device name |
| `fetch_device_name` | Pull real hostname from device |
| `diagnose_command` | Match error patterns → cause + fix suggestion |
| `diagnose_batch` | Diagnose multiple command results |
| `search_kb` | Search knowledge base (commands, experiences, troubleshooting) |
| `get_kb_stats` | Knowledge base statistics |
| `get_config_guidance` | Comprehensive guidance for a config topic |
| `record_experience` | Save experiment result to KB |
| `get_command_catalog` | List supported commands |
| `generate_lab_report` | Export lab report from all connected devices |
| `get_topology` | Topology summary |
| `save_topology` | Save/update topology data |
| `config_method_*` | Standard config procedures (list/get/search/steps/add/update) |

## Quickstart

```bash
cd mcpensp_new
pip install -r requirements.txt
python mcp_server.py
```

MCP client config:

```json
{
  "mcpServers": {
    "ensp": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "e:/eNSP-MCP/mcpensp_new"
    }
  }
}
```

No `ENSP_SERVER_URL` needed. One process, one connection per device.

## Running tests

```bash
pip install pytest pytest-asyncio
python -m pytest tests/ -v
```

All 87 tests pass without eNSP running — they use `MockTransport` and in-process state.

## Migrating from old system

```bash
python migrate_kb.py
```

Reads `../mcpensp1/kb/global_kb.json`, `structured_commands_kb.json`, and copies `config_methods/*.json` into the new `kb/` directory.

## Design notes

**Why middleware instead of a god object?** Each concern (block, auto-undo, execute, record) is a 20-40 line middleware class. Adding a new concern = adding a new middleware. No existing code changes.

**Why JSONL + index instead of one big JSON?** Append-only writes are atomic and crash-safe. The memory index loads instantly on startup. No `_dirty` flag, no delayed flush.

**Why dedicated thread per device?** Shared `ThreadPoolExecutor` can deadlock when heartbeat + commands + batch all compete. A private single-worker executor per device serialises naturally, and 10 devices = 10 independent workers.

**Why YAML for tool definitions?** UTF-8 by nature. YAML can't produce garbled text the way Python source files with wrong encoding can. Plus a built-in fallback: if `tools.yaml` is missing or broken, the server starts with 18 core tools hardcoded.

**Why no Agent runtime?** The AI is the Agent. The tool side provides sharp primitives: connect, execute, diagnose, check status, search, record. AI composes them. You don't need a planner on a hammer.
