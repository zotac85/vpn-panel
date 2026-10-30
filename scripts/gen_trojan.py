#!/usr/bin/env python3
import sqlite3
import uuid
import json
import sys
import subprocess
import urllib.parse

DB_PATH = '/etc/UDPCustom/vpn.db'
XRAY_CONFIG = '/usr/local/etc/xray/config.json'
CF_IP = "104.18.0.3"
WS_PATH = "/trojan-ws"
SNI = "ruzone27.shop"

def get_trojan_link(login, node_domain="de.ruzone27.shop"):
    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()
    
    row = cursor.execute("SELECT trojan_password FROM vip_keys WHERE login=?", (login,)).fetchone()
        
    if not row:
        return "NOT_FOUND" 

    password = row[0]
    
    if not password:
        password = str(uuid.uuid4()).replace('-', '')[:16]
        cursor.execute("UPDATE vip_keys SET trojan_password=? WHERE login=?", (password, login))
        db.commit()
        
        try:
            with open(XRAY_CONFIG, 'r') as f:
                config = json.load(f)
            clients = config['inbounds'][0]['settings']['clients']
            if not any(c.get('password') == password for c in clients):
                clients.append({"password": password})
                with open(XRAY_CONFIG, 'w') as f:
                    json.dump(config, f, indent=2)
                subprocess.run(['systemctl', 'restart', 'xray'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
            
    db.close()
    
    # Кодируем название, чтобы не было пробелов
    remark = urllib.parse.quote(f"VIP {login}")
    link = f"trojan://{password}@{CF_IP}:443?security=tls&type=ws&path={WS_PATH}&host={node_domain}&sni={SNI}#{remark}"
    return link

if __name__ == '__main__':
    if len(sys.argv) > 1:
        login = sys.argv[1]
        node = sys.argv[2] if len(sys.argv) > 2 else "de.ruzone27.shop" 
        print(get_trojan_link(login, node))
    else:
        print("Ошибка")
