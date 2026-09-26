#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Уведомления об истекающих VIP-ключах (за 24 часа, один раз).
Запускается cron каждые 5 минут.
"""
import os
import sys
import json
import time
import sqlite3
import logging
import urllib.request

DB = "/etc/UDPCustom/vpn.db"
CONFIG = "/etc/UDPCustom/bot.conf"
LOG = "/var/log/vpn-notify.log"

logging.basicConfig(filename=LOG, level=logging.INFO,
    format='%(asctime)s [NOTIFY] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

NOTIFY_WINDOW_HOURS = 24       # уведомлять за 24 часа
PAUSE_BETWEEN = 1.5            # пауза между отправками (сек)


def load_token():
    with open(CONFIG) as f:
        for line in f:
            if line.startswith('BOT_TOKEN'):
                return line.split('=', 1)[1].strip().strip('"')
    return None


def tg(token, method, params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(params).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def human_bytes(b):
    try: b = int(b)
    except: return "0 B"
    if b >= 1073741824: return f"{b/1073741824:.1f} GB"
    if b >= 1048576: return f"{b/1048576:.0f} MB"
    if b >= 1024: return f"{b/1024:.0f} KB"
    return f"{b} B"


def human_time(sec):
    sec = int(sec)
    if sec <= 0: return "истёк"
    h = sec // 3600
    m = (sec % 3600) // 60
    if h >= 24:
        return f"{h//24}д {h%24}ч"
    if h > 0:
        return f"{h}ч {m}мин"
    return f"{m}мин"


def main():
    token = load_token()
    if not token:
        logging.error("BOT_TOKEN не найден")
        return

    now = int(time.time())
    deadline = now + NOTIFY_WINDOW_HOURS * 3600

    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Ищем VIP-ключи:
    # - tg_id > 0 (привязан к юзеру)
    # - expires_at > now (ещё активен)
    # - expires_at <= deadline (истечёт в течение 24ч)
    # - notified_24h = 0 (ещё не уведомляли)
    try:
        rows = c.execute("""
            SELECT login, tg_id, expires_at, traffic_used, traffic_limit, tariff
            FROM vip_keys
            WHERE tg_id > 0
              AND expires_at > ?
              AND expires_at <= ?
              AND COALESCE(notified_24h, 0) = 0
        """, (now, deadline)).fetchall()
    except Exception as e:
        logging.error(f"query error: {e}")
        conn.close()
        return

    if not rows:
        conn.close()
        return

    logging.info(f"Найдено {len(rows)} ключей для уведомления")

    sent = 0
    for r in rows:
        tg_id = r['tg_id']
        login = r['login']
        left = r['expires_at'] - now
        used = human_bytes(r['traffic_used'] or 0)
        limit = r['traffic_limit'] or 0
        limit_str = f" / {human_bytes(limit)}" if limit > 0 else ""

        NL = chr(10)
        text = NL.join([
            "⚠️ <b>VIP-КЛЮЧ ИСТЕКАЕТ</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"💎 <code>{login}</code>",
            f"⏰ Осталось: <b>{human_time(left)}</b>",
            f"📊 Трафик: <b>{used}{limit_str}</b>",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "💡 <i>Продли VIP — не потеряй доступ!</i>"
        ])
        kb = {'inline_keyboard': [
            [{'text': '💎 Купить / Продлить VIP', 'callback_data': 'cab_buy_vip'}],
            [{'text': '👤 Личный кабинет', 'callback_data': 'cab_main'}]
        ]}
        res = tg(token, 'sendMessage', {
            'chat_id': tg_id,
            'text': text,
            'parse_mode': 'HTML',
            'reply_markup': kb,
            'disable_web_page_preview': True
        })
        if res and res.get('ok'):
            # Помечаем что уведомление отправлено
            c.execute("UPDATE vip_keys SET notified_24h = 1 WHERE login = ?", (login,))
            conn.commit()
            sent += 1
            logging.info(f"Отправлено: {login} → {tg_id}")
        else:
            err = res.get('description') if res else 'no response'
            logging.warning(f"Ошибка {login} → {tg_id}: {err}")
            # Если юзер заблокировал бота — тоже помечаем, чтобы не спамить
            if res and 'blocked' in str(res.get('description', '')).lower():
                c.execute("UPDATE vip_keys SET notified_24h = 1 WHERE login = ?", (login,))
                conn.commit()
                logging.info(f"Помечен как неактивный (blocked): {login}")
        time.sleep(PAUSE_BETWEEN)

    conn.close()
    logging.info(f"Готово. Отправлено: {sent}/{len(rows)}")


if __name__ == '__main__':
    main()
