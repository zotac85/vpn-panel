#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Синхронизация трафика: файлы /etc/UDPCustom/traffic/* → SQLite vpn.db"""
import os
import sqlite3
import logging

DB = "/etc/UDPCustom/vpn.db"
TRAFFIC_DIR = "/etc/UDPCustom/traffic"
LOG = "/var/log/vpn-traffic-sync.log"

logging.basicConfig(filename=LOG, level=logging.INFO,
    format='%(asctime)s [SYNC] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


def main():
    if not os.path.exists(DB) or not os.path.isdir(TRAFFIC_DIR):
        return
    conn = sqlite3.connect(DB, timeout=10)
    c = conn.cursor()
    updated = 0
    try:
        for fname in os.listdir(TRAFFIC_DIR):
            path = os.path.join(TRAFFIC_DIR, fname)
            if not os.path.isfile(path):
                continue
            try:
                used = int(open(path).read().strip() or 0)
            except:
                continue
            # Обновляем в test_keys и vip_keys
            r1 = c.execute("UPDATE test_keys SET traffic_used=? WHERE login=? AND traffic_used != ?",
                           (used, fname, used))
            r2 = c.execute("UPDATE vip_keys SET traffic_used=? WHERE login=? AND traffic_used != ?",
                           (used, fname, used))
            if (r1.rowcount or 0) + (r2.rowcount or 0) > 0:
                updated += 1
        conn.commit()
        if updated:
            logging.info(f"Обновлено ключей: {updated}")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
