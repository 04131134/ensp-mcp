import select
# -*- coding: utf-8 -*-
import os, json, re, secrets, socket, time, threading, hashlib, tempfile, logging
from functools import wraps
from collections import defaultdict, deque
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, make_response
from flask_socketio import SocketIO, emit, join_room

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
            gkb = self._gkb_cache or self._load(self.global_path)
            dkb = self._dkb_cache or self._load(self.devices_path)
            cmd_lower = command.strip().lower()
            parts = cmd_lower.split()
            base_cmd = parts[0] if parts else cmd_lower
            cat_entry = COMMAND_CATALOG.get(cmd_lower) or COMMAND_CATALOG.get(base_cmd)
            desc = cat_entry['description'] if cat_entry else ''
            cat = cat_entry['category'] if cat_entry else self._guess_cat(cmd_lower)
            risk = cat_entry['risk'] if cat_entry else 'unknown'
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
        """Record an experience/lesson learned after an experiment.
        
        Args:
            experience_data: dict with keys:
                - experiment: str (experiment name)
                - date: str (YYYY-MM-DD)
                - topology: str (topology description)
                - features_implemented: list[str]
                - new_commands_learned: list[dict with cmd, device, desc]
                - lessons_learned: list[str]
                - troubleshooting_cases: list[dict]
        Returns:
            dict with success status
        """
        try:
            skb = self._skb_cache or self.load_structured_kb()
            if not skb:
                return {'success': False, 'error': 'Structured KB not available'}
            
            experiences = skb.setdefault('experiences', [])
            
            # Check if experiment already exists, update it
            exp_name = experience_data.get('experiment', '')
            existing = next((i for i, e in enumerate(experiences) if e.get('experiment') == exp_name), None)
            
            if existing is not None:
                # Merge: append new commands, lessons, troubleshooting
                old = experiences[existing]
                old_cmds = {c.get('cmd') for c in old.get('new_commands_learned', [])}
                for cmd in experience_data.get('new_commands_learned', []):
                    if cmd.get('cmd') not in old_cmds:
                        old['new_commands_learned'].append(cmd)
                old_lessons = set(old.get('lessons_learned', []))
                for lesson in experience_data.get('lessons_learned', []):
                    if lesson not in old_lessons:
                        old['lessons_learned'].append(lesson)
                old_cases = {c.get('problem') for c in old.get('troubleshooting_cases', [])}
                for case in experience_data.get('troubleshooting_cases', []):
                    if case.get('problem') not in old_cases:
                        old['troubleshooting_cases'].append(case)
                old['date'] = experience_data.get('date', old.get('date', ''))
                experiences[existing] = old
            else:
                experiences.append(experience_data)
            
            # Update meta
            meta = skb.setdefault('meta', {})
            meta['experiment_count'] = len(experiences)
            meta['total_experiments_recorded'] = [e.get('experiment', '') for e in experiences]
            meta['last_updated'] = datetime.now().strftime('%Y-%m-%d')
            skb['meta'] = meta
            
            # Also add new commands to the structured command sections
            for cmd_entry in experience_data.get('new_commands_learned', []):
                device = cmd_entry.get('device', '')
                cmd = cmd_entry.get('cmd', '')
                desc = cmd_entry.get('desc', '')
                if not device or not cmd:
                    continue
                model_key = self._match_model(device)
                if model_key:
                    sv = skb.setdefault('system_view_commands', {})
                    model_section = sv.setdefault(model_key, {'description': f'{model_key} commands', 'topics': {}})
                    topics = model_section.setdefault('topics', {})
                    exp_topic = topics.setdefault('经验积累', {'commands': [], 'tips': []})
                    existing_cmds = {c.get('cmd') for c in exp_topic.get('commands', [])}
                    if cmd not in existing_cmds:
                        exp_topic['commands'].append({'cmd': cmd, 'desc': desc, 'source': exp_name})
            
            # Save to disk
            with open(self.structured_path, 'w', encoding='utf-8') as f:
                json.dump(skb, f, ensure_ascii=False, indent=2)
            self._skb_cache = skb
            
            return {
                'success': True,
                'experiment': exp_name,
                'total_experiences': len(experiences),
                'message': f'Experience recorded. Total experiences: {len(experiences)}'
            }
        except Exception as e:
            logger.error('Failed to record experience: %s', e)
            return {'success': False, 'error': str(e)}

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
        """???????????????????????
        ?????????????????????????????????"""
        try:
            meaningful = []
            for r in command_results:
                cmd = r.get('command', '').strip()
                if not cmd:
                    continue
                if cmd.lower() in self._TRIVIAL_COMMANDS:
                    continue
                meaningful.append(r)

            if len(meaningful) < 3:
                return

            all_cmds = [r['command'] for r in meaningful]
            intent, score = self._detect_config_intent(all_cmds)
            if not intent:
                return

            success_count = sum(1 for r in meaningful if r.get('success', False))
            success_rate = success_count / len(meaningful)
            if success_rate <= 0.5:
                return

            from datetime import datetime as _dt
            today = _dt.now().strftime('%Y%m%d')
            exp_name = f'????-{intent}-{device_type}-{today}'

            # ??????????
            success_cmds = [r for r in meaningful if r.get('success', False)]
            failed_cmds = [r for r in meaningful if not r.get('success', False)]

            # ?????????????????????????
            CMD_SEMANTICS = {
                'system-view': '??????',
                'interface': '??????',
                'vlan batch': '????VLAN',
                'vlan ': '??/??VLAN',
                'port link-type': '??????',
                'port default vlan': '??????VLAN',
                'port trunk allow': '??Trunk??VLAN',
                'port trunk pvid': '??Trunk PVID',
                'capwap': '??CAPWAP??',
                'wlan': '??WLAN??',
                'security-profile': '??????',
                'ssid-profile': '??SSID??',
                'vap-profile': '??VAP??',
                'ap-id': '??AP(?ID)',
                'ap-mac': '??AP(?MAC)',
                'ap-name': '??AP??',
                'ap-group': '??AP?',
                'radio ': '????',
                'service-vlan': '????VLAN',
                'dhcp enable': '??DHCP',
                'dhcp select': '??DHCP??',
                'ip pool': '?????',
                'gateway-list': '????',
                'dns-list': '??DNS',
                'ospf': '??OSPF??',
                'router-id': '????ID',
                'area ': '??OSPF??',
                'network ': '????',
                'vrrp vrid': '??VRRP',
                'stp mode': '??STP??',
                'stp enable': '??STP',
                'stp region': '??STP?',
                'region-name': '????',
                'revision-level': '?????',
                'instance ': '??????',
                'active region': '???',
                'eth-trunk': '??????',
                'mode lacp': '??LACP??',
                'ip route-static': '??????',
                'sysname': '??????',
                'save': '????',
                'display': '??/????',
                'ping': '?????',
                'authentication-profile': '??????',
                'mac-authen': '??MAC??',
                'dot1x': '??802.1X??',
                'aaa': '??AAA??',
                'manager-user': '???????',
                'firewall zone': '??????',
                'security-policy': '??????',
                'rule ': '??????',
                'ntp-service': '??NTP??',
                'snmp-agent': '??SNMP',
                'user-interface': '??????',
                'authentication-mode': '??????',
                'idle-timeout': '??????',
                'undo ': '????',
                'shutdown': '????',
                'undo shutdown': '????',
            }

            new_commands = []
            for idx, r in enumerate(success_cmds, 1):
                cmd = r.get('command', '').strip()
                cmd_lower = cmd.lower()
                desc = f'??{idx}'
                for keyword, sem in CMD_SEMANTICS.items():
                    if keyword in cmd_lower:
                        desc = sem
                        break
                new_commands.append({
                    'cmd': cmd,
                    'device': device_type,
                    'desc': desc,
                    'step': idx,
                })

            # ??????
            troubleshooting = []
            for r in failed_cmds:
                output = r.get('output', '') or ''
                error_line = ''
                for line in output.splitlines():
                    if 'Error' in line or 'Unrecognized' in line or 'Wrong' in line:
                        error_line = line.strip()
                        break
                troubleshooting.append({
                    'problem': r['command'] + ' ????',
                    'root_cause': error_line or '????',
                    'solution': '???????????????????????',
                    'diagnosis_cmd': 'display current-configuration | include ' + r['command'].split()[0]
                })

            # ??????????
            lessons = []
            lessons.append(f'{intent}?????{len(meaningful)}??????{success_count}?????{int(success_rate*100)}%')
            if success_rate == 1.0:
                lessons.append(f'{intent}?????{device_type}???????')
            else:
                lessons.append(f'{intent}?{len(failed_cmds)}??????????????????')

            # ??????????????
            cmd_sequence = [r['command'] for r in success_cmds]
            if any('system-view' in c.lower() for c in cmd_sequence):
                lessons.append('????????? -> ???? -> ??? -> ??')
            if device_type and 'ap' in device_type.lower():
                lessons.append('?AP???AC???AP?????????VLAN/IP???')
            if any('capwap' in c.lower() for c in cmd_sequence):
                lessons.append('CAPWAP?????AP????AP?????????????')
            if any('dhcp' in c.lower() for c in cmd_sequence):
                lessons.append('DHCP???????VLAN???????????????IP')

            # ?????????
            with name_lock:
                device_name = names.get(device_path, device_path)

            exp_data = {
                'experiment': exp_name,
                'date': _dt.now().strftime('%Y-%m-%d'),
                'topology': f'??: {device_name} ({device_type})',
                'features_implemented': [intent],
                'new_commands_learned': new_commands,
                'lessons_learned': lessons,
                'troubleshooting_cases': troubleshooting,
                'device_path': device_path,
                'device_name': device_name,
                'device_type': device_type,
                'command_count': len(meaningful),
                'success_rate': round(success_rate, 2),
            }

            result = self.record_experience(exp_data)
            if result.get('success'):
                logger.info('Auto-recorded knowledge: %s (%d cmds, %s)', exp_name, len(meaningful), device_name)
            else:
                logger.warning('Auto-record knowledge failed: %s', result.get('error', ''))

        except Exception as e:
            logger.error('Auto knowledge recording failed: %s', e)

    def get_config_guidance(self, topic):
        """??????????????????????????????
        ????????????AI agent???????????"""
        topic_lower = topic.lower()
        guidance = {
            'topic': topic,
            'related_experiences': [],
            'related_best_practices': [],
            'related_troubleshooting': [],
            'related_commands': [],
            'config_tips': [],
        }

        skb = self._skb_cache or self.load_structured_kb()
        if not skb:
            return guidance

        # ??????
        for exp in skb.get('experiences', []):
            exp_text = json.dumps(exp, ensure_ascii=False).lower()
            # ???????
            topic_words = topic_lower.split()
            match_score = sum(1 for w in topic_words if w in exp_text)
            if match_score > 0:
                guidance['related_experiences'].append({
                    'experiment': exp.get('experiment', ''),
                    'date': exp.get('date', ''),
                    'features': exp.get('features_implemented', []),
                    'commands': [c.get('cmd', '') for c in exp.get('new_commands_learned', [])[:15]],
                    'lessons': exp.get('lessons_learned', []),
                    'relevance': match_score,
                })

        # ?????? (best_practices.command_rules is a list of rules)
        bp_rules = skb.get('best_practices', {})
        if isinstance(bp_rules, dict):
            bp_list = bp_rules.get('command_rules', [])
        else:
            bp_list = bp_rules if isinstance(bp_rules, list) else []
        for bp in bp_list:
            bp_text = json.dumps(bp, ensure_ascii=False).lower()
            topic_words = topic_lower.split()
            if any(w in bp_text for w in topic_words):
                guidance['related_best_practices'].append(bp)

        # ?????? (troubleshooting is a dict keyed by problem name)
        for problem_name, tc_data in skb.get('troubleshooting', {}).items():
            tc_text = (problem_name + ' ' + json.dumps(tc_data, ensure_ascii=False)).lower()
            topic_words = topic_lower.split()
            if any(w in tc_text for w in topic_words):
                entry = dict(tc_data)
                entry['problem'] = problem_name
                guidance['related_troubleshooting'].append(entry)

        # ???KB???????????
        gkb = self._gkb_cache or {}
        for cmd, info in gkb.items():
            if cmd in ('last_updated', '_meta'):
                continue
            if not isinstance(info, dict):
                continue
            cmd_text = (cmd + ' ' + json.dumps(info, ensure_ascii=False)).lower()
            topic_words = topic_lower.split()
            if any(w in cmd_text for w in topic_words):
                guidance['related_commands'].append({
                    'cmd': cmd,
                    'desc': info.get('description', info.get('output_preview', ''))[:100],
                    'category': info.get('category', ''),
                    'devices': info.get('devices', []),
                    'usage_count': info.get('usage_count', 0),
                })

        # ??????
        intent, _ = self._detect_config_intent([topic])
        if intent:
            guidance['config_tips'].append(f'???????: {intent}')
        guidance['config_tips'].append('????????????????????')
        guidance['config_tips'].append('??????????????')
        guidance['config_tips'].append('?????????save??')

        # ??????
        guidance['related_experiences'].sort(key=lambda x: x.get('relevance', 0), reverse=True)

        return guidance


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


