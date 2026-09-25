#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Модуль работы с SQLite. Единая точка доступа к /etc/UDPCustom/vpn.db"""
import os
import sqlite3
import time
import secrets
import string
import logging
import threading

DB_PATH = "/etc/UDPCustom/vpn.db"
LOG_FILE = "/var/log/vpn-tg-bot.log"

db_log = logging.getLogger("db")
if not db_log.handlers:
    db_log.setLevel(logging.INFO)
    _h = logging.FileHandler(LOG_FILE)
    _h.setFormatter(logging.Formatter('%(asctime)s [DB] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    db_log.addHandler(_h)

# Глобальный лок для записи (чтобы потоки не били друг друга)
_write_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════
# СОЕДИНЕНИЕ
# ═══════════════════════════════════════════════════════════════

def _conn():
    """Открывает соединение. check_same_thread=False — можно из разных потоков."""
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # параллельное чтение
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def query(sql, params=()):
    """SELECT — возвращает список словарей."""
    try:
        with _conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        db_log.error(f"query error: {e} | sql={sql} | params={params}")
        return []


def query_one(sql, params=()):
    """SELECT — возвращает одну строку или None."""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    """INSERT/UPDATE/DELETE — возвращает lastrowid или None."""
    with _write_lock:
        try:
            with _conn() as conn:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur.lastrowid
        except Exception as e:
            db_log.error(f"execute error: {e} | sql={sql} | params={params}")
            return None


# ═══════════════════════════════════════════════════════════════
# УТИЛИТЫ
# ═══════════════════════════════════════════════════════════════

def gen_ref_code(n=8):
    alphabet = string.ascii_lowercase + string.digits
    while True:
        code = ''.join(secrets.choice(alphabet) for _ in range(n))
        if not query_one("SELECT 1 FROM users WHERE ref_code=?", (code,)):
            return code


def human_bytes(b):
    try:
        b = int(b)
    except:
        return "0 B"
    if b >= 1073741824: return f"{b/1073741824:.2f} GB"
    if b >= 1048576:    return f"{b/1048576:.1f} MB"
    if b >= 1024:       return f"{b/1024:.0f} KB"
    return f"{b} B"


def human_time(sec):
    try:
        sec = int(sec)
    except:
        return "—"
    if sec <= 0: return "истёк"
    h = sec // 3600
    m = (sec % 3600) // 60
    if h >= 24:
        d = h // 24; h = h % 24
        return f"{d}д {h}ч"
    if h > 0: return f"{h}ч {m}мин"
    return f"{m}мин"


# ═══════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════

def get_user(tg_id):
    return query_one("SELECT * FROM users WHERE tg_id=?", (int(tg_id),))


def upsert_user(tg_id, first_name="", username=""):
    """Создаёт юзера если нет, обновляет first_name/username если есть."""
    tg_id = int(tg_id)
    existing = get_user(tg_id)
    if existing:
        execute("UPDATE users SET first_name=?, username=? WHERE tg_id=?",
                (first_name or "", username or "", tg_id))
        return existing
    ref_code = gen_ref_code()
    execute("""INSERT INTO users
        (tg_id, first_name, username, registered_at, verified_until, balance, ref_code, ref_by)
        VALUES (?, ?, ?, ?, 0, 0, ?, 0)""",
        (tg_id, first_name or "", username or "", int(time.time()), ref_code))
    db_log.info(f"Новый юзер: {tg_id} ({first_name})")
    return get_user(tg_id)


def set_verified(tg_id, until_ts):
    execute("UPDATE users SET verified_until=? WHERE tg_id=?", (int(until_ts), int(tg_id)))


def get_balance(tg_id):
    u = get_user(tg_id)
    return float(u['balance']) if u else 0.0


def add_balance(tg_id, amount, method="manual", meta=None):
    """Начисляет/списывает баланс + пишет в payments."""
    tg_id = int(tg_id)
    amount = round(float(amount), 4)
    execute("UPDATE users SET balance = balance + ? WHERE tg_id=?", (amount, tg_id))
    import json
    execute("""INSERT INTO payments
        (tg_id, amount, currency, method, status, meta, created_at, paid_at)
        VALUES (?, ?, 'USDT', ?, 'paid', ?, ?, ?)""",
        (tg_id, amount, method, json.dumps(meta or {}), int(time.time()), int(time.time())))
    return get_balance(tg_id)


def get_ref_code(tg_id):
    u = get_user(tg_id)
    return u['ref_code'] if u else None


def find_by_ref_code(ref_code):
    return query_one("SELECT * FROM users WHERE ref_code=?", (ref_code,))


def set_ref_by(tg_id, inviter_id):
    """Привязка: юзер tg_id пришёл по ссылке inviter_id."""
    tg_id = int(tg_id); inviter_id = int(inviter_id)
    if tg_id == inviter_id:
        return False  # сам себя пригласить нельзя
    u = get_user(tg_id)
    if not u or u['ref_by']:
        return False  # уже привязан или не существует
    execute("UPDATE users SET ref_by=? WHERE tg_id=?", (inviter_id, tg_id))
    execute("""INSERT OR IGNORE INTO referrals
        (invited_id, inviter_id, ts) VALUES (?, ?, ?)""",
        (tg_id, inviter_id, int(time.time())))
    db_log.info(f"Referral: {inviter_id} -> {tg_id}")
    return True


# ═══════════════════════════════════════════════════════════════
# TEST KEYS
# ═══════════════════════════════════════════════════════════════

def get_test_keys(tg_id, active_only=False):
    sql = "SELECT * FROM test_keys WHERE tg_id=?"
    params = [int(tg_id)]
    if active_only:
        sql += " AND (expires_at=0 OR expires_at > ?)"
        params.append(int(time.time()))
    sql += " ORDER BY created_at DESC"
    return query(sql, tuple(params))


def create_test_key(login, tg_id, password, expires_at, devices=1,
                    traffic_limit=0, traffic_used=0):
    execute("""INSERT OR REPLACE INTO test_keys
        (login, tg_id, password, created_at, expires_at, devices, traffic_used, traffic_limit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (login, int(tg_id), password, int(time.time()),
         int(expires_at), int(devices), int(traffic_used), int(traffic_limit)))
    return query_one("SELECT * FROM test_keys WHERE login=?", (login,))


def get_test_key(login):
    return query_one("SELECT * FROM test_keys WHERE login=?", (login,))


def delete_expired_test_keys():
    """Удаляет из БД истёкшие тестовые. Возвращает список удалённых логинов."""
    now = int(time.time())
    rows = query("SELECT login FROM test_keys WHERE expires_at > 0 AND expires_at < ?", (now,))
    logins = [r['login'] for r in rows]
    if logins:
        execute("DELETE FROM test_keys WHERE expires_at > 0 AND expires_at < ?", (now,))
        db_log.info(f"Удалено истёкших test_keys: {len(logins)}")
    return logins


# ═══════════════════════════════════════════════════════════════
# VIP KEYS
# ═══════════════════════════════════════════════════════════════

def get_vip_keys(tg_id, active_only=False):
    sql = "SELECT * FROM vip_keys WHERE tg_id=?"
    params = [int(tg_id)]
    if active_only:
        sql += " AND (expires_at=0 OR expires_at > ?)"
        params.append(int(time.time()))
    sql += " ORDER BY created_at DESC"
    return query(sql, tuple(params))


def create_vip_key(login, tg_id, password, expires_at, devices=1,
                   traffic_limit=0, tariff="vip_30d",
                   price_paid=0, paid_via="manual"):
    execute("""INSERT OR REPLACE INTO vip_keys
        (login, tg_id, password, created_at, expires_at, devices,
         traffic_used, traffic_limit, tariff, price_paid, paid_via)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)""",
        (login, int(tg_id), password, int(time.time()),
         int(expires_at), int(devices), int(traffic_limit),
         tariff, float(price_paid), paid_via))
    return query_one("SELECT * FROM vip_keys WHERE login=?", (login,))


def get_vip_key(login):
    return query_one("SELECT * FROM vip_keys WHERE login=?", (login,))


# ═══════════════════════════════════════════════════════════════
# REFERRALS
# ═══════════════════════════════════════════════════════════════

def get_ref_count(inviter_id):
    r = query_one("SELECT COUNT(*) as n FROM referrals WHERE inviter_id=?", (int(inviter_id),))
    return r['n'] if r else 0


def get_ref_bonus_total(inviter_id):
    r = query_one("""SELECT COALESCE(SUM(amount), 0) as s FROM payments
                     WHERE tg_id=? AND method='referral_bonus'""", (int(inviter_id),))
    return float(r['s']) if r else 0.0


def get_ref_list(inviter_id):
    return query("""SELECT r.invited_id, r.ts, r.bonus_paid, u.first_name, u.username
                    FROM referrals r
                    LEFT JOIN users u ON u.tg_id = r.invited_id
                    WHERE r.inviter_id=?
                    ORDER BY r.ts DESC""", (int(inviter_id),))


def mark_first_purchase(tg_id):
    """Вызывается при первой покупке юзера. Возвращает inviter_id если надо платить бонус."""
    tg_id = int(tg_id)
    row = query_one("SELECT * FROM referrals WHERE invited_id=?", (tg_id,))
    if not row or row['bonus_paid']:
        return None
    # фиксируем первую покупку
    if not row['first_purchase']:
        execute("UPDATE referrals SET first_purchase=? WHERE invited_id=?",
                (int(time.time()), tg_id))
        return row['inviter_id']
    return None


def mark_bonus_paid(invited_id):
    execute("UPDATE referrals SET bonus_paid=1 WHERE invited_id=?", (int(invited_id),))


# ═══════════════════════════════════════════════════════════════
# PAYMENTS
# ═══════════════════════════════════════════════════════════════

def add_payment(tg_id, amount, method, status="pending",
                external_id=None, meta=None):
    import json
    return execute("""INSERT INTO payments
        (tg_id, amount, currency, method, status, external_id, meta, created_at)
        VALUES (?, ?, 'USDT', ?, ?, ?, ?, ?)""",
        (int(tg_id), float(amount), method, status,
         external_id, json.dumps(meta or {}), int(time.time())))


def mark_payment_paid(payment_id):
    execute("UPDATE payments SET status='paid', paid_at=? WHERE id=?",
            (int(time.time()), int(payment_id)))


def get_payments(tg_id, limit=20):
    return query("SELECT * FROM payments WHERE tg_id=? ORDER BY created_at DESC LIMIT ?",
                 (int(tg_id), int(limit)))


# ═══════════════════════════════════════════════════════════════
# PROMO
# ═══════════════════════════════════════════════════════════════

def get_promo(code):
    return query_one("SELECT * FROM promo_codes WHERE code=?", (code,))


def check_promo(code, tg_id):
    """Возвращает (ok, reason, promo_dict)."""
    p = get_promo(code)
    if not p:
        return False, "not_found", None
    if p['expires_at'] and p['expires_at'] < int(time.time()):
        return False, "expired", None
    if p['uses_left'] == 0:
        return False, "exhausted", None
    used = query_one("SELECT 1 FROM promo_used WHERE code=? AND tg_id=?",
                     (p['code'], int(tg_id)))
    if used:
        return False, "already_used", p
    return True, "ok", p


def use_promo(code, tg_id):
    """Применяет промокод: списывает использование + начисляет бонус. Возвращает (ok, msg, value)."""
    code = code.strip()
    ok, reason, p = check_promo(code, tg_id)
    if not ok:
        return False, reason, None

    # Уменьшаем использования
    if p['uses_left'] > 0:
        execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code=?", (code,))

    # Пишем что использован
    execute("INSERT INTO promo_used (code, tg_id, ts) VALUES (?, ?, ?)",
            (code, int(tg_id), int(time.time())))

    # Начисляем
    value = float(p['value'])
    if p['type'] == 'balance':
        add_balance(tg_id, value, method='promo', meta={'code': code})
    elif p['type'] == 'days':
        # продлеваем ТОЛЬКО VIP-ключи
        cnt_ext = extend_vip_keys(tg_id, int(value))
        if cnt_ext == 0:
            return False, "no_vip_key", None
    # 'traffic' пока не реализован
    return True, "ok", value


def create_promo(code, type_, value, max_uses=1, expires_at=0):
    execute("""INSERT OR REPLACE INTO promo_codes
        (code, type, value, uses_left, max_uses, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (code, type_, float(value), int(max_uses), int(max_uses),
         int(time.time()), int(expires_at)))


# ═══════════════════════════════════════════════════════════════
# УТИЛИТЫ ДЛЯ КЛЮЧЕЙ
# ═══════════════════════════════════════════════════════════════

def extend_vip_keys(tg_id, days):
    """Продлевает только VIP-ключи юзера на N дней."""
    secs = int(days) * 86400
    now = int(time.time())
    rows = query("SELECT login, expires_at FROM vip_keys WHERE tg_id=?", (int(tg_id),))
    for r in rows:
        base = r['expires_at'] if r['expires_at'] and r['expires_at'] > now else now
        execute("UPDATE vip_keys SET expires_at=? WHERE login=?",
                (base + secs, r['login']))
    return len(rows)


def get_all_user_keys(tg_id, active_only=False):
    """Возвращает объединённый список test + vip ключей, отсортированный по дате."""
    tests = get_test_keys(tg_id, active_only=active_only)
    vips  = get_vip_keys(tg_id, active_only=active_only)
    for k in tests: k['kind'] = 'test'
    for k in vips:  k['kind'] = 'vip'
    all_keys = tests + vips
    all_keys.sort(key=lambda k: k['created_at'], reverse=True)
    return all_keys


# ═══════════════════════════════════════════════════════════════
# ТЕСТ / CLI
# ═══════════════════════════════════════════════════════════════




# ═══════════════════════════════════════════════════════════════
# PENDING ACTIONS (что бот ждёт от юзера)
# ═══════════════════════════════════════════════════════════════

PENDING_DIR = "/etc/UDPCustom/pending"


def set_pending(user_id, action):
    try:
        os.makedirs(PENDING_DIR, exist_ok=True)
        with open(f"{PENDING_DIR}/{user_id}", 'w') as f:
            f.write(action)
    except Exception as e:
        db_log.error(f"set_pending: {e}")


def get_pending(user_id):
    path = f"{PENDING_DIR}/{user_id}"
    if os.path.exists(path):
        try:
            with open(path) as f:
                return f.read().strip()
        except: pass
    return None


def clear_pending(user_id):
    try:
        os.remove(f"{PENDING_DIR}/{user_id}")
    except: pass


if __name__ == '__main__':
    print("=== Подключение ===")
    print(f"DB: {DB_PATH}")
    print(f"Users: {query_one('SELECT COUNT(*) as n FROM users')['n']}")
    print(f"Test keys: {query_one('SELECT COUNT(*) as n FROM test_keys')['n']}")
    print(f"VIP keys: {query_one('SELECT COUNT(*) as n FROM vip_keys')['n']}")
    print()
    print("=== Проверка функций ===")
    u = get_user(1738878748)
    print(f"get_user(1738878748): {u['first_name'] or '(без имени)'} | ref_code={u['ref_code']}")
    print(f"get_balance: {get_balance(1738878748)}")
    print(f"get_vip_keys: {len(get_vip_keys(1738878748))} шт.")
    print("✅ Всё работает")
