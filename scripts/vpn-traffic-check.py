#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vpn-traffic-check.py — единый скрипт трафика + блокировки.
1. Собирает трафик с мастера (iptables) + всех нод (SSH)
2. Пишет traffic_used в БД
3. При превышении лимита — блокирует на мастере + всех нодах
4. Разблокирует, если админ поднял лимит
"""
import os
import sys
import sqlite3
import subprocess
import logging

sys.path.insert(0, '/usr/local/bin')

DB = "/etc/UDPCustom/vpn.db"
TRAFFIC_DIR = "/etc/UDPCustom/traffic"
TRAFFIC_CHAIN = "VPN_TRAFFIC"
USERS_DB = "/etc/UDPCustom/users.db"
LOG = "/var/log/vpn-traffic-check.log"

logging.basicConfig(
    filename=LOG, level=logging.INFO,
    format='%(asctime)s [CHECK] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def read_users():
    if not os.path.isfile(USERS_DB):
        return []
    with open(USERS_DB) as f:
        return [u.strip() for u in f if u.strip()]


def read_master_counters():
    """Возвращает {login: delta_bytes} с iptables."""
    users = read_users()
    if not users:
        return {}
    uid_to_user = {}
    for u in users:
        r = subprocess.run(['id', '-u', u], capture_output=True, text=True)
        if r.returncode == 0:
            try:
                uid_to_user[int(r.stdout.strip())] = u
            except ValueError:
                pass
    if not uid_to_user:
        return {}
    r = subprocess.run(
        ['iptables', '-L', TRAFFIC_CHAIN, '-v', '-x', '-n'],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        return {}
    result = {}
    for line in r.stdout.splitlines():
        if 'owner UID match' not in line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            bytes_val = int(parts[1])
            uid = int(parts[-1])
        except (ValueError, IndexError):
            continue
        if uid in uid_to_user:
            result[uid_to_user[uid]] = bytes_val
    return result


def update_master_files():
    """Обновляет cumulative-файлы мастера, возвращает {login: total_bytes}."""
    deltas = read_master_counters()
    os.makedirs(TRAFFIC_DIR, exist_ok=True)
    for login, delta in deltas.items():
        path = os.path.join(TRAFFIC_DIR, login)
        prev = 0
        if os.path.isfile(path):
            try:
                prev = int(open(path).read().strip() or 0)
            except ValueError:
                prev = 0
        with open(path, 'w') as f:
            f.write(str(prev + delta))
    if deltas:
        subprocess.run(['iptables', '-Z', TRAFFIC_CHAIN], capture_output=True)
    result = {}
    if os.path.isdir(TRAFFIC_DIR):
        for fname in os.listdir(TRAFFIC_DIR):
            path = os.path.join(TRAFFIC_DIR, fname)
            if os.path.isfile(path):
                try:
                    result[fname] = int(open(path).read().strip() or 0)
                except ValueError:
                    result[fname] = 0
    return result


def collect_node_traffic():
    try:
        from bot_modules import nodes_client as nc
        return nc.collect_traffic_from_all_nodes()
    except Exception as e:
        logging.error(f"collect_node_traffic: {e}")
        return {}


def get_lock_state(user):
    """'locked' если shell = nologin, иначе 'active' (или 'missing')."""
    try:
        import pwd
        shell = pwd.getpwnam(user).pw_shell
        if shell in ('/usr/sbin/nologin', '/sbin/nologin'):
            return 'locked'
        return 'active'
    except KeyError:
        return 'missing'


def set_lock_state(user, state):
    if state == 'locked':
        subprocess.run(['usermod', '-L', user], capture_output=True)
        subprocess.run(['usermod', '-s', '/usr/sbin/nologin', user], capture_output=True)
        subprocess.run(['pkill', '-KILL', '-u', user], capture_output=True)
    else:
        subprocess.run(['usermod', '-U', user], capture_output=True)
        subprocess.run(['usermod', '-s', '/bin/false', user], capture_output=True)


def sync_lock_to_nodes(user, action):
    """action: 'lock' | 'unlock'"""
    try:
        from bot_modules import nodes_client as nc
        con = sqlite3.connect(DB)
        rows = con.execute(
            "SELECT id FROM nodes WHERE is_active=1 AND is_master=0"
        ).fetchall()
        con.close()
        for (node_id,) in rows:
            online, _ = nc.node_check(node_id)
            if not online:
                continue
            nc._run_on_node(node_id, action, user)
    except Exception as e:
        logging.error(f"sync_lock_to_nodes {action} {user}: {e}")



def ensure_traffic_chain():
    """Проверяет цепочку VPN_TRAFFIC. Если нет — создаёт + правила. Защита от ufw reset."""
    users = read_users()
    uid_map = {}
    for u in users:
        r = subprocess.run(['id', '-u', u], capture_output=True, text=True)
        if r.returncode == 0:
            try:
                uid_map[u] = int(r.stdout.strip())
            except ValueError:
                pass

    # Проверка: существует ли цепочка
    check = subprocess.run(['iptables', '-L', TRAFFIC_CHAIN, '-n'],
                           capture_output=True, text=True)
    if check.returncode != 0:
        # Создаём
        subprocess.run(['iptables', '-N', TRAFFIC_CHAIN], capture_output=True)
        logging.info(f"Self-heal: создана цепочка {TRAFFIC_CHAIN}")
        # Вставляем в OUTPUT
        subprocess.run(['iptables', '-I', 'OUTPUT', '-j', TRAFFIC_CHAIN], capture_output=True)

    # Проверка: есть ли ссылка из OUTPUT
    link = subprocess.run(['iptables', '-C', 'OUTPUT', '-j', TRAFFIC_CHAIN],
                          capture_output=True)
    if link.returncode != 0:
        subprocess.run(['iptables', '-I', 'OUTPUT', '-j', TRAFFIC_CHAIN], capture_output=True)
        logging.info(f"Self-heal: добавлено правило OUTPUT -> {TRAFFIC_CHAIN}")

    # Проверка/добавление правил для юзеров
    cur = subprocess.run(['iptables', '-L', TRAFFIC_CHAIN, '-n'],
                         capture_output=True, text=True)
    cur_uids = set()
    if cur.returncode == 0:
        for line in cur.stdout.splitlines():
            if 'owner UID match' in line:
                try:
                    cur_uids.add(int(line.split()[-1]))
                except (ValueError, IndexError):
                    pass

    added = 0
    for u, uid in uid_map.items():
        if uid in cur_uids:
            continue
        subprocess.run(['iptables', '-A', TRAFFIC_CHAIN,
                        '-m', 'owner', '--uid-owner', str(uid),
                        '-j', 'RETURN'], capture_output=True)
        added += 1
    if added:
        logging.info(f"Self-heal: добавлено {added} правил uid-owner")

def main():
    if not os.path.exists(DB):
        return
    try:
        ensure_traffic_chain()
    except Exception as e:
        logging.error(f"ensure_traffic_chain: {e}")

    master = update_master_files()
    nodes = collect_node_traffic()

    total = {}
    for login, b in master.items():
        total[login] = total.get(login, 0) + int(b)
    for login, b in nodes.items():
        total[login] = total.get(login, 0) + int(b)

    con = sqlite3.connect(DB, timeout=15)
    c = con.cursor()
    updated = locked = unlocked = 0
    try:
        for login, used in total.items():
            row = c.execute(
                "SELECT traffic_limit FROM vip_keys WHERE login=?", (login,)
            ).fetchone()
            if not row:
                row = c.execute(
                    "SELECT traffic_limit FROM test_keys WHERE login=?", (login,)
                ).fetchone()
            if not row:
                continue
            limit = row[0] or 0

            r1 = c.execute(
                "UPDATE test_keys SET traffic_used=? WHERE login=? AND traffic_used!=?",
                (used, login, used)
            )
            r2 = c.execute(
                "UPDATE vip_keys SET traffic_used=? WHERE login=? AND traffic_used!=?",
                (used, login, used)
            )
            if (r1.rowcount or 0) + (r2.rowcount or 0) > 0:
                updated += 1

            if limit > 0 and used >= limit:
                if get_lock_state(login) != 'locked':
                    set_lock_state(login, 'locked')
                    sync_lock_to_nodes(login, 'lock')
                    locked += 1
                    logging.info(f"LOCKED {login}: {used}/{limit}")
            else:
                if get_lock_state(login) == 'locked':
                    set_lock_state(login, 'active')
                    sync_lock_to_nodes(login, 'unlock')
                    unlocked += 1
                    logging.info(f"UNLOCKED {login}: {used}/{limit}")

        con.commit()
        logging.info(f"traffic: updated={updated} locked={locked} unlocked={unlocked} | master={len(master)} nodes={len(nodes)}")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
    finally:
        con.close()


if __name__ == '__main__':
    main()