class HeartbeatMonitor:
    def __init__(self, kb_ref):
        self.kb = kb_ref
        self.status = {}
        self.lock = threading.Lock()
        self.running = False
        self.reconnect_counts = {}
        self.reconnect_lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.running: return
            self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            try: self._check_all()
            except Exception as e: logger.warning('[Heartbeat] %s', e)
            time.sleep(HEARTBEAT_INTERVAL)

    def _check_all(self):
        with devices_lock:
            current_devices = list(devices.keys())
        for path in current_devices:
            alive = self._ping(path)
            with self.lock:
                old = self.status.get(path, {}).get('alive')
                self.status[path] = {'alive': alive, 'last_check': self._now(), 'last_alive': self._now() if alive else self.status.get(path, {}).get('last_alive'), 'response_time': self.status.get(path, {}).get('response_time', 0)}
            if old is True and alive is False:
                with self.reconnect_lock:
                    self.reconnect_counts[path] = self.reconnect_counts.get(path, 0) + 1
                    count = self.reconnect_counts[path]
                if count <= HEARTBEAT_RECONNECT_ATTEMPTS:
                    self._try_reconnect(path)
                else:
                    with name_lock:
                        nm = device_names.get(path, path)
                    socketio.emit('heartbeat_status', {'path': path, 'alive': False, 'status': 'disconnected', 'message': f'{nm} 宸叉柇寮€'})
            elif old is False and alive is True:
                with self.reconnect_lock:
                    self.reconnect_counts[path] = 0
                with name_lock:
                    nm = device_names.get(path, path)
                socketio.emit('heartbeat_status', {'path': path, 'alive': True, 'status': 'reconnected', 'message': f'{nm} 已恢复'})
            else:
                socketio.emit('heartbeat_status', {'path': path, 'alive': alive, 'status': 'alive' if alive else 'unresponsive', 'response_time': self.status.get(path, {}).get('response_time', 0)})
        with self.lock:
            stale = [p for p in self.status if p not in devices]
            for p in stale: self.status.pop(p, None)
        with self.reconnect_lock:
            stale_rc = [p for p in self.reconnect_counts if p not in devices]
            for p in stale_rc: self.reconnect_counts.pop(p, None)

    def _ping(self, path):
        """Check device liveness by probing socket, without sending commands."""
        with devices_lock:
            conn = devices.get(path)
        if not conn or not conn.sock:
            return False
        try:
            t0 = time.time()
            import select  # already imported at top
            # Use select to check if socket is still alive (very fast)
            _, writable, errored = select.select([], [conn.sock], [conn.sock], 0.5)
            if errored:
                raise ConnectionError('Socket error')
            if not writable:
                raise ConnectionError('Socket not writable')
            with self.lock:
                self.status.setdefault(path, {})['response_time'] = round(time.time() - t0, 3)
            return True
        except Exception:
            try:
                port = int(path.split(':')[1])
                nc = TelnetConnection('127.0.0.1', port)
                nc.connect()
                with devices_lock:
                    old = devices.get(path)
                    if old:
                        try: old.close()
                        except OSError: pass
                    devices[path] = nc
                return True
            except Exception as e:
                logger.debug('Ping reconnect failed for %s: %s', path, e)
                return False
    def _try_reconnect(self, path):
        with devices_lock:
            if path not in devices: return
        nc = None
        try:
            port = int(path.split(':')[1])
            nc = TelnetConnection('127.0.0.1', port)
            nc.connect()
            with devices_lock:
                if path not in devices:
                    try: nc.close()
                    except OSError: pass
                    return
                old = devices.get(path)
                if old:
                    try: old.close()
                    except OSError: pass
                devices[path] = nc
            with name_lock:
                nm = device_names.get(path, path)
            socketio.emit('heartbeat_status', {'path': path, 'alive': True, 'status': 'reconnected', 'message': f'{nm} 已恢复愬姛'})
        except Exception as e:
            logger.error('Reconnect failed for %s: %s', path, e)
            if nc:
                try: nc.close()
                except OSError: pass

    def get_status(self, path=None):
        with self.lock: return self.status.get(path, {'alive': False}) if path else dict(self.status)

    def _now(self): return datetime.now(timezone.utc).isoformat()


