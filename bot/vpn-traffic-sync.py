#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Синхронизация трафика: мастер + все ноды → SQLite vpn.db"""
import os
import sqlite3
import logging
import sys

sys.path.insert(0, '/usr/local/bin')

DB = "/etc/UDPCustom/vpn.db"
TRAFFIC_DIR = "/etc/UDPCustom/traffic"
LOG = "/var/log/vpn-traffic-sync.log"

logging.basicConfig(filename=LOG, level=logging.INFO,
    format='%(asctime)s [SYNC] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


def collect_master_traffic():
    """Возвращает dict {login: bytes} с мастера."""
    result = {}
    if not os.path.isdir(TRAFFIC_DIR):
        return result
    for fname in os.listdir(TRAFFIC_DIR):
        path = os.path.join(TRAFFIC_DIR, fname)
        if not os.path.isfile(path):
            continue
        try:
            used = int(open(path).read().strip() or 0)
            result[fname] = used
        except Exception:
            continue
    return result


def collect_nodes_traffic():
    """Возвращает dict {login: bytes} суммарно со всех нод."""
    try:
        from bot_modules import nodes_client as nc
        return nc.collect_traffic_from_all_nodes()
    except Exception as e:
        logging.error(f"collect_nodes_traffic: {e}")
        return {}


def main():
    if not os.path.exists(DB):
        return

    master = collect_master_traffic()
    nodes = collect_nodes_traffic()

    # Суммируем по логинам
    total = {}
    for login, b in master.items():
        total[login] = total.get(login, 0) + int(b)
    for login, b in nodes.items():
        total[login] = total.get(login, 0) + int(b)

    if not total:
        logging.info("Нет данных для обновления")
        return

    conn = sqlite3.connect(DB, timeout=15)
    c = conn.cursor()
    updated = 0
    try:
        for login, used in total.items():
            r1 = c.execute(
                "UPDATE test_keys SET traffic_used=? WHERE login=? AND traffic_used != ?",
                (used, login, used)
            )
            r2 = c.execute(
                "UPDATE vip_keys SET traffic_used=? WHERE login=? AND traffic_used != ?",
                (used, login, used)
            )
            if (r1.rowcount or 0) + (r2.rowcount or 0) > 0:
                updated += 1
        conn.commit()
        if updated:
            logging.info(f"Обновлено: {updated} (мастер: {len(master)}, ноды: {len(nodes)})")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
