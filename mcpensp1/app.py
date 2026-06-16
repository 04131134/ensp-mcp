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
    "ping": {"description": "测试网络连通性", "category": "verify", "tags": ["connectivity","test"], "risk": "safe", "output_hint": "ICMP响应、延迟、丢包", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "tracert": {"description": "追踪数据包路径", "category": "verify", "tags": ["path","trace"], "risk": "safe", "output_hint": "逐跳IP、延迟", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "system-view": {"description": "进入系统视图（配置前提）", "category": "config", "tags": ["prerequisite"], "risk": "safe", "output_hint": "提示符变为[设备名]", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "interface": {"description": "进入接口视图进行配置", "category": "config", "tags": ["interface"], "risk": "low", "output_hint": "提示符变为[设备接口]", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "undo shutdown": {"description": "启用接口", "category": "config", "tags": ["enable","up"], "risk": "medium", "output_hint": "接口UP", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "shutdown": {"description": "关闭接口", "category": "config", "tags": ["disable","down"], "risk": "medium", "output_hint": "接口DOWN", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "ip address": {"description": "为接口配置IP地址", "category": "config", "tags": ["ip","address"], "risk": "medium", "output_hint": "接口获得IP", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "quit": {"description": "退出当前视图", "category": "config", "tags": ["navigation"], "risk": "safe", "output_hint": "返回上级视图", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "return": {"description": "直接返回用户视图", "category": "config", "tags": ["navigation"], "risk": "safe", "output_hint": "提示符变为<设备名>", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "save": {"description": "保存配置到启动文件", "category": "config", "tags": ["save","persist"], "risk": "low", "output_hint": "确认保存", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "reboot": {"description": "重启设备（危险）", "category": "config", "tags": ["reboot","dangerous"], "risk": "high", "output_hint": "设备重启，连接断开", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "reset saved-configuration": {"description": "清除启动配置（危险，恢复出厂设置）", "category": "config", "tags": ["factory","dangerous"], "risk": "high", "output_hint": "确认操作", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display device": {"description": "显示设备基本信息（型号、槽位、状态）", "category": "display", "tags": ["hardware","device"], "risk": "safe", "output_hint": "设备型号、槽位、状态", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display clock": {"description": "显示系统时间和时区", "category": "display", "tags": ["time","system"], "risk": "safe", "output_hint": "日期时间、时区", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display ip interface": {"description": "显示接口详细IP信息", "category": "display", "tags": ["interface","ip","detail"], "risk": "safe", "output_hint": "接口IP、掩码、MTU、状态", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display ip routing-table statistics": {"description": "显示路由表统计信息", "category": "display", "tags": ["routing","statistics"], "risk": "safe", "output_hint": "路由条目数、协议分布", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display static-route": {"description": "显示静态路由配置", "category": "display", "tags": ["routing","static"], "risk": "safe", "output_hint": "目的网络、下一跳、优先级", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display acl all": {"description": "显示所有ACL规则", "category": "display", "tags": ["acl","security","filter"], "risk": "safe", "output_hint": "ACL编号、规则、动作", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display users": {"description": "显示当前登录用户", "category": "display", "tags": ["user","session"], "risk": "safe", "output_hint": "用户、终端、登录时间", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display user-interface": {"description": "显示用户界面配置", "category": "display", "tags": ["user","interface","console"], "risk": "safe", "output_hint": "控制台、VTY配置", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display startup": {"description": "显示启动文件信息", "category": "display", "tags": ["startup","boot"], "risk": "safe", "output_hint": "启动配置、系统软件版本", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display logfile": {"description": "显示日志文件信息", "category": "diagnostic", "tags": ["log","file"], "risk": "safe", "output_hint": "日志文件名、大小", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display trapbuffer": {"description": "显示告警缓冲区", "category": "diagnostic", "tags": ["trap","alarm","buffer"], "risk": "safe", "output_hint": "告警时间、类型、描述", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display local-user": {"description": "显示本地用户配置", "category": "display", "tags": ["user","aaa","security"], "risk": "safe", "output_hint": "用户名、权限、状态", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display aaa": {"description": "显示AAA认证授权信息", "category": "display", "tags": ["aaa","security","auth"], "risk": "safe", "output_hint": "认证方式、在线用户", "huawei": True, "h3c": True, "cisco": True, "juniper": False},
    "display timezone": {"description": "显示时区配置", "category": "display", "tags": ["time","timezone"], "risk": "safe", "output_hint": "当前时区", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display license": {"description": "显示License信息", "category": "display", "tags": ["license","feature"], "risk": "safe", "output_hint": "授权状态、到期时间", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display resource": {"description": "显示资源使用情况", "category": "diagnostic", "tags": ["resource","usage"], "risk": "safe", "output_hint": "CPU/内存/会话使用率", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display version brief": {"description": "显示简要版本信息", "category": "display", "tags": ["version","info"], "risk": "safe", "output_hint": "版本号、发布时间", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display cpu-usage history 1": {"description": "显示CPU使用率历史记录", "category": "diagnostic", "tags": ["cpu","history","performance"], "risk": "safe", "output_hint": "历史CPU使用率曲线图", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display memory statistics": {"description": "显示详细内存统计", "category": "diagnostic", "tags": ["memory","statistics"], "risk": "safe", "output_hint": "内存分页统计", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display terminal monitor": {"description": "显示终端监控状态", "category": "display", "tags": ["terminal","monitor"], "risk": "safe", "output_hint": "终端监控开关状态", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display info-center": {"description": "显示信息中心配置", "category": "display", "tags": ["info-center","logging"], "risk": "safe", "output_hint": "日志模块、输出通道", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display ntp-status": {"description": "显示NTP同步状态", "category": "display", "tags": ["ntp","time","sync"], "risk": "safe", "output_hint": "NTP服务器、偏移量、同步状态", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display dns": {"description": "显示DNS配置", "category": "display", "tags": ["dns","resolution"], "risk": "safe", "output_hint": "DNS服务器地址", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display http-server info": {"description": "显示HTTP服务器信息", "category": "display", "tags": ["http","web","server"], "risk": "safe", "output_hint": "HTTP服务状态、端口", "huawei": True, "h3c": True, "cisco": False, "juniper": False},
    "display ssh server status": {"description": "显示SSH服务状态", "category": "display", "tags": ["ssh","security","server"], "risk": "safe", "output_hint": "SSH版本、端口、超时", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display telnet server status": {"description": "显示Telnet服务状态", "category": "display", "tags": ["telnet","server"], "risk": "safe", "output_hint": "Telnet端口、连接数", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display arp all": {"description": "显示所有ARP条目", "category": "display", "tags": ["arp","mac","neighbor"], "risk": "safe", "output_hint": "IP-MAC映射表", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display arp static": {"description": "显示静态ARP条目", "category": "display", "tags": ["arp","static"], "risk": "safe", "output_hint": "静态IP-MAC绑定", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
    "display arp dynamic": {"description": "显示动态ARP条目", "category": "display", "tags": ["arp","dynamic"], "risk": "safe", "output_hint": "动态学习的IP-MAC映射", "huawei": True, "h3c": True, "cisco": True, "juniper": True},
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
            gkb = self._load(self.global_path)
            dkb = self._load(self.devices_path)
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
            self._save(self.global_path, gkb)

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
            self._save(self.devices_path, dkb)

    def get_device_history(self, device_path=None):
        with self.lock:
            dkb = self._load(self.devices_path)
            return dkb.get('devices', {}).get(device_path, {}) if device_path else dkb.get('devices', {})

    def get_device_capabilities(self, device_path=None):
        with self.lock:
            dkb = self._load(self.devices_path)
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
            max_id = max((int(r.get('id', 'BP-000').split('-')[1]) for r in rules), default=0)
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
        if cmd.startswith(('system-view', 'interface', 'ip ', 'undo ', 'shutdown', 'sysname', 'save', 'quit', 'return')): return 'config'
        if cmd.startswith(('ping', 'tracert', 'telnet')): return 'verify'
        return 'other'



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
            except Exception as e: print(f'[Heartbeat] {e}')
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
                    socketio.emit('heartbeat_status', {'path': path, 'alive': False, 'status': 'disconnected', 'message': f'{nm} 已断开'})
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
            import select
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
            socketio.emit('heartbeat_status', {'path': path, 'alive': True, 'status': 'reconnected', 'message': f'{nm} 自动重连成功'})
        except Exception as e:
            logger.error('Reconnect failed for %s: %s', path, e)
            if nc:
                try: nc.close()
                except OSError: pass

    def get_status(self, path=None):
        with self.lock: return self.status.get(path, {'alive': False}) if path else dict(self.status)

    def _now(self): return datetime.now(timezone.utc).isoformat()


class TelnetConnection:
    def __init__(self, host, port):
        self.host, self.port, self.sock = host, port, None
        self.lock = threading.Lock()

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect((self.host, self.port))
        self.sock.send(b'\r\n')
        time.sleep(0.2)
        try: self.sock.recv(4096)
        except socket.timeout: pass
        self.sock.settimeout(10)
        return True

    def send_cmd(self, cmd):
        MAX_RECV = 4 * 1024 * 1024  # 4MB buffer limit
        with self.lock:
            if not self.sock: raise ConnectionError('Socket not connected')
            cmd_lower = cmd.strip().lower()
            # Longer timeout for display/dir commands that produce large output
            is_display = cmd_lower.startswith('display') or cmd_lower.startswith('dir')
            is_diag = cmd_lower.startswith(('ping', 'tracert'))
            recv_timeout = 3 if is_display else (4 if is_diag else 1.5)
            self.sock.settimeout(recv_timeout)
            self.sock.send(f'{cmd}\r\n'.encode())
            time.sleep(0.3 if is_display else 0.2)
            chunks = []
            total = 0
            try:
                while True:
                    chunk = self.sock.recv(65536)
                    if not chunk: break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= MAX_RECV: break
                    self.sock.settimeout(recv_timeout)
            except socket.timeout: pass
            return b''.join(chunks).decode('gbk', errors='ignore')

    def close(self):
        with self.lock:
            if self.sock:
                try: self.sock.close()
                except OSError: pass
                self.sock = None


kb = KnowledgeBase(app.config['KB_FOLDER'])
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
                pass
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
    """Fetch device name and type from display version output."""
    try:
        r = conn.send_cmd('display version')
        if not r: return None, "unknown"
        dt = _detect_device_type(r)
        name = None
        if dt in ('huawei', 'h3c'):
            nr = conn.send_cmd('display current-configuration | include sysname')
            if nr and 'Unrecognized' not in nr and 'Error' not in nr:
                m = re.search(r'sysname\s+(\S+)' , nr, re.IGNORECASE)
                if m:
                    sysname_val = m.group(1)
                    generic_names = ['<Huawei>', '<H3C>', '<HUAWEI>', '<h3c>', '<huawei>', 'sysname']
                    if sysname_val.lower() not in [g.lower() for g in generic_names]:
                        name = sysname_val
        if not name:
            model_patterns = [
                (r'(CE\d+\S*)', 'CE'),
                (r'(NE\d+\S*)', 'NE'),
                (r'(USG\d+\S*)', 'USG'),
                (r'(AR\d+\S*)', 'AR'),
                (r'(S\d{4}\S*)', 'Switch'),
                (r'(AC\d+\S*)', 'AC'),
                (r'(AP\d+\S*)', 'AP'),
                (r'(NetEngine\s*\S+)', 'NE'),
                (r'(Huawei\s+\S+\s+Series)', 'HUAWEI'),
            ]
            for pattern, prefix in model_patterns:
                m = re.search(pattern, r, re.IGNORECASE)
                if m:
                    name = m.group(1).strip()
                    break
        if not name:
            name = f'{dt.upper() if dt != "unknown" else "DEVICE"}-{conn.port}'
        return name, dt
    except Exception:
        return None, "unknown"
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

def disconnect_device(path):
    with devices_lock:
        conn = devices.pop(path, None)
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
