import sqlite3
import os

db_path = '/etc/UDPCustom/vpn.db'
db = sqlite3.connect(db_path)
cursor = db.cursor()

# 1. Создаем таблицу nodes (если ее нет)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        host TEXT,
        tls_host TEXT,
        ip TEXT,
        ssh_port INTEGER,
        ws_port INTEGER,
        ssh_user TEXT,
        is_master INTEGER,
        is_active INTEGER,
        status TEXT,
        last_check TEXT,
        created_at TEXT
    )
''')

# 2. Если таблица nodes уже была, но без tls_host - добавляем колонку
try:
    cursor.execute("ALTER TABLE nodes ADD COLUMN tls_host TEXT;")
except sqlite3.OperationalError:
    pass

# 3. Создаем таблицу settings
cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('MODE', 'WS')")

db.commit()
db.close()
print("✅ База данных успешно проверена и обновлена!")
