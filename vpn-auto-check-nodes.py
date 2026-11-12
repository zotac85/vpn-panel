#!/usr/bin/env python3
import sqlite3
import socket

DB = '/etc/UDPCustom/vpn.db'

def check_node(ip):
    # Проверяем 443 порт (Nginx), так как он жизненно важен для VPN
    try:
        with socket.create_connection((ip, 443), timeout=5):
            return True
    except:
        return False

def main():
    db = sqlite3.connect(DB, timeout=15) # Таймаут 15 сек, если база занята
    nodes = db.execute("SELECT id, ip FROM nodes WHERE is_master=0 AND is_active=1").fetchall()
    
    for nid, ip in nodes:
        if check_node(ip):
            db.execute("UPDATE nodes SET status='online' WHERE id=?", (nid,))
        else:
            db.execute("UPDATE nodes SET status='offline' WHERE id=?", (nid,))
            
    db.commit()
    db.close()

if __name__ == '__main__':
    main()
