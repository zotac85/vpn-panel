#!/usr/bin/env python3
"""vpn-nodes-check.py - проверка статуса всех нод (cron)"""
import sys
import sqlite3
import time

sys.path.insert(0, '/usr/local/bin')
from bot_modules import nodes_client as nc

DB_PATH = '/etc/UDPCustom/vpn.db'


def main():
    try:
        db = sqlite3.connect(DB_PATH, timeout=15)
        rows = db.execute(
            "SELECT id, name, ip, ssh_port, is_master FROM nodes WHERE is_active=1"
        ).fetchall()

        for node_id, name, ip, ssh_port, is_master in rows:
            if is_master:
                # Мастер всегда online
                db.execute(
                    "UPDATE nodes SET status='online', last_check=datetime('now') WHERE id=?",
                    (node_id,)
                )
                continue

            online, ms = nc.node_check(node_id)
            status = 'online' if online else 'offline'
            db.execute(
                "UPDATE nodes SET status=?, last_check=datetime('now') WHERE id=?",
                (status, node_id)
            )

        db.commit()
        db.close()
        print(f"[{time.strftime('%F %T')}] Nodes check done")
    except Exception as e:
        print(f"[{time.strftime('%F %T')}] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
