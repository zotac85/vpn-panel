import sqlite3
import time
import sys
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DB_PATH = "/etc/UDPCustom/vpn.db"
TOKEN_FILE = "/root/vpn-subscription/token.json"
FOLDER_ID = "1fFY8-dXCPsQ3DLkpRZ2sokvCWBfA5n5c"

def get_active_logins():
    """Возвращает множество активных логинов из обеих таблиц."""
    active = set()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = int(time.time())
        
        # Берем VIP ключи, у которых срок действия еще не истек
        cursor.execute("SELECT login FROM vip_keys WHERE expires_at > ?", (now,))
        for row in cursor.fetchall():
            active.add(row[0])
            
        # Берем тестовые ключи, у которых срок действия еще не истек
        cursor.execute("SELECT login FROM test_keys WHERE expires_at > ?", (now,))
        for row in cursor.fetchall():
            active.add(row[0])
            
        conn.close()
    except Exception as e:
        print(f"Ошибка БД: {e}")
    return active

def clean_drive():
    print("1. Собираем список активных ключей из базы...")
    active_logins = get_active_logins()
    print(f"   ✅ Найдено активных ключей: {len(active_logins)}")

    print("2. Подключаемся к Google Drive...")
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE)
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"   ❌ Ошибка авторизации Google: {e}")
        return

    print("3. Получаем список файлов из папки VpnSubs...")
    try:
        results = drive.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed=false and name contains '.txt'",
            fields="files(id, name)", pageSize=1000
        ).execute()
        files = results.get('files', [])
        print(f"   ✅ Найдено файлов на Диске: {len(files)}")
    except Exception as e:
        print(f"   ❌ Ошибка получения списка файлов: {e}")
        return

    deleted_count = 0
    kept_count = 0

    print("4. Проверяем файлы и удаляем мусор...")
    for f in files:
        filename = f['name']
        file_id = f['id']
        
        # Пропускаем файлы, которые не относятся к нашим подпискам (например, тестовые)
        if not (filename.startswith("sub_dark_") or filename.startswith("sub_") or filename.startswith("trojan_")):
            continue

        # Вырезаем имя ключа из названия файла
        if filename.startswith("sub_dark_"):
            login = filename[9:-4]   # убираем 'sub_dark_' и '.txt'
        elif filename.startswith("trojan_"):
            login = filename[7:-4]   # убираем 'trojan_' и '.txt'
        elif filename.startswith("sub_"):
            login = filename[4:-4]   # убираем 'sub_' и '.txt'
        else:
            continue

        # Если логин есть в списке активных — оставляем файл
        if login in active_logins:
            kept_count += 1
        else:
            # Если логина нет в базе (удален или просрочен) — удаляем
            try:
                drive.files().delete(fileId=file_id).execute()
                print(f"   🗑 Удален файл: {filename} (ключ {login} неактивен)")
                deleted_count += 1
            except Exception as e:
                print(f"   ❌ Ошибка удаления {filename}: {e}")

    print(f"\n📊 ИТОГО:")
    print(f"   - Оставлено (активные): {kept_count}")
    print(f"   - Удалено (мусор): {deleted_count}")

if __name__ == "__main__":
    clean_drive()
