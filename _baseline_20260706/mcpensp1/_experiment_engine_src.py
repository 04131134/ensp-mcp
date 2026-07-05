# -*- coding: utf-8 -*-
"""实验状态机与执行引擎（备份源文件）"""
from __future__ import annotations
import copy, json, os, re, time, threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
def _now_iso():
    return datetime.now(timezone.utc).isoformat()
@dataclass
class InterfaceState:
    name: str
    status: str = 'unknown'
    ip: str = ''
    mask: str = ''
    vlan: Optional[int] = None
    description: str = ''
    protocol: str = ''
    extra: Dict[str, Any] = field(default_factory=dict)
    def is_up(self):
        return self.status.lower() in {'up', 'administratively up'}
    def has_ip(self):
        return bool(self.ip)
    def to_dict(self):
        return asdict(self)
@dataclass
class DeviceState:
    path: str
    name: str
    device_type: str = 'unknown'
    model: str = ''
    version: str = ''
    connected: bool = False
    interfaces: Dict[str, InterfaceState] = field(default_factory=dict)
    protocols: Dict[str, Any] = field(default_factory=dict)
    routes: List[Dict[str, Any]] = field(default_factory=list)
    acls: List[Dict[str, Any]] = field(default_factory=list)
    last_verified_at: Optional[str] = None
    last_error: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    def get_interface(self, name: str):
        return self.interfaces.setdefault(name, InterfaceState(name=name))
    def update_interface(self, name: str, **kw: Any):
        iface = self.get_interface(name)
        for k, v in kw.items():
            if hasattr(iface, k):
                setattr(iface, k, v)
    def set_protocol(self, name: str, state: Any):
        self.protocols[name] = state
    def to_dict(self):
        data = asdict(self)
        data['interfaces'] = {k: v.to_dict() for k, v in self.interfaces.items()}
        return data
@dataclass
class ExperimentState:
    experiment_id: str
    name: str
    goal: str = ''
    devices: Dict[str, DeviceState] = field(default_factory=dict)
    links: List[Dict[str, Any]] = field(default_factory=list)
    topology: Dict[str, Any] = field(default_factory=dict)
    phase_history: List[Dict[str, Any]] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    def snapshot(self):
        data = {
            'experiment_id': self.experiment_id,
            'name': self.name,
            'goal': self.goal,
            'devices': {k: v.to_dict() for k, v in self.devices.items()},
            'links': self.links,
            'topology': self.topology,
            'phase_history': self.phase_history[-50:],
            'constraints': self.constraints,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }
        return copy.deepcopy(data)
class OutputParsers:
    @staticmethod
    def parse_ip_brief(output: str):
        result: Dict[str, Dict[str, str]] = {}
        for line in output.splitlines():
            line = line.strip()
            if not line or line.lower().startswith('interface'):
                continue
            parts = line.split()
            if len(parts) >= 2 and ('.' in parts[1] or '/' in parts[1]):
                result[parts[0]] = {'ip': parts[1], 'status': parts[-1]}
        return result
    @staticmethod
    def parse_vlan(output: str):
        vlans: List[Dict[str, Any]] = []
        vid = None
        ports: List[str] = []
        for line in output.splitlines():
            s = line.strip()
            m = re.match(r'^(\d+)\s', s)
            if m:
                if vid is not None:
                    vlans.append({'vlan_id': vid, 'ports': ports})
                vid = int(m.group(1))
                ports = [p.strip() for p in s[m.end():].split() if p.strip()]
            elif vid is not None and s:
                ports.extend([p.strip() for p in s.split() if p.strip()])
        if vid is not None:
            vlans.append({'vlan_id': vid, 'ports': ports})
        return vlans
    @staticmethod
    def parse_ospf_peer(output: str):
        peers: List[Dict[str, str]] = []
        for line in output.splitlines():
            s = line.strip()
            if not s or ('Peer' in s and 'Address' in s):
                continue
            parts = s.split()
            if len(parts) >= 4:
                peers.append({'area': parts[0], 'interface': parts[1], 'neighbor': parts[2], 'state': parts[3]})
        return peers
    @staticmethod
    def parse_route(output: str):
        routes: List[Dict[str, str]] = []
        for line in output.splitlines():
            s = line.strip()
            if not s:
                continue
            if re.match(r'^(Static|O_|O IA|S |D |B |ISIS|Ö±Á¬)', s):
                parts = s.split()
                if len(parts) >= 3:
                    routes.append({'proto': parts[0], 'destination': parts[1], 'nexthop': parts[2]})
        return routes
