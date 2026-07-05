/* ============================================================
 * eNSP MCP Frontend - app.js
 * 智能网络实验平台前端逻辑
 * ============================================================ */
'use strict';

/* ==================== Socket.IO 初始化 ==================== */
var socket;
try { socket = io(); } catch (e) { console.error('socket.io failed:', e); }
if (typeof socket === 'undefined' || !socket) { socket = { on: function () {}, emit: function () {} }; }

/* ==================== 全局状态 ==================== */
var state = {
  connected: {}, names: {}, types: {}, alive: {}, termData: {},
  curDev: null, scanned: [], renameTarget: null, topoSummary: null,
  kbModel: 'S5700', kbView: 'both', experiments: [], curExp: null, logCount: 0
};

/* ==================== 工具函数 ==================== */
function pathId(p) { return p.replace(/[^a-zA-Z0-9_-]/g, '_'); }
function idToPath(id) { return id.replace(/_/g, '.'); }
function esc(text) { var d = document.createElement('div'); d.textContent = text; return d.innerHTML; }
function fmtTime() { return new Date().toLocaleTimeString('zh-CN', { hour12: false }); }
function truncate(s, max) { if (!s) return ''; return s.length > max ? s.substring(0, max) + '...' : s; }

/* ==================== 日志系统 ==================== */
var _logLines = [];
function log(msg, level) {
  level = level || 'info';
  _logLines.push({ time: fmtTime(), msg: msg, level: level });
  if (_logLines.length > 500) _logLines.shift();
  state.logCount++;
  renderLogs();
}
function renderLogs() {
  var el = document.getElementById('logs'); if (!el) return;
  var lines = _logLines.slice(-200); var html = '';
  for (var i = 0; i < lines.length; i++) {
    var l = lines[i];
    html += '<div class="log-line"><span class="log-time">[' + esc(l.time) + ']</span><span class="log-' + l.level + '">' + esc(l.msg) + '</span></div>';
  }
  el.innerHTML = html; el.scrollTop = el.scrollHeight;
  var cntEl = document.getElementById('logCount'); if (cntEl) cntEl.textContent = '(' + state.logCount + ')';
}
function clearLogs() { _logLines = []; state.logCount = 0; renderLogs(); }
function toggleLogs() { var el = document.getElementById('logs'); if (el) el.classList.toggle('collapsed'); }

/* ==================== 模态框工具 ==================== */
function showModalPrompt(title, defaultVal, callback) {
  var overlay = document.createElement('div'); overlay.className = 'modal'; overlay.style.display = 'flex';
  var modal = document.createElement('div'); modal.className = 'mc'; modal.style.minWidth = '400px';
  var titleEl = document.createElement('div'); titleEl.className = 'mt'; titleEl.textContent = title;
  var textarea = document.createElement('textarea'); textarea.className = 'mi'; textarea.rows = 6;
  textarea.style.resize = 'vertical'; textarea.style.fontFamily = 'Consolas, monospace'; textarea.value = defaultVal || '';
  var btnRow = document.createElement('div'); btnRow.className = 'mb';
  var cancelBtn = document.createElement('button'); cancelBtn.className = 'mbtn cancel'; cancelBtn.textContent = '取消';
  var okBtn = document.createElement('button'); okBtn.className = 'mbtn confirm'; okBtn.textContent = '确定';
  function close() { overlay.remove(); }
  okBtn.onclick = function () { var v = textarea.value; close(); callback(v); };
  cancelBtn.onclick = function () { close(); callback(null); };
  textarea.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { close(); callback(null); }
    if (e.key === 'Enter' && e.ctrlKey) { var v = textarea.value; close(); callback(v); }
  });
  btnRow.appendChild(cancelBtn); btnRow.appendChild(okBtn);
  modal.appendChild(titleEl); modal.appendChild(textarea); modal.appendChild(btnRow);
  overlay.appendChild(modal); document.body.appendChild(overlay); textarea.focus();
}

/* ==================== 视图切换 ==================== */
function sw(view) {
  document.querySelectorAll('.panel-container').forEach(function (p) { p.classList.remove('active'); });
  document.querySelectorAll('.btn-nav').forEach(function (b) { b.classList.remove('active'); });
  var panelId = 'v' + view.charAt(0).toUpperCase() + view.slice(1);
  var navId = 'n' + view.charAt(0).toUpperCase() + view.slice(1);
  var panel = document.getElementById(panelId); var nav = document.getElementById(navId);
  if (panel) panel.classList.add('active'); if (nav) nav.classList.add('active');
  if (view === 'kb') loadKb(); if (view === 'topo') loadTopo(); if (view === 'exp') loadExperiments();
}
/* ==================== Socket.IO 事件处理 ==================== */
socket.on('connect', function () { log('已连接到服务器', 'success'); socket.emit('get_connected_devices'); });
socket.on('disconnect', function () { log('与服务器断开连接', 'error'); });
socket.on('scan_result', function (data) {
  state.scanned = data;
  data.forEach(function (x) { if (x.name && x.name !== x.path) state.names[x.path] = x.name; if (x.device_type) state.types[x.path] = x.device_type; });
  updateDeviceList(); log('扫描完成，发现 ' + data.length + ' 个设备', 'success');
});
socket.on('connected_devices_list', function (data) {
  data.forEach(function (x) {
    state.connected[x.path] = true;
    if (x.name && x.name !== x.path) state.names[x.path] = x.name;
    if (x.device_type) state.types[x.path] = x.device_type;
    if (x.alive !== undefined) state.alive[x.path] = x.alive;
  });
  updateDeviceList();
});
socket.on('device_connected', function (data) {
  state.connected[data.path] = true;
  if (data.name && data.name !== data.path) state.names[data.path] = data.name;
  if (data.device_type) state.types[data.path] = data.device_type;
  updateDeviceList(); addTerminal(data.path, data.name || data.path); log('已连接: ' + (data.name || data.path), 'success');
});
socket.on('device_output', function (data) {
  if (!state.termData[data.path]) state.termData[data.path] = [];
  state.termData[data.path].push({ type: 'output', text: data.output });
  if (state.termData[data.path].length > 500) state.termData[data.path].shift();
  if (state.curDev === data.path) renderTerminal(data.path);
});
socket.on('device_error', function (data) { if (data.path && state.termData[data.path]) { state.termData[data.path].push({ type: 'error', text: '[错误] ' + data.error }); if (state.termData[data.path].length > 500) state.termData[data.path].shift(); if (state.curDev === data.path) renderTerminal(data.path); } log('错误: ' + data.error, 'error'); });
socket.on('device_disconnected', function (data) {
  delete state.connected[data.path]; delete state.names[data.path];
  delete state.types[data.path]; delete state.alive[data.path];
  var deid = pathId(data.path); var dinput = document.getElementById('ti_' + deid);
  if (dinput) { dinput.disabled = true; dinput.placeholder = '设备已断开'; }
  updateDeviceList(); removeTerminal(data.path); log('已断开: ' + data.path);
});
socket.on('device_renamed', function (data) {
  state.names[data.path] = data.name; updateDeviceList();
  updateTabHeader(data.path, data.name); log('已重命名: ' + data.name, 'success');
});
/* ==================== 批量命令实时错误 ==================== */
socket.on('batch_error', function (data) {
  if (data.path && state.termData[data.path]) {
    state.termData[data.path].push({ type: 'error', text: '[批量错误] 命令: ' + data.command + ' -> ' + (data.error || data.output || '').substring(0, 200) });
    if (state.termData[data.path].length > 500) state.termData[data.path].shift();
    if (state.curDev === data.path) renderTerminal(data.path);
  }
  log('批量错误: ' + data.command + ' - ' + (data.error || data.output || '').substring(0, 100), 'error');
});

