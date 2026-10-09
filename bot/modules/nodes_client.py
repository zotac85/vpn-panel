"""nodes_client.py - работа бота с нодами (SSH + node-user.sh)"""
import subprocess
import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = "/etc/UDPCustom/vpn.db"
SSH_KEY = "/root/.ssh/id_ed25519"
SSH_OPTS = [
    "-i", SSH_KEY,
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=8",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
]


def _get_node(node_id):
    """Возвращает (name, host, ip, ssh_port, ws_port, ssh_user) или None."""
    try:
        db = sqlite3.connect(DB_PATH)
        r = db.execute(
            "SELECT name, host, ip, ssh_port, ws_port, ssh_user FROM nodes WHERE id=? AND is_active=1",
            (int(node_id),)
        ).fetchone()
        db.close()
        return r
    except Exception as e:
        logger.error(f"_get_node({node_id}): {e}")
        return None


def get_all_active_nodes(include_master=True):
    """Список всех активных нод. Если include_master=False — только ноды (без мастера)."""
    try:
        db = sqlite3.connect(DB_PATH)
        q = "SELECT id, name, host, ip, ssh_port, ws_port, is_master FROM nodes WHERE is_active=1"
        if not include_master:
            q += " AND is_master=0"
        rows = db.execute(q + " ORDER BY is_master DESC, id").fetchall()
        db.close()
        return rows
    except Exception as e:
        logger.error(f"get_all_active_nodes: {e}")
        return []


def _run_on_node(node_id, *args, timeout=15):
    """Выполняет node-user.sh <args> на ноде по SSH. Возвращает (rc, stdout, stderr)."""
    node = _get_node(node_id)
    if not node:
        return (-1, "", "node not found")
    name, host, ip, ssh_port, ws_port, ssh_user = node
    cmd = ["ssh"] + SSH_OPTS + ["-p", str(ssh_port), f"{ssh_user}@{ip}", "node-user.sh"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.returncode, r.stdout.strip(), r.stderr.strip())
    except subprocess.TimeoutExpired:
        return (-1, "", "timeout")
    except Exception as e:
        return (-1, "", str(e))


def node_add_user(node_id, username, password, device_limit=None):
    rc, out, err = _run_on_node(node_id, "add", username, password)
    if rc != 0 or "OK" not in out:
        return (False, err or out or "unknown error")
    # Устанавливаем лимит устройств
    if device_limit is not None:
        try:
            dl = int(device_limit)
            _run_on_node(node_id, "setlimit", username, str(dl))
        except Exception as e:
            logger.error(f"setlimit {username}={device_limit}: {e}")
    return (True, out)


def node_del_user(node_id, username):
    rc, out, err = _run_on_node(node_id, "del", username)
    if rc == 0:
        return (True, out)
    return (False, err or out)


def node_passwd(node_id, username, password):
    rc, out, err = _run_on_node(node_id, "passwd", username, password)
    if rc == 0:
        return (True, out)
    return (False, err or out)


def node_list_users(node_id):
    rc, out, err = _run_on_node(node_id, "list")
    if rc == 0:
        return [u for u in out.splitlines() if u.strip()]
    return []


def node_get_traffic(node_id):
    """Возвращает dict {username: bytes} или {} при ошибке."""
    import json
    rc, out, err = _run_on_node(node_id, "traffic-all", timeout=20)
    if rc != 0 or not out:
        return {}
    try:
        return json.loads(out)
    except Exception:
        return {}


def node_check(node_id):
    """Проверка онлайн. Возвращает (online: bool, latency_ms: int)."""
    node = _get_node(node_id)
    if not node:
        return (False, 0)
    name, host, ip, ssh_port, ws_port, ssh_user = node
    import time
    t0 = time.time()
    try:
        r = subprocess.run(
            ["ssh"] + SSH_OPTS + ["-p", str(ssh_port), f"{ssh_user}@{ip}", "echo", "OK"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 and "OK" in r.stdout:
            return (True, int((time.time() - t0) * 1000))
    except Exception:
        pass
    return (False, 0)


def sync_user_to_all_nodes(username, password, action="add", device_limit=None):
    """Синхронизирует юзера на все активные ноды (кроме мастера).
    action: 'add' | 'del' | 'passwd'
    device_limit: количество устройств (только для action='add')
    Возвращает dict {node_name: (success, msg)}.
    """
    results = {}
    for node_id, name, host, ip, ssh_port, ws_port, is_master in get_all_active_nodes():
        if is_master:
            continue
        if action == "add":
            ok, msg = node_add_user(node_id, username, password, device_limit=device_limit)
        elif action == "del":
            ok, msg = node_del_user(node_id, username)
        elif action == "passwd":
            ok, msg = node_passwd(node_id, username, password)
        else:
            ok, msg = (False, f"unknown action: {action}")
        results[name] = (ok, msg)
        logger.info(f"sync_user_to_all_nodes {action} {username} -> {name}: {ok} {msg}")
    return results


def collect_traffic_from_all_nodes():
    """Суммарный трафик {username: bytes} со всех активных нод (включая мастера)."""
    total = {}
    for node_id, name, host, ip, ssh_port, ws_port, is_master in get_all_active_nodes():
        if is_master:
            continue
        data = node_get_traffic(node_id)
        for user, bytes_val in data.items():
            try:
                total[user] = total.get(user, 0) + int(bytes_val)
            except Exception:
                pass
    return total