@dataclass
class Precondition:
    check_id: str
    description: str
    checker: Callable[[ExperimentState, Dict[str, Any]], Tuple[bool, str]]
class PreconditionRegistry:
    def __init__(self):
        self._checks: Dict[str, Precondition] = {}
    def register(self, check_id: str, description: str, checker: Callable[[ExperimentState, Dict[str, Any]], Tuple[bool, str]]):
        self._checks[check_id] = Precondition(check_id=check_id, description=description, checker=checker)
    def verify(self, experiment: ExperimentState, required_ids: List[str], context: Optional[Dict[str, Any]] = None):
        ctx = context or {}
        reasons = []
        for cid in required_ids:
            pre = self._checks.get(cid)
            if not pre:
                reasons.append(f'È±Ê§Ç°ÖÃÌõ¼þ¼ì²éÆ÷: {cid}')
                continue
            ok, r = pre.checker(experiment, ctx)
            if not ok:
                reasons.append(f'[{cid}] {r}')
        return (len(reasons)==0), reasons
@dataclass
class RecoveryAction:
    action_id: str
    description: str
    handler: Callable[['ExperimentEngine', Dict[str, Any]], Dict[str, Any]]
class RecoveryRegistry:
    def __init__(self):
        self._actions: Dict[str, RecoveryAction] = {}
    def register(self, action_id: str, description: str, handler: Callable[['ExperimentEngine', Dict[str, Any]], Dict[str, Any]]):
        self._actions[action_id] = RecoveryAction(action_id=action_id, description=description, handler=handler)
    def run(self, engine: 'ExperimentEngine', action_id: str, context: Dict[str, Any]):
        action = self._actions.get(action_id)
        if not action:
            return {'success': False, 'error': f'Î´×¢²áµÄ»Ö¸´²ßÂÔ: {action_id}'}
        return action.handler(engine, context)
    def suggest(self, error_signature: str):
        s = error_signature.lower()
        rec = []
        if 'unrecognized command' in s or 'unknown command' in s:
            rec.extend(['rollback_last', 'sync_view_state', 'retry_after_fix'])
        if 'does not exist' in s and 'vlan' in s:
            rec.extend(['ensure_vlan_created', 'retry_after_fix'])
        if 'does not exist' in s and 'interface' in s:
            rec.extend(['refresh_interface_state', 'correct_interface_name', 'retry_after_fix'])
        if 'neighbor' in s and 'ospf' in s:
            rec.extend(['check_ospf_consistency', 'refresh_protocol_state', 'retry_after_fix'])
        if 'timeout' in s:
            rec.extend(['wait_convergence', 'refresh_device_state', 'retry_after_fix'])
        if not rec:
            rec.append('collect_diagnostics')
        return list(dict.fromkeys(rec))
@dataclass
class CheckResult:
    check_name: str
    passed: bool
    detail: str
    evidence: Dict[str, Any] = field(default_factory=dict)