// ==================== 心跳状态 ====================
socket.on('heartbeat_status', function (data) {
  state.alive[data.path] = data.alive; updateDeviceList();
  if (data.status === 'reconnected') {
    log((state.names[data.path] || data.path) + ' 已自动恢复', 'success');
    addTermSys(data.path, '设备已自动恢复连接');
  } else if (data.status === 'disconnected') {
    log(data.message, 'error'); addTermSys(data.path, data.message);
  }
});
socket.on('topology_updated', function (data) {
  state.topoSummary = data;
  var ind = document.getElementById('topoInd');
  if (ind) ind.textContent = '拓扑: ' + data.node_count + ' 节点, ' + data.link_count + ' 链路';
  var sumEl = document.getElementById('topoSummary');
  if (sumEl) sumEl.textContent = data.node_count + ' 个节点, ' + data.link_count + ' 条链路';
  if (document.getElementById('vTopo').classList.contains('active')) renderTopo();
});

/* ==================== 设备列表管理 ==================== */
function updateDeviceList() {
  var el = document.getElementById('dList'); if (!el) return;
  var html = ''; var allPaths = {};
  Object.keys(state.connected).forEach(function (p) { allPaths[p] = true; });
  state.scanned.forEach(function (x) { allPaths[x.path] = true; });
  var paths = Object.keys(allPaths).sort();
  var devCountEl = document.getElementById('devCount'); if (devCountEl) devCountEl.textContent = paths.length;
  paths.forEach(function (path) {
    var isConn = !!state.connected[path]; var name = state.names[path] || path;
    var type = state.types[path] || ''; var alive = state.alive[path]; var isSelected = state.curDev === path;
    var cls = 'di'; if (isSelected) cls += ' selected';
    if (isConn && alive !== false) cls += ' connected'; else if (alive === false) cls += ' unresponsive';
    var hbCls = 'hb'; if (!isConn) hbCls += ' dead'; else if (alive === false) hbCls += ' unresponsive'; else hbCls += ' alive';
    html += '<div class="' + cls + '" onclick="selectDevice(\'' + esc(path) + '\')">'
      + '<div class="dh"><div class="dn"><span class="' + hbCls + '"></span> ' + esc(name)
      + (isConn ? ' <span class="edit-icon" onclick="event.stopPropagation();renameDevice(\'' + esc(path) + '\')" title="重命名">✏️</span>' : '')
      + '</div>' + (type ? '<span class="dt">' + esc(type) + '</span>' : '') + '</div>'
      + '<div class="dm"><span class="dp">' + esc(path) + '</span></div>';
    if (isConn) {
      html += '<div class="dar"><button class="btn btn-sm btn-danger" onclick="event.stopPropagation();disconnectDev(\'' + esc(path) + '\')">断开</button>'
        + '<button class="btn btn-sm btn-ghost" onclick="event.stopPropagation();fetchName(\'' + esc(path) + '\')">获取名称</button></div>';
    } else {
      html += '<div class="dar"><button class="btn btn-sm" style="background:var(--green);color:var(--bg-base)" onclick="event.stopPropagation();connectDev(\'' + esc(path) + '\')">连接</button></div>';
    }
    html += '</div>';
  });
  el.innerHTML = html;
}

/* ==================== 设备操作 ==================== */
function doScan() {
  var s = parseInt(document.getElementById('pS').value) || 2000;
  var e = parseInt(document.getElementById('pE').value) || 2050;
  if (e - s > 1000) { log('扫描范围不能超过 1000', 'error'); return; }
  log('正在扫描端口 ' + s + '-' + e + ' ...');
  fetch('/api/devices/scan?start=' + s + '&end=' + e).then(function (r) { return r.json(); }).then(function (data) {
    state.scanned = data;
    data.forEach(function (x) { if (x.name) state.names[x.path] = x.name; if (x.device_type) state.types[x.path] = x.device_type; });
    updateDeviceList(); log('扫描完成，发现 ' + data.length + ' 个设备', 'success');
  }).catch(function (e) { log('扫描失败: ' + e, 'error'); });
}
function doRefresh() {
  fetch('/api/devices').then(function (r) { return r.json(); }).then(function (data) {
    state.connected = {}; state.names = {}; state.types = {};
    (data.devices || data || []).forEach(function (x) { var p = x.path || x; state.connected[p] = true; if (x.name) state.names[p] = x.name; if (x.device_type) state.types[p] = x.device_type; });
    updateDeviceList(); log('设备列表已刷新', 'success');
  }).catch(function (e) { log('刷新失败: ' + e, 'error'); });
}
function connectDev(path) {
  log('正在连接 ' + path + ' ...');
  fetch('/api/devices/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: path }) })
    .then(function (r) { return r.json(); }).then(function (data) {
      if (data.success) {
        state.connected[path] = true; if (data.name) state.names[path] = data.name; if (data.device_type) state.types[path] = data.device_type;
        updateDeviceList(); addTerminal(path, data.name || path); log('已连接: ' + (data.name || path), 'success');
      } else { log('连接失败: ' + (data.error || '未知错误'), 'error'); }
    }).catch(function (e) { log('连接失败: ' + e, 'error'); });
}
function disconnectDev(path) {
  fetch('/api/devices/disconnect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: path }) })
    .then(function (r) { return r.json(); }).then(function (data) {
      if (data.success) { delete state.connected[path]; updateDeviceList(); removeTerminal(path); log('已断开: ' + path); }
    }).catch(function (e) { log('断开失败: ' + e, 'error'); });
}
function selectDevice(path) {
  state.curDev = path; updateDeviceList(); switchToTerm(path);
  var toolbar = document.getElementById('deviceToolbar'); if (toolbar) toolbar.classList.add('visible');
}
function renameDevice(path) {
  state.renameTarget = path; var input = document.getElementById('renameInput');
  input.value = state.names[path] || ''; document.getElementById('renameModal').style.display = 'flex'; input.focus(); input.select();
}
function closeRM() { document.getElementById('renameModal').style.display = 'none'; state.renameTarget = null; }
function confirmRM() {
  var name = document.getElementById('renameInput').value.trim();
  if (!name || !state.renameTarget) { closeRM(); return; }
  fetch('/api/devices/rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: state.renameTarget, name: name }) })
    .then(function (r) { return r.json(); }).then(function (data) {
      if (data.success) { state.names[state.renameTarget] = name; updateDeviceList(); updateTabHeader(state.renameTarget, name); log('已重命名: ' + name, 'success'); }
    }).catch(function (e) { log('重命名失败: ' + e, 'error'); });
  closeRM();
}
function fetchName(path) {
  fetch('/api/devices/fetch-name', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: path }) })
    .then(function (r) { return r.json(); }).then(function (data) {
      if (data.success && data.name) { state.names[path] = data.name; updateDeviceList(); updateTabHeader(path, data.name); log('设备名称: ' + data.name, 'success'); }
    }).catch(function (e) { log('获取名称失败: ' + e, 'error'); });
}