class TelnetConnection:
    """Telnet connection using raw socket (eNSP compatible, no IAC negotiation)."""
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.sock = None
        self.lock = threading.Lock()

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((self.host, self.port))
        time.sleep(0.5)
        # Flush initial data
        self.sock.settimeout(0.5)
        try:
            while True:
                d = self.sock.recv(65536)
                if not d: break
        except (socket.timeout, OSError):
            pass
        self.sock.settimeout(10)
        # Send enter and flush prompt
        self.sock.send(b'\r\n')
        time.sleep(0.3)
        self._flush()
        return True

    def _flush(self):
        """Flush pending data from socket."""
        old_timeout = self.sock.gettimeout()
        self.sock.settimeout(0.5)
        try:
            while True:
                d = self.sock.recv(65536)
                if not d: break
        except (socket.timeout, OSError):
            pass
        self.sock.settimeout(old_timeout)

    def _strip_escape(self, data):
        """Remove ANSI/VT escape codes from data."""
        return re.sub(rb'\x1b\[[0-9;]*[A-Za-z]', b'', data)

    def send_cmd(self, cmd):
        MAX_RECV = 4 * 1024 * 1024
        with self.lock:
            if not self.sock:
                raise ConnectionError('Socket not connected')
            cmd_lower = cmd.strip().lower()
            is_display = cmd_lower.startswith('display') or cmd_lower.startswith('dir')
            is_diag = cmd_lower.startswith(('ping', 'tracert'))
            recv_timeout = 3 if is_display else (4 if is_diag else 1.5)
            # Flush pending data thoroughly
            self._flush()
            time.sleep(0.15)
            self._flush()
            # Send command
            self.sock.send(f'{cmd}\r\n'.encode())
            time.sleep(0.3 if is_display else 0.2)
            # Read response
            chunks = []
            total = 0
            deadline = time.time() + recv_timeout
            while time.time() < deadline:
                try:
                    self.sock.settimeout(0.1)
                    data = self.sock.recv(65536)
                    if data:
                        chunks.append(data)
                        total += len(data)
                        if total >= MAX_RECV:
                            break
                        deadline = time.time() + 0.5  # extend if still getting data
                except socket.timeout:
                    pass
                except OSError:
                    break
            self.sock.settimeout(10)
            output = b''.join(chunks)
            output = self._strip_escape(output).decode('gbk', errors='ignore')
            # Auto-handle [Y/N] prompts
            auto_yn = 0
            while auto_yn < 3:
                tail = output[-200:] if len(output) > 200 else output
                if re.search(r'\[Y/?N\]|\(Y/?N\)', tail):
                    self.sock.send(b'y')
                    time.sleep(0.3)
                    self.sock.send(b'\r\n')
                    time.sleep(0.5)
                    follow_deadline = time.time() + recv_timeout
                    while time.time() < follow_deadline:
                        try:
                            self.sock.settimeout(0.1)
                            c = self.sock.recv(65536)
                            if c:
                                chunks.append(c)
                                total += len(c)
                                if total >= MAX_RECV:
                                    break
                        except socket.timeout:
                            pass
                        except OSError:
                            break
                    self.sock.settimeout(10)
                    output = self._strip_escape(b''.join(chunks)).decode('gbk', errors='ignore')
                    auto_yn += 1
                else:
                    break
            return output

    def handle_firewall_login(self, username='admin', password='Admin@1234'):
        """Handle USG6000V firewall login flow."""
        if not self.sock:
            return False
        try:
            initial = ''
            for _attempt in range(3):
                self.sock.send(b'\r\n')
                time.sleep(2)
                try:
                    self.sock.settimeout(3)
                    initial = self.sock.recv(65536).decode('gbk', errors='ignore')
                except Exception:
                    initial = ''
                self.sock.settimeout(10)
                if 'Username' in initial or 'Login' in initial:
                    break
            else:
                return False
            # Send username
            self.sock.send((username + '\r\n').encode())
            time.sleep(2)
            try:
                self.sock.settimeout(3)
                resp = self.sock.recv(65536).decode('gbk', errors='ignore')
            except Exception:
                resp = ''
            self.sock.settimeout(10)
            if 'Password' not in resp:
                return False
            # Send password
            self.sock.send((password + '\r\n').encode())
            time.sleep(3)
            try:
                self.sock.settimeout(3)
                resp = self.sock.recv(65536).decode('gbk', errors='ignore')
            except Exception:
                resp = ''
            self.sock.settimeout(10)
            # Handle password change
            if '[Y/N]' in resp or '(Y/N)' in resp:
                self.sock.send(b'y')
                time.sleep(0.5)
                self.sock.send(b'\r\n')
                time.sleep(3)
                try:
                    self.sock.settimeout(3)
                    resp = self.sock.recv(65536).decode('gbk', errors='ignore')
                except Exception:
                    resp = ''
                self.sock.settimeout(10)
                if 'old password' in resp.lower():
                    # Send the OLD password (same as login password)
                    # New password (change to same for simplicity, or use a new one)
                    new_pw = password
                    self.sock.send((new_pw + '\r\n').encode())
                    time.sleep(2)
                    try: self.sock.recv(65536)
                    except Exception: pass
                    # Confirm new password
                    self.sock.send((new_pw + '\r\n').encode())
                    time.sleep(3)
                    try: self.sock.recv(65536)
                    except Exception: pass
                    self.sock.settimeout(10)
            # Flush
            time.sleep(1)
            self._flush()
            self.sock.send(b'\r\n')
            time.sleep(0.5)
            self._flush()
            return True
        except Exception as e:
            logger.debug('Firewall login failed: %s', e)
            return False

    def close(self):
        with self.lock:
            if self.sock:
                try: self.sock.close()
                except OSError: pass
                self.sock = None

kb = KnowledgeBase(app.config['KB_FOLDER'])
def _extract_topo_names(data):
    """Extract port鈫抧ame mapping from topology data."""
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
        # Update already-connected devices with topo names
        with name_lock:
            for port_int, topo_name in mapping.items():
                path = f'127.0.0.1:{port_int}'
                if path in devices:
                    device_names[path] = topo_name

topo_engine = TopologyEngine()
heartbeat = HeartbeatMonitor(kb)

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
    r = scan_ports(start, end)
    with name_lock:
        for d in r:
            port = d['port']
            topo_name = topo_names.get(port)
            d['name'] = topo_name or device_names.get(d['path'], d['path'])
            d['device_type'] = device_types.get(d['path'], 'unknown')
    return r