class VerificationEngine:
    def __init__(self, executor: Callable[[str, str], Dict[str, Any]]):
        self._executor = executor
    def _exec(self, path: str, cmd: str):
        r = self._executor(path, cmd)
        if isinstance(r, dict):
            return bool(r.get('success')), str(r.get('output', ''))
        return False, str(r)
    def run_checks(self, experiment: ExperimentState, path: str, checks: List[str], target_ip: Optional[str] = None):
        results: List[CheckResult] = []
        device = experiment.devices.get(path)
        if not device:
            return [CheckResult(check_name='device_lookup', passed=False, detail='Ä¿±êÉè±¸²»´æÔÚÓÚÊµÑé×´Ì¬ÖÐ')]
        if 'interface' in checks:
            ok, out = self._exec(path, 'display ip interface brief')
            mp = OutputParsers.parse_ip_brief(out)
            for n, info in mp.items():
                device.update_interface(n, ip=info.get('ip', ''), status=info.get('status', 'unknown'))
            results.append(CheckResult(check_name='interface', passed=any(i.is_up() for i in device.interfaces.values()), detail=f'ÒÑ½âÎö {len(mp)} ¸ö½Ó¿Ú', evidence={'interfaces': mp}))
        if 'ospf' in checks:
            ok, out = self._exec(path, 'display ospf peer brief')
            peers = OutputParsers.parse_ospf_peer(out)
            device.set_protocol('ospf_peers', peers)
            results.append(CheckResult(check_name='ospf', passed=bool(peers) and all(p.get('state','').lower()=='full' for p in peers), detail=f'ÁÚ¾ÓÊýÁ¿ {len(peers)}', evidence={'peers': peers}))
        if 'route' in checks:
            ok, out = self._exec(path, 'display ip routing-table')
            routes = OutputParsers.parse_route(out)
            device.routes = routes
            results.append(CheckResult(check_name='route', passed=bool(routes), detail=f'Â·ÓÉÊýÁ¿ {len(routes)}', evidence={'routes_sample': routes[:20]}))
        if 'reachability' in checks and target_ip:
            ok, out = self._exec(path, f'ping {target_ip}')
            passed = ('Reply' in out or 'reply' in out) and ('0.00%' in out or 'loss is 0' in out)
            results.append(CheckResult(check_name='reachability', passed=passed, detail=f'Ä¿±êµØÖ·={target_ip}', evidence={'output': out[:800]}))
        device.last_verified_at = _now_iso()
        device.last_error = None if all(r.passed for r in results) else '; '.join(r.detail for r in results if not r.passed)
        experiment.updated_at = _now_iso()
        return results
@dataclass
class ExperimentPhase:
    phase_id: str
    title: str
    description: str
    commands_provider: Callable[[ExperimentState, Dict[str, Any]], List[str]]
    target_devices: Callable[[ExperimentState, Dict[str, Any]], List[str]]
    required_preconditions: List[str]
    required_checks: List[str]
    optional: bool = False
    max_retries: int = 2
    recovery_hints: List[str] = field(default_factory=list)
class ExperimentPlanner:
    def __init__(self):
        self._phases: Dict[str, ExperimentPhase] = {}
    def register(self, phase: ExperimentPhase):
        self._phases[phase.phase_id] = phase
    def resolve(self, ordered_ids: List[str]):
        out = []
        for pid in ordered_ids:
            if pid not in self._phases:
                raise ValueError(f'Î´×¢²á½×¶Î: {pid}')
            out.append(self._phases[pid])
        return out
    def list_phases(self):
        return [{'phase_id': p.phase_id, 'title': p.title, 'description': p.description} for p in self._phases.values()]