/* ==================== 终端管理 ==================== */
function addTerminal(path, name) {
  var tabsEl = document.getElementById('termTabs'); var termsEl = document.getElementById('terminals'); var eid = pathId(path);
  if (document.getElementById('term_' + eid)) { switchToTerm(path); return; }
  var placeholder = termsEl.querySelector('[style*="text-align:center"]'); if (placeholder) placeholder.remove();
  var tab = document.createElement('div'); tab.className = 'tab'; tab.id = 'tab_' + eid;
  tab.onclick = function () { switchToTerm(path); };
  tab.innerHTML = '<span>' + esc(name || path) + '</span><button class="cls" onclick="event.stopPropagation();closeTerm(\'' + esc(path) + '\')" title="关闭">&times;</button>';
  tabsEl.appendChild(tab);
  var tp = document.createElement('div'); tp.className = 'tp'; tp.id = 'term_' + eid;
  tp.innerHTML = '<div class="th"><span class="th-title">' + esc(name || path) + '</span><span class="ri" onclick="clearTerm(\'' + esc(path) + '\')" title="清空">🗑️</span></div>'
    + '<div class="tb" id="tb_' + eid + '"></div>'
    + '<div class="ti"><span class="pm">&gt;</span><input type="text" id="ti_' + eid + '" placeholder="输入命令..." onkeydown="if(event.key===\'Enter\')sendCmd(\'' + esc(path) + '\')"></div>';
  termsEl.appendChild(tp); switchToTerm(path);
}
function switchToTerm(path) {
  state.curDev = path; var eid = pathId(path);
  document.querySelectorAll('#termTabs .tab').forEach(function (t) { t.classList.remove('active'); });
  var tab = document.getElementById('tab_' + eid); if (tab) tab.classList.add('active');
  document.querySelectorAll('.tp').forEach(function (t) { t.classList.remove('active'); });
  var term = document.getElementById('term_' + eid); if (term) term.classList.add('active');
  var toolbar = document.getElementById('deviceToolbar'); if (toolbar) toolbar.classList.add('visible');
  renderTerminal(path); updateDeviceList();
  var input = document.getElementById('ti_' + eid); if (input) input.focus();
}
function removeTerminal(path) {
  var eid = pathId(path);
  var tab = document.getElementById('tab_' + eid); if (tab) tab.remove();
  var term = document.getElementById('term_' + eid); if (term) term.remove();
  if (state.curDev === path) {
    state.curDev = null; var firstTab = document.querySelector('#termTabs .tab');
    if (firstTab) { switchToTerm(idToPath(firstTab.id.replace('tab_', ''))); }
    else { var toolbar = document.getElementById('deviceToolbar'); if (toolbar) toolbar.classList.remove('visible'); }
  }
}
function closeTerm(path) { if (state.connected[path]) { disconnectDev(path); } else { removeTerminal(path); } }
function clearTerm(path) { if (state.termData[path]) state.termData[path] = []; renderTerminal(path); }
function clearCurTerm() { if (state.curDev) clearTerm(state.curDev); }
function renderTerminal(path) {
  var eid = pathId(path); var tb = document.getElementById('tb_' + eid); if (!tb) return;
  var data = state.termData[path] || []; var html = '';
  for (var i = 0; i < data.length; i++) { html += '<div class="' + (data[i].type || 'output') + '">' + esc(data[i].text) + '</div>'; }
  tb.innerHTML = html; tb.scrollTop = tb.scrollHeight;
}
function updateTabHeader(path, name) {
  var eid = pathId(path);
  var tab = document.getElementById('tab_' + eid); if (tab) { var span = tab.querySelector('span'); if (span) span.textContent = name; }
  var th = document.querySelector('#term_' + eid + ' .th-title'); if (th) th.textContent = name;
}
function addTermSys(path, text) {
  if (!state.termData[path]) state.termData[path] = [];
  state.termData[path].push({ type: 'system', text: '[系统] ' + text });
  if (state.termData[path].length > 500) state.termData[path].shift();
  if (state.curDev === path) renderTerminal(path);
}

