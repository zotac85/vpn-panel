#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite для бота поддержки: тикеты, сообщения"""
import sqlite3
import time
import logging

DB_PATH = "/etc/UDPCustom/support.db"
LOG_FILE = "/var/log/vpn-support-bot.log"

sup_log = logging.getLogger("support_db")
if not sup_log.handlers:
    sup_log.setLevel(logging.INFO)
    _h = logging.FileHandler(LOG_FILE)
    _h.setFormatter(logging.Formatter('%(asctime)s [DB] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    sup_log.addHandler(_h)


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema():
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        tg_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        registered_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        status TEXT DEFAULT 'open',
        created_at INTEGER,
        updated_at INTEGER,
        closed_at INTEGER DEFAULT 0,
        last_msg_text TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id);
    CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER,
        from_user_id INTEGER,
        to_user_id INTEGER,
        text TEXT,
        is_admin INTEGER DEFAULT 0,
        created_at INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_messages_ticket ON messages(ticket_id);

    CREATE TABLE IF NOT EXISTS faq_stats (
        block_name TEXT PRIMARY KEY,
        hits INTEGER DEFAULT 0,
        helped INTEGER DEFAULT 0,
        not_helped INTEGER DEFAULT 0
    );
    """
    with _conn() as conn:
        conn.executescript(schema)
        conn.commit()


def query(sql, params=()):
    try:
        with _conn() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception as e:
        sup_log.error(f"query: {e}")
        return []


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    try:
        with _conn() as conn:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        sup_log.error(f"execute: {e}")
        return None


# === USERS ===

def upsert_user(tg_id, username="", first_name=""):
    existing = query_one("SELECT tg_id FROM users WHERE tg_id=?", (int(tg_id),))
    if existing:
        execute("UPDATE users SET username=?, first_name=? WHERE tg_id=?",
                (username or "", first_name or "", int(tg_id)))
    else:
        execute("INSERT INTO users (tg_id, username, first_name, registered_at) VALUES (?, ?, ?, ?)",
                (int(tg_id), username or "", first_name or "", int(time.time())))


def get_user(tg_id):
    return query_one("SELECT * FROM users WHERE tg_id=?", (int(tg_id),))


# === TICKETS ===

def get_open_ticket(user_id):
    return query_one("SELECT * FROM tickets WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",
                     (int(user_id),))


def create_ticket(user_id, first_text):
    now = int(time.time())
    tid = execute("""INSERT INTO tickets (user_id, status, created_at, updated_at, last_msg_text)
                     VALUES (?, 'open', ?, ?, ?)""",
                  (int(user_id), now, now, first_text[:200]))
    return tid


def add_message(ticket_id, from_user_id, to_user_id, text, is_admin=0):
    now = int(time.time())
    execute("""INSERT INTO messages (ticket_id, from_user_id, to_user_id, text, is_admin, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (int(ticket_id), int(from_user_id), int(to_user_id), text, 1 if is_admin else 0, now))
    execute("UPDATE tickets SET updated_at=? WHERE id=?", (now, int(ticket_id)))


def close_ticket(ticket_id):
    execute("UPDATE tickets SET status='closed', closed_at=? WHERE id=?",
            (int(time.time()), int(ticket_id)))


def get_ticket(ticket_id):
    return query_one("SELECT * FROM tickets WHERE id=?", (int(ticket_id),))


def get_active_tickets():
    return query("SELECT * FROM tickets WHERE status='open' ORDER BY updated_at DESC")


def get_all_tickets(limit=20):
    return query("SELECT * FROM tickets ORDER BY updated_at DESC LIMIT ?", (int(limit),))


def auto_close_old(hours=1):
    """Закрывает тикеты где не было активности N часов"""
    cutoff = int(time.time()) - int(hours) * 3600
    rows = query("SELECT id FROM tickets WHERE status='open' AND updated_at < ?", (cutoff,))
    cnt = 0
    for r in rows:
        close_ticket(r['id'])
        cnt += 1
    return cnt


# === FAQ STATS ===

def faq_hit(block_name):
    existing = query_one("SELECT block_name FROM faq_stats WHERE block_name=?", (block_name,))
    if existing:
        execute("UPDATE faq_stats SET hits = hits + 1 WHERE block_name=?", (block_name,))
    else:
        execute("INSERT INTO faq_stats (block_name, hits) VALUES (?, 1)", (block_name,))


def faq_feedback(block_name, helped=True):
    col = "helped" if helped else "not_helped"
    existing = query_one("SELECT block_name FROM faq_stats WHERE block_name=?", (block_name,))
    if existing:
        execute(f"UPDATE faq_stats SET {col} = {col} + 1 WHERE block_name=?", (block_name,))
    else:
        execute(f"INSERT INTO faq_stats (block_name, {col}) VALUES (?, 1)", (block_name,))


def get_stats():
    total_tickets = query_one("SELECT COUNT(*) as n FROM tickets")['n']
    open_tickets = query_one("SELECT COUNT(*) as n FROM tickets WHERE status='open'")['n']
    closed_tickets = query_one("SELECT COUNT(*) as n FROM tickets WHERE status='closed'")['n']
    total_users = query_one("SELECT COUNT(*) as n FROM users")['n']
    faq_total = query_one("SELECT COALESCE(SUM(hits),0) as n FROM faq_stats")['n']
    return {
        'total_tickets': total_tickets,
        'open_tickets': open_tickets,
        'closed_tickets': closed_tickets,
        'total_users': total_users,
        'faq_hits': faq_total
    }


# Автоинициализация
try:
    _c = _conn()
    _has = _c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tickets'").fetchone()
    _c.close()
    if not _has:
        init_schema()
except: pass


if __name__ == '__main__':
    init_schema()
    print("DB:", DB_PATH)
    print("Users:", query_one("SELECT COUNT(*) as n FROM users")['n'])
    print("Tickets:", query_one("SELECT COUNT(*) as n FROM tickets")['n'])
    print("✅ OK")