class ExperimentEngine:
    def __init__(self, executor: Callable[[str, str], Dict[str, Any]], persist_dir: Optional[str] = None):
        self._executor = executor
        self._persist_dir = persist_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'experiments')
        os.makedirs(self._persist_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._experiments: Dict[str, ExperimentState] = {}
        self.preconditions = PreconditionRegistry()
        self.recoveries = RecoveryRegistry()
        self.verifier = VerificationEngine(executor)
        self.planner = ExperimentPlanner()
        self._register_defaults()
    def _register_defaults(self):
        reg = self.preconditions
        reg.register('connected', 'Éè±¸±ØÐë´¦ÓÚÒÑÁ¬½Ó×´Ì¬', lambda e, c: (True, '') if (e.devices.get(c.get('path','')) or DeviceState(path='', name='')).connected else (False, 'Éè±¸Î´Á¬½Ó'))
        reg.register('interface_ip_ready', 'ÖÁÉÙÒ»¸ö½Ó¿ÚÒÑÅäÖÃ IP', lambda e, c: (True, '') if any(i.has_ip() for i in (e.devices.get(c.get('path','')) or DeviceState(path='', name='')).interfaces.values()) else (False, 'È±ÉÙ½Ó¿Ú IP ÅäÖÃ'))
        reg.register('vlan_exists', 'Ä¿±ê VLAN ÒÑ´æÔÚ', lambda e, c: (True, '') if any(v.get('vlan_id')==c.get('vlan_id') for v in (e.devices.get(c.get('path','')) or DeviceState(path='', name='')).protocols.get('vlans', [])) else (False, 'Ä¿±ê VLAN Î´´´½¨'))
        reg.register('acl_direction_ready', 'ACL ÐèÃ÷È·½Ó¿ÚÓë·½Ïò', lambda e, c: (True, '') if c.get('interface') and c.get('direction') else (False, 'È±ÉÙ½Ó¿Ú»ò·½Ïò'))

        planner = self.planner
        planner.register(ExperimentPhase('base', '»ù´¡»·¾³×¼±¸', '½øÈëÏµÍ³ÊÓÍ¼²¢¹Ø±Õ¸ÉÈÅÊä³ö', lambda e, c: ['system-view', 'undo terminal monitor'], lambda e, c: [c['path']], ['connected'], []))
        planner.register(ExperimentPhase('interface', '½Ó¿ÚÓë IP ÅäÖÃ', 'ÅäÖÃ½Ó¿Ú IP ²¢È·±£½Ó¿ÚÔÚÏß', lambda e, c: [f"interface {c['interface']}", f"ip address {c['ip']} {c['mask']}", 'undo shutdown', 'quit'] if c.get('interface') and c.get('ip') and c.get('mask') else [], lambda e, c: [c['path']], ['connected'], ['interface']))
        planner.register(ExperimentPhase('ospf', 'OSPF Ð­ÒéÅäÖÃ', 'ÅäÖÃ OSPF ²¢Ð£ÑéÁÚ¾ÓÊÕÁ²', lambda e, c: [f"ospf {c.get('process_id', 1)}", f"area {c.get('area', 0)}"] + [f"network {n}" for n in c.get('networks', [])] + ['quit'], lambda e, c: c.get('paths', [c.get('path', '')]), ['connected', 'interface_ip_ready'], ['ospf']))
        planner.register(ExperimentPhase('acl', 'ACL ²ßÂÔÅäÖÃ', '°´½Ó¿Ú·½ÏòÏÂ·¢ ACL ²¢ÑéÖ¤ÃüÖÐ', lambda e, c: ([f"acl number {c['acl_number']}"] + list(c.get('rules', [])) + ['quit'] if c.get('acl_number') and c.get('rules') else []) + ([f"interface {c['interface']}", f"traffic-filter {c['direction']} acl {c['acl_number']}", 'quit'] if c.get('interface') and c.get('direction') and c.get('acl_number') else []), lambda e, c: [c['path']], ['connected', 'acl_direction_ready'], ['interface']))
        planner.register(ExperimentPhase('verify', '×ÛºÏÑéÖ¤', 'Ö´ÐÐÍ¨ÓÃ¼ì²éÓëÁ¬Í¨ÐÔ²âÊÔ', lambda e, c: [], lambda e, c: [c.get('path', '')], [], ['interface', 'route', 'reachability']))

        rec = self.recoveries
        rec.register('rollback_last', '»Ø¹öµ½ÉÏÒ»½×¶ÎÇ°ÖÃ¿ìÕÕ', lambda engine, ctx: engine.rollback((ctx.get('paths') or [ctx.get('path', '')])[0], 'rollback'))
        rec.register('refresh_interface_state', 'Ë¢ÐÂ½Ó¿Ú×´Ì¬', lambda engine, ctx: {'checks': [asdict(c) for c in engine.verifier.run_checks(engine.get_experiment(ctx['experiment_id']), ctx.get('path', ''), ['interface'])]})
        rec.register('check_ospf_consistency', 'Ð£Ñé OSPF Ò»ÖÂÐÔ', lambda engine, ctx: {'checks': [asdict(c) for p in ctx.get('paths', []) for c in engine.verifier.run_checks(engine.get_experiment(ctx['experiment_id']), p, ['ospf'])]})
        rec.register('collect_diagnostics', '²É¼¯Õï¶ÏÐÅÏ¢', lambda engine, ctx: {'diagnostics': {cmd: engine._command(ctx.get('path', ''), cmd)[1][:1500] for cmd in ['display current-configuration', 'display ip interface brief', 'display logbuffer']}})
    def _persist(self, experiment: ExperimentState):
        path = os.path.join(self._persist_dir, f'{experiment.experiment_id}.json')
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(experiment.snapshot(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    def create_experiment(self, experiment_id: str, name: str, goal: str = '', devices: Optional[List[Dict[str, Any]]] = None, topology: Optional[Dict[str, Any]] = None, constraints: Optional[List[str]] = None):
        with self._lock:
            state = ExperimentState(experiment_id=experiment_id, name=name, goal=goal, topology=topology or {}, constraints=constraints or [])
            for d in devices or []:
                state.devices[d['path']] = DeviceState(path=d['path'], name=d.get('name', d['path']), device_type=d.get('device_type', 'unknown'), model=d.get('model', ''), connected=bool(d.get('connected', False)))
            self._experiments[experiment_id] = state
            self._persist(state)
            return state
    def get_experiment(self, experiment_id: str):
        with self._lock:
            if experiment_id not in self._experiments:
                raise KeyError(f'ÊµÑé²»´æÔÚ: {experiment_id}')
            return self._experiments[experiment_id]
    def update_device(self, experiment_id: str, path: str, **kw: Any):
        experiment = self.get_experiment(experiment_id)
        device = experiment.devices.setdefault(path, DeviceState(path=path, name=path))
        for k, v in kw.items():
            if hasattr(device, k):
                setattr(device, k, v)
        experiment.updated_at = _now_iso()
        self._persist(experiment)
        return device
    def update_interface(self, experiment_id: str, path: str, interface: str, **kw: Any):
        experiment = self.get_experiment(experiment_id)
        device = experiment.devices.setdefault(path, DeviceState(path=path, name=path))
        iface = device.get_interface(interface)
        for k, v in kw.items():
            if hasattr(iface, k):
                setattr(iface, k, v)
        experiment.updated_at = _now_iso()
        self._persist(experiment)
        return iface
    def record_protocol_state(self, experiment_id: str, path: str, protocol: str, state: Any):
        experiment = self.get_experiment(experiment_id)
        device = experiment.devices.setdefault(path, DeviceState(path=path, name=path))
        device.set_protocol(protocol, state)
        experiment.updated_at = _now_iso()
        self._persist(experiment)
    def add_link(self, experiment_id: str, link: Dict[str, Any]):
        experiment = self.get_experiment(experiment_id)
        experiment.links.append(link)
        experiment.updated_at = _now_iso()
        self._persist(experiment)
    def _command(self, path: str, command: str):
        r = self._executor(path, command)
        if isinstance(r, dict):
            return bool(r.get('success')), str(r.get('output', ''))
        return False, str(r)
    def verify_device(self, experiment_id: str, path: str, checks: Optional[List[str]] = None, target_ip: Optional[str] = None):
        experiment = self.get_experiment(experiment_id)
        results = self.verifier.run_checks(experiment, path, checks or ['interface', 'route', 'reachability'], target_ip)
        self._persist(experiment)
        return results
    def rollback(self, path: str, snapshot_text: str):
        self._command(path, 'system-view')
        self._command(path, 'return')
        ok, out = self._command(path, 'reset saved-configuration')
        return {'success': ok, 'output': out}
    def execute_phase(self, experiment_id: str, phase_id: str, context: Dict[str, Any], auto_verify: bool = True, dry_run: bool = False):
        experiment = self.get_experiment(experiment_id)
        phase = self.planner.resolve([phase_id])[0]
        ok, reasons = self.preconditions.verify(experiment, phase.required_preconditions, context)
        if not ok:
            return {'success': False, 'error': 'Ç°ÖÃÌõ¼þ²»Âú×ã', 'reasons': reasons}
        targets = phase.target_devices(experiment, context)
        commands = phase.commands_provider(experiment, context)
        if dry_run:
            return {'success': True, 'phase_id': phase_id, 'targets': targets, 'commands': commands}
        executed = []
        for target in targets:
            for cmd in commands:
                ok, out = self._command(target, cmd)
                executed.append({'device': target, 'command': cmd, 'success': ok, 'output': out[:600]})
        ver = []
        if auto_verify and phase.required_checks:
            for target in targets:
                ver.extend([asdict(c) for c in self.verifier.run_checks(experiment, target, phase.required_checks, context.get('target_ip'))])
        experiment.phase_history.append({'phase_id': phase_id, 'context': context, 'targets': targets, 'commands': commands, 'executed': executed, 'verification': ver, 'timestamp': _now_iso()})
        experiment.updated_at = _now_iso()
        self._persist(experiment)
        return {'success': all(r.get('success', False) for r in executed), 'phase_id': phase_id, 'executed': executed, 'verification': ver}
    def execute_plan(self, experiment_id: str, ordered_phases: List[str], base_context: Dict[str, Any], auto_verify: bool = True, max_retries: int = 1):
        plan = {'experiment_id': experiment_id, 'phases': []}
        for pid in ordered_phases:
            attempt = 0
            phase_result = None
            while attempt <= max_retries:
                phase_result = self.execute_phase(experiment_id, pid, base_context, auto_verify=auto_verify)
                if phase_result.get('success'):
                    break
                attempt += 1
                sig = ' '.join([str(phase_result.get('error', ''))] + [str(x.get('output', '')) for x in phase_result.get('executed', []) if not x.get('success')] + [str(x.get('detail', '')) for x in phase_result.get('verification', []) if not x.get('passed')])
                phase_result['recovery_attempted'] = self.recoveries.suggest(sig)
                for act in phase_result['recovery_attempted']:
                    self.recoveries.run(self, act, {'experiment_id': experiment_id, 'path': base_context.get('path', ''), 'paths': base_context.get('paths', [])})
            if not phase_result.get('success'):
                return {'success': False, 'failed_phase': pid, 'last_phase_result': phase_result}
            plan['phases'].append(phase_result)
        plan['success'] = True
        return plan
    def list_experiments(self):
        with self._lock:
            return [{'experiment_id': e.experiment_id, 'name': e.name, 'goal': e.goal, 'updated_at': e.updated_at} for e in self._experiments.values()]
    def describe_phase(self, phase_id: str):
        phases = self.planner.list_phases()
        return next((p for p in phases if p['phase_id'] == phase_id), {'phase_id': phase_id, 'error': 'Î´ÕÒµ½½×¶Î'})
    def build_dependency_graph(self):
        graph = {p['phase_id']: [] for p in self.planner.list_phases()}
        if 'interface' in graph and 'ospf' in graph:
            graph['interface'].append('ospf')
        if 'ospf' in graph and 'verify' in graph:
            graph['ospf'].append('verify')
        if 'acl' in graph and 'verify' in graph:
            graph['acl'].append('verify')
        return graph