/* ==================== 命令发送 ==================== */
function sendCmd(path) {
  var eid = pathId(path); var input = document.getElementById('ti_' + eid); if (!input) return;
  var cmd = input.value.trim(); if (!cmd) return;
  if (!state.connected[path]) { input.value = ''; addTermSys(path, '设备未连接，请先在左侧列表中连接设备'); renderTerminal(path); return; }
  input.value = '';
  if (!state.termData[path]) state.termData[path] = [];
  state.termData[path].push({ type: 'input', text: '> ' + cmd });
  if (state.termData[path].length > 500) state.termData[path].shift(); renderTerminal(path);
  fetch('/api/devices/command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: path, command: cmd }) })
    .then(function (r) { return r.json(); }).then(function (data) {
      if (data.output) state.termData[path].push({ type: data.success ? 'output' : 'error', text: data.output });
      if (data.error) state.termData[path].push({ type: 'error', text: '错误: ' + data.error });
      if (state.termData[path].length > 500) state.termData[path].shift(); renderTerminal(path);
    }).catch(function (e) { state.termData[path].push({ type: 'error', text: '请求失败: ' + e }); renderTerminal(path); });
}

/* ==================== 批量命令 ==================== */
function doBatchCmd() {
  if (!state.curDev) { log('请先选择设备', 'error'); return; }
  showModalPrompt('批量命令（每行一条）:', '', function (cmds) {
    if (cmds === null) return;
    var cmdList = cmds.split('\n').map(function (c) { return c.trim(); }).filter(function (c) { return c; });
    if (!cmdList.length) return;
    log('批量执行: ' + cmdList.length + ' 条命令 → ' + (state.names[state.curDev] || state.curDev));
    if (!state.termData[state.curDev]) state.termData[state.curDev] = [];
    state.termData[state.curDev].push({ type: 'batch', text: '[批量] 开始执行 ' + cmdList.length + ' 条命令...' });
    fetch('/api/devices/batch-command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: state.curDev, commands: cmdList, auto_view: true, auto_undo_tm: true }) })
      .then(function (r) { return r.json(); }).then(function (data) {
        if (data.success) {
          log('批量完成: ' + data.passed + '/' + data.total + ' 成功 (' + data.elapsed + 's)', 'success');
          state.termData[state.curDev].push({ type: 'batch', text: '[批量] 完成: ' + data.passed + '/' + data.total + ' 成功' });
        } else {
          log('批量部分失败: ' + data.passed + '/' + data.total, 'error');
          state.termData[state.curDev].push({ type: 'error', text: '[批量] 部分失败: ' + data.passed + '/' + data.total });
        }
        if (data.results) { data.results.forEach(function (r) { state.termData[state.curDev].push({ type: r.success ? 'output' : 'error', text: '  ' + (r.success ? '✓' : '✗') + ' ' + r.command }); if (!r.success) { var _err = (r.error || r.output || '').substring(0, 200).replace(/\n/g, ' ').trim(); if (_err) state.termData[state.curDev].push({ type: 'error', text: '     → ' + _err }); } }); }
        if (state.termData[state.curDev].length > 500) state.termData[state.curDev] = state.termData[state.curDev].slice(-500);
        renderTerminal(state.curDev);
      }).catch(function (e) { log('批量执行失败: ' + e, 'error'); });
  });
}

/* ==================== 设备验证 ==================== */
function doVerify(checkType) {
  if (!state.curDev) { log('请先选择设备', 'error'); return; }
  var label = checkType === 'all' ? '全面验证' : checkType.toUpperCase() + ' 验证';
  log(label + ': ' + (state.names[state.curDev] || state.curDev));
  if (!state.termData[state.curDev]) state.termData[state.curDev] = [];
  state.termData[state.curDev].push({ type: 'verify', text: '[验证] 开始 ' + label + '...' }); renderTerminal(state.curDev);
  var body = { path: state.curDev }; if (checkType !== 'all') body.check_type = checkType;
  if (checkType === 'ping') {
    showModalPrompt('输入目标 IP 地址:', '', function (ip) { if (!ip) return; body.check_type = 'ping'; body.target_ip = ip.trim(); execVerify(body); });
  } else { execVerify(body); }
}
function execVerify(body) {
  fetch('/api/devices/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    .then(function (r) { return r.json(); }).then(function (data) {
      if (!state.termData[body.path]) state.termData[body.path] = [];
      if (data.success) {
        var checks = data.checks || []; var passed = checks.filter(function (c) { return c.passed; }).length;
        state.termData[body.path].push({ type: 'verify', text: '[验证] 结果: ' + passed + '/' + checks.length + ' 通过' });
        checks.forEach(function (c) { state.termData[body.path].push({ type: c.passed ? 'output' : 'error', text: '  ' + (c.passed ? '✓' : '✗') + ' ' + c.name + (c.detail ? ': ' + c.detail : '') }); });
        log('验证完成: ' + passed + '/' + checks.length + ' 通过', passed === checks.length ? 'success' : 'error');
      } else {
        state.termData[body.path].push({ type: 'error', text: '[验证] 失败: ' + (data.error || '未知错误') }); log('验证失败: ' + (data.error || '未知错误'), 'error');
      }
      if (state.termData[body.path].length > 500) state.termData[body.path] = state.termData[body.path].slice(-500); renderTerminal(body.path);
    }).catch(function (e) { log('验证请求失败: ' + e, 'error'); });
}

/* ==================== 建议下一步 ==================== */
function doSuggestNext() {
  if (!state.curDev) { log('请先选择设备', 'error'); return; }
  log('分析设备进度: ' + (state.names[state.curDev] || state.curDev));
  fetch('/api/devices/suggest-next', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: state.curDev }) })
    .then(function (r) { return r.json(); }).then(function (data) {
      if (!data.success) { log('分析失败: ' + data.error, 'error'); return; }
      if (!state.termData[state.curDev]) state.termData[state.curDev] = [];
      state.termData[state.curDev].push({ type: 'system', text: '[建议] 设备: ' + data.device_name + ' (' + data.role + ') 进度: ' + data.progress + ' 阶段: ' + data.current_phase });
      if (data.completed_topics && data.completed_topics.length) state.termData[state.curDev].push({ type: 'output', text: '  已完成: ' + data.completed_topics.join(', ') });
      if (data.next_steps && data.next_steps.length) {
        state.termData[state.curDev].push({ type: 'output', text: '  下一步:' });
        data.next_steps.forEach(function (s, i) { state.termData[state.curDev].push({ type: 'output', text: '    ' + (i + 1) + '. ' + s }); });
      }
      if (state.termData[state.curDev].length > 500) state.termData[state.curDev] = state.termData[state.curDev].slice(-500);
      renderTerminal(state.curDev); log('进度分析完成', 'success');
    }).catch(function (e) { log('分析失败: ' + e, 'error'); });
}

/* ==================== 快照管理 ==================== */
function doSnapshot() {
  if (!state.curDev) { log('请先选择设备', 'error'); return; }
  showModalPrompt('快照标签（可选）:', '', function (label) {
    log('保存快照: ' + (state.names[state.curDev] || state.curDev));
    fetch('/api/devices/snapshot', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: state.curDev, label: label || null }) })
      .then(function (r) { return r.json(); }).then(function (data) {
        if (data.success) { log('快照已保存: ' + data.snapshot_id + ' (' + data.size + ' bytes)', 'success'); } else { log('快照失败: ' + data.error, 'error'); }
      }).catch(function (e) { log('快照失败: ' + e, 'error'); });
  });
}
function doListSnapshots() {
  if (!state.curDev) { log('请先选择设备', 'error'); return; }
  fetch('/api/devices/snapshots?path=' + encodeURIComponent(state.curDev)).then(function (r) { return r.json(); }).then(function (data) {
    if (!data.length) { log('暂无快照'); return; }
    log('快照列表 (' + data.length + ' 个):'); data.forEach(function (s) { log('  ' + s.snapshot_id + ' | ' + (s.label || '无标签') + ' | ' + s.timestamp); });
  }).catch(function (e) { log('查询失败: ' + e, 'error'); });
}

