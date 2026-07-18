import select
# -*- coding: utf-8 -*-
import os, json, re, secrets, socket, time, threading, hashlib, tempfile, logging
from functools import wraps
from collections import defaultdict, deque
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, make_response
from flask_socketio import SocketIO, emit, join_room
from agent.bootstrap import init_agent_runtime, get_agent_runtime
from device_manager import dm
from services import kb, topo_engine, config_methods
from heartbeat import HeartbeatMonitor

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('ENSP_SECRET_KEY', secrets.token_hex(32))
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['KB_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kb')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
socketio = SocketIO(app, cors_allowed_origins=os.environ.get('CORS_ORIGINS', 'http://127.0.0.1:5000'), async_mode='threading')

API_KEY = os.environ.get('ENSP_API_KEY', '')
MAX_SCAN_RANGE = 1000
logger = logging.getLogger(__name__)

def _check_api_key(provided_key):
    if not API_KEY:
        return True
    return bool(provided_key) and secrets.compare_digest(str(provided_key), API_KEY)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key')
        if not _check_api_key(key):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

class RateLimiter:
    def __init__(self, max_calls=120, window=60):
        self._max_calls = max_calls
        self._window = window
        self._calls = defaultdict(list)
        self._lock = threading.Lock()
        self._last_cleanup = time.time()
    def check(self, key):
        now = time.time()
        with self._lock:
            if now - self._last_cleanup > self._window * 2:
                cleaned = {k: [t for t in v if now - t < self._window]
                               for k, v in self._calls.items()
                               if any(now - t < self._window for t in v)}
                self._calls = defaultdict(list, cleaned)
                self._last_cleanup = now
            self._calls[key] = [t for t in self._calls.get(key, []) if now - t < self._window]
            if len(self._calls[key]) >= self._max_calls:
                return False
            self._calls[key].append(now)
            return True

rate_limiter = RateLimiter()

