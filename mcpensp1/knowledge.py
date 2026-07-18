# -*- coding: utf-8 -*-
"""Knowledge base for eNSP device commands and experiences."""
import os, json, re, hashlib, tempfile, logging, threading, time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Forward references - these will be set by app.py after import
device_names = {}
device_types = {}
devices = {}
devices_lock = threading.Lock()
name_lock = threading.Lock()
COMMAND_CATALOG = {}  # Will be set by app.py

class KnowledgeBase:
    def __init__(self, kb_folder):
        self.folder = kb_folder
        self.global_path = os.path.join(kb_folder, 'global_kb.json')
        self.devices_path = os.path.join(kb_folder, 'devices_kb.json')
        self.structured_path = os.path.join(kb_folder, 'structured_commands_kb.json')
        self._skb_cache = None
        self.lock = threading.Lock()
        # In-memory cache to avoid disk IO on every command
        self._gkb_cache = None
        self._dkb_cache = None
        self._dirty = False
        self._last_flush = time.time()
        self._flush_interval = 10  # Flush to disk at most every 10 seconds
        if not os.path.exists(self.global_path): self._save(self.global_path, {'last_updated': self._now()})
        if not os.path.exists(self.devices_path): self._save(self.devices_path, {'devices': {}})
        # Pre-load caches
        self._gkb_cache = self._load(self.global_path)
        self._dkb_cache = self._load(self.devices_path)
        self._skb_cache = self.load_structured_kb()

    def _flush_if_needed(self):
        """Flush dirty cache to disk if enough time has passed."""
        if not self._dirty:
            return
        now = time.time()
        if now - self._last_flush >= self._flush_interval:
            self._do_flush()

    def _do_flush(self):
        """Force flush cache to disk."""
        if not self._dirty:
            return
        try:
            self._save(self.global_path, self._gkb_cache)
            self._save(self.devices_path, self._dkb_cache)
            self._dirty = False
            self._last_flush = time.time()
        except Exception as e:
            logger.error('KB flush failed: %s', e)

    def _load(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except Exception as e:
            logger.warning('Failed to load %s: %s', path, e)
            return {}

    def _save(self, path, data):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        dir_name = os.path.dirname(path) or '.'
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            try: os.unlink(tmp_path)
            except OSError: pass
            raise

    def _now(self): return datetime.now(timezone.utc).isoformat()

    def record_command(self, command, output, device_type="unknown", device_path=None, success=True):
        with self.lock:
            # ── Data quality guards (Phase 5) ──
            # Guard 1: Auto-detect success from output
            if output and output.strip():
                _err_patterns = ['Error:', 'Unrecognized command', 'Wrong parameter',
                                 'Too many parameters', 'Ambiguous command',
                                 'Incomplete command', 'Please renew the default configurations']
                if any(kw in output for kw in _err_patterns):
                    success = False

            gkb = self._gkb_cache or self._load(self.global_path)
            dkb = self._dkb_cache or self._load(self.devices_path)
            cmd_lower = command.strip().lower()
            parts = cmd_lower.split()
            base_cmd = parts[0] if parts else cmd_lower
            cat_entry = COMMAND_CATALOG.get(cmd_lower) or COMMAND_CATALOG.get(base_cmd)
            desc = cat_entry['description'] if cat_entry else ''
            cat = cat_entry['category'] if cat_entry else self._guess_cat(cmd_lower)
            # Guard 2: Risk defaults: known catalog → catalog value, else → medium
            risk = cat_entry['risk'] if cat_entry else 'medium'
            # Guard 3: Description must not be empty
            if not desc or desc.strip() == '':
                desc = base_cmd or 'network command'
            cmd_key = hashlib.sha256(f'{device_type}:{cmd_lower}'.encode()).hexdigest()[:16]
            cmds = gkb.setdefault("commands", [])
            existing = next((i for i, c in enumerate(cmds) if c.get("key") == cmd_key), None)
            entry = {"key": cmd_key, "command": command.strip(), "description": desc,
                     "device_type": device_type, "category": cat, "risk": risk,
                     "output_preview": (output[:500] if output else ""),
                     "success": success, "last_used": self._now(),
                     "use_count": 1, "devices_used": []}
            if existing is not None:
                old = cmds[existing]
                entry['use_count'] = old.get('use_count', 0) + 1
                entry['devices_used'] = list(set(old.get('devices_used', []) + [device_path])) if device_path else old.get('devices_used', [])
                entry['output_preview'] = output[:500] if output else old.get('output_preview', '')
                cmds[existing] = entry
            else:
                if device_path: entry["devices_used"] = [device_path]
                cmds.append(entry)
            gkb['last_updated'] = self._now()
            gkb['commands'] = cmds[-300:]
            self._gkb_cache = gkb
            self._dirty = True

            devs = dkb.setdefault("devices", {})
            dev = devs.setdefault(device_path or "unknown", {"device_type": device_type, "display_name": device_names.get(device_path, device_path), "executed_commands": [], "failed_commands": [], "first_seen": self._now()})
            dev["device_type"] = device_type
            dev["display_name"] = device_names.get(device_path, device_path)
            dev["last_seen"] = self._now()
            cmd_rec = {"command": command.strip(), "description": desc, "category": cat, "risk": risk,
                       "success": success, "output_preview": (output[:300] if output else ""), "timestamp": self._now(), "use_count": 1}
            if success:
                ec = next((c for c in dev['executed_commands'] if c['command'] == command.strip()), None)
                if ec:
                    ec['use_count'] = ec.get('use_count', 0) + 1
                    ec['last_used'] = self._now()
                    ec['output_preview'] = output[:300] if output else ec.get('output_preview', '')
                else:
                    dev['executed_commands'].append(cmd_rec)
                dev['executed_commands'] = dev['executed_commands'][-100:]
                dev['failed_commands'] = [c for c in dev.get('failed_commands', []) if c['command'] != command.strip()]
            else:
                dev['failed_commands'].append(cmd_rec)
                dev['failed_commands'] = dev['failed_commands'][-50:]
            self._dkb_cache = dkb
            self._dirty = True
            self._flush_if_needed()

    def get_device_history(self, device_path=None):
        with self.lock:
            dkb = self._dkb_cache or self._load(self.devices_path)
            return dkb.get('devices', {}).get(device_path, {}) if device_path else dkb.get('devices', {})

    def get_device_capabilities(self, device_path=None):
        with self.lock:
            dkb = self._dkb_cache or self._load(self.devices_path)
            devs = dkb.get('devices', {})
            if device_path:
                dev = devs.get(device_path, {})
                return self._build_cap(dev, dev.get('device_type', 'unknown'))
            return {p: self._build_cap(d, d.get('device_type', 'unknown')) for p, d in devs.items()}

    def _build_cap(self, dev, dt):
        executed = set(c['command'].strip().lower() for c in dev.get('executed_commands', []))
        failed = set(c['command'].strip().lower() for c in dev.get('failed_commands', []))
        can, cannot, untested = [], [], []
        for cmd, info in COMMAND_CATALOG.items():
            entry = {'command': cmd, 'description': info['description'], 'category': info['category'],
                     'risk': info['risk'], 'tags': info['tags'], 'output_hint': info['output_hint']}
            if cmd in executed:
                entry['status'] = 'verified'
                entry['use_count'] = next((c.get('use_count', 1) for c in dev.get('executed_commands', []) if c['command'].strip().lower() == cmd), 1)
                can.append(entry)
            elif cmd in failed:
                entry['status'] = 'failed'
                cannot.append(entry)
            elif info.get(dt, False):
                entry['status'] = 'supported'
                can.append(entry)
            else:
                entry['status'] = 'unsupported'
                untested.append(entry)
        can.sort(key=lambda x: (0 if x['status'] == 'verified' else 1, x['risk'] != 'safe'))
        return {'device_type': dt, 'display_name': dev.get('display_name', ''),
                'can_execute': can, 'cannot_execute': cannot, 'untested': untested,
                'total_executed': len(dev.get('executed_commands', [])),
                'total_failed': len(dev.get('failed_commands', []))}

    def get_global_commands(self, category=None, device_type=None, risk=None, limit=50):
        with self.lock:
            cmds = self._load(self.global_path).get('commands', [])
            if category: cmds = [c for c in cmds if c.get("category") == category]
            if device_type: cmds = [c for c in cmds if c.get("device_type") == device_type]
            if risk: cmds = [c for c in cmds if c.get("risk") == risk]
            cmds.sort(key=lambda x: x.get('use_count', 0), reverse=True)
            return cmds[:limit]

    def get_command_catalog(self, category=None, device_type=None, risk=None):
        result = []
        for cmd, info in COMMAND_CATALOG.items():
            if category and info['category'] != category: continue
            if device_type and not info.get(device_type, False): continue
            if risk and info['risk'] != risk: continue
            result.append({'command': cmd, 'description': info['description'], 'category': info['category'],
                          'risk': info['risk'], 'tags': info['tags'], 'output_hint': info['output_hint'],
                          'supported': {k: info.get(k, False) for k in ['huawei', 'h3c', 'cisco', 'juniper']}})
        return result

    def get_stats(self):
        with self.lock:
            gkb = self._load(self.global_path)
            dkb = self._load(self.devices_path)
            return {'total_commands_recorded': len(gkb.get('commands', [])), 'total_devices': len(dkb.get('devices', {})),
                    'catalog_size': len(COMMAND_CATALOG), 'last_updated': gkb.get('last_updated', 'never')}

    def load_structured_kb(self):
        """Load the structured command knowledge base from JSON file."""
        try:
            with open(self.structured_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info('Loaded structured KB: %s', self.structured_path)
            return data
        except FileNotFoundError:
            logger.warning('Structured KB not found: %s', self.structured_path)
            return {}
        except Exception as e:
            logger.error('Failed to load structured KB: %s', e)
            return {}

    def get_structured_kb(self, view_type=None, device_model=None):
        """Get structured KB, optionally filtered by view type and/or device model."""
        skb = self._skb_cache or {}
        if not view_type and not device_model:
            return skb
        result = {}
        if view_type == 'user_view':
            uv = skb.get('user_view_commands', {})
            if device_model:
                result['user_view_commands'] = {
                    '_meta': uv.get('_meta', {}),
                    device_model: uv.get(device_model, uv.get('common', {}))
                }
            else:
                result['user_view_commands'] = uv
        elif view_type == 'system_view':
            sv = skb.get('system_view_commands', {})
            if device_model:
                result['system_view_commands'] = {
                    '_meta': sv.get('_meta', {}),
                    device_model: sv.get(device_model, {})
                }
            else:
                result['system_view_commands'] = sv
        else:
            if device_model:
                uv = skb.get('user_view_commands', {})
                sv = skb.get('system_view_commands', {})
                result['user_view_commands'] = {'_meta': uv.get('_meta', {}), device_model: uv.get(device_model, uv.get('common', {}))}
                result['system_view_commands'] = {'_meta': sv.get('_meta', {}), device_model: sv.get(device_model, {})}
        result['troubleshooting'] = skb.get('troubleshooting', {})
        result['config_order'] = skb.get('config_order', [])
        return result

    def suggest_commands(self, device_model, view_type=None):
        """Suggest commands for a given device model based on structured KB."""
        skb = self._skb_cache or {}
        suggestions = {'device_model': device_model, 'user_view': [], 'system_view': []}
        model_key = self._match_model(device_model)
        
        if view_type is None or view_type == 'user_view':
            uv = skb.get('user_view_commands', {})
            common_cmds = uv.get('common', {}).get('commands', [])
            suggestions['user_view'].extend([{'group': 'common', **c} for c in common_cmds])
            if model_key and model_key in uv:
                model_cmds = uv[model_key].get('commands', [])
                suggestions['user_view'].extend([{'group': model_key, **c} for c in model_cmds])
        
        if view_type is None or view_type == 'system_view':
            sv = skb.get('system_view_commands', {})
            if model_key and model_key in sv:
                topics = sv[model_key].get('topics', {})
                for topic_name, topic_data in topics.items():
                    cmds = topic_data.get('commands', [])
                    tips = topic_data.get('tips', [])
                    view = topic_data.get('view', '')
                    for c in cmds:
                        suggestions['system_view'].append({
                            'group': topic_name, 'view': view, 'tips': tips, **c
                        })
        return suggestions

    def _match_model(self, device_name):
        """Match a device name/model to a known model key in the structured KB."""
        if not device_name:
            return None
        dn = device_name.upper()
        model_map = {
            'S5700': 'S5700', 'S3700': 'S3700',
            'USG6000V': 'USG6000V', 'USG6000': 'USG6000V',
            'AR2220': 'AR2220', 'AR1': 'AR2220', 'AR2': 'AR2220',
            'AC6605': 'AC6605', 'AC1': 'AC6605', 'AC2': 'AC6605',
            'FW1': 'USG6000V', 'FW2': 'USG6000V',
        }
        for key, val in model_map.items():
            if key in dn:
                return val
        m = re.match(r'LSW(\d+)', dn)
        if m:
            idx = int(m.group(1))
            return 'S5700' if idx <= 4 else 'S3700'
        return None

    def scan_device_commands(self, device_path):
        """Scan a connected device, detect model, and suggest commands."""
        with devices_lock:
            conn = devices.get(device_path)
        if not conn:
            return {'success': False, 'error': f'Device {device_path} not connected'}
        try:
            ver_output = conn.send_cmd('display version')
            if not ver_output:
                return {'success': False, 'error': 'Failed to get device version'}
            model = None
            model_patterns = [
                (r'(S\d{4}\S*)', 'S'),
                (r'(USG\d+\S*)', 'USG'),
                (r'(AR\d+\S*)', 'AR'),
                (r'(AC\d+\S*)', 'AC'),
            ]
            for pattern, prefix in model_patterns:
                m = re.search(pattern, ver_output, re.IGNORECASE)
                if m:
                    model = m.group(1).strip()
                    break
            name = device_names.get(device_path, device_path)
            kb_model = self._match_model(model or name)
            suggestions = self.suggest_commands(kb_model) if kb_model else {'user_view': [], 'system_view': []}
            return {
                'success': True,
                'device_path': device_path,
                'device_name': name,
                'detected_model': model,
                'kb_model_key': kb_model,
                'version_preview': ver_output[:300],
                'suggestions': suggestions,
                'troubleshooting': self._skb_cache.get('troubleshooting', {}) if self._skb_cache else {},
                'config_order': self._skb_cache.get('config_order', []) if self._skb_cache else []
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def record_experience(self, experience_data):
        """Record config method knowledge (simplified v2.4).
        Stores: experiment (topic), device_type, commands, lessons.
        """
        try:
            skb = self._skb_cache or self.load_structured_kb()
            if not skb:
                return {"success": False, "error": "Structured KB not available"}
            
            experiences = skb.setdefault("experiences", [])
            exp_name = experience_data.get("experiment", "")
            
            existing = next((i for i, e in enumerate(experiences) if e.get("experiment") == exp_name), None)
            if existing is not None:
                old = experiences[existing]
                old_cmds = set(old.get("commands", []))
                for cmd in experience_data.get("commands", []):
                    if cmd not in old_cmds:
                        old["commands"].append(cmd)
            else:
                experiences.append({
                    "experiment": exp_name,
                    "device_type": experience_data.get("device_type", ""),
                    "commands": experience_data.get("commands", []),
                    "lessons": experience_data.get("lessons", []),
                })
            
            meta = skb.setdefault("meta", {})
            meta["experiment_count"] = len(experiences)
            meta["last_updated"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
            skb["meta"] = meta
            
            with open(self.structured_path, "w", encoding="utf-8") as f:
                __import__("json").dump(skb, f, ensure_ascii=False, indent=2)
            return {"success": True, "experiment": exp_name}
        except Exception as e:
            return {"success": False, "error": str(e)}
    def record_best_practice(self, practice_data):
        """Add a new best practice to the knowledge base.
        
        Args:
            practice_data: dict with rule, detail, view, command, priority, applies_to
        Returns:
            dict with success status
        """
        try:
            skb = self._skb_cache or self.load_structured_kb()
            bp = skb.setdefault('best_practices', {'command_rules': []})
            rules = bp.setdefault('command_rules', [])
            
            # Auto-generate ID
            def _safe_id(r):
                try: return int(r.get('id', 'BP-000').split('-')[1])
                except (ValueError, IndexError): return 0
            max_id = max((_safe_id(r) for r in rules), default=0)
            practice_data.setdefault('id', f'BP-{max_id+1:03d}')
            
            # Check for duplicates
            existing = any(r.get('rule') == practice_data.get('rule') for r in rules)
            if existing:
                return {'success': False, 'error': 'Best practice already exists'}
            
            rules.append(practice_data)
            
            with open(self.structured_path, 'w', encoding='utf-8') as f:
                json.dump(skb, f, ensure_ascii=False, indent=2)
            self._skb_cache = skb
            
            return {'success': True, 'id': practice_data['id'], 'total_practices': len(rules)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_best_practices(self, priority=None, applies_to=None):
        """Get best practices, optionally filtered."""
        skb = self._skb_cache or {}
        bp = skb.get('best_practices', {})
        rules = bp.get('command_rules', [])
        if priority:
            rules = [r for r in rules if r.get('priority') == priority]
        if applies_to:
            rules = [r for r in rules if applies_to.lower() in r.get('applies_to', '').lower() or applies_to.lower() in r.get('rule', '').lower()]
        return rules

    def get_experiences(self, experiment=None):
        """Get recorded experiences, optionally filtered by experiment name."""
        skb = self._skb_cache or {}
        exps = skb.get('experiences', [])
        if experiment:
            return next((e for e in exps if experiment.lower() in e.get('experiment', '').lower()), None)
        return exps

    def search_experiences(self, query: str = "", category: str = None, limit: int = 20):
        """Search experiences by query text (for agent tools)."""
        exps = self.get_experiences()
        if not query and not category:
            return exps[:limit]
        results = []
        for e in exps:
            e_text = json.dumps(e, ensure_ascii=False).lower()
            if query and query.lower() in e_text:
                results.append(e)
            elif category and category.lower() in e.get('experiment', '').lower():
                results.append(e)
        return results[:limit]

    def get_troubleshooting_cases(self, query: str = None):
        """Get troubleshooting cases, optionally filtered by symptom."""
        skb = self._skb_cache or {}
        cases = skb.get('troubleshooting_cases', [])
        if not cases:
            # try loading from external file
            cases_path = os.path.join(self.folder, 'troubleshooting_cases.json')
            if os.path.exists(cases_path):
                try:
                    with open(cases_path, 'r', encoding='utf-8') as f:
                        cases = json.load(f)
                        if isinstance(cases, dict):
                            cases = cases.get('cases', [])
                except Exception:
                    cases = []
        if query:
            ql = query.lower()
            return [c for c in cases if ql in json.dumps(c, ensure_ascii=False).lower()][:20]
        return cases[:20]

    def detect_view_mode(self, prompt_text):
        """Detect whether a device is in user view < > or system view [ ].
        
        Args:
            prompt_text: the terminal prompt string from the device
        Returns:
            'user_view' if < > prompt, 'system_view' if [ ] prompt, 'unknown' otherwise
        """
        if not prompt_text:
            return 'unknown'
        pt = prompt_text.strip()
        # User view: <Hostname> or <Hostname-something>
        if '<' in pt and '>' in pt:
            return 'user_view'
        # System view: [Hostname] or [Hostname-something]
        if '[' in pt and ']' in pt:
            return 'system_view'
        return 'unknown'

    def reload_structured_kb(self):
        """Force reload the structured KB from disk."""
        self._skb_cache = self.load_structured_kb()
        return bool(self._skb_cache)

    def _guess_cat(self, cmd):
        if cmd.startswith('display'): return 'display'
        if cmd.startswith(('ping', 'tracert', 'telnet')): return 'verify'
        config_prefixes = (
            'system-view', 'interface', 'ip ', 'undo ', 'shutdown', 'sysname',
            'save', 'quit', 'return', 'vlan', 'port ', 'stp ', 'vrrp ',
            'ospf', 'bgp', 'dhcp', 'ip pool', 'ip route', 'capwap', 'wlan',
            'security-profile', 'ssid-profile', 'vap-profile', 'ap-id', 'ap-mac',
            'ap-name', 'ap-group', 'eth-trunk', 'mode lacp', 'mode manual',
            'firewall', 'security-policy', 'rule ', 'aaa', 'manager-user',
            'authentication-profile', 'mac-authen', 'dot1x', 'radius-server',
            'traffic-filter', 'traffic-policy', 'qos', 'snmp', 'ntp',
            'user-interface', 'authentication', 'idle-timeout',
            'silent-interface', 'default-route', 'import-route',
            'network ', 'area ', 'router-id', 'revision-level', 'region-name',
            'instance ', 'active region', 'gateway-list', 'dns-list',
            'dhcp select', 'service-vlan', 'set priority', 'add interface',
        )
        if cmd.startswith(config_prefixes): return 'config'
        return 'other'

    # ==================== AUTO KNOWLEDGE RECORDING ====================

    _CONFIG_INTENT_PATTERNS = [
        ('AC/WLAN配置', ['capwap', 'wlan', 'security-profile', 'ssid-profile', 'vap-profile', 'ap-id', 'ap-mac', 'ap-name', 'ap-group', 'radio ', 'service-vlan']),
        ('OSPF路由配置', ['ospf ', 'router-id', 'area 0', 'network 192', 'silent-interface', 'default-route-advertise', 'import-route']),
        ('VRRP冗余配置', ['vrrp vrid']),
        ('MSTP生成树配置', ['stp mode mstp', 'stp region', 'region-name', 'revision-level', 'instance ', 'active region', 'stp instance', 'stp enable']),
        ('DHCP配置', ['dhcp enable', 'ip pool', 'gateway-list', 'dns-list', 'dhcp select', 'dhcp snooping']),
        ('VLAN配置', ['vlan batch', 'vlan ', 'port link-type', 'port default vlan', 'port trunk allow', 'port trunk pvid']),
        ('防火墙安全策略', ['security-policy', 'rule name', 'firewall zone', 'set priority', 'add interface', 'service-manage']),
        ('链路聚合配置', ['eth-trunk', 'mode lacp-static', 'mode manual load-balance', 'max active-linknumber', 'least active-linknumber', 'load-balance']),
        ('静态路由配置', ['ip route-static']),
        ('端口安全配置', ['dot1x enable', 'mac-authen', 'authentication-profile', 'port-security']),
        ('STP配置', ['stp mode', 'stp enable', 'stp priority', 'stp root']),
        ('NAT配置', ['nat server', 'nat outbound', 'nat static', 'nat address-group']),
        ('ACL/QoS配置', ['acl ', 'rule permit', 'rule deny', 'traffic-filter', 'traffic-policy', 'qos']),
        ('Telnet/SSH远程管理', ['telnet server', 'stelnet server', 'user-interface', 'authentication-mode', 'idle-timeout']),
        ('SNMP网管配置', ['snmp-agent', 'snmp']),
        ('NTP时钟配置', ['ntp-service', 'ntp']),
    ]

    _TRIVIAL_COMMANDS = {
        'undo terminal monitor', 'undo t m', 'undo info-center enable',
        'system-view', 'return', 'quit', 'save', 'y', '',
    }

    def _detect_config_intent(self, commands):
        intent_scores = {}
        for cmd in commands:
            cmd_lower = cmd.strip().lower()
            if cmd_lower in self._TRIVIAL_COMMANDS:
                continue
            for intent_name, keywords in self._CONFIG_INTENT_PATTERNS:
                score = sum(1 for kw in keywords if kw in cmd_lower)
                if score > 0:
                    intent_scores[intent_name] = intent_scores.get(intent_name, 0) + score
        if not intent_scores:
            return None, 0
        best = max(intent_scores.items(), key=lambda x: x[1])
        return best[0], best[1]

    def _auto_record_knowledge(self, device_path, device_type, command_results):
        """Simplified: record config methods only (v2.4)."""
        try:
            cmds = [r.get("command", "").strip() for r in command_results if r.get("command", "").strip()]
            meaningful = [c for c in cmds if c and c.lower() not in {
                "undo terminal monitor", "undo t m", "undo info-center enable",
                "system-view", "return", "quit", "save", "y", ""}]
            if len(meaningful) < 3:
                return
            
            intent, _ = self._detect_config_intent(meaningful)
            if not intent:
                return
            
            self.record_experience({
                "experiment": intent,
                "device_type": device_type or "unknown",
                "commands": meaningful[:30],
                "lessons": [],
            })
        except Exception as e:
            __import__("logging").getLogger(__name__).error("Auto knowledge failed: %s", e)

def _build_interface_map(dev_element):
    """Build a mapping from interface index to real interface name (e.g. GE0/0/1).
    Huawei devices typically start port numbering from 1, not 0."""
    ifaces = []
    type_counter = {}
    for slot in dev_element.iter('slot'):
        for iface in slot.iter('interface'):
            name = iface.get('interfacename', '')
            count = int(iface.get('count', 0))
            for i in range(count):
                idx = type_counter.get(name, 0) + 1
                ifaces.append(f'{name}0/0/{idx}')
                type_counter[name] = idx
    return {idx: name for idx, name in enumerate(ifaces)}

def _resolve_interface(iface_map, index):
    """Resolve an interface index to its name, fallback to IndexN."""
    try:
        return iface_map.get(int(index), f'Index{index}')
    except (ValueError, TypeError):
        return f'Index{index}'