/* ==================== 实验管理 ==================== */
function showCreateExp() {
  document.getElementById('createExpModal').style.display = 'flex';
  document.getElementById('expName').value = ''; document.getElementById('expGoal').value = '';
  document.getElementById('expName').focus();
}
function closeCreateExp() { document.getElementById('createExpModal').style.display = 'none'; }
function confirmCreateExp() {
  var name = document.getElementById('expName').value.trim(); var goal = document.getElementById('expGoal').value.trim();
  if (!name) { log('请输入实验名称', 'error'); return; }
  fetch('/api/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name, goal: goal }) })
    .then(function (r) { return r.json(); }).then(function (data) {
      if (data.success || data.experiment_id) { log('实验已创建: ' + name, 'success'); closeCreateExp(); loadExperiments(); }
      else { log('创建失败: ' + (data.error || '未知错误'), 'error'); }
    }).catch(function (e) { log('创建失败: ' + e, 'error'); });
}
function loadExperiments() {
  fetch('/api/experiments').then(function (r) { return r.json(); }).then(function (data) {
    state.experiments = data.experiments || data || []; renderExperiments();
  }).catch(function (e) { log('加载实验失败: ' + e, 'error'); document.getElementById('expList').innerHTML = '<div style="text-align:center;color:var(--red);padding:20px">加载失败</div>'; });
}
function renderExperiments() {
  var el = document.getElementById('expList'); var countEl = document.getElementById('expCount'); if (!el) return;
  var exps = state.experiments; if (countEl) countEl.textContent = exps.length + ' 个实验';
  if (!exps.length) { el.innerHTML = '<div style="text-align:center;color:var(--overlay);padding:40px;font-size:13px"><span style="font-size:32px;display:block;margin-bottom:8px">🧪</span>暂无实验，点击「新建实验」开始</div>'; return; }
  var html = '';
  exps.forEach(function (exp) {
    var id = exp.experiment_id || exp.id; var name = exp.name || '未命名实验'; var goal = exp.goal || '';
    var created = exp.created_at || ''; var devices = exp.devices || {}; var devCount = typeof devices === 'object' ? Object.keys(devices).length : 0;
    var phases = exp.phase_history || [];
    html += '<div class="exp-card" onclick="viewExperiment(\'' + esc(id) + '\')">'
      + '<h3>' + esc(name) + ' <span class="badge badge-running">运行中</span></h3>'
      + (goal ? '<div class="exp-detail" style="margin-bottom:8px">' + esc(goal) + '</div>' : '')
      + '<div class="exp-detail"><span>🖥️ ' + devCount + ' 台设备</span> · <span>📋 ' + phases.length + ' 个阶段</span> · <span>🕐 ' + (created ? new Date(created).toLocaleString('zh-CN') : '未知') + '</span></div>';
    if (phases.length > 0) {
      html += '<div class="exp-phases">';
      phases.slice(-5).forEach(function (p) {
        var pName = p.name || p.phase || '未知阶段'; var pStatus = p.status || 'pending';
        var statusCls = pStatus === 'success' || pStatus === 'passed' ? 'pass' : (pStatus === 'failed' ? 'fail' : 'pending');
        html += '<div class="phase-item"><span>' + esc(pName) + '</span><span class="phase-status ' + statusCls + '">' + esc(pStatus) + '</span></div>';
      });
      if (phases.length > 5) html += '<div style="font-size:10px;color:var(--overlay);text-align:center;padding:2px">还有 ' + (phases.length - 5) + ' 个阶段...</div>';
      html += '</div>';
    }
    html += '</div>';
  });
  el.innerHTML = html;
}
function viewExperiment(expId) {
  state.curExp = expId;
  fetch('/api/experiments/' + expId).then(function (r) { return r.json(); }).then(function (data) {
    var el = document.getElementById('expList'); var exp = data;
    var name = exp.name || '未命名实验'; var goal = exp.goal || ''; var devices = exp.devices || {};
    var links = exp.links || []; var phases = exp.phase_history || [];
    var html = '<div style="margin-bottom:12px"><button class="btn btn-ghost btn-sm" onclick="loadExperiments()">← 返回列表</button></div>';
    html += '<div class="exp-card"><h3>' + esc(name) + '</h3>' + (goal ? '<div class="exp-detail" style="margin-bottom:8px">' + esc(goal) + '</div>' : '')
      + '<div class="exp-detail"><dt>设备 (' + Object.keys(devices).length + ')</dt>';
    Object.keys(devices).forEach(function (dp) {
      var dev = devices[dp]; html += '<dd>• ' + esc(dev.name || dp) + ' (' + (dev.device_type || '未知') + ') ' + (dev.connected ? '<span style="color:var(--green)">●</span>' : '<span style="color:var(--red)">●</span>') + '</dd>';
    });
    if (links.length > 0) { html += '<dt>链路 (' + links.length + ')</dt>'; links.forEach(function (l) { html += '<dd>• ' + esc(l.source || '') + ' ↔ ' + esc(l.target || '') + '</dd>'; }); }
    html += '</div></div>';
    html += '<div class="exp-card"><h3>📋 阶段历史</h3>';
    if (phases.length === 0) { html += '<div class="exp-detail">暂无阶段记录</div>'; }
    else {
      html += '<div class="exp-phases">';
      phases.forEach(function (p) {
        var pName = p.name || p.phase || '未知'; var pStatus = p.status || 'pending';
        var statusCls = pStatus === 'success' || pStatus === 'passed' ? 'pass' : (pStatus === 'failed' ? 'fail' : 'pending');
        html += '<div class="phase-item"><span>' + esc(pName) + '</span><span class="phase-status ' + statusCls + '">' + esc(pStatus) + '</span></div>';
      }); html += '</div>';
    }
    html += '</div>';
    html += '<div style="display:flex;gap:8px;margin-top:10px">'
      + '<button class="btn btn-teal btn-sm" onclick="execExpPlan(\'' + esc(expId) + '\')">▶ 执行计划</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="verifyExpDevice(\'' + esc(expId) + '\')">✅ 验证设备</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="viewExpDepGraph(\'' + esc(expId) + '\')">📊 依赖图</button></div>';
    el.innerHTML = html;
  }).catch(function (e) { log('获取实验详情失败: ' + e, 'error'); });
}
function execExpPlan(expId) {
  log('执行实验计划: ' + expId);
  fetch('/api/experiments/' + expId + '/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
    .then(function (r) { return r.json(); }).then(function (data) {
      if (data.success) { log('实验计划执行完成', 'success'); viewExperiment(expId); } else { log('执行失败: ' + (data.error || '未知错误'), 'error'); }
    }).catch(function (e) { log('执行失败: ' + e, 'error'); });
}
function verifyExpDevice(expId) {
  var path = state.curDev; if (!path) { log('请先在设备面板选择一台设备', 'error'); return; }
  log('验证实验设备: ' + path);
  fetch('/api/experiments/' + expId + '/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: path }) })
    .then(function (r) { return r.json(); }).then(function (data) {
      if (data.success) { log('验证完成', 'success'); viewExperiment(expId); } else { log('验证失败: ' + (data.error || '未知错误'), 'error'); }
    }).catch(function (e) { log('验证失败: ' + e, 'error'); });
}
function viewExpDepGraph(expId) {
  fetch('/api/experiments/dependency-graph').then(function (r) { return r.json(); }).then(function (data) {
    var el = document.getElementById('expList');
    var html = '<div style="margin-bottom:12px"><button class="btn btn-ghost btn-sm" onclick="viewExperiment(\'' + esc(expId) + '\')">← 返回</button></div>'
      + '<div class="exp-card"><h3>📊 实验阶段依赖图</h3><div class="cmd-output" style="max-height:500px;overflow-y:auto;white-space:pre-wrap;font-family:Consolas,monospace;font-size:11px">' + esc(JSON.stringify(data, null, 2)) + '</div></div>';
    el.innerHTML = html;
  }).catch(function (e) { log('获取依赖图失败: ' + e, 'error'); });
}

/* ==================== 知识库 ==================== */
function loadKb() {
  fetch('/api/kb/stats').then(function (r) { return r.json(); }).then(function (data) {
    var kb = data.knowledge_base || data;
    var skb = data.structured_kb || kb.structured_kb || {};
    var el = function (id) { return document.getElementById(id); };
    if (el('kbTotalCmds')) el('kbTotalCmds').textContent = data.catalog_size || kb.total_commands || kb.catalog_size || 0;
    if (el('kbDevCount')) el('kbDevCount').textContent = data.total_devices || kb.devices_count || 0;
    if (el('kbExpCount')) el('kbExpCount').textContent = skb.experiment_count || kb.experiences || 0;
    if (el('kbBpCount')) el('kbBpCount').textContent = skb.best_practice_count || kb.best_practices || 0;
    if (el('kbTsCount')) el('kbTsCount').textContent = skb.troubleshooting_count || kb.troubleshooting || 0;
  }).catch(function () {});
  loadKbStructured();
}
function switchKbTab(tab, el) {
  document.querySelectorAll('.kb-tab').forEach(function (t) { t.classList.remove('active'); });
  document.querySelectorAll('.kb-section').forEach(function (s) { s.classList.remove('active'); });
  if (el) el.classList.add('active');
  var m = { structured:'kbStructured', bestpractice:'kbBestpractice', experience:'kbExperience', troubleshoot:'kbTroubleshoot', configorder:'kbConfigorder', runtime:'kbRuntime', search:'kbSearch', templates:'kbTemplates', report:'kbReport' };
  var s = document.getElementById(m[tab]); if (s) s.classList.add('active');
  if (tab === 'bestpractice') loadKbBestPractice(); if (tab === 'experience') loadKbExperience();
  if (tab === 'troubleshoot') loadKbTroubleshoot(); if (tab === 'configorder') loadKbConfigOrder();
  if (tab === 'runtime') loadKbRuntime();
}
function switchKbView(view, el) {
  document.querySelectorAll('.view-sel-btn').forEach(function (b) { b.classList.remove('active'); });
  if (el) el.classList.add('active'); state.kbView = view; loadKbStructured();
}
function loadKbStructured() {
  fetch('/api/kb/structured').then(function (r) { return r.json(); }).then(function (data) {
    var content = document.getElementById('kbStructuredContent'); if (!content) return;
    var devSel = document.getElementById('kbDeviceSel');
    if (devSel) {
      var models = {};
      var views = data.views || {};
      Object.keys(views).forEach(function (vn) {
        var cats = (views[vn] || {}).categories || {};
        Object.keys(cats).forEach(function (cn) {
          var ms = (cats[cn] || {}).models || {};
          Object.keys(ms).forEach(function (m) { models[m] = true; });
        });
      });
      var dhtml = '<button class="device-sel-btn active" onclick="selectKbDevice(\'all\', this)">全部设备</button>';
      Object.keys(models).sort().forEach(function (model) {
        dhtml += '<button class="device-sel-btn" onclick="selectKbDevice(\'' + esc(model) + '\', this)">' + esc(model) + '</button>';
      });
      devSel.innerHTML = dhtml;
    }
    renderStructuredKb(data, content);
  }).catch(function () { var c = document.getElementById('kbStructuredContent'); if (c) c.innerHTML = '<div style="color:var(--red);padding:10px">加载失败</div>'; });
}
function selectKbDevice(model, el) {
  document.querySelectorAll('.device-sel-btn').forEach(function (b) { b.classList.remove('active'); });
  if (el) el.classList.add('active'); state.kbModel = model; loadKbStructured();
}
function renderStructuredKb(data, container) {
  var html = ''; var views = data.views || {};
  Object.keys(views).forEach(function (viewName) {
    if (state.kbView !== 'both' && viewName !== state.kbView) return;
    var viewData = views[viewName] || {};
    var viewLabel = viewName === 'user_view' ? '👤 用户视图 <>' : '⚙️ 系统视图 []';
    html += '<div style="margin-bottom:16px"><h3 style="font-size:14px;color:var(--blue);margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid var(--surface0)">' + viewLabel + '</h3>';
    var categories = viewData.categories || {};
    Object.keys(categories).forEach(function (catName) {
      var cat = categories[catName] || {};
      html += '<div style="margin-bottom:12px;margin-left:8px"><h4 style="font-size:12px;color:var(--mauve);margin-bottom:6px">📂 ' + esc(catName) + '</h4>';
      var models = cat.models || {};
      Object.keys(models).forEach(function (model) {
        if (state.kbModel !== 'all' && model !== state.kbModel) return;
        var modelData = models[model] || {};
        var cmds = modelData.commands || [];
        if (!cmds.length) return;
        html += '<div class="cmd-card"><div class="cmd-title"><span class="cmd-tag">' + esc(model) + '</span> <span style="font-size:10px;color:var(--overlay)">' + esc(modelData.description || '') + '</span></div><div class="cmd-output">';
        cmds.forEach(function (cmd) {
          var cmdText = cmd.cmd || cmd.command || '';
          var desc = cmd.desc || cmd.description || '';
          var when = cmd.when || '';
          html += esc(cmdText);
          if (desc) html += '  // ' + esc(desc);
          if (when) html += ' [' + esc(when) + ']';
          html += '\n';
        });
        html += '</div></div>';
      });
      html += '</div>';
    });
    var common = viewData.common;
    if (common && common.commands && common.commands.length) {
      html += '<div style="margin-bottom:12px;margin-left:8px"><h4 style="font-size:12px;color:var(--teal);margin-bottom:6px">📋 通用命令</h4>';
      html += '<div class="cmd-card"><div class="cmd-output">';
      common.commands.forEach(function (cmd) {
        var cmdText = cmd.cmd || cmd.command || '';
        var desc = cmd.desc || cmd.description || '';
        var short = cmd.short || '';
        html += esc(cmdText);
        if (short) html += ' (' + esc(short) + ')';
        if (desc) html += '  // ' + esc(desc);
        html += '\n';
      });
      html += '</div></div></div>';
    }
    html += '</div>';
  });
  if (!html) html = '<div style="color:var(--overlay);padding:10px">暂无结构化命令数据</div>';
  container.innerHTML = html;
}
function loadKbBestPractice() {
  fetch('/api/kb/structured').then(function (r) { return r.json(); }).then(function (data) {
    var el = document.getElementById('kbBpContent'); if (!el) return;
    var bp = data.best_practices || {};
    var rules = bp.command_rules || [];
    if (!rules.length) { el.innerHTML = '<div style="color:var(--overlay)">暂无操作规范</div>'; return; }
    var html = '';
    rules.forEach(function (item) {
      if (typeof item === 'string') { html += '<div class="cmd-card"><div class="cmd-output">' + esc(item) + '</div></div>'; return; }
      var title = item.rule || item.title || item.id || '';
      var detail = item.detail || item.description || '';
      var priority = item.priority || '';
      var priColor = priority === 'critical' ? 'var(--red)' : (priority === 'high' ? 'var(--yellow)' : 'var(--overlay)');
      html += '<div class="cmd-card"><div class="cmd-title"><span style="color:' + priColor + ';font-size:9px;padding:1px 5px;border-radius:3px;background:var(--surface0);margin-right:6px">' + esc(priority) + '</span>' + esc(title) + '</div>';
      html += '<div class="cmd-output">' + esc(detail) + '</div>';
      if (item.applies_to) html += '<div style="font-size:10px;color:var(--overlay);margin-top:4px">适用: ' + esc(item.applies_to) + '</div>';
      if (item.command) html += '<div style="font-size:10px;color:var(--teal);margin-top:2px">命令: ' + esc(item.command) + '</div>';
      html += '</div>';
    });
    el.innerHTML = html;
  }).catch(function () {});
}
function loadKbExperience() {
  fetch('/api/kb/structured').then(function (r) { return r.json(); }).then(function (data) {
    var el = document.getElementById('kbExpContent'); if (!el) return;
    var expData = data.experiments || {};
    var entries = [];
    if (Array.isArray(expData)) { entries = expData; }
    else if (typeof expData === 'object') {
      Object.keys(expData).forEach(function (k) {
        var v = expData[k];
        if (typeof v === 'object' && v !== null) { v._name = k; entries.push(v); }
      });
    }
    if (!entries.length) { el.innerHTML = '<div style="color:var(--overlay)">暂无实验经验</div>'; return; }
    var html = '';
    entries.forEach(function (item) {
      var name = item._name || item.name || item.title || '经验';
      html += '<div class="cmd-card"><div class="cmd-title">📝 ' + esc(name) + '</div>';
      if (item.commands) {
        html += '<div class="cmd-output">';
        (Array.isArray(item.commands) ? item.commands : [item.commands]).forEach(function (c) {
          html += (typeof c === 'string' ? esc(c) : esc(JSON.stringify(c))) + '\n';
        });
        html += '</div>';
      }
      if (item.verify) html += '<div style="font-size:10px;color:var(--teal);margin-top:4px">验证: ' + esc(item.verify) + '</div>';
      if (item.description) html += '<div style="font-size:11px;color:var(--subtext);margin-top:4px">' + esc(item.description) + '</div>';
      html += '</div>';
    });
    el.innerHTML = html;
  }).catch(function () {});
}
function loadKbTroubleshoot() {
  fetch('/api/kb/troubleshooting').then(function (r) { return r.json(); }).then(function (data) {
    var el = document.getElementById('kbTsContent'); if (!el) return;
    var items = [];
    if (Array.isArray(data)) { items = data; }
    else if (data.cases) { items = Array.isArray(data.cases) ? data.cases : []; }
    else if (typeof data === 'object') {
      Object.keys(data).forEach(function (k) {
        if (typeof data[k] === 'object' && data[k] !== null) { data[k]._name = k; items.push(data[k]); }
      });
    }
    if (!items.length) { el.innerHTML = '<div style="color:var(--overlay)">暂无排障案例</div>'; return; }
    var html = '';
    items.forEach(function (item) {
      var symptom = item.symptom || item._name || item.title || '';
      var cause = item.cause || '';
      var fix = item.fix || item.solution || '';
      var verify = item.verify || '';
      var commands = item.commands || '';
      html += '<div class="cmd-card"><div class="cmd-title">🔧 ' + esc(symptom) + '</div>';
      if (cause) html += '<div style="font-size:11px;color:var(--peach);margin-bottom:4px">原因: ' + esc(cause) + '</div>';
      if (fix) html += '<div style="font-size:11px;color:var(--green);margin-bottom:4px">修复: ' + esc(fix) + '</div>';
      if (verify) html += '<div style="font-size:10px;color:var(--teal);margin-bottom:2px">验证: ' + esc(verify) + '</div>';
      if (commands) html += '<div class="cmd-output" style="margin-top:4px">' + esc(commands) + '</div>';
      html += '</div>';
    });
    el.innerHTML = html;
  }).catch(function () {});
}
function loadKbConfigOrder() {
  fetch('/api/kb/config-order').then(function (r) { return r.json(); }).then(function (data) {
    var el = document.getElementById('kbCoContent'); if (!el) return;
    var order = data.order || data.config_order || data || [];
    if (!order.length) { el.innerHTML = '<div style="color:var(--overlay)">暂无配置顺序</div>'; return; }
    var html = '<div class="cmd-card"><div class="cmd-title">📋 推荐配置顺序</div><div class="cmd-output">';
    if (Array.isArray(order)) { order.forEach(function (item, i) { html += (i + 1) + '. ' + esc(typeof item === 'string' ? item : JSON.stringify(item)) + '\n'; }); }
    else { html += esc(JSON.stringify(order, null, 2)); }
    html += '</div></div>'; el.innerHTML = html;
  }).catch(function () {});
}
function loadKbRuntime() {
  var cat = document.getElementById('kbCatF').value;
  fetch('/api/kb/commands' + (cat ? '?category=' + cat : '')).then(function (r) { return r.json(); }).then(function (data) {
    var el = document.getElementById('kbList'); if (!el) return;
    var cmds = data.commands || data || [];
    if (!cmds.length) { el.innerHTML = '<div style="color:var(--overlay)">暂无记录</div>'; return; }
    var html = ''; cmds.slice(0, 100).forEach(function (cmd) {
      html += '<div class="cmd-card" style="padding:6px 10px"><span class="cmd-tag">' + esc(cmd.category || '') + '</span> <span style="font-size:11px">' + esc(cmd.command || cmd.name || '') + '</span>' + (cmd.description ? ' <span style="color:var(--overlay);font-size:10px">' + esc(cmd.description) + '</span>' : '') + '</div>';
    }); el.innerHTML = html;
  }).catch(function () {});
}
function doKbSearch() {
  var q = document.getElementById('kbSearchInput').value.trim(); if (!q) return;
  fetch('/api/kb/search?q=' + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (data) {
    var el = document.getElementById('kbSearchContent'); if (!el) return;
    var results = data.results || data || [];
    if (!results.length) { el.innerHTML = '<div style="color:var(--overlay);padding:10px">未找到匹配结果</div>'; return; }
    var html = '<div style="font-size:11px;color:var(--overlay);margin-bottom:8px">找到 ' + results.length + ' 条结果</div>';
    results.forEach(function (item) { html += '<div class="cmd-card"><div class="cmd-title">' + esc(item.command || item.name || '') + '</div><div class="cmd-output">' + esc(item.description || item.content || JSON.stringify(item)) + '</div></div>'; });
    el.innerHTML = html;
  }).catch(function (e) { log('搜索失败: ' + e, 'error'); });
}
function loadKbTemplate() {
  var type = document.getElementById('kbTplType').value;
  fetch('/api/kb/template?type=' + type).then(function (r) { return r.json(); }).then(function (data) {
    var el = document.getElementById('kbTemplateContent'); if (!el) return;
    if (data.commands || data.template) {
      var cmds = data.commands || data.template || [];
      var html = '<div class="cmd-card"><div class="cmd-title">📄 ' + esc(type.toUpperCase()) + ' 配置模板</div><div class="cmd-output">';
      if (Array.isArray(cmds)) { cmds.forEach(function (c) { html += esc(typeof c === 'string' ? c : JSON.stringify(c)) + '\n'; }); }
      else { html += esc(JSON.stringify(cmds, null, 2)); }
      html += '</div></div>'; el.innerHTML = html;
    } else { el.innerHTML = '<div style="color:var(--overlay)">暂无模板</div>'; }
  }).catch(function (e) { log('模板加载失败: ' + e, 'error'); });
}
function genLabReport() {
  var name = (document.getElementById('kbReportName') || {}).value || 'eNSP Lab Report';
  fetch('/api/kb/lab-report?name=' + encodeURIComponent(name)).then(function (r) { return r.json(); }).then(function (data) {
    var el = document.getElementById('kbReportContent'); if (!el) return;
    var html = '<div class="cmd-card"><div class="cmd-title">📊 ' + esc(name) + '</div>';
    if (data.markdown) html += '<div class="cmd-output" style="max-height:500px;white-space:pre-wrap">' + esc(data.markdown) + '</div>';
    if (data.knowledge_base) html += '<div style="font-size:10px;color:var(--overlay);margin-top:6px">命令: ' + (data.knowledge_base.total_commands || 0) + ' | 经验: ' + (data.knowledge_base.experiences || 0) + ' | 排障: ' + (data.knowledge_base.troubleshooting || 0) + '</div>';
    html += '</div>'; el.innerHTML = html; log('实验报告已生成', 'success');
  }).catch(function (e) { log('报告生成失败: ' + e, 'error'); });
}

/* ==================== 拓扑管理 ==================== */
function loadTopo() {
  fetch('/api/topology').then(function (r) { return r.json(); }).then(function (data) {
    state.topoSummary = data;
    var sumEl = document.getElementById('topoSummary');
    if (sumEl) sumEl.textContent = (data.node_count || 0) + ' 个节点, ' + (data.link_count || 0) + ' 条链路';
    renderTopo();
  }).catch(function () {
    var canvas = document.getElementById('topoCanvas');
    if (canvas) canvas.innerHTML = '<div style="text-align:center;color:var(--overlay);padding:40px">暂无拓扑数据，请先上传 .topo 文件</div>';
  });
}
function renderTopo() {
  var canvas = document.getElementById('topoCanvas'); if (!canvas || !state.topoSummary) return;
  var data = state.topoSummary; var nodes = data.nodes || []; var links = data.links || [];
  if (!nodes.length) { canvas.innerHTML = '<div style="text-align:center;color:var(--overlay);padding:40px">暂无拓扑节点</div>'; return; }
  var html = ''; var cx = canvas.clientWidth / 2 || 400; var cy = canvas.clientHeight / 2 || 300;
  var r = Math.min(cx, cy) * 0.6; var nodePositions = {};
  nodes.forEach(function (node, i) {
    var angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
    var x = cx + r * Math.cos(angle); var y = cy + r * Math.sin(angle);
    nodePositions[node.id] = { x: x, y: y };
    var roleClass = ''; var type = (node.type || '').toLowerCase();
    if (type.includes('core') || type.includes('核心')) roleClass = 'core';
    else if (type.includes('distribution') || type.includes('汇聚')) roleClass = 'distribution';
    else if (type.includes('access') || type.includes('接入')) roleClass = 'access';
    else if (type.includes('router') || type.includes('路由')) roleClass = 'router';
    html += '<div class="topo-node ' + roleClass + '" style="left:' + (x - 40) + 'px;top:' + (y - 16) + 'px" onclick="showTopoDevice(\'' + esc(node.id) + '\')" title="' + esc(node.id) + '">' + esc(node.name || node.id) + '</div>';
  });
  html += '<svg style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:-1">';
  links.forEach(function (link) {
    var sp = nodePositions[link.source]; var tp = nodePositions[link.target];
    if (sp && tp) html += '<line x1="' + sp.x + '" y1="' + sp.y + '" x2="' + tp.x + '" y2="' + tp.y + '" stroke="#45475a" stroke-width="2"/>';
  });
  html += '</svg>'; canvas.innerHTML = html;
}
function showTopoDevice(nid) {
  var info = document.getElementById('topoInfo'); if (!info) return;
  fetch('/api/topology/device/' + encodeURIComponent(nid)).then(function (r) { return r.json(); }).then(function (data) {
    var html = '<strong>' + esc(data.name || nid) + '</strong>';
    if (data.neighbors && data.neighbors.length) html += ' — 连接: ' + data.neighbors.map(function (n) { return n.target_name || n.target; }).join(', ');
    info.innerHTML = html;
  }).catch(function () { info.textContent = nid; });
}

/* ==================== 页面初始化 ==================== */
document.addEventListener('DOMContentLoaded', function () {
  var topoIn = document.getElementById('topoIn');
  if (topoIn) {
    topoIn.addEventListener('change', function (e) {
      var file = e.target.files[0]; if (!file) return;
      var formData = new FormData(); formData.append('file', file);
      log('上传拓扑文件: ' + file.name);
      fetch('/api/topology/file', { method: 'POST', body: formData })
        .then(function (r) { return r.json(); }).then(function (data) {
          if (data.success) { log('拓扑上传成功: ' + (data.node_count || 0) + ' 节点', 'success'); loadTopo(); }
          else { log('拓扑上传失败: ' + (data.error || '未知错误'), 'error'); }
        }).catch(function (e) { log('上传失败: ' + e, 'error'); });
      topoIn.value = '';
    });
  }
  var si = document.getElementById('kbSearchInput');
  if (si) si.addEventListener('keydown', function (e) { if (e.key === 'Enter') doKbSearch(); });
  var ri = document.getElementById('renameInput');
  if (ri) ri.addEventListener('keydown', function (e) { if (e.key === 'Enter') confirmRM(); if (e.key === 'Escape') closeRM(); });
  var en = document.getElementById('expName');
  if (en) en.addEventListener('keydown', function (e) { if (e.key === 'Enter') document.getElementById('expGoal').focus(); });
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey && e.key === 'k') { e.preventDefault(); sw('kb'); setTimeout(function () { var s = document.getElementById('kbSearchInput'); if (s) s.focus(); }, 100); }
    if (e.ctrlKey && e.shiftKey && e.key === 'S') { e.preventDefault(); doScan(); }
  });
});
window.addEventListener('load', function () {
  log('eNSP MCP 平台已就绪');
  log('提示: Ctrl+K 搜索知识库 | Ctrl+Shift+S 扫描设备');
});