def rate_limit(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.remote_addr or 'unknown'
        if not rate_limiter.check(key):
            return jsonify({'success': False, 'error': 'Rate limit exceeded'}), 429
        return f(*args, **kwargs)
    return decorated

devices = {}
device_names = {}
device_types = {}
topo_names = {}
# Auto-naming counters per device role
device_role_counters = {}
device_role_lock = threading.Lock()
devices_lock = threading.Lock()
name_lock = threading.Lock()
HEARTBEAT_INTERVAL = int(os.environ.get('HEARTBEAT_INTERVAL', '30'))
HEARTBEAT_RECONNECT_ATTEMPTS = int(os.environ.get('HEARTBEAT_RECONNECT', '3'))
MAX_TOPO_NODES = 500
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['KB_FOLDER'], exist_ok=True)
COMMAND_CATALOG = {
    "display version": {"description": "显示设备版本信息，识别型号和OS版本", "category": "display", "tags": ["info","version"], "risk": "safe", "output_hint": "设备型号、VRP版本、发布时间", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display current-configuration": {"description": "显示完整运行配置，用于审计和备份", "category": "display", "tags": ["config","audit"], "risk": "safe", "output_hint": "完整运行配置", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display current-configuration | include sysname": {"description": "提取设备主机名", "category": "display", "tags": ["hostname"], "risk": "safe", "output_hint": "sysname <名称>", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display ip interface brief": {"description": "显示所有接口IP地址和状态摘要", "category": "display", "tags": ["interface","ip","status"], "risk": "safe", "output_hint": "接口名、IP、掩码、状态", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display interface brief": {"description": "显示接口简要状态（不含IP）", "category": "display", "tags": ["interface","status"], "risk": "safe", "output_hint": "接口名、MTU、状态", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display interface": {"description": "显示接口详细统计信息", "category": "display", "tags": ["interface","detail"], "risk": "safe", "output_hint": "收发包数、错误数、带宽", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display ip routing-table": {"description": "显示IP路由表", "category": "display", "tags": ["routing","table"], "risk": "safe", "output_hint": "目的网络、下一跳、出接口", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display arp": {"description": "显示ARP缓存表，查看IP-MAC映射", "category": "display", "tags": ["arp","mac"], "risk": "safe", "output_hint": "IP、MAC、接口、老化时间", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display mac-address": {"description": "显示MAC地址表", "category": "display", "tags": ["mac","switching"], "risk": "safe", "output_hint": "MAC、VLAN、接口、类型", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display vlan": {"description": "显示VLAN配置信息", "category": "display", "tags": ["vlan"], "risk": "safe", "output_hint": "VLAN ID、名称、成员端口", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display stp brief": {"description": "显示生成树协议摘要", "category": "display", "tags": ["stp","spanning-tree"], "risk": "safe", "output_hint": "端口角色、状态、开销", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display cpu-usage": {"description": "显示CPU利用率", "category": "diagnostic", "tags": ["cpu","performance"], "risk": "safe", "output_hint": "CPU使用率百分比", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display memory-usage": {"description": "显示内存利用率", "category": "diagnostic", "tags": ["memory","performance"], "risk": "safe", "output_hint": "内存总量、已用、剩余", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display logbuffer": {"description": "显示日志缓冲区，排查故障", "category": "diagnostic", "tags": ["log","troubleshooting"], "risk": "safe", "output_hint": "时间戳、模块、事件", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display temperature all": {"description": "显示温度传感器信息", "category": "diagnostic", "tags": ["hardware","temperature"], "risk": "safe", "output_hint": "温度、阈值、状态", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display power": {"description": "显示电源状态", "category": "diagnostic", "tags": ["hardware","power"], "risk": "safe", "output_hint": "电源编号、状态", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display fan": {"description": "显示风扇状态", "category": "diagnostic", "tags": ["hardware","fan"], "risk": "safe", "output_hint": "风扇转速、状态", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "ping": {"description": "测试网络连通性", "category": "verify", "tags": ["connectivity","icmp"], "risk": "safe", "output_hint": "ICMP响应、延迟、丢包", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "tracert": {"description": "追踪数据包路径", "category": "verify", "tags": ["traceroute","routing"], "risk": "safe", "output_hint": "逐跳IP、延迟", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "system-view": {"description": "进入系统视图（配置前提）", "category": "config", "tags": ["view","admin"], "risk": "safe", "output_hint": "提示符变为[设备名]", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "interface": {"description": "进入接口视图进行配置", "category": "config", "tags": ["interface","config"], "risk": "low", "output_hint": "提示符变为[设备接口]", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "undo shutdown": {"description": "启用接口", "category": "config", "tags": ["interface","enable"], "risk": "low", "output_hint": "接口UP", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "shutdown": {"description": "关闭接口", "category": "config", "tags": ["interface","disable"], "risk": "medium", "output_hint": "接口DOWN", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "ip address": {"description": "为接口配置IP地址", "category": "config", "tags": ["ip","interface"], "risk": "low", "output_hint": "接口获得IP", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "quit": {"description": "退出当前视图", "category": "config", "tags": ["navigation"], "risk": "safe", "output_hint": "返回上级视图", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "return": {"description": "直接返回用户视图", "category": "config", "tags": ["navigation"], "risk": "safe", "output_hint": "提示符变为<设备名>", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "save": {"description": "保存配置到启动文件", "category": "config", "tags": ["save","persist"], "risk": "low", "output_hint": "确认保存", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "reboot": {"description": "重启设备（危险）", "category": "config", "tags": ["reboot","danger"], "risk": "high", "output_hint": "设备重启，连接断开", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "reset saved-configuration": {"description": "清除启动配置（危险，恢复出厂设置）", "category": "config", "tags": ["reset","danger"], "risk": "high", "output_hint": "确认操作", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display device": {"description": "显示设备基本信息（型号、槽位、状态）", "category": "display", "tags": ["hardware","device"], "risk": "safe", "output_hint": "设备型号、槽位、状态", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display clock": {"description": "显示系统时间和时区", "category": "display", "tags": ["time","clock"], "risk": "safe", "output_hint": "日期时间、时区", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display ip interface": {"description": "显示接口详细IP信息", "category": "display", "tags": ["interface","ip","detail"], "risk": "safe", "output_hint": "接口IP、掩码、MTU、状态", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display ip routing-table statistics": {"description": "显示路由表统计信息", "category": "display", "tags": ["routing","statistics"], "risk": "safe", "output_hint": "路由条目数、协议分布", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display static-route": {"description": "显示静态路由配置", "category": "display", "tags": ["routing","static"], "risk": "safe", "output_hint": "目的网络、下一跳、优先级", "huawei": False, "h3c": True, "cisco": False, "juniper": False},
    "display acl all": {"description": "显示所有ACL规则", "category": "display", "tags": ["acl","security","filter"], "risk": "safe", "output_hint": "ACL编号、规则、动作", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display users": {"description": "显示当前登录用户", "category": "display", "tags": ["user","session"], "risk": "safe", "output_hint": "用户、终端、登录时间", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display user-interface": {"description": "显示用户界面配置", "category": "display", "tags": ["user","interface","console"], "risk": "safe", "output_hint": "控制台、VTY配置", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display startup": {"description": "显示启动文件信息", "category": "display", "tags": ["startup","boot"], "risk": "safe", "output_hint": "启动配置、系统软件版本", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display logfile": {"description": "显示日志文件信息", "category": "display", "tags": ["log","file"], "risk": "safe", "output_hint": "日志文件名、大小", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display trapbuffer": {"description": "显示告警缓冲区", "category": "display", "tags": ["trap","alarm","buffer"], "risk": "safe", "output_hint": "告警时间、类型、描述", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display local-user": {"description": "显示本地用户配置", "category": "display", "tags": ["user","aaa","security"], "risk": "safe", "output_hint": "用户名、权限、状态", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display aaa": {"description": "显示AAA认证授权信息", "category": "display", "tags": ["aaa","security","auth"], "risk": "safe", "output_hint": "认证方式、在线用户", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display timezone": {"description": "显示时区配置", "category": "display", "tags": ["time","timezone"], "risk": "safe", "output_hint": "当前时区", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display license": {"description": "显示License信息", "category": "display", "tags": ["license","authorization"], "risk": "safe", "output_hint": "授权状态、到期时间", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display resource": {"description": "显示资源使用情况", "category": "display", "tags": ["resource","usage"], "risk": "safe", "output_hint": "CPU/内存/会话使用率", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display version brief": {"description": "显示简要版本信息", "category": "display", "tags": ["version","brief"], "risk": "safe", "output_hint": "版本号、发布时间", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display cpu-usage history 1": {"description": "显示CPU使用率历史记录", "category": "display", "tags": ["cpu","history","performance"], "risk": "safe", "output_hint": "历史CPU使用率曲线图", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display memory statistics": {"description": "显示详细内存统计", "category": "display", "tags": ["memory","statistics"], "risk": "safe", "output_hint": "内存分页统计", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display terminal monitor": {"description": "显示终端监控状态", "category": "display", "tags": ["terminal","monitor"], "risk": "safe", "output_hint": "终端监控开关状态", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display info-center": {"description": "显示信息中心配置", "category": "display", "tags": ["info-center","log"], "risk": "safe", "output_hint": "日志模块、输出通道", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display ntp-status": {"description": "显示NTP同步状态", "category": "display", "tags": ["ntp","time","sync"], "risk": "safe", "output_hint": "NTP服务器、偏移量、同步状态", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display dns": {"description": "显示DNS配置", "category": "display", "tags": ["dns","config"], "risk": "safe", "output_hint": "DNS服务器地址", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display http-server info": {"description": "显示HTTP服务器信息", "category": "display", "tags": ["http","web","server"], "risk": "safe", "output_hint": "HTTP服务状态、端口", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display ssh server status": {"description": "显示SSH服务状态", "category": "display", "tags": ["ssh","security","server"], "risk": "safe", "output_hint": "SSH版本、端口、超时", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display telnet server status": {"description": "显示Telnet服务状态", "category": "display", "tags": ["telnet","server"], "risk": "safe", "output_hint": "Telnet端口、连接数", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display arp all": {"description": "显示所有ARP条目", "category": "display", "tags": ["arp","mac","neighbor"], "risk": "safe", "output_hint": "IP-MAC映射表", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display arp static": {"description": "显示静态ARP条目", "category": "display", "tags": ["arp","static"], "risk": "safe", "output_hint": "静态IP-MAC绑定", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display arp dynamic": {"description": "显示动态ARP条目", "category": "display", "tags": ["arp","dynamic"], "risk": "safe", "output_hint": "动态学习的IP-MAC映射", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display mac-address dynamic": {"description": "显示动态MAC地址表", "category": "display", "tags": ["mac","dynamic","switching"], "risk": "safe", "output_hint": "动态学习的MAC地址", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display mac-address static": {"description": "显示静态MAC地址表", "category": "display", "tags": ["mac","static","switching"], "risk": "safe", "output_hint": "静态MAC绑定", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display vlan brief": {"description": "显示VLAN简要信息", "category": "display", "tags": ["vlan","brief"], "risk": "safe", "output_hint": "VLAN列表、成员端口", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display port vlan": {"description": "显示端口VLAN配置", "category": "display", "tags": ["vlan","port","trunk","access"], "risk": "safe", "output_hint": "端口类型、PVID、VLAN列表", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display stp": {"description": "显示完整生成树信息", "category": "display", "tags": ["stp","spanning-tree","detail"], "risk": "safe", "output_hint": "根桥、端口角色、开销", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display current-configuration interface": {"description": "显示接口相关配置", "category": "display", "tags": ["config","interface"], "risk": "safe", "output_hint": "接口IP、VLAN、描述等配置", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display ospf peer brief": {"description": "显示OSPF邻居摘要", "category": "display", "tags": ["ospf","routing","neighbor"], "risk": "safe", "output_hint": "邻居ID、状态、区域", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display ospf interface brief": {"description": "显示OSPF接口摘要", "category": "display", "tags": ["ospf","routing","interface"], "risk": "safe", "output_hint": "接口、区域、开销", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display bgp peer": {"description": "显示BGP邻居信息", "category": "display", "tags": ["bgp","routing","peer"], "risk": "safe", "output_hint": "邻居IP、AS、状态", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display bgp routing-table": {"description": "显示BGP路由表", "category": "display", "tags": ["bgp","routing","table"], "risk": "safe", "output_hint": "BGP路由条目、下一跳", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display ip pool": {"description": "显示DHCP地址池", "category": "display", "tags": ["dhcp","pool","ip"], "risk": "safe", "output_hint": "地址池、已分配、可用", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display nat session": {"description": "显示NAT会话表", "category": "display", "tags": ["nat","session","translation"], "risk": "safe", "output_hint": "源/目的地址、转换地址", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display ipsec sa": {"description": "显示IPSec安全关联", "category": "display", "tags": ["ipsec","vpn","security"], "risk": "safe", "output_hint": "SA状态、加密算法、SPI", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display pki certificate": {"description": "显示PKI证书信息", "category": "display", "tags": ["pki","certificate","security"], "risk": "safe", "output_hint": "证书颁发者、有效期", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display storm suppression": {"description": "显示风暴抑制配置", "category": "display", "tags": ["storm","suppression","broadcast"], "risk": "safe", "output_hint": "广播/组播/未知单播抑制", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display cpu-defend": {"description": "显示CPU防攻击策略", "category": "display", "tags": ["cpu","defend","security"], "risk": "safe", "output_hint": "攻击类型、丢弃统计", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display device manuinfo": {"description": "显示设备制造信息", "category": "display", "tags": ["hardware","manufacture","info"], "risk": "safe", "output_hint": "序列号、MAC、生产日期", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display patch-information": {"description": "显示补丁信息", "category": "display", "tags": ["patch","software"], "risk": "safe", "output_hint": "已安装补丁列表", "huawei": True, "h3c": True, "cisco": False, "juniper": False},

}

# 将本模块维护的命令目录注入 knowledge 模块，供 kb.get_command_catalog() 使用。
# knowledge.py 的 COMMAND_CATALOG 初始为空（注释标明 'Will be set by app.py'），
# 此前缺失注入导致 /api/kb/catalog 始终返回空列表；现补回预期接线。
import knowledge as _knowledge_mod
_knowledge_mod.COMMAND_CATALOG = COMMAND_CATALOG

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

class TopologyEngine:
    def __init__(self):
        self.graph, self.nodes, self.links = {}, [], []
        self.lock = threading.Lock()

    def load(self, data):
        with self.lock:
            self.nodes = data.get('nodes', [])
            self.links = data.get('links', [])
            self.graph = {n.get('id', ''): {'info': n, 'neighbors': []} for n in self.nodes}
            for l in self.links:
                s, t = l.get('source', ''), l.get('target', '')
                if s in self.graph and t in self.graph:
                    self.graph[s]['neighbors'].append({'target': t, 'link': l})
                    self.graph[t]['neighbors'].append({'target': s, 'link': l})

    def get_neighbors(self, nid):
        with self.lock: return self.graph.get(nid, {}).get('neighbors', []) if nid in self.graph else []

    def find_path(self, start, end):
        with self.lock:
            if start not in self.graph or end not in self.graph: return None
            if start == end: return [start]
            visited = {start}
            queue = deque([[start]])
            while queue:
                path = queue.popleft()
                for nb in self.graph.get(path[-1], {}).get('neighbors', []):
                    n = nb['target']
                    if n == end: return path + [n]
                    if n not in visited:
                        visited.add(n)
                        queue.append(path + [n])
            return None

    def get_device_connections(self, nid):
        with self.lock:
            if nid not in self.graph: return []
            return [{'target': nb['target'], 'target_name': self.graph.get(nb['target'], {}).get('info', {}).get('name', nb['target']), 'link': nb['link']} for nb in self.graph[nid]['neighbors']]

    def get_summary(self):
        with self.lock:
            return {'node_count': len(self.nodes), 'link_count': len(self.links),
                    'nodes': [{'id': n.get('id'), 'name': n.get('name', n.get('id')), 'type': n.get('type', 'unknown')} for n in self.nodes],
                    'links': [{'source': l.get('source'), 'target': l.get('target'), 'source_interface': l.get('source_interface', ''), 'target_interface': l.get('target_interface', ''), 'line_type': l.get('line_type', 'Copper')} for l in self.links]}
heartbeat = HeartbeatMonitor(kb)
import heartbeat as _hb; _hb.socketio_ref = socketio

def _extract_topo_names(data):
    """Extract port→name mapping from topology data."""
    global topo_names
    mapping = {}
    for n in data.get('nodes', []):
        port = n.get('port', '')
        name = n.get('name', '')
        if port and name:
            try:
                mapping[int(port)] = name
            except (ValueError, TypeError):
                continue
    if mapping:
        topo_names = mapping
        for port_int, topo_name in mapping.items():
            dm.set_topo_name(port_int, topo_name)
            path = f'127.0.0.1:{port_int}'
            if dm.has(path):
                dm.set_name(path, topo_name)

# ==================== Agent Runtime v3.0 集成 ====================
try:
    _agent_runtime = init_agent_runtime(app, lambda p, c: send_command(p, c))
    logger.info('[App] Agent Runtime v3.0 集成成功')
except Exception as _agent_err:
    logger.warning(f'[App] Agent Runtime 加载失败，原有功能不受影响: {_agent_err}')


def _validate_port(p):
    try: return 1 <= int(p) <= 65535
    except (ValueError, TypeError): return False

def _validate_path(p):
    return bool(p and isinstance(p, str) and re.match(r'^127\.0\.0\.1:(\d{1,5})$', p) and 1 <= int(re.match(r'^127\.0\.0\.1:(\d{1,5})$', p).group(1)) <= 65535)

def _safe_error(e):
    msg = str(e)
    if len(msg) > 200: msg = msg[:200]
    logger.error('Error: %s', msg)
    return msg

def _detect_device_type(ver):
    if not ver: return "unknown"
    lo = ver.lower()
    if 'vrp' in lo or 'huawei' in lo: return 'huawei'
    if 'h3c' in lo or 'comware' in lo: return 'h3c'
    if 'cisco ios' in lo or 'cisco' in lo: return 'cisco'
    if 'junos' in lo or 'juniper' in lo: return 'juniper'
    return "unknown"

def _fetch_device_name(conn):
    """Fetch device name and type, auto-assign role-based name if sysname is generic."""
    try:
        r = conn.send_cmd('display version')
        if not r: return None, "unknown"
        dt = _detect_device_type(r)
        # Detect specific model from version output
        model = _detect_model(r)
        name = None
        if dt in ('huawei', 'h3c'):
            nr = conn.send_cmd('display current-configuration | include sysname')
            if nr and 'Unrecognized' not in nr and 'Error' not in nr:
                m = re.search(r'^sysname\s+(\S+)', nr, re.IGNORECASE | re.MULTILINE)
                if m:
                    sysname_val = m.group(1)
                    generic_names = ['Huawei', 'H3C', 'HUAWEI', 'h3c', 'huawei', 'sysname']
                    if sysname_val not in generic_names:
                        name = sysname_val
        # If sysname is generic, auto-assign a role-based name
        if not name and model:
            name = _auto_assign_role_name(model, conn.port)
        if not name:
            name = f'{dt.upper() if dt != "unknown" else "DEVICE"}-{conn.port}'
        return name, dt
    except Exception:
        return None, "unknown"


def _detect_model(ver):
    """Detect specific device model from display version output."""
    if not ver: return None
    patterns = [
        (r'(AC\d+\S*)', 'AC'),
        (r'(USG\d+\S*)', 'FW'),
        (r'(AR\d+\S*)', 'AR'),
        (r'(S\d{4}\S*)', 'SW'),
        (r'(CE\d+\S*)', 'CE'),
        (r'(NE\d+\S*)', 'NE'),
        (r'(AP\d+\S*)', 'AP'),
    ]
    for pattern, role in patterns:
        m = re.search(pattern, ver, re.IGNORECASE)
        if m:
            return {'role': role, 'model': m.group(1).strip()}
    return None


def _auto_assign_role_name(model_info, port):
    """Assign a role-based name like SW1, AC1, AR1, FW1 using per-role counters."""
    role = model_info['role']
    with device_role_lock:
        cnt = device_role_counters.get(role, 0) + 1
        device_role_counters[role] = cnt
    return f'{role}{cnt}'
def scan_ports(start=2000, end=2050):
    found = []
    for port in range(start, end + 1):
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            if s.connect_ex(('127.0.0.1', port)) == 0:
                found.append({'port': port, 'path': f'127.0.0.1:{port}'})
        except Exception: pass
        finally:
            if s:
                try: s.close()
                except OSError: pass
    return found

def scan_devices(start=2000, end=2050):
    """Scan for eNSP devices in port range. Delegates to DeviceManager."""
    return dm.scan_devices(start, end)

def connect_device(port):
    """Connect to eNSP device. Delegates to DeviceManager."""
    path = f'127.0.0.1:{port}'

    # Check if already connected via dm
    existing = dm.get(path)
    if existing:
        try:
            existing.sock.send(b'')
            return {'success': True, 'port': port, 'path': path,
                    'name': dm.get_name(path), 'device_type': dm.get_type(path),
                    'reconnected': False}
        except Exception:
            logger.info('Dead connection detected for %s, reconnecting', path)
            dm.remove(path)
            try: existing.close()
            except Exception: pass

    conn = None
    try:
        conn = TelnetConnection('127.0.0.1', port)
        conn.connect()
        conn.handle_firewall_login()
        try:
            conn.send_cmd('undo terminal monitor')
            time.sleep(0.1)
        except Exception:
            pass
        dm.set(path, conn)

        name, dt = _fetch_device_name(conn)
        topo_name = topo_names.get(port)
        if topo_name:
            dm.set_name(path, topo_name)
        elif name:
            dm.set_name(path, name)
        dm.set_type(path, dt)

        with heartbeat.reconnect_lock:
            heartbeat.reconnect_counts[path] = 0
        display = f'{dm.get_name(path)} ({dt.upper()})' if dt != 'unknown' else dm.get_name(path)
        return {'success': True, 'port': port, 'path': path,
                'name': dm.get_name(path), 'display_name': display, 'device_type': dt}
    except Exception as e:
        if conn:
            try: conn.close()
            except OSError: pass
        dm.remove(path)
        return {'success': False, 'error': 'Connection failed'}

def send_command(path, command):
    conn = dm.get(path)
    if not conn: return {'success': False, 'error': 'Device not connected'}
    cmd_lower = command.strip().lower()
    try:
        # Auto undo t m before first config command if not already done
        config_prefixes = ('system-view', 'interface ', 'vlan', 'ospf', 'vrrp', 'stp ',
            'dhcp', 'ip pool', 'ip route', 'firewall', 'capwap', 'wlan', 'sysname',
            'undo info', 'security-policy', 'aaa', 'manager-user', 'eth-trunk')
        if cmd_lower.startswith(config_prefixes) or cmd_lower in ('undo terminal monitor', 'undo t m'):
            # Check if undo t m already sent for this session
            _undo_key = f'_undo_tm_{path}'
            if not hasattr(send_command, '_undo_done'):
                send_command._undo_done = set()
            if _undo_key not in send_command._undo_done and cmd_lower not in ('undo terminal monitor', 'undo t m'):
                try:
                    conn.send_cmd('undo terminal monitor')
                    send_command._undo_done.add(_undo_key)
                    time.sleep(0.1)
                except Exception:
                    pass
            elif cmd_lower in ('undo terminal monitor', 'undo t m'):
                send_command._undo_done.add(_undo_key)
        # Use view_router for unified view classification
        _required_view = view_router.classify(command)

        def _exec_and_check():
            t = time.time()
            res = conn.send_cmd(command)
            el = round(time.time() - t, 3)
            _errs = ['Error:', 'Unrecognized command', 'Wrong parameter',
                     'Too many parameters', 'Ambiguous command', 'Incomplete command',
                     'Please renew the default configurations']
            ok = bool(res and not any(kw in res for kw in _errs))
            return res, el, ok

        result, elapsed, cmd_success = _exec_and_check()

        # View auto-correction via view_router (single retry)
        if not cmd_success:
            error_check = check_command_error(result or '')
            if error_check['errors']:
                view_before = view_router.detect_view(conn)
                corrected = view_router.ensure_view(conn, path, _required_view)
                if corrected:
                    result, elapsed, cmd_success = _exec_and_check()
                    logger.info('View auto-corrected for %s: %s -> retry cmd_success=%s',
                               path, view_before, cmd_success)

        dt = dm.get_type(path)
        kb.record_command(command, result, device_type=dt, device_path=path, success=cmd_success)
        return {'success': True, 'path': path, 'output': result, 'response_time': elapsed, 'cmd_success': cmd_success}
    except ConnectionError:
        dm.remove(path)
        dm.remove_name(path)
        return {'success': False, 'error': 'Connection lost, device disconnected'}
    except Exception as e:
        logger.error('Command failed for %s: %s', path, str(e)[:200])
        dt = dm.get_type(path)
        kb.record_command(command, 'Error', device_type=dt, device_path=path, success=False)
        return {'success': False, 'error': 'Command execution failed'}


# ==================== NEW FEATURES ====================



# ==================== CONTEXT-AWARE SUGGESTIONS ====================

def generate_lab_report(experiment_name=None, paths=None):
    """Generate a lab report from current experiment data.
    
    Args:
        experiment_name: name of the experiment
        paths: list of device paths to include (None = all connected)
    Returns:
        dict with report content
    """
    if paths is None:
        with devices_lock:
            paths = list(devices.keys())
    
    report = {
        'experiment': experiment_name or 'eNSP Lab Report',
        'generated_at': datetime.now().isoformat(),
        'devices': [],
        'summary': {},
        'knowledge_base': {}
    }
    
    # Collect device info
    total_cmds = 0
    total_success = 0
    total_failed = 0
    
    for path in sorted(paths):
        with name_lock:
            name = device_names.get(path, path)
            dt = device_types.get(path, 'unknown')
        
        # Get command history
        cmds = []
        gkb_path = os.path.join(app.config.get('KB_FOLDER', 'kb'), 'global_kb.json')
        try:
            with open(gkb_path, 'r', encoding='utf-8') as _f: gkb = json.load(_f)
            for c in gkb.get('commands', []):
                if path in c.get('devices_used', []):
                    cmds.append(c)
        except Exception:
            pass
        
        # Get device-specific history
        dkb_path = os.path.join(app.config.get('KB_FOLDER', 'kb'), 'devices_kb.json')
        dev_cmds = []
        try:
            with open(dkb_path, 'r', encoding='utf-8') as _f: dkb = json.load(_f)
            dev_data = dkb.get('devices', {}).get(path, {})
            dev_cmds = dev_data.get('executed_commands', [])
        except Exception:
            pass
        
        success_count = sum(1 for c in dev_cmds if c.get('success', True))
        failed_count = len(dev_cmds) - success_count
        total_cmds += len(dev_cmds)
        total_success += success_count
        total_failed += failed_count
        
        device_report = {
            'name': name,
            'type': dt,
            'path': path,
            'commands_executed': len(dev_cmds),
            'success': success_count,
            'failed': failed_count,
            'role': 'unknown',
            'completed_topics': [],
            'current_phase': 'unknown',
            'progress': '0/0',
            'command_list': [{'cmd': c.get('command',''), 'success': c.get('success',True)} for c in dev_cmds[-20:]]
        }
        report['devices'].append(device_report)
    
    # Summary
    report['summary'] = {
        'total_devices': len(paths),
        'total_commands': total_cmds,
        'total_success': total_success,
        'total_failed': total_failed,
        'success_rate': '%.1f%%' % (total_success / total_cmds * 100) if total_cmds > 0 else '0%'
    }
    
    # KB stats
    skb = kb._skb_cache or {}
    gkb_path = os.path.join(app.config.get('KB_FOLDER', 'kb'), 'global_kb.json')
    report['knowledge_base'] = {
        'structured_commands': sum(
            len(v.get('commands', [])) + sum(len(t.get('commands', [])) for t in v.get('topics', {}).values())
            for s in ['user_view_commands', 'system_view_commands']
            for k, v in skb.get(s, {}).items() if k != '_meta' and isinstance(v, dict)
        ),
        'experiences': len(skb.get('experiences', [])),
        'troubleshooting': len(skb.get('troubleshooting', {})),
        'best_practices': len(skb.get('best_practices', {}).get('command_rules', [])),
        'runtime_commands': 0
    }
    try:
        with open(gkb_path, 'r', encoding='utf-8') as _f: gkb = json.load(_f)
        report['knowledge_base']['runtime_commands'] = len(gkb.get('commands', []))
    except Exception:
        pass
    
    # Generate markdown report
    report['markdown'] = _format_report_markdown(report)
    
    return report

def _format_report_markdown(report):
    """Format report as markdown text."""
    md = []
    md.append('# ' + report['experiment'])
    md.append('')
    md.append('> Generated: ' + report['generated_at'])
    md.append('')
    
    # Summary
    md.append('## Summary')
    s = report['summary']
    md.append('| Metric | Value |')
    md.append('|--------|-------|')
    md.append('| Devices | ' + str(s['total_devices']) + ' |')
    md.append('| Commands Executed | ' + str(s['total_commands']) + ' |')
    md.append('| Success | ' + str(s['total_success']) + ' |')
    md.append('| Failed | ' + str(s['total_failed']) + ' |')
    md.append('| Success Rate | ' + s['success_rate'] + ' |')
    md.append('')
    
    # Devices
    md.append('## Device Details')
    md.append('')
    for dev in report['devices']:
        md.append('### ' + dev['name'] + ' (' + dev['type'].upper() + ')')
        md.append('')
        md.append('- Path: `' + dev['path'] + '`')
        md.append('- Role: ' + dev['role'])
        md.append('- Commands: ' + str(dev['commands_executed']) + ' (OK: ' + str(dev['success']) + ', Failed: ' + str(dev['failed']) + ')')
        md.append('- Progress: ' + dev['progress'])
        md.append('- Completed: ' + ', '.join(dev['completed_topics']) if dev['completed_topics'] else '- Completed: (none)')
        md.append('- Current Phase: ' + dev['current_phase'])
        md.append('')
        
        if dev['command_list']:
            md.append('Recent commands:')
            md.append('```')
            for c in dev['command_list']:
                status = 'OK' if c['success'] else 'FAIL'
                md.append('  [' + status + '] ' + c['cmd'])
            md.append('```')
        md.append('')
    
    # KB stats
    md.append('## Knowledge Base')
    kb = report['knowledge_base']
    md.append('| Category | Count |')
    md.append('|----------|-------|')
    md.append('| Structured Commands | ' + str(kb['structured_commands']) + ' |')
    md.append('| Experiments | ' + str(kb['experiences']) + ' |')
    md.append('| Troubleshooting | ' + str(kb['troubleshooting']) + ' |')
    md.append('| Best Practices | ' + str(kb['best_practices']) + ' |')
    md.append('| Runtime Commands | ' + str(kb['runtime_commands']) + ' |')
    md.append('')
    
    return chr(10).join(md)


def search_kb(query, limit=20):
    query_lower = query.lower()
    results = []
    skb = kb._skb_cache or {}
    for section in ['user_view_commands', 'system_view_commands']:
        for model, data in skb.get(section, {}).items():
            if model == '_meta':
                continue
            if isinstance(data, dict):
                for cmd in data.get('commands', []):
                    score = 0
                    if query_lower in cmd.get('cmd', '').lower(): score += 3
                    if query_lower in cmd.get('desc', '').lower(): score += 2
                    if query_lower in cmd.get('when', '').lower(): score += 1
                    if score > 0:
                        results.append({'type': 'command', 'section': section, 'model': model, 'score': score, **cmd})
                for topic_name, topic_data in data.get('topics', {}).items():
                    for cmd in topic_data.get('commands', []):
                        score = 0
                        if query_lower in cmd.get('cmd', '').lower(): score += 3
                        if query_lower in cmd.get('desc', '').lower(): score += 2
                        if query_lower in topic_name.lower(): score += 2
                        if score > 0:
                            results.append({'type': 'command', 'section': section, 'model': model, 'topic': topic_name, 'score': score, **cmd})
    for name, ts in skb.get('troubleshooting', {}).items():
        # troubleshooting 条目可能是 dict（含 symptom/cause/fix）或 list/str
        if isinstance(ts, dict):
            blob = ' '.join(str(ts.get(k, '')) for k in ('symptom', 'cause', 'fix', 'description'))
        elif isinstance(ts, (list, tuple)):
            blob = ' '.join(str(x) for x in ts)
        else:
            blob = str(ts)
        score = 0
        if query_lower in name.lower(): score += 3
        if query_lower in blob.lower(): score += 2
        if score > 0:
            results.append({'type': 'troubleshooting', 'name': name, 'score': score, 'content': ts})
    for exp in skb.get('experiences', []):
        score = 0
        if query_lower in exp.get('experiment', '').lower(): score += 3
        for lesson in exp.get('lessons_learned', []):
            if query_lower in lesson.lower(): score += 2
        if score > 0:
            results.append({'type': 'experience', 'score': score, **exp})
    results.sort(key=lambda x: x.get('score', 0), reverse=True)
    return results[:limit]

def get_command_help(cmd_name):
    cmd_lower = cmd_name.lower().strip()
    skb = kb._skb_cache or {}
    found = []
    for section in ['user_view_commands', 'system_view_commands']:
        for model, data in skb.get(section, {}).items():
            if model == '_meta':
                continue
            if isinstance(data, dict):
                for cmd in data.get('commands', []):
                    if cmd_lower in cmd.get('cmd', '').lower() or cmd_lower in cmd.get('short', '').lower():
                        found.append({'section': section, 'model': model, 'topic': 'general', **cmd})
                for topic_name, topic_data in data.get('topics', {}).items():
                    for cmd in topic_data.get('commands', []):
                        if cmd_lower in cmd.get('cmd', '').lower() or cmd_lower in cmd.get('short', '').lower():
                            found.append({'section': section, 'model': model, 'topic': topic_name, **cmd})
    return found

def send_command_batch(path, commands, wait=0.1, auto_view=True, auto_undo_tm=True):
    """Batch command execution with error-aware stopping and view routing.

    v2.4: Uses view_router for smart view switching and stops on first error.
    """
    conn = dm.get(path)
    if not conn:
        return {'success': False, 'error': 'Device not connected'}

    # Auto undo terminal monitor
    if auto_undo_tm:
        try:
            conn.send_cmd('undo terminal monitor')
            time.sleep(0.1)
        except Exception:
            pass

    results = []
    total = 0
    success_count = 0
    stopped_due_to_error = False

    for cmd in commands:
        if not cmd or not cmd.strip():
            continue
        cmd_stripped = cmd.strip()
        total += 1

        # Pre-command: route to correct view via view_router
        if auto_view:
            view_router.before_command(conn, path, cmd_stripped)

        # Execute
        t0 = time.time()
        try:
            output = conn.send_cmd(cmd_stripped)
            elapsed = round(time.time() - t0, 3)
        except ConnectionError:
            dm.remove(path)
            dm.remove_name(path)
            results.append({'command': cmd_stripped, 'success': False,
                            'output': 'Connection lost', 'response_time': 0})
            results.append({'command': '?', 'success': False,
                            'output': '=== BATCH STOPPED: Connection lost ===',
                            'response_time': 0})
            return {
                'success': False,
                'error': 'Connection lost',
                'path': path,
                'results': results,
                'total': total,
                'success_count': success_count,
                'stopped_due_to_error': True,
            }
        except Exception as e:
            results.append({'command': cmd_stripped, 'success': False,
                            'output': str(e)[:200], 'response_time': 0,
                            'cmd_success': False})
            results.append({'command': '?', 'success': False,
                            'output': f'=== BATCH STOPPED: Exception ({str(e)[:80]}) ===',
                            'response_time': 0})
            stopped_due_to_error = True
            break

        # Check for errors
        error_check = check_command_error(output)

        # Track view state
        cmd_lower = cmd_stripped.lower()
        if cmd_lower == 'system-view':
            view_router.update_view(path, 'system')
        elif cmd_lower in ('quit', 'return'):
            view_router.update_view(path, 'user')

        if error_check['success']:
            success_count += 1
            results.append({'command': cmd_stripped, 'success': True,
                            'output': output, 'response_time': elapsed,
                            'cmd_success': True})
        else:
            results.append({'command': cmd_stripped, 'success': False,
                            'output': output, 'response_time': elapsed,
                            'cmd_success': False,
                            'errors': error_check['errors']})
            # Stop on first error ? don't blindly continue
            results.append({'command': '?', 'success': False,
                            'output': f'=== BATCH STOPPED: command error ({", ".join(error_check["errors"])}) ===',
                            'response_time': 0})
            stopped_due_to_error = True
            break

        # Record to KB
        dt = dm.get_type(path)
        kb.record_command(cmd_stripped, output, device_type=dt, device_path=path,
                          success=error_check['success'])

        time.sleep(wait)

    if not results:
        return {'success': False, 'error': 'No commands executed'}

    return {
        'success': not stopped_due_to_error,
        'path': path,
        'results': results,
        'total': total,
        'success_count': success_count,
        'stopped_due_to_error': stopped_due_to_error,
    }

def send_command_to_group(paths, command):
    results = []
    for path in paths:
        r = send_command(path, command)
        results.append({'path': path, **r})
    return {'success': all(r.get('success') for r in results), 'total': len(results), 'results': results}

def disconnect_device(path):
    conn = dm.remove(path)
    # Cleanup _undo_done tracking
    if hasattr(send_command, "_undo_done"):
        send_command._undo_done.discard(f"_undo_tm_{path}")
    if not conn: return {'success': False, 'error': 'Not connected'}
    try:
        conn.close()
        dm.remove_name(path)
        return {'success': True, 'path': path}
    except Exception as e:
        logger.error('Disconnect failed for %s: %s', path, e)
        return {'success': False, 'error': 'Disconnect failed'}

def get_connected_devices():
    result = []
    for path in list(dm.list_all().keys()):
        port = int(path.split(':')[1])
        topo_name = topo_names.get(port)
        name = topo_name or dm.get_name(path)
        dt = dm.get_type(path)
        hb = heartbeat.get_status(path)
        display = f'{name} ({dt.upper()})' if name and dt != 'unknown' else name if name else path
        result.append({'port': port, 'path': path, 'name': name, 'display_name': display, 'device_type': dt, 'alive': hb.get('alive', False), 'response_time': hb.get('response_time', 0)})
    return result

def rename_device(path, name):
    if not dm.has(path):
        return {'success': False, 'error': 'Not connected'}
    dm.set_name(path, name)
    return {'success': True, 'path': path, 'name': name}

def _validate_topology(data):
    if not isinstance(data, dict): return False, 'Data must be a JSON object'
    nodes = data.get("nodes", [])
    links = data.get("links", [])
    if not isinstance(nodes, list) or not isinstance(links, list): return False, 'nodes and links must be arrays'
    if len(nodes) > MAX_TOPO_NODES: return False, f'Too many nodes (max {MAX_TOPO_NODES})'
    if len(links) > MAX_TOPO_NODES * 10: return False, 'Too many links'
    node_ids = set()
    for n in nodes:
        if not isinstance(n, dict) or not n.get('id'): return False, 'Each node must have an id'
        nid = str(n['id'])
        if nid in node_ids: return False, f'Duplicate node id: {nid}'
        node_ids.add(nid)
    for l in links:
        if not isinstance(l, dict): return False, 'Each link must be an object'
        if not l.get('source') or not l.get('target'): return False, 'Links must have source and target'
    return True, None


@app.route('/')
@require_auth
def index(): resp = make_response(render_template("index.html")); resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; resp.headers["Pragma"] = "no-cache"; return resp

@app.route('/api/devices/scan')
@require_auth
@rate_limit
def api_scan():
    s = request.args.get("start", 2000, type=int)
    e = request.args.get("end", 2050, type=int)
    if not (1 <= s <= e <= 65535): return jsonify({"success": False, "error": "Invalid range"}), 400
    if e - s + 1 > MAX_SCAN_RANGE: return jsonify({"success": False, "error": f"Range too large (max {MAX_SCAN_RANGE} ports)"}), 400
    return jsonify(scan_devices(s, e))

@app.route('/api/devices/connect', methods=['POST'])
@require_auth
@rate_limit
def api_connect():
    data = request.get_json(silent=True)
    if not data: return jsonify({"success": False}), 400
    port = data.get("port")
    if not _validate_port(port): return jsonify({"success": False, "error": "Invalid port"}), 400
    r = connect_device(int(port))
    if r["success"]: socketio.emit("device_connected", r)
    else: socketio.emit("device_error", {"port": port, "error": r["error"]})
    return jsonify(r)

@app.route('/api/devices/command', methods=['POST'])
@require_auth
@rate_limit
def api_command():
    data = request.get_json(silent=True)
    if not data: return jsonify({"success": False}), 400
    path, command = data.get("path"), data.get("command")
    if not _validate_path(path): return jsonify({"success": False, "error": "Invalid path"}), 400
    if not command or len(command) > 1024: return jsonify({"success": False, "error": "Invalid command"}), 400
    r = send_command(path, command.strip())
    if r["success"]: socketio.emit("device_output", {"path": path, "output": r["output"]})
    else: socketio.emit("device_error", {"path": path, "error": r["error"]})
    return jsonify(r)

@app.route('/api/devices/disconnect', methods=['POST'])
@require_auth
def api_disconnect():
    data = request.get_json(silent=True)
    if not data: return jsonify({"success": False}), 400
    path = data.get("path")
    if not _validate_path(path): return jsonify({"success": False, "error": "Invalid"}), 400
    r = disconnect_device(path)
    if r["success"]: socketio.emit("device_disconnected", {"path": path})
    return jsonify(r)

@app.route('/api/devices')
@require_auth
def api_get_devices(): return jsonify(get_connected_devices())

@app.route('/api/devices/rename', methods=['POST'])
@require_auth
def api_rename():
    data = request.get_json(silent=True)
    if not data: return jsonify({"success": False}), 400
    path, name = data.get("path"), data.get("name")
    if not _validate_path(path) or not name or len(name) > 128: return jsonify({"success": False}), 400
    r = rename_device(path, name.strip())
    if r["success"]: socketio.emit("device_renamed", {"path": path, "name": name.strip()})
    return jsonify(r)


@app.route('/api/devices/fetch-name', methods=['POST'])
@require_auth
@rate_limit
def api_fetch_name():
    data = request.get_json(silent=True)
    if not data: return jsonify({'success': False}), 400
    path = data.get('path')
    if not _validate_path(path): return jsonify({'success': False, 'error': 'Invalid path'}), 400
    conn = dm.get(path)
    if not conn: return jsonify({'success': False, 'error': 'Device not connected'}), 404
    name, dt = _fetch_device_name(conn)
    if name:
        dm.set_name(path, name)
        dm.set_type(path, dt)
        return jsonify({'success': True, 'path': path, 'name': name, 'device_type': dt})
    return jsonify({'success': False, 'error': 'Could not fetch name'})
@app.route('/api/devices/heartbeat')
@require_auth
def api_heartbeat(): return jsonify(heartbeat.get_status())

@app.route('/api/kb/commands')
@require_auth
def api_kb_commands():
    return jsonify(kb.get_global_commands(category=request.args.get("category"), device_type=request.args.get("device_type"), risk=request.args.get("risk"), limit=request.args.get("limit", 50, type=int)))

@app.route('/api/kb/catalog')
@require_auth
def api_kb_catalog():
    return jsonify(kb.get_command_catalog(category=request.args.get("category"), device_type=request.args.get("device_type"), risk=request.args.get("risk")))

@app.route('/api/kb/devices')
@require_auth
def api_kb_devices(): return jsonify(kb.get_device_history())

@app.route('/api/kb/devices/<path:p>')
@require_auth
def api_kb_device_detail(p): return jsonify(kb.get_device_history(p))

@app.route('/api/kb/capabilities')
@require_auth
def api_kb_capabilities():
    result = kb.get_device_capabilities(request.args.get("path"))
    skb = kb._skb_cache or {}
    result['_troubleshooting'] = skb.get('troubleshooting', {})
    return jsonify(result)

@app.route('/api/kb/stats')
@require_auth
def api_kb_stats():
    stats = kb.get_stats()
    skb = kb._skb_cache or {}
    uv = skb.get('user_view_commands', {})
    sv = skb.get('system_view_commands', {})
    stats['structured_kb'] = {
        'loaded': bool(skb),
        'user_view_models': [k for k in uv.keys() if k != '_meta'],
        'system_view_models': [k for k in sv.keys() if k != '_meta'],
        'troubleshooting_count': len(skb.get('troubleshooting', {})),
        'experiment_count': len(skb.get('experiences', [])),
        'best_practice_count': len(skb.get('best_practices', {}).get('command_rules', []))
    }
    return jsonify(stats)



@app.route('/api/kb/suggest')
@require_auth
def api_kb_suggest():
    """Get command suggestions for a device model."""
    model = request.args.get('model')
    if not model:
        return jsonify({'success': False, 'error': 'Missing model parameter'}), 400
    view_type = request.args.get('view_type')
    return jsonify(kb.suggest_commands(model, view_type=view_type))


@app.route('/api/kb/structured')
@require_auth
def api_kb_structured():
    """Get structured command knowledge base, optionally filtered."""
    view_type = request.args.get('view_type')
    model = request.args.get('model')
    return jsonify(kb.get_structured_kb(view_type=view_type, device_model=model))

@app.route('/api/kb/scan', methods=['POST'])
@require_auth
def api_kb_scan():
    """Scan a connected device and return command suggestions."""
    data = request.get_json(silent=True) or {}
    path = data.get('path')
    if not path:
        return jsonify({'success': False, 'error': 'Missing path parameter'}), 400
    return jsonify(kb.scan_device_commands(path))

@app.route('/api/kb/troubleshooting')
@require_auth
def api_kb_troubleshooting():
    """Get troubleshooting knowledge base."""
    skb = kb._skb_cache or {}
    symptom = request.args.get('symptom')
    if symptom:
        return jsonify(skb.get('troubleshooting', {}).get(symptom, {}))
    return jsonify(skb.get('troubleshooting', {}))

@app.route('/api/kb/experience', methods=['POST'])
@require_auth
def api_kb_record_experience():
    """Record an experience/lesson learned after an experiment.
    Body: {experiment, date, topology, features_implemented, new_commands_learned, lessons_learned, troubleshooting_cases}
    """
    data = request.get_json(silent=True)
    if not data or not data.get('experiment'):
        return jsonify({'success': False, 'error': 'Missing experiment name'}), 400
    return jsonify(kb.record_experience(data))

@app.route('/api/kb/experience', methods=['GET'])
@require_auth
def api_kb_get_experiences():
    """Get all recorded experiences, or filter by ?experiment=name."""
    return jsonify(kb.get_experiences(experiment=request.args.get('experiment')))

@app.route('/api/kb/auto-extract', methods=['POST'])
@require_auth
def api_kb_auto_extract():
    """Manually trigger auto knowledge extraction for a device's recent batch.
    Body: {path: device_path, commands_results: [{command, output, success}...]}
    If commands_results is omitted, uses the last batch from devices_kb.
    """
    data = request.get_json(silent=True) or {}
    path = data.get('path')
    if not path:
        return jsonify({'success': False, 'error': 'Missing path'}), 400
    cmd_results = data.get('commands_results')
    if not cmd_results:
        # Fallback: get recent commands from devices_kb
        with name_lock:
            dt = device_types.get(path, 'unknown')
        try:
            dkb = kb._load(kb.devices_path)
            dev = dkb.get('devices', {}).get(path, {})
            cmd_results = [
                {'command': c.get('command', ''), 'output': c.get('output_preview', ''), 'success': c.get('success', True)}
                for c in dev.get('executed_commands', [])[-20:]
            ]
        except Exception:
            cmd_results = []
    if not cmd_results:
        return jsonify({'success': False, 'error': 'No commands found'}), 400
    with name_lock:
        dt = device_types.get(path, 'unknown')
    kb._auto_record_knowledge(path, dt, cmd_results)
    return jsonify({'success': True, 'message': 'Auto knowledge extraction triggered', 'commands_analyzed': len(cmd_results)})

@app.route('/api/kb/best-practice', methods=['POST'])
@require_auth
def api_kb_record_best_practice():
    """Add a new best practice. Body: {rule, detail, priority, applies_to, ...}"""
    data = request.get_json(silent=True)
    if not data or not data.get('rule'):
        return jsonify({'success': False, 'error': 'Missing rule'}), 400
    return jsonify(kb.record_best_practice(data))

@app.route('/api/kb/best-practice', methods=['GET'])
@require_auth
def api_kb_get_best_practices():
    """Get best practices. Optional filters: ?priority=critical&applies_to=S5700"""
    return jsonify(kb.get_best_practices(
        priority=request.args.get('priority'),
        applies_to=request.args.get('applies_to')
    ))

@app.route('/api/kb/detect-view', methods=['POST'])
@require_auth
def api_kb_detect_view():
    """Detect device view mode from terminal prompt. Body: {prompt: '<LSW1>'}"""
    data = request.get_json(silent=True) or {}
    prompt = data.get('prompt', '')
    view = kb.detect_view_mode(prompt)
    return jsonify({'prompt': prompt, 'view': view, 'can_commands': 'display/save/ping/system-view' if view == 'user_view' else 'interface/vlan/ospf/vrrp...' if view == 'system_view' else 'unknown'})

@app.route('/api/kb/reload', methods=['POST'])
@require_auth
def api_kb_reload():
    """Force reload structured KB from disk (pick up external edits)."""
    ok = kb.reload_structured_kb()
    return jsonify({'success': ok, 'message': 'Structured KB reloaded from disk'})



# ==================== NEW API ROUTES ====================

@app.route('/api/devices/batch-command', methods=['POST'])
@require_auth
@rate_limit
def api_batch_command():
    data = request.get_json(silent=True)
    if not data: return jsonify({'success': False, 'error': 'No data'}), 400
    path = data.get('path')
    commands = data.get('commands', [])
    if not _validate_path(path): return jsonify({'success': False, 'error': 'Invalid path'}), 400
    if not commands or not isinstance(commands, list): return jsonify({'success': False, 'error': 'Commands must be a list'}), 400
    if len(commands) > 200: return jsonify({'success': False, 'error': 'Max 200 commands per batch'}), 400
    wait = data.get('wait', 0.1)
    auto_view = data.get('auto_view', True)
    auto_undo_tm = data.get('auto_undo_tm', True)
    r = send_command_batch(path, commands, wait=wait, auto_view=auto_view, auto_undo_tm=auto_undo_tm)
    return jsonify(r)

@app.route('/api/kb/search')
@require_auth
def api_kb_search():
    query = request.args.get('q', '')
    if not query: return jsonify({'success': False, 'error': 'Missing q'}), 400
    limit = int(request.args.get('limit', 20))
    return jsonify(search_kb(query, limit))

@app.route('/api/kb/help')
@require_auth
def api_kb_help():
    cmd = request.args.get('cmd', '')
    if not cmd: return jsonify({'success': False, 'error': 'Missing cmd'}), 400
    return jsonify(get_command_help(cmd))

@app.route('/api/devices/group-command', methods=['POST'])
@require_auth
@rate_limit
def api_group_command():
    data = request.get_json(silent=True)
    if not data: return jsonify({'success': False, 'error': 'No data'}), 400
    paths = data.get('paths', [])
    command = data.get('command', '')
    if not paths or not command: return jsonify({'success': False, 'error': 'Missing paths or command'}), 400
    for p in paths:
        if not _validate_path(p): return jsonify({'success': False, 'error': 'Invalid path'}), 400
    return jsonify(send_command_to_group(paths, command))




@app.route('/api/kb/lab-report', methods=['POST'])
@require_auth
def api_lab_report():
    """Generate a lab report from experiment data."""
    data = request.get_json(silent=True) or {}
    experiment_name = data.get('name', 'eNSP Lab Report')
    paths = data.get('paths')
    return jsonify(generate_lab_report(experiment_name, paths))

@app.route('/api/topology', methods=['GET'])
@require_auth
def api_get_topology(): return jsonify(topo_engine.get_summary())

@app.route('/api/topology', methods=['POST'])
@require_auth
def api_save_topology():
    data = request.get_json(silent=True)
    if not data: return jsonify({"success": False}), 400
    ok, err = _validate_topology(data)
    if not ok: return jsonify({"success": False, "error": err}), 400
    topo_engine.load(data)
    _extract_topo_names(data)
    socketio.emit("topology_updated", topo_engine.get_summary())
    return jsonify({"success": True, "topology": topo_engine.get_summary()})

@app.route('/api/topology/file', methods=['POST'])
@require_auth
def api_upload_topology():
    if "file" not in request.files: return jsonify({"success": False, "error": "No file"}), 400
    file = request.files["file"]
    if not file.filename: return jsonify({"success": False}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".json", ".txt", ".xml", ".cfg", ".topo", ".yml", ".yaml", ".csv", ".conf"}: return jsonify({"success": False, "error": "Type not allowed"}), 400
    try:
        content = file.read(10 * 1024 * 1024)
        raw = content.decode("utf-8", errors="ignore")
        data = None
        # Try JSON parsing first
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
        # Try XML parsing if JSON failed
        if data is None and ext in (".xml", ".topo", ".cfg"):
            try:
                import xml.etree.ElementTree as ET
                # Fix encoding=UNICODE declaration that confuses the parser
                raw = re.sub(r'encoding=".*?"', 'encoding="UTF-8"', raw, count=1)
                # Strip txttips section (may contain invalid XML chars in attributes)
                raw = re.sub(r'<txttips>.*?</txttips>', '', raw, flags=re.DOTALL)
                # Strip BOM if present
                raw = raw.lstrip('\ufeff')
                # Security: disable external entity processing to prevent XXE
                try:
                    parser = ET.XMLParser(resolve_entities=False)
                except TypeError:
                    parser = ET.XMLParser()
                root = ET.fromstring(raw, parser=parser)
                nodes, links = [], []
                node_ids = {}
                # Handle eNSP native format (<dev> tags)
                for dev in root.iter("dev"):
                    nid = dev.get("id", f"n{len(nodes)}")
                    nname = dev.get("name", nid)
                    model = dev.get("model", "unknown")
                    port = dev.get("com_port", "")
                    cx = float(dev.get("cx", 0))
                    cy = float(dev.get("cy", 0))
                    # Determine device type from model
                    if "Router" in model or model.startswith("AR"):
                        ntype = "router"
                    elif "STA" in model or "sta" in nname.lower():
                        ntype = "wireless"
                    elif "AC" in model or "AP" in model:
                        ntype = "wireless"
                    elif "Switch" in model or (model.startswith("S") and not model.startswith("STA")) or "SW" in nname.upper():
                        ntype = "switch"
                    elif "PC" in model or "PC" in nname.upper():
                        ntype = "pc"
                    elif "FW" in model or "USG" in model or "FW" in nname.upper():
                        ntype = "firewall"
                    else:
                        ntype = "unknown"
                    nodes.append({"id": nid, "name": nname, "type": ntype, "model": model, "port": port, "x": cx, "y": cy})
                    node_ids[nid] = nname
                # Build interface maps for each device
                dev_iface_maps = {}
                for dev in root.iter("dev"):
                    dev_id = dev.get("id", "")
                    dev_iface_maps[dev_id] = _build_interface_map(dev)
                # Handle eNSP native format (<line> tags with <interfacePair>)
                for line_elem in root.iter("line"):
                    src_id = line_elem.get("srcDeviceID", "")
                    dst_id = line_elem.get("destDeviceID", "")
                    if src_id and dst_id:
                        link = {"source": src_id, "target": dst_id}
                        # Extract interface pair info
                        for pair in line_elem.iter("interfacePair"):
                            src_idx = pair.get("srcIndex", "")
                            tar_idx = pair.get("tarIndex", "")
                            line_name = pair.get("lineName", "Copper")
                            src_iface = _resolve_interface(dev_iface_maps.get(src_id, {}), src_idx)
                            tar_iface = _resolve_interface(dev_iface_maps.get(dst_id, {}), tar_idx)
                            link["source_interface"] = src_iface
                            link["target_interface"] = tar_iface
                            link["line_type"] = line_name
                            break  # One interfacePair per line
                        links.append(link)
                # Fallback: generic XML tags
                if not nodes:
                    for elem in root.iter():
                        if elem.tag in ("node", "device", "router", "switch"):
                            nid = elem.get("id") or elem.get("name") or f"n{len(nodes)}"
                            ntype = elem.get("type", "unknown")
                            nname = elem.get("name", nid)
                            nodes.append({"id": nid, "name": nname, "type": ntype})
                        elif elem.tag in ("link", "connection", "edge"):
                            src = elem.get("source") or elem.get("from") or ""
                            tgt = elem.get("target") or elem.get("to") or ""
                            if src and tgt:
                                links.append({"source": src, "target": tgt})
                if nodes:
                    data = {"nodes": nodes, "links": links}
            except Exception:
                pass
        # Fallback: reject files that cannot be parsed as valid topology
        if data is None:
            return jsonify({"success": False, "error": "Unsupported file format or invalid topology data"}), 400
        ok, err = _validate_topology(data)
        if not ok: return jsonify({"success": False, "error": err}), 400
        topo_engine.load(data)
        _extract_topo_names(data)
        socketio.emit("topology_updated", topo_engine.get_summary())
        return jsonify({"success": True, "topology": topo_engine.get_summary()})
    except json.JSONDecodeError: return jsonify({"success": False, "error": "Invalid JSON"}), 400
    except Exception: return jsonify({"success": False, "error": "File processing failed"}), 500

@app.route('/api/topology/path')
@require_auth
def api_topo_path():
    s, e = request.args.get("start", ""), request.args.get("end", "")
    if not s or not e: return jsonify({"success": False}), 400
    p = topo_engine.find_path(s, e)
    if p is None: return jsonify({"success": False, "error": "No path"}), 404
    return jsonify({"path": p})

@app.route('/api/topology/device/<path:nid>')
@require_auth
def api_topo_device(nid): return jsonify({"node_id": nid, "connections": topo_engine.get_device_connections(nid)})

@app.route('/api/health')
@require_auth
def api_health(): return jsonify({"status": "ok", "devices": len(devices), "kb": kb.get_stats()})

# ==================== 配置方法库 API ====================
# config_methods 已通过 services.py 共享单例导入（与 MCP Server 共用同一实例）

@app.route('/api/config-methods/list')
@require_auth
def api_config_method_list():
    category = request.args.get('category', '')
    if category:
        methods = config_methods.list_methods(category)
    else:
        methods = config_methods.list_methods()
    return jsonify({
        "success": True,
        "count": len(methods),
        "methods": [{
            "id": m.get("id"),
            "name": m.get("name"),
            "category": m.get("category"),
            "device_types": m.get("device_types", []),
            "steps_count": len(m.get("steps", [])),
            "usage_count": m.get("usage_count", 0),
            "success_rate": m.get("success_rate", 0.0)
        } for m in methods]
    })

@app.route('/api/config-methods/get/<method_id>')
@require_auth
def api_config_method_get(method_id):
    method = config_methods.get_method(method_id)
    if method:
        return jsonify({"success": True, "method": method})
    return jsonify({"success": False, "error": "config method not found: " + method_id}), 404

@app.route('/api/config-methods/search')
@require_auth
def api_config_method_search():
    keyword = request.args.get('keyword', '')
    if not keyword:
        return jsonify({"success": False, "error": "keyword required"}), 400
    results = config_methods.search_methods(keyword)
    return jsonify({
        "success": True,
        "count": len(results),
        "methods": [{
            "id": m.get("id"),
            "name": m.get("name"),
            "category": m.get("category"),
            "description": m.get("description", ""),
            "steps_count": len(m.get("steps", []))
        } for m in results]
    })

@app.route('/api/config-methods/add', methods=['POST'])
@require_auth
def api_config_method_add():
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "data required"}), 400
    result = config_methods.add_method(data)
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 400

@app.route('/api/config-methods/steps/<method_id>')
@require_auth
def api_config_method_steps(method_id):
    method = config_methods.get_method(method_id)
    if not method:
        return jsonify({"success": False, "error": "config method not found: " + method_id}), 404
    steps = method.get('steps', [])
    commands = config_methods.get_method_commands(method_id)
    verification = config_methods.get_verification_commands(method_id)
    return jsonify({
        "success": True,
        "method_id": method_id,
        "name": method.get("name"),
        "steps": steps,
        "all_commands": commands,
        "verification_commands": verification
    })

@app.route('/api/config-methods/summary')
@require_auth
def api_config_method_summary():
    summary = config_methods.export_methods_summary()
    return jsonify({"success": True, "summary": summary})

@app.route('/api/config-methods/update/<method_id>', methods=['POST'])
@require_auth
def api_config_method_update(method_id):
    """更新配置方法"""
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "data required"}), 400
    result = config_methods.update_method(method_id, data)
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 400





# ==================== 设备验证与快照 API ====================

@app.route('/api/devices/verify', methods=['POST'])
@require_auth
def api_device_verify():
    """验证设备配置"""
    data = request.json
    if not data or 'path' not in data:
        return jsonify({'success': False, 'error': '缺少 path 参数'}), 400
    path = data['path']
    check_type = data.get('check_type', 'all')
    target_ip = data.get('target_ip')
    conn = devices.get(path)
    if not conn:
        return jsonify({'success': False, 'error': '设备未连接: ' + path}), 400
    try:
        from agent.verifier import SemanticVerifier
        verifier = SemanticVerifier(send_command)
        if check_type == 'all':
            results = verifier.verify_all(path, target_ip=target_ip)
        elif check_type == 'connectivity' and target_ip:
            results = [verifier.verify_connectivity(path, target_ip)]
        else:
            meth = getattr(verifier, f'verify_{check_type}', None)
            results = [meth(path)] if meth else verifier.verify_all(path, target_ip=target_ip)
        return jsonify({'success': True, 'checks': [r.to_dict() for r in results]})
    except Exception as e:
        logger.exception('[DeviceVerify] 验证失败')
        return jsonify({'success': False, 'error': str(e)}), 500



        logger.exception('[Snapshots] 获取快照列表失败')
        return jsonify([])


# ==================== 实验管理 API ====================

@app.route('/api/experiments', methods=['POST'])
@require_auth
def api_create_experiment():
    """创建新实验"""
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'success': False, 'error': '缺少实验名称'}), 400
    name = data['name']
    goal = data.get('goal', '')
    try:
        runtime = get_agent_runtime()
        if runtime:
            exp_data = {
                'name': name,
                'goal': goal,
                'devices': {},
                'links': [],
                'status': 'created',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'phase_history': []
            }
            exp_id = hashlib.md5((name + str(time.time())).encode()).hexdigest()[:12]
            if hasattr(runtime, 'experiments'):
                runtime.experiments[exp_id] = exp_data
            return jsonify({'success': True, 'experiment_id': exp_id, 'experiment': exp_data})
        if 'experiments' not in globals():
            globals()['experiments'] = {}
        experiments = globals()['experiments']
        exp_id = hashlib.md5((name + str(time.time())).encode()).hexdigest()[:12]
        exp_data = {
            'name': name, 'goal': goal, 'devices': {}, 'links': [],
            'status': 'created', 'created_at': datetime.now(timezone.utc).isoformat(),
            'phase_history': []
        }
        experiments[exp_id] = exp_data
        return jsonify({'success': True, 'experiment_id': exp_id, 'experiment': exp_data})
    except Exception as e:
        logger.exception('[Experiment] 创建实验失败')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/experiments', methods=['GET'])
@require_auth
def api_list_experiments():
    """列出所有实验"""
    try:
        runtime = get_agent_runtime()
        if runtime and hasattr(runtime, 'experiments'):
            return jsonify(runtime.experiments)
        experiments = globals().get('experiments', {})
        return jsonify(experiments)
    except Exception as e:
        logger.exception('[Experiment] 获取实验列表失败')
        return jsonify({})


@app.route('/api/experiments/<exp_id>', methods=['GET'])
@require_auth
def api_get_experiment(exp_id):
    """获取实验详情"""
    try:
        runtime = get_agent_runtime()
        if runtime and hasattr(runtime, 'experiments') and exp_id in runtime.experiments:
            return jsonify(runtime.experiments[exp_id])
        experiments = globals().get('experiments', {})
        exp = experiments.get(exp_id)
        if exp:
            return jsonify(exp)
        return jsonify({'error': '实验未找到: ' + exp_id}), 404
    except Exception as e:
        logger.exception('[Experiment] 获取实验详情失败')
        return jsonify({'error': str(e)}), 500


@app.route('/api/experiments/<exp_id>/plan', methods=['POST'])
@require_auth
def api_experiment_plan(exp_id):
    """生成并执行实验计划"""
    try:
        runtime = get_agent_runtime()
        if not runtime:
            return jsonify({'success': False, 'error': 'Agent Runtime 未初始化'}), 500
        if not hasattr(runtime, 'experiments') or exp_id not in runtime.experiments:
            return jsonify({'success': False, 'error': '实验未找到'}), 404
        exp = runtime.experiments[exp_id]
        if hasattr(runtime, 'execute_plan'):
            result = runtime.execute_plan(exp)
            return jsonify({'success': True, 'result': result})
        phases = []
        for path, dev in exp.get('devices', {}).items():
            phases.append({
                'name': f"配置 {dev.get('name', path)}",
                'device_path': path,
                'status': 'pending'
            })
        if 'phase_history' not in exp:
            exp['phase_history'] = []
        exp['phase_history'].extend(phases)
        exp['status'] = 'planned'
        return jsonify({'success': True, 'phases': phases, 'experiment': exp})
    except Exception as e:
        logger.exception('[Experiment] 执行计划失败')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/experiments/<exp_id>/verify', methods=['POST'])
@require_auth
def api_experiment_verify(exp_id):
    """验证实验中的指定设备"""
    data = request.json
    path = data.get('path') if data else None
    if not path:
        return jsonify({'success': False, 'error': '缺少 path 参数'}), 400
    try:
        from agent.verifier import SemanticVerifier
        verifier = SemanticVerifier(send_command)
        results = verifier.verify_all(path)
        return jsonify({'success': True, 'checks': [r.to_dict() for r in results]})
    except Exception as e:
        logger.exception('[Experiment] 验证设备失败')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/experiments/dependency-graph', methods=['GET'])
@require_auth
def api_experiment_dependency_graph():
    """获取实验阶段依赖图"""
    try:
        runtime = get_agent_runtime()
        if runtime and hasattr(runtime, 'experiments'):
            graph = {'nodes': [], 'edges': []}
            for exp_id, exp in runtime.experiments.items():
                graph['nodes'].append({
                    'id': exp_id,
                    'name': exp.get('name', exp_id),
                    'status': exp.get('status', 'unknown')
                })
                phases = exp.get('phase_history', [])
                for i in range(1, len(phases)):
                    graph['edges'].append({
                        'source': f"{exp_id}_phase_{i-1}",
                        'target': f"{exp_id}_phase_{i}"
                    })
            return jsonify(graph)
        return jsonify({'nodes': [], 'edges': []})
    except Exception as e:
        logger.exception('[Experiment] 获取依赖图失败')
        return jsonify({'nodes': [], 'edges': []})


def _ws_check_auth():
    """Check API key for WebSocket connections. Returns True if auth OK."""
    if not API_KEY:
        return True
    from flask import request as flask_request
    key = flask_request.headers.get('X-API-Key', '')
    return _check_api_key(key)

def _ws_check_rate(sid):
    """Check rate limit for WebSocket connections. Returns True if OK."""
    return rate_limiter.check(f'ws:{sid}')

@socketio.on("connect")
def on_connect():
    if not _ws_check_auth():
        emit("device_error", {"error": "Unauthorized"}); return False
    logger.info("Client connected: %s", request.sid if hasattr(request, "sid") else "unknown")

@socketio.on("scan")
def on_scan(data):
    if not _ws_check_auth(): emit("device_error", {"error": "Unauthorized"}); return
    if not _ws_check_rate(request.sid): emit("device_error", {"error": "Rate limit exceeded"}); return
    s, e = data.get("start", 2000), data.get("end", 2050)
    if isinstance(s, int) and isinstance(e, int) and 1 <= s <= e <= 65535 and (e - s + 1) <= MAX_SCAN_RANGE:
        emit("scan_result", scan_devices(s, e))
    else:
        emit("scan_result", [])

@socketio.on("get_connected_devices")
def on_get_connected():
    if not _ws_check_auth(): emit("device_error", {"error": "Unauthorized"}); return
    emit("connected_devices_list", get_connected_devices())

@socketio.on("connect_device")
def on_connect_device(data):
    if not _ws_check_auth(): emit("device_error", {"error": "Unauthorized"}); return
    if not _ws_check_rate(request.sid): emit("device_error", {"error": "Rate limit exceeded"}); return
    port = data.get("port")
    if not _validate_port(port): emit("device_error", {"port": port, "error": "Invalid port"}); return
    r = connect_device(int(port))
    if r["success"]: emit("device_connected", r)
    else: emit("device_error", {"port": port, "error": r["error"]})

@socketio.on("send_command")
def on_send(data):
    if not _ws_check_auth(): emit("device_error", {"error": "Unauthorized"}); return
    if not _ws_check_rate(request.sid): emit("device_error", {"error": "Rate limit exceeded"}); return
    path, cmd = data.get("path"), data.get("command")
    if not _validate_path(path) or not cmd or len(cmd) > 1024: emit("device_error", {"path": path, "error": "Invalid"}); return
    r = send_command(path, cmd.strip())
    if r["success"]: emit("device_output", {"path": path, "output": r["output"]})
    else: emit("device_error", {"path": path, "error": r["error"]})

@socketio.on("disconnect_device")
def on_disconnect(data):
    if not _ws_check_auth(): emit("device_error", {"error": "Unauthorized"}); return
    path = data.get("path")
    if _validate_path(path) and disconnect_device(path)["success"]: emit("device_disconnected", {"path": path})

@socketio.on("rename_device")
def on_rename(data):
    if not _ws_check_auth(): emit("device_error", {"error": "Unauthorized"}); return
    path, name = data.get("path"), data.get("name", "")
    if _validate_path(path) and name and len(name) <= 128:
        r = rename_device(path, name.strip())
        if r["success"]: emit("device_renamed", {"path": path, "name": name.strip()})

@socketio.on("fetch_device_name")
def on_fetch_name(data):
    if not _ws_check_auth(): emit("device_error", {"error": "Unauthorized"}); return
    if not _ws_check_rate(request.sid): emit("device_error", {"error": "Rate limit exceeded"}); return
    path = data.get("path")
    if not _validate_path(path): emit("device_error", {"path": path, "error": "Invalid path"}); return
    conn = dm.get(path)
    if not conn: emit("device_error", {"path": path, "error": "Not connected"}); return
    name, dt = _fetch_device_name(conn)
    if name:
        dm.set_name(path, name)
        dm.set_type(path, dt)
        emit("device_renamed", {"path": path, "name": name})


if __name__ == "__main__":
    # Add file handler for debugging
    fh = logging.FileHandler('server_debug.log', encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    logging.getLogger().addHandler(fh)
    logging.getLogger().setLevel(logging.DEBUG)
    print("eNSP Server starting on http://127.0.0.1:5000")
    heartbeat.start()
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)
