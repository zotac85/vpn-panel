import sqlite3
import sys
import os
import time

sys.path.append("/usr/local/bin/bot_modules")
import gdrive_helper

DB_PATH = "/etc/UDPCustom/vpn.db"

def update_all():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = int(time.time())
        
        cursor.execute("SELECT login FROM vip_keys WHERE expires_at > ?", (now,))
        logins = set(row[0] for row in cursor.fetchall())
        
        cursor.execute("SELECT login FROM test_keys WHERE expires_at > ?", (now,))
        logins.update(row[0] for row in cursor.fetchall())
        
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")
        return

    print(f"Начинаю обновление {len(logins)} ключей...")
    for login in logins:
        # Обновляем все три типа подписок
        gdrive_helper.get_drive_link(login, "sub")
        gdrive_helper.get_drive_link(login, "sub_dark")
        gdrive_helper.get_drive_link(login, "trojan")
        print(f"✅ Обновлен: {login}")
        
        # Пауза 1.5 секунды между ключами, чтобы не превысить лимиты Google API
        time.sleep(1.5)

if __name__ == "__main__":
    update_all()