def connect_device(port):
    path = f'127.0.0.1:{port}'
    with devices_lock:
        if path in devices:
            return {'success': True, 'port': port, 'path': path, 'name': device_names.get(path, path), 'device_type': device_types.get(path, 'unknown'), 'reconnected': False}
    conn = None
    try:
        conn = TelnetConnection('127.0.0.1', port)
        conn.connect()
        # Try firewall login if device has login prompt
        conn.handle_firewall_login()
        # Auto undo terminal monitor on connect
        try:
            conn.send_cmd('undo terminal monitor')
            time.sleep(0.1)
        except Exception:
            pass
        with devices_lock:
            # Close old connection if exists (race condition fix)
            old_conn = devices.get(path)
            if old_conn:
                try: old_conn.close()
                except OSError: pass
            devices[path] = conn
        name, dt = _fetch_device_name(conn)
        topo_name = topo_names.get(port)
        with name_lock:
            if topo_name:
                device_names[path] = topo_name
            elif name:
                device_names[path] = name
            device_types[path] = dt
        with heartbeat.reconnect_lock:
            heartbeat.reconnect_counts[path] = 0
        display = f'{device_names.get(path, path)} ({dt.upper()})' if dt != 'unknown' else device_names.get(path, path)
        return {'success': True, 'port': port, 'path': path, 'name': device_names.get(path, path), 'display_name': display, 'device_type': dt}
    except Exception as e:
        if conn:
            try: conn.close()
            except OSError: pass
        with devices_lock:
            devices.pop(path, None)
        return {'success': False, 'error': 'Connection failed'}

BLOCKED_COMMANDS = {
    'reboot', 'reset saved-configuration', 'erase startup-configuration',
    'format', 'delete', 'reset arp', 'reset bgp', 'reset ospf',
    'set authentication password', 'set user-password',
    'undo save', 'startup saved-configuration',
    'reset interface', 'reset statistics',
    'reset ip routing-table', 'reset mac-address',
    'clear configuration', 'reset arp all',
}

BLOCKED_PREFIXES = (
    'reboot', 'reset ', 'erase ', 'format ', 'delete ',
    'set authentication', 'set user-password',
    'undo save', 'startup saved-configuration',
    'clear ', 'initialize',
)

def _is_blocked_command(cmd_lower):
    if cmd_lower in BLOCKED_COMMANDS:
        return True
    for prefix in BLOCKED_PREFIXES:
        if cmd_lower.startswith(prefix):
            return True
    return False

def send_command(path, command):
    with devices_lock:
        conn = devices.get(path)
    if not conn: return {'success': False, 'error': 'Device not connected'}
    cmd_lower = command.strip().lower()
    if _is_blocked_command(cmd_lower):
        return {'success': False, 'error': f'Blocked dangerous command: {cmd_lower}'}
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
        t0 = time.time()
        result = conn.send_cmd(command)
        elapsed = round(time.time() - t0, 3)
        with name_lock: dt = device_types.get(path, "unknown")
        cmd_success = bool(result and not result.strip().startswith('Error') and 'Unrecognized command' not in result)
        kb.record_command(command, result, device_type=dt, device_path=path, success=cmd_success)
        return {'success': True, 'path': path, 'output': result, 'response_time': elapsed, 'cmd_success': cmd_success}
    except ConnectionError:
        with devices_lock:
            devices.pop(path, None)
        with name_lock:
            device_names.pop(path, None)
            device_types.pop(path, None)
        return {'success': False, 'error': 'Connection lost, device disconnected'}
    except Exception as e:
        logger.error('Command failed for %s: %s', path, str(e)[:200])
        with name_lock: dt = device_types.get(path, "unknown")
        kb.record_command(command, 'Error', device_type=dt, device_path=path, success=False)
        return {'success': False, 'error': 'Command execution failed'}


# ==================== NEW FEATURES ====================



# ==================== CONTEXT-AWARE SUGGESTIONS ====================

def suggest_next_steps(path):
    """Analyze device command history and suggest next configuration steps.
    
    Returns:
        dict with current_phase, completed_topics, next_steps, missing_commands
    """
    with devices_lock:
        conn = devices.get(path)
    if not conn:
        return {'success': False, 'error': 'Device not connected'}
    
    with name_lock:
        device_name = device_names.get(path, path)
        device_type = device_types.get(path, 'unknown')
    
    # Get command history for this device from KB
    all_cmds = []
    gkb_path = os.path.join(app.config.get('KB_FOLDER', 'kb'), 'global_kb.json')
    try:
        with open(gkb_path, 'r', encoding='utf-8') as _f: gkb = json.load(_f)
        for c in gkb.get('commands', []):
            if path in c.get('devices_used', []):
                all_cmds.append(c.get('command', '').strip())
    except Exception:
        pass
    
    # Also get from devices_kb
    dkb_path = os.path.join(app.config.get('KB_FOLDER', 'kb'), 'devices_kb.json')
    try:
        with open(dkb_path, 'r', encoding='utf-8') as _f: dkb = json.load(_f)
        dev_data = dkb.get('devices', {}).get(path, {})
        for cmd_entry in dev_data.get('executed_commands', []):
            cmd = cmd_entry.get('command', '').strip()
            if cmd and cmd not in all_cmds:
                all_cmds.append(cmd)
    except Exception:
        pass
    
    executed_set = set(c.lower() for c in all_cmds)
    executed_text = ' '.join(all_cmds).lower()
    
    # Determine device role
    model_key = None
    dn = device_name.upper()
    if 'SW1' in dn or dn.endswith('-SW1'):
        model_key = 'SW1'
    elif 'SW2' in dn or dn.endswith('-SW2'):
        model_key = 'SW2'
    elif re.match(r'LSW[34]', dn):
        model_key = 'AGG'
    elif re.match(r'LSW[5-8]', dn):
        model_key = 'ACCESS'
    elif re.match(r'LSW[9]|LSW1[0]', dn):
        model_key = 'SERVER_SW'
    elif 'FW' in dn:
        model_key = 'FW'
    elif 'AR' in dn:
        model_key = 'AR'
    elif 'AC' in dn:
        model_key = 'AC'
    
    # Define phase checks per device role
    phases = {
        'SW1': [
            ('基础', ['undo t m', 'undo info-center', 'sysname']),
            ('VLAN', ['vlan batch']),
            ('MSTP', ['stp mode mstp', 'region-name', 'revision-level', 'instance', 'active region']),
            ('DHCP', ['dhcp enable', 'ip pool', 'gateway-list', 'dns-list']),
            ('VLANIF', ['interface vlanif', 'ip address', 'vrrp vrid', 'dhcp select global']),
            ('端口', ['port link-type', 'port trunk', 'port default']),
            ('LACP', ['interface eth-trunk', 'mode lacp-static', 'eth-trunk']),
            ('OSPF', ['ospf', 'router-id', 'area', 'network', 'silent-interface']),
            ('淇濆瓨', ['save']),
        ],
        'SW2': [
            ('基础', ['undo t m', 'undo info-center', 'sysname']),
            ('VLAN', ['vlan batch']),
            ('MSTP', ['stp mode mstp', 'region-name', 'revision-level', 'instance', 'active region']),
            ('DHCP', ['dhcp enable', 'ip pool', 'gateway-list', 'dns-list']),
            ('VLANIF', ['interface vlanif', 'ip address', 'vrrp vrid', 'dhcp select global']),
            ('端口', ['port link-type', 'port trunk', 'port default']),
            ('LACP', ['interface eth-trunk', 'mode lacp-static', 'eth-trunk']),
            ('OSPF', ['ospf', 'router-id', 'area', 'network', 'silent-interface']),
            ('淇濆瓨', ['save']),
        ],
        'AGG': [
            ('基础', ['undo t m', 'undo info-center', 'sysname']),
            ('VLAN', ['vlan batch']),
            ('MSTP', ['stp mode mstp', 'region-name', 'active region']),
            ('端口', ['port link-type', 'port trunk', 'port default']),
            ('淇濆瓨', ['save']),
        ],
        'ACCESS': [
            ('基础', ['undo t m', 'undo info-center', 'sysname']),
            ('VLAN', ['vlan batch']),
            ('端口', ['port link-type', 'port default']),
            ('淇濆瓨', ['save']),
        ],
        'FW': [
            ('基础', ['sysname']),
            ('鎺ュ彛', ['interface gigabitethernet', 'ip address', 'undo shutdown', 'service-manage ping permit']),
            ('鍖哄煙', ['firewall zone', 'set priority', 'add interface']),
            ('瀹夊叏绛栫暐', ['security-policy', 'rule name', 'source-zone', 'destination-zone', 'action permit']),
            ('路由', ['ospf', 'default-route-advertise', 'ip route-static']),
            ('淇濆瓨', ['save']),
        ],
        'AR': [
            ('基础', ['undo t m', 'sysname']),
            ('鎺ュ彛', ['interface gigabitethernet', 'ip address']),
            ('路由', ['ip route-static']),
            ('淇濆瓨', ['save']),
        ],
        'AC': [
            ('基础', ['undo t m', 'vlan batch', 'dhcp enable', 'capwap source']),
            ('WLAN', ['wlan', 'security-profile', 'ssid-profile', 'vap-profile']),
            ('AP娉ㄥ唽', ['ap-id', 'ap-mac', 'ap-name', 'ap-group']),
            ('端口', ['interface gigabitethernet', 'port link-type trunk']),
            ('淇濆瓨', ['save']),
        ],
    }
    
    role_phases = phases.get(model_key, phases.get('ACCESS', []))
    
    # Check each phase
    completed_topics = []
    next_steps = []
    current_phase = 'unknown'
    
    for phase_name, keywords in role_phases:
        matched = any(kw in executed_text for kw in keywords)
        if matched:
            completed_topics.append(phase_name)
        else:
            if not next_steps:
                current_phase = phase_name
                # Generate specific next commands
                next_steps = _generate_phase_commands(model_key, phase_name, device_name, executed_text)
            elif len(next_steps) < 5:
                next_steps.extend(_generate_phase_commands(model_key, phase_name, device_name, executed_text))
    
    if not next_steps:
        current_phase = '瀹屾垚'
    
    # Get model-specific commands from structured KB
    skb = kb._skb_cache or {}
    model_in_kb = kb._match_model(device_name) or kb._match_model(device_type)
    available_topics = []
    if model_in_kb:
        sv = skb.get('system_view_commands', {}).get(model_in_kb, {})
        for topic_name in sv.get('topics', {}).keys():
            available_topics.append(topic_name)
    
    return {
        'success': True,
        'path': path,
        'device_name': device_name,
        'device_type': device_type,
        'role': model_key or 'unknown',
        'total_commands_executed': len(all_cmds),
        'completed_topics': completed_topics,
        'current_phase': current_phase,
        'next_steps': next_steps[:10],
        'available_kb_topics': available_topics,
        'progress': '%d/%d' % (len(completed_topics), len(role_phases))
    }

