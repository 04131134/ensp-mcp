import re
path = 'E:/eNSP-MCP/mcpensp1/app.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if line.startswith('from flask_socketio import SocketIO, emit, join_room'):
        if 'from experiment_engine import ExperimentEngine' not in ''.join(lines[:40]):
            lines.insert(i+1, 'from experiment_engine import ExperimentEngine\n')
        break
for i, line in enumerate(lines):
    if line.strip() == 'heartbeat = HeartbeatMonitor(kb)':
        if 'experiment_engine = ExperimentEngine(' not in ''.join(lines[i:i+20]):
            lines.insert(i+1, "experiment_engine = ExperimentEngine(lambda p, c: send_command(p, c))\n")
        break
marker = 'if __name__ == "__main__":'
for idx, line in enumerate(lines):
    if line.strip() == marker:
        block = []
        block.append('\n@app.route("/api/experiments", methods=["POST"])\n@require_auth\n@rate_limit\ndef api_create_experiment():\n    data = request.get_json(silent=True) or {}\n    if not data.get("experiment_id") or not data.get("name"):\n        return jsonify({"success": False, "error": "experiment_id and name required"}), 400\n    state = experiment_engine.create_experiment(data["experiment_id"], data["name"], data.get("goal", ""), data.get("devices"), data.get("topology"), data.get("constraints"))\n    return jsonify({"success": True, "experiment": state.snapshot()})\n')
        block.append('\n@app.route("/api/experiments", methods=["GET"])\n@require_auth\ndef api_list_experiments():\n    return jsonify(experiment_engine.list_experiments())\n')
        block.append('\n@app.route("/api/experiments/<experiment_id>", methods=["GET"])\n@require_auth\ndef api_get_experiment(experiment_id):\n    try:\n        return jsonify(experiment_engine.get_experiment(experiment_id).snapshot())\n    except KeyError as e:\n        return jsonify({"success": False, "error": str(e)}), 404\n')
        block.append('\n@app.route("/api/experiments/<experiment_id>/device", methods=["POST"])\n@require_auth\n@rate_limit\ndef api_update_experiment_device(experiment_id):\n    data = request.get_json(silent=True) or {}\n    path = data.get("path")\n    if not path:\n        return jsonify({"success": False, "error": "path required"}), 400\n    device = experiment_engine.update_device(experiment_id, path, **{k: v for k, v in data.items() if k != "path"})\n    return jsonify({"success": True, "device": device.to_dict()})\n')
        block.append('\n@app.route("/api/experiments/<experiment_id>/interface", methods=["POST"])\n@require_auth\n@rate_limit\ndef api_update_experiment_interface(experiment_id):\n    data = request.get_json(silent=True) or {}\n    path, iface = data.get("path"), data.get("interface")\n    if not path or not iface:\n        return jsonify({"success": False, "error": "path and interface required"}), 400\n    state = experiment_engine.update_interface(experiment_id, path, iface, **{k: v for k, v in data.items() if k not in {"path", "interface"}})\n    return jsonify({"success": True, "interface": state.to_dict()})\n')
        block.append('\n@app.route("/api/experiments/<experiment_id>/protocol", methods=["POST"])\n@require_auth\n@rate_limit\ndef api_record_experiment_protocol(experiment_id):\n    data = request.get_json(silent=True) or {}\n    if not data.get("path") or not data.get("protocol"):\n        return jsonify({"success": False, "error": "path and protocol required"}), 400\n    experiment_engine.record_protocol_state(experiment_id, data["path"], data["protocol"], data.get("state"))\n    return jsonify({"success": True})\n')
        block.append('\n@app.route("/api/experiments/<experiment_id>/link", methods=["POST"])\n@require_auth\n@rate_limit\ndef api_add_experiment_link(experiment_id):\n    data = request.get_json(silent=True) or {}\n    if not data:\n        return jsonify({"success": False, "error": "link data required"}), 400\n    experiment_engine.add_link(experiment_id, data)\n    return jsonify({"success": True})\n')
        block.append('\n@app.route("/api/experiments/<experiment_id>/execute", methods=["POST"])\n@require_auth\n@rate_limit\ndef api_execute_experiment_phase(experiment_id):\n    data = request.get_json(silent=True) or {}\n    phase_id = data.pop("phase_id", None)\n    if not phase_id:\n        return jsonify({"success": False, "error": "phase_id required"}), 400\n    result = experiment_engine.execute_phase(experiment_id, phase_id, data, auto_verify=data.get("auto_verify", True), dry_run=data.get("dry_run", False))\n    return jsonify(result)\n')
        block.append('\n@app.route("/api/experiments/<experiment_id>/plan", methods=["POST"])\n@require_auth\n@rate_limit\ndef api_execute_experiment_plan(experiment_id):\n    data = request.get_json(silent=True) or {}\n    ordered = data.get("ordered_phases", [])\n    if not ordered:\n        return jsonify({"success": False, "error": "ordered_phases required"}), 400\n    result = experiment_engine.execute_plan(experiment_id, ordered, data.get("context", {}), auto_verify=data.get("auto_verify", True), max_retries=data.get("max_retries", 1))\n    return jsonify(result)\n')
        block.append('\n@app.route("/api/experiments/<experiment_id>/verify", methods=["POST"])\n@require_auth\n@rate_limit\ndef api_verify_experiment_device(experiment_id):\n    data = request.get_json(silent=True) or {}\n    path = data.get("path")\n    if not path:\n        return jsonify({"success": False, "error": "path required"}), 400\n    checks = experiment_engine.verify_device(experiment_id, path, data.get("checks"), data.get("target_ip"))\n    return jsonify({"success": True, "checks": [c.__dict__ for c in checks]})\n')
        block.append('\n@app.route("/api/experiments/phases", methods=["GET"])\n@require_auth\ndef api_experiment_phases():\n    return jsonify(experiment_engine.planner.list_phases())\n')
        block.append('\n@app.route("/api/experiments/dependency-graph", methods=["GET"])\n@require_auth\ndef api_experiment_dependency_graph():\n    return jsonify(experiment_engine.build_dependency_graph())\n')
        lines.insert(idx, '\n'.join(block))
        break
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('patched')
