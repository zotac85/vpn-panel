#!/usr/bin/env python3
import sqlite3
import uuid
import json
import sys
import subprocess
import urllib.parse

DB_PATH = '/etc/UDPCustom/vpn.db'
XRAY_CONFIG = '/usr/local/etc/xray/config.json'
WS_PATH = "/trojan-ws"

def get_cf_settings():
    """Читает актуальные настройки из БД и proxies.txt"""
    cf_ip = "104.18.0.3"
    sni = "ruzone27.shop"
    port = 443

    try:
        db = sqlite3.connect(DB_PATH)
        settings = dict(db.execute("SELECT key, value FROM settings").fetchall())
        db.close()
    except:
        settings = {}

    # 1. Прокси (IP) из proxies.txt (первая строка)
    try:
        with open('/etc/UDPCustom/proxies.txt', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    cf_ip = line.split(':')[0]
                    break
    except:
        if 'TLS_PROXY' in settings:
            cf_ip = settings['TLS_PROXY'].split(':')[0]

    # 2. SNI из settings
    if 'TLS_SNI' in settings:
        sni = settings['TLS_SNI']

    # 3. Порт из settings (по умолчанию 443)
    if 'TLS_PROXY' in settings and ':' in settings['TLS_PROXY']:
        try:
            port = int(settings['TLS_PROXY'].split(':')[1])
        except:
            pass

    return cf_ip, sni, port

def get_trojan_link(login, node_selector="master"):
    """
    Генерирует trojan:// ссылку для VIP-юзера.
    node_selector: "master" | N (порядковый номер) | host | подстрока имени
    Если node_selector != master — авто-push пароля через xray-push-password.sh
    """
    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()

    row = cursor.execute("SELECT trojan_password FROM vip_keys WHERE login=?", (login,)).fetchone()
    if not row:
        db.close()
        return "NOT_FOUND"

    password = row[0]
    if not password:
        password = str(uuid.uuid4()).replace('-', '')[:16]
        cursor.execute("UPDATE vip_keys SET trojan_password=? WHERE login=?", (password, login))
        db.commit()

    node_host = "de.ruzone27.shop"
    need_push = False
    push_target = None

    if node_selector and node_selector not in ("master", "", None):
        rows = cursor.execute("SELECT id,name,host,tls_host,ip,is_master FROM nodes ORDER BY is_master DESC, id").fetchall()
        chosen = None
        if node_selector.isdigit():
            idx = int(node_selector) - 1
            if 0 <= idx < len(rows):
                chosen = rows[idx]
        if not chosen:
            for r in rows:
                if (r[2] and node_selector == r[2]) or (r[3] and node_selector == r[3]) or (r[4] and node_selector == r[4]) or node_selector in str(r[1]):
                    chosen = r
                    break
        if not chosen:
            db.close()
            return "NODE_NOT_FOUND"
        node_host = chosen[3] or chosen[2] or "de.ruzone27.shop"
        if chosen[5] != 1:
            need_push = True
            push_target = chosen[4]   # IP — однозначный идентификатор
    db.close()

    if need_push and push_target:
        try:
            res = subprocess.run(
                ['/usr/local/bin/xray-push-password.sh', login, push_target],
                capture_output=True, text=True, timeout=30
            )
            if res.returncode != 0:
                print(f"[gen_trojan] WARN push: {res.stdout.strip()} {res.stderr.strip()}", file=sys.stderr)
        except Exception as e:
            print(f"[gen_trojan] WARN push: {e}", file=sys.stderr)

    try:
        with open(XRAY_CONFIG, 'r') as f:
            config = json.load(f)
        clients = config['inbounds'][0]['settings']['clients']
        if not any(cl.get('password') == password for cl in clients):
            clients.append({"password": password})
            with open(XRAY_CONFIG, 'w') as f:
                json.dump(config, f, indent=2)
            subprocess.run(['systemctl', 'restart', 'xray'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    cf_ip, sni, port = get_cf_settings()
    remark = urllib.parse.quote(f"VIP {login}")
    link = f"trojan://{password}@{cf_ip}:{port}?security=tls&type=ws&path={WS_PATH}&host={node_host}&sni={sni}#{remark}"
    return link

def get_all_trojan_links(login):
    """
    Генерирует trojan:// ссылки для ВСЕХ активных нод (мастер + ноды).
    Авто-push пароля на каждую ноду. Возвращает многострочный результат.
    """
    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()

    row = cursor.execute("SELECT trojan_password FROM vip_keys WHERE login=?", (login,)).fetchone()
    if not row:
        db.close()
        return "NOT_FOUND"

    password = row[0]
    if not password:
        password = str(uuid.uuid4()).replace('-', '')[:16]
        cursor.execute("UPDATE vip_keys SET trojan_password=? WHERE login=?", (password, login))
        db.commit()

    rows = cursor.execute(
        "SELECT id,name,host,tls_host,ip,is_master FROM nodes "
        "WHERE is_active=1 AND (is_master=1 OR status='online') "
        "ORDER BY is_master DESC, id"
    ).fetchall()
    db.close()

    if not rows:
        return "NODE_NOT_FOUND"

    # Push пароля на все ноды (best-effort)
    for r in rows:
        if r[5] == 1:
            continue
        node_ip = r[4]
        if not node_ip:
            continue
        try:
            subprocess.run(
                ['/usr/local/bin/xray-push-password.sh', login, node_ip],
                capture_output=True, text=True, timeout=20
            )
        except Exception:
            pass

    # Гарантия пароля в конфиге мастера
    try:
        with open(XRAY_CONFIG, 'r') as f:
            config = json.load(f)
        clients = config['inbounds'][0]['settings']['clients']
        if not any(cl.get('password') == password for cl in clients):
            clients.append({"password": password})
            with open(XRAY_CONFIG, 'w') as f:
                json.dump(config, f, indent=2)
            subprocess.run(['systemctl', 'restart', 'xray'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    cf_ip, sni, port = get_cf_settings()
    links = []
    for r in rows:
        _id, name, host, tls_host, ip, is_master = r
        node_host = tls_host or host or "de.ruzone27.shop"
        remark = urllib.parse.quote(f"VIP {login} · {name}")
        link = f"trojan://{password}@{cf_ip}:{port}?security=tls&type=ws&path={WS_PATH}&host={node_host}&sni={sni}#{remark}"
        links.append(link)

    return "\n".join(links)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        login = sys.argv[1]
        node = sys.argv[2] if len(sys.argv) > 2 else "master"
        if node == "all":
            print(get_all_trojan_links(login))
        else:
            print(get_trojan_link(login, node))
    else:
        print("Ошибка: передайте логин.")