def _generate_phase_commands(role, phase, device_name, executed_text):
    """Generate specific commands for a device role and phase."""
    cmds = []
    dn = device_name.upper()
    
    if phase == '基础':
        if role == 'AC':
            cmds = ['undo terminal monitor', 'system-view', 'undo info-center enable', 'sysname ' + device_name,
                    'vlan batch 100 to 101', 'dhcp enable',
                    'interface Vlanif100', 'ip address 192.168.100.1 255.255.255.0', 'dhcp select interface', 'quit',
                    'interface GigabitEthernet0/0/19', 'port link-type trunk', 'port trunk allow-pass vlan 2 to 4094', 'quit',
                    'capwap source interface Vlanif100']
        else:
            cmds = ['undo terminal monitor', 'system-view', 'undo info-center enable', 'sysname ' + device_name]
    elif phase == 'VLAN':
        if role in ('SW1', 'SW2'):
            cmds = ['vlan batch 10 20 30 40 100 to 101 520 to 521']
        elif role == 'AGG':
            cmds = ['vlan batch 10 20 30 40 100 to 101']
        elif role == 'ACCESS':
            # Determine VLAN based on device name (building)
            vlan_map = {'LSW5': '10', 'LSW6': '20', 'LSW7': '30', 'LSW8': '40'}
            vlan_id = vlan_map.get(dn[:4], '10')
            cmds = ['vlan batch ' + vlan_id]
    elif phase == 'MSTP':
        if role in ('SW1', 'SW2'):
            cmds = ['stp mode mstp', 'stp enable', 'stp region-configuration', 'region-name huawei', 'revision-level 16', 'instance 1 vlan 10 100 101', 'instance 2 vlan 20 30 40', 'active region-configuration']
            if role == 'SW1':
                cmds.extend(['stp instance 1 root primary', 'stp instance 2 root secondary'])
            else:
                cmds.extend(['stp instance 1 root secondary', 'stp instance 2 root primary'])
        elif role == 'AGG':
            cmds = ['stp mode mstp', 'stp enable', 'stp region-configuration', 'region-name huawei', 'revision-level 16', 'instance 1 vlan 10 100 101', 'instance 2 vlan 20 30 40', 'active region-configuration']
    elif phase == 'DHCP':
        cmds = ['dhcp enable']
        for v in ['vlan10', 'vlan20', 'vlan30', 'vlan40', 'vlan101']:
            gw_last = {'vlan10': '1', 'vlan20': '2', 'vlan30': '3', 'vlan40': '4', 'vlan101': '101'}[v]
            cmds.extend(['ip pool ' + v, 'gateway-list 192.168.' + gw_last + '.254', 'network 192.168.' + gw_last + '.0 mask 255.255.255.0', 'dns-list 192.168.0.1', 'quit'])
    elif phase == 'VLANIF':
        if role == 'SW1':
            for v, ip, vrid, pri in [('10','192.168.1.100','10','120'),('20','192.168.2.100','20','100'),('30','192.168.3.100','30','100'),('40','192.168.4.100','40','100'),('101','192.168.101.100','101','120')]:
                cmds.extend(['interface Vlanif'+v, 'ip address '+ip+' 255.255.255.0', 'vrrp vrid '+vrid+' virtual-ip 192.168.'+ ('1' if v=='10' else v.rstrip('0') if v!='101' else '101')+'.254'])
                if pri != '100':
                    cmds.append('vrrp vrid '+vrid+' priority '+pri)
                cmds.extend(['dhcp select global', 'quit'])
        elif role == 'SW2':
            for v, ip, vrid, pri in [('10','192.168.1.200','10','100'),('20','192.168.2.200','20','120'),('30','192.168.3.200','30','120'),('40','192.168.4.200','40','120'),('101','192.168.101.200','101','100')]:
                cmds.extend(['interface Vlanif'+v, 'ip address '+ip+' 255.255.255.0', 'vrrp vrid '+vrid+' virtual-ip 192.168.'+ ('1' if v=='10' else v.rstrip('0') if v!='101' else '101')+'.254'])
                if pri != '100':
                    cmds.append('vrrp vrid '+vrid+' priority '+pri)
                cmds.extend(['dhcp select global', 'quit'])
    elif phase == '端口':
        cmds = ['interface GigabitEthernet0/0/1', 'port link-type trunk', 'port trunk allow-pass vlan 2 to 4094', 'quit']
    elif phase == 'LACP':
        cmds = ['interface Eth-Trunk 1', 'mode lacp-static', 'port link-type trunk', 'port trunk allow-pass vlan 2 to 4094', 'quit', 'interface GigabitEthernet0/0/10', 'eth-trunk 1', 'quit', 'interface GigabitEthernet0/0/11', 'eth-trunk 1', 'quit']
    elif phase == 'OSPF':
        rid = '1.1.1.1' if role == 'SW1' else '2.2.2.2'
        cmds = ['ospf 1 router-id ' + rid, 'area 0.0.0.0', 'network 192.168.0.0 0.0.255.255',
                'silent-interface Vlanif10', 'silent-interface Vlanif20', 'silent-interface Vlanif30',
                'silent-interface Vlanif40', 'silent-interface Vlanif100', 'silent-interface Vlanif101', 'quit']
    elif phase == '鎺ュ彛':
        cmds = [
            'interface GigabitEthernet0/0/0', 'undo shutdown', 'ip address 192.168.0.1 255.255.255.0', 'quit',
            'interface GigabitEthernet1/0/0', 'undo shutdown', 'ip address 192.168.0.254 255.255.255.0', 'service-manage ping permit', 'quit',
            'interface GigabitEthernet1/0/1', 'undo shutdown', 'ip address 200.1.1.1 255.255.255.0', 'quit',
            'interface GigabitEthernet1/0/2', 'undo shutdown', 'ip address 192.168.50.2 255.255.255.0', 'service-manage ping permit', 'quit',
            'interface GigabitEthernet1/0/3', 'undo shutdown', 'ip address 192.168.51.2 255.255.255.0', 'service-manage ping permit', 'quit',
        ]
    elif phase == '鍖哄煙':
        cmds = [
            'firewall zone trust', 'set priority 85',
            'add interface GigabitEthernet1/0/2', 'add interface GigabitEthernet1/0/3', 'quit',
            'firewall zone untrust', 'set priority 5',
            'add interface GigabitEthernet1/0/1', 'quit',
            'firewall zone dmz', 'set priority 50',
            'add interface GigabitEthernet1/0/0', 'quit',
        ]
    elif phase == '瀹夊叏绛栫暐':
        cmds = [
            'security-policy',
            'rule name trust_to_dmz_untrust', 'source-zone trust', 'destination-zone dmz', 'destination-zone untrust', 'action permit', 'quit',
            'rule name untrust_to_dmz', 'source-zone untrust', 'destination-zone dmz', 'action permit', 'quit',
            'rule name deny_dmz_out', 'source-zone dmz', 'action deny', 'quit',
            'quit',
        ]
    elif phase == '路由':
        cmds = [
            'ip route-static 0.0.0.0 0.0.0.0 200.1.1.2',
            'ospf 1 router-id 3.3.3.3', 'default-route-advertise',
            'area 0.0.0.0', 'network 192.168.0.0 0.0.255.255', 'quit',
        ]
    elif phase == 'WLAN':
        cmds = ['wlan', 'security-profile name sec', 'security wpa-wpa2 psk pass-phrase zz1234567 aes', 'quit', 'ssid-profile name ssid', 'ssid wlan-2024', 'quit', 'vap-profile name vap', 'service-vlan vlan-id 101', 'ssid-profile ssid', 'security-profile sec', 'quit', 'ap-group name ap', 'radio 0', 'vap-profile vap wlan 1', 'quit', 'radio 1', 'vap-profile vap wlan 1', 'quit', 'quit']
    elif phase == 'AP娉ㄥ唽':
        cmds = [
            'ap-id 1 ap-mac 00e0-fc3f-6920 ap-sn 210235448310076D7959', 'ap-name ap1', 'ap-group ap',
            'ap-id 2 ap-mac 00e0-fc3f-6921 ap-sn 210235448310076D7960', 'ap-name ap2', 'ap-group ap',
        ]
    elif phase == '淇濆瓨':
        cmds = ['save']
    
    return cmds

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
        
        # Get context-aware status
        context = suggest_next_steps(path)
        
        device_report = {
            'name': name,
            'type': dt,
            'path': path,
            'commands_executed': len(dev_cmds),
            'success': success_count,
            'failed': failed_count,
            'role': context.get('role', 'unknown'),
            'completed_topics': context.get('completed_topics', []),
            'current_phase': context.get('current_phase', 'unknown'),
            'progress': context.get('progress', '0/0'),
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


SNAPSHOT_DIR = os.path.join(app.config.get('KB_FOLDER', 'kb'), 'snapshots')
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

def _detect_prompt_view(conn):
    try:
        result = conn.send_cmd('')
        if not result:
            return 'unknown', ''
        lines = result.strip().splitlines()
        prompt = lines[-1].strip() if lines else ''
        if '<' in prompt and '>' in prompt:
            return 'user_view', prompt
        if '[' in prompt and ']' in prompt:
            return 'system_view', prompt
        return 'unknown', prompt
    except Exception:
        return 'unknown', ''

def _ensure_user_view(conn):
    view, prompt = _detect_prompt_view(conn)
    if view == 'system_view':
        conn.send_cmd('return')
        time.sleep(0.2)
        return True
    return False

def _ensure_system_view(conn):
    view, prompt = _detect_prompt_view(conn)
    if view == 'user_view':
        conn.send_cmd('system-view')
        time.sleep(0.3)
        return True
    return False

def send_command_batch(path, commands, wait=0.1, auto_view=True, auto_undo_tm=True):
    with devices_lock:
        conn = devices.get(path)
    if not conn:
        return {'success': False, 'error': 'Device not connected'}
    t0 = time.time()
    results = []
    errors = []
    if auto_undo_tm and commands:
        first_cmd = commands[0].strip().lower()
        if first_cmd not in ('undo terminal monitor', 'undo t m'):
            try:
                out = conn.send_cmd('undo t m')
                results.append({'command': 'undo t m', 'output': out, 'success': True})
            except Exception:
                pass
    for cmd in commands:
        cmd = cmd.strip()
        if not cmd:
            continue
        cmd_lower = cmd.lower()
        if _is_blocked_command(cmd_lower):
            results.append({'command': cmd, 'output': '', 'success': False, 'error': 'Blocked'})
            errors.append('Blocked: ' + cmd)
            continue
        try:
            if auto_view:
                if cmd_lower == 'system-view':
                    _ensure_user_view(conn)
                elif cmd_lower in ('return', 'quit'):
                    pass
                elif cmd_lower.startswith(('interface ', 'vlan', 'ospf', 'vrrp', 'stp ', 'dhcp', 'ip pool', 'ip route', 'firewall', 'capwap', 'wlan', 'sysname', 'undo info', 'security-policy', 'aaa', 'manager-user')):
                    _ensure_system_view(conn)
                elif cmd_lower.startswith(('display ', 'save', 'ping', 'tracert', 'telnet')):
                    _ensure_user_view(conn)
            result = conn.send_cmd(cmd)
            cmd_ok = bool(result and 'Error' not in result[:100] and 'Unrecognized command' not in result)
            results.append({'command': cmd, 'output': result, 'success': cmd_ok})
            if not cmd_ok:
                errors.append('Failed: ' + cmd)
            with name_lock:
                dt = device_types.get(path, 'unknown')
            kb.record_command(cmd, result, device_type=dt, device_path=path, success=cmd_ok)
            time.sleep(wait)
        except ConnectionError:
            results.append({'command': cmd, 'output': '', 'success': False, 'error': 'Connection lost'})
            errors.append('Connection lost at: ' + cmd)
            break
        except Exception as e:
            results.append({'command': cmd, 'output': '', 'success': False, 'error': str(e)[:100]})
            errors.append('Error at ' + cmd + ': ' + str(e)[:100])
    elapsed = round(time.time() - t0, 3)
    # Auto-extract and record structured knowledge after batch completes
    try:
        with name_lock:
            dt = device_types.get(path, 'unknown')
        kb._auto_record_knowledge(path, dt, results)
    except Exception as _kb_err:
        logger.warning('Auto KB recording skipped: %s', _kb_err)
    return {
        'success': len(errors) == 0,
        'path': path,
        'total': len(results),
        'passed': sum(1 for r in results if r.get('success')),
        'failed': len(errors),
        'elapsed': elapsed,
        'results': results,
        'errors': errors
    }

def snapshot_config(path, label=None):
    with devices_lock:
        conn = devices.get(path)
    if not conn:
        return {'success': False, 'error': 'Device not connected'}
    try:
        _ensure_user_view(conn)
        config = conn.send_cmd('display current-configuration')
        if not config or len(config) < 50:
            return {'success': False, 'error': 'Empty config output'}
        with name_lock:
            name = device_names.get(path, path.replace(':', '_'))
            dt = device_types.get(path, 'unknown')
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        snap_id = name + '_' + ts
        if label:
            snap_id = snap_id + '_' + label
        filename = snap_id + '.cfg'
        filepath = os.path.join(SNAPSHOT_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('# Snapshot: ' + snap_id + '\n')
            f.write('# Device: ' + name + ' (' + dt + ')\n')
            f.write('# Path: ' + path + '\n')
            f.write('# Time: ' + datetime.now().isoformat() + '\n')
            f.write('# Label: ' + (label or 'auto') + '\n\n')
            f.write(config)
        meta_file = os.path.join(SNAPSHOT_DIR, 'snapshots.json')
        meta = {}
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r', encoding='utf-8') as _f: meta = json.load(_f)
            except Exception:
                meta = {}
        meta[snap_id] = {
            'path': path, 'name': name, 'device_type': dt,
            'label': label or 'auto', 'timestamp': datetime.now().isoformat(),
            'file': filename, 'size': len(config)
        }
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return {'success': True, 'snapshot_id': snap_id, 'file': filepath, 'size': len(config)}
    except Exception as e:
        return {'success': False, 'error': str(e)[:200]}

def list_snapshots(path=None):
    meta_file = os.path.join(SNAPSHOT_DIR, 'snapshots.json')
    if not os.path.exists(meta_file):
        return []
    try:
        with open(meta_file, 'r', encoding='utf-8') as _f: meta = json.load(_f)
        results = []
        for sid, info in meta.items():
            if path and info.get('path') != path:
                continue
            results.append({'snapshot_id': sid, **info})
        results.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return results
    except Exception:
        return []

def get_snapshot(snapshot_id):
    meta_file = os.path.join(SNAPSHOT_DIR, 'snapshots.json')
    if not os.path.exists(meta_file):
        return {'success': False, 'error': 'No snapshots'}
    try:
        with open(meta_file, 'r', encoding='utf-8') as _f: meta = json.load(_f)
        info = meta.get(snapshot_id)
        if not info:
            return {'success': False, 'error': 'Snapshot not found'}
        filepath = os.path.join(SNAPSHOT_DIR, info['file'])
        if not os.path.exists(filepath):
            return {'success': False, 'error': 'Snapshot file missing'}
        content = open(filepath, 'r', encoding='utf-8').read()
        return {'success': True, 'snapshot_id': snapshot_id, 'meta': info, 'content': content}
    except Exception as e:
        return {'success': False, 'error': str(e)[:200]}

def diff_configs(config1, config2):
    lines1 = set(config1.splitlines())
    lines2 = set(config2.splitlines())
    added = sorted(lines2 - lines1)
    removed = sorted(lines1 - lines2)
    common = lines1 & lines2
    return {
        'added': len(added), 'removed': len(removed), 'unchanged': len(common),
        'added_lines': added[:100], 'removed_lines': removed[:100],
        'total1': len(lines1), 'total2': len(lines2)
    }

def diff_snapshots(snap_id1, snap_id2):
    s1 = get_snapshot(snap_id1)
    s2 = get_snapshot(snap_id2)
    if not s1.get('success'):
        return {'success': False, 'error': 'Snapshot 1 not found'}
    if not s2.get('success'):
        return {'success': False, 'error': 'Snapshot 2 not found'}
    c1 = s1['content'].split('\n\n', 1)[-1] if '\n\n' in s1['content'] else s1['content']
    c2 = s2['content'].split('\n\n', 1)[-1] if '\n\n' in s2['content'] else s2['content']
    diff = diff_configs(c1, c2)
    diff['success'] = True
    diff['snapshot1'] = snap_id1
    diff['snapshot2'] = snap_id2
    return diff

def rollback_config(path, snapshot_id):
    pre_snap = snapshot_config(path, label='pre-rollback')
    snap = get_snapshot(snapshot_id)
    if not snap.get('success'):
        return {'success': False, 'error': 'Snapshot not found: ' + snapshot_id}
    content = snap['content']
    if '\n\n' in content:
        content = content.split('\n\n', 1)[-1]
    commands = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            commands.append(line)
    if not commands:
        return {'success': False, 'error': 'Empty snapshot config'}
    result = send_command_batch(path, commands, wait=0.05, auto_view=True, auto_undo_tm=True)
    result['pre_rollback_snapshot'] = pre_snap.get('snapshot_id')
    result['rolled_back_to'] = snapshot_id
    return result

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
        score = 0
        if query_lower in name.lower(): score += 3
        if query_lower in ts.get('symptom', '').lower(): score += 2
        if query_lower in ts.get('cause', '').lower(): score += 2
        if query_lower in ts.get('fix', '').lower(): score += 1
        if score > 0:
            results.append({'type': 'troubleshooting', 'name': name, 'score': score, **ts})
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

def generate_config_template(template_type, params=None):
    params = params or {}
    TEMPLATES = {
        'vlan': {'description': 'VLAN', 'commands': ['system-view', 'undo info-center enable', 'vlan batch %(vlans)s', 'interface %(interface)s', 'port link-type %(link_type)s', 'port default vlan %(vlan_id)s', 'return', 'save']},
        'vrrp': {'description': 'VRRP', 'commands': ['system-view', 'undo info-center enable', 'interface Vlanif%(vlan_id)s', 'ip address %(ip)s %(mask)s', 'vrrp vrid %(vrid)s virtual-ip %(vip)s', 'vrrp vrid %(vrid)s priority %(priority)s', 'dhcp select global', 'return', 'save']},
        'mstp': {'description': 'MSTP', 'commands': ['system-view', 'undo info-center enable', 'stp mode mstp', 'stp enable', 'stp region-configuration', 'region-name %(region_name)s', 'revision-level %(revision)s', 'instance 1 vlan %(vlan_group1)s', 'instance 2 vlan %(vlan_group2)s', 'active region-configuration', 'quit', 'stp instance %(instance)s root %(role)s', 'return', 'save']},
        'dhcp': {'description': 'DHCP', 'commands': ['system-view', 'undo info-center enable', 'dhcp enable', 'ip pool %(pool_name)s', 'gateway-list %(gateway)s', 'network %(network)s mask %(mask)s', 'dns-list %(dns)s', 'quit', 'return', 'save']},
        'ospf': {'description': 'OSPF', 'commands': ['system-view', 'undo info-center enable', 'ospf 1 router-id %(router_id)s', 'area 0.0.0.0', 'network %(network)s %(wildcard)s', 'return', 'save']},
        'lacp': {'description': 'LACP', 'commands': ['system-view', 'undo info-center enable', 'interface Eth-Trunk %(trunk_id)s', 'mode lacp-static', 'port link-type trunk', 'port trunk allow-pass vlan 2 to 4094', 'quit', 'interface %(interface1)s', 'eth-trunk %(trunk_id)s', 'quit', 'interface %(interface2)s', 'eth-trunk %(trunk_id)s', 'quit', 'return', 'save']},
        'wlan': {'description': 'WLAN', 'commands': ['system-view', 'undo info-center enable', 'vlan batch 100 to 101', 'dhcp enable', 'interface Vlanif100', 'ip address %(ac_ip)s %(mask)s', 'dhcp select interface', 'quit', 'capwap source interface Vlanif100', 'wlan', 'security-profile name sec', 'security wpa-wpa2 psk pass-phrase %(password)s aes', 'quit', 'ssid-profile name ssid', 'ssid %(ssid_name)s', 'quit', 'vap-profile name vap', 'service-vlan vlan-id 101', 'ssid-profile ssid', 'security-profile sec', 'quit', 'ap-group name ap', 'radio 0', 'vap-profile vap wlan 1', 'quit', 'radio 1', 'vap-profile vap wlan 1', 'quit', 'quit', 'return', 'save']},
    }
    template = TEMPLATES.get(template_type)
    if not template:
        return {'success': False, 'error': 'Unknown template. Available: ' + ', '.join(TEMPLATES.keys())}
    commands = []
    for cmd in template['commands']:
        try:
            commands.append(cmd % params)
        except (KeyError, ValueError):
            commands.append(cmd)
    return {'success': True, 'template': template_type, 'description': template['description'], 'commands': commands}

def send_command_to_group(paths, command):
    results = []
    for path in paths:
        r = send_command(path, command)
        results.append({'path': path, **r})
    return {'success': all(r.get('success') for r in results), 'total': len(results), 'results': results}

def disconnect_device(path):
    with devices_lock:
        conn = devices.pop(path, None)
    # Cleanup _undo_done tracking
    if hasattr(send_command, "_undo_done"):
        send_command._undo_done.discard(f"_undo_tm_{path}")
    if not conn: return {'success': False, 'error': 'Not connected'}
    try:
        conn.close()
        with name_lock:
            device_names.pop(path, None)
            device_types.pop(path, None)
        return {'success': True, 'path': path}
    except Exception as e:
        logger.error('Disconnect failed for %s: %s', path, e)
        return {'success': False, 'error': 'Disconnect failed'}

def get_connected_devices():
    result = []
    with devices_lock:
        paths = list(devices.keys())
    for path in paths:
        port = int(path.split(':')[1])
        with name_lock:
            topo_name = topo_names.get(port)
            name = topo_name or device_names.get(path, path)
            dt = device_types.get(path, "unknown")
        hb = heartbeat.get_status(path)
        display = f'{name} ({dt.upper()})' if name and dt != 'unknown' else name if name else path
        result.append({'port': port, 'path': path, 'name': name, 'display_name': display, 'device_type': dt, 'alive': hb.get('alive', False), 'response_time': hb.get('response_time', 0)})
    return result

def rename_device(path, name):
    with devices_lock:
        if path not in devices: return {'success': False, 'error': 'Not connected'}
    with name_lock: device_names[path] = name
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
    with devices_lock:
        conn = devices.get(path)
    if not conn: return jsonify({'success': False, 'error': 'Device not connected'}), 404
    name, dt = _fetch_device_name(conn)
    if name:
        with name_lock:
            device_names[path] = name
            device_types[path] = dt
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
    # Enrich with structured KB tips and config_order
    skb = kb._skb_cache or {}
    result['_config_order'] = skb.get('config_order', [])
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
        'config_steps': len(skb.get('config_order', [])),
        'experiment_count': len(skb.get('experiences', [])),
        'best_practice_count': len(skb.get('best_practices', {}).get('command_rules', []))
    }
    return jsonify(stats)



@app.route('/api/kb/structured')
@require_auth
def api_kb_structured():
    """Get the full structured command knowledge base."""
    view_type = request.args.get('view_type')
    device_model = request.args.get('model')
    return jsonify(kb.get_structured_kb(view_type=view_type, device_model=device_model))

@app.route('/api/kb/structured/<device_type>')
@require_auth
def api_kb_structured_by_type(device_type):
    """Get structured KB filtered by device type/model."""
    return jsonify(kb.get_structured_kb(device_model=device_type))

@app.route('/api/kb/scan', methods=['POST'])
@require_auth
def api_kb_scan():
    """Scan a connected device and return suggested commands from structured KB."""
    data = request.get_json(silent=True) or {}
    path = data.get('path')
    if not path:
        return jsonify({'success': False, 'error': 'Missing path parameter'}), 400
    return jsonify(kb.scan_device_commands(path))

@app.route('/api/kb/suggest')
@require_auth
def api_kb_suggest():
    """Get command suggestions for a device model."""
    model = request.args.get('model')
    if not model:
        return jsonify({'success': False, 'error': 'Missing model parameter'}), 400
    view_type = request.args.get('view_type')
    return jsonify(kb.suggest_commands(model, view_type=view_type))

@app.route('/api/kb/troubleshooting')
@require_auth
def api_kb_troubleshooting():
    """Get troubleshooting knowledge base."""
    skb = kb._skb_cache or {}
    symptom = request.args.get('symptom')
    if symptom:
        return jsonify(skb.get('troubleshooting', {}).get(symptom, {}))
    return jsonify(skb.get('troubleshooting', {}))

@app.route('/api/kb/config-order')
@require_auth
def api_kb_config_order():
    """Get the recommended configuration order."""
    skb = kb._skb_cache or {}
    return jsonify(skb.get('config_order', []))

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

@app.route('/api/devices/snapshot', methods=['POST'])
@require_auth
def api_snapshot():
    data = request.get_json(silent=True)
    if not data: return jsonify({'success': False, 'error': 'No data'}), 400
    path = data.get('path')
    if not _validate_path(path): return jsonify({'success': False, 'error': 'Invalid path'}), 400
    label = data.get('label')
    return jsonify(snapshot_config(path, label))

@app.route('/api/devices/snapshots')
@require_auth
def api_list_snapshots():
    path = request.args.get('path')
    return jsonify(list_snapshots(path))

@app.route('/api/devices/snapshot/<snapshot_id>')
@require_auth
def api_get_snapshot(snapshot_id):
    return jsonify(get_snapshot(snapshot_id))

@app.route('/api/devices/diff', methods=['POST'])
@require_auth
def api_diff():
    data = request.get_json(silent=True)
    if not data: return jsonify({'success': False, 'error': 'No data'}), 400
    s1 = data.get('snapshot1')
    s2 = data.get('snapshot2')
    if s1 and s2:
        return jsonify(diff_snapshots(s1, s2))
    c1 = data.get('config1', '')
    c2 = data.get('config2', '')
    return jsonify({'success': True, **diff_configs(c1, c2)})

@app.route('/api/devices/rollback', methods=['POST'])
@require_auth
def api_rollback():
    data = request.get_json(silent=True)
    if not data: return jsonify({'success': False, 'error': 'No data'}), 400
    path = data.get('path')
    snapshot_id = data.get('snapshot_id')
    if not _validate_path(path): return jsonify({'success': False, 'error': 'Invalid path'}), 400
    if not snapshot_id: return jsonify({'success': False, 'error': 'Missing snapshot_id'}), 400
    return jsonify(rollback_config(path, snapshot_id))

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

@app.route('/api/kb/config-guidance')
@require_auth
def api_kb_config_guidance():
    """??????????????????????????????????"""
    topic = request.args.get('topic', '')
    if not topic:
        return jsonify({'success': False, 'error': 'Missing topic parameter'}), 400
    guidance = kb.get_config_guidance(topic)
    guidance['success'] = True
    return jsonify(guidance)

@app.route('/api/kb/template', methods=['POST'])
@require_auth
def api_template():
    data = request.get_json(silent=True)
    if not data: return jsonify({'success': False, 'error': 'No data'}), 400
    template_type = data.get('type')
    params = data.get('params', {})
    if not template_type: return jsonify({'success': False, 'error': 'Missing type'}), 400
    return jsonify(generate_config_template(template_type, params))

@app.route('/api/kb/templates')
@require_auth
def api_list_templates():
    return jsonify({'templates': ['vlan', 'vrrp', 'mstp', 'dhcp', 'ospf', 'lacp', 'wlan']})

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




@app.route('/api/devices/suggest-next', methods=['POST'])
@require_auth
def api_suggest_next():
    """Get context-aware next steps for a device."""
    data = request.get_json(silent=True)
    if not data: return jsonify({'success': False, 'error': 'No data'}), 400
    path = data.get('path')
    if not _validate_path(path): return jsonify({'success': False, 'error': 'Invalid path'}), 400
    return jsonify(suggest_next_steps(path))

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
    with devices_lock:
        conn = devices.get(path)
    if not conn: emit("device_error", {"path": path, "error": "Not connected"}); return
    name, dt = _fetch_device_name(conn)
    if name:
        with name_lock: device_names[path] = name; device_types[path] = dt
        emit("device_renamed", {"path": path, "name": name})


if __name__ == "__main__":
    print("eNSP Server starting on http://127.0.0.1:5000")
    heartbeat.start()
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)

