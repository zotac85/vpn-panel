#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Модуль личного кабинета пользователя"""
import os
import json
import time
import base64
import logging
import urllib.request
from bot_modules import db

# ─── Пути ───
SMART_DIR = "/etc/UDPCustom/smart_chat"
ISSUED_DB = "/etc/UDPCustom/bot_issued.db"
PASSWORDS_DIR = "/etc/UDPCustom/passwords"
EXPIRE_DIR = "/etc/UDPCustom/expire_ts"
TRAFFIC_DIR = "/etc/UDPCustom/traffic"
TRAFFIC_LIMITS_DIR = "/etc/UDPCustom/traffic_limits"
LIMITS_DIR = "/etc/UDPCustom/limits"
DOMAIN_FILE = "/etc/vpn-domain"
PAYLOAD_FILE = "/etc/UDPCustom/payload.txt"
PROXIES_FILE = "/etc/UDPCustom/proxies.txt"
CONFIG_FILE = "/etc/UDPCustom/bot.conf"
LOG_FILE = "/var/log/vpn-tg-bot.log"

cab_log = logging.getLogger("cabinet")
if not cab_log.handlers:
    cab_log.setLevel(logging.INFO)
    _h = logging.FileHandler(LOG_FILE)
    _h.setFormatter(logging.Formatter('%(asctime)s [CABINET] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    cab_log.addHandler(_h)


# ═══════════════════════════════════════════════════════════════
# БАЗОВЫЕ УТИЛИТЫ
# ═══════════════════════════════════════════════════════════════

def _tg(token, method, params=None, timeout=35):
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        if params:
            data = json.dumps(params).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        cab_log.error(f"TG ({method}): {e}")
        return None


def _send(token, chat_id, text, reply_markup=None, parse_mode='HTML'):
    """Отправляет сообщение, удаляя предыдущее (умный чат)."""
    try:
        os.makedirs(SMART_DIR, exist_ok=True)
        path = f"{SMART_DIR}/{chat_id}"
        if os.path.exists(path):
            try:
                old_id = int(open(path).read().strip())
                _tg(token, 'deleteMessage', {'chat_id': chat_id, 'message_id': old_id})
            except: pass
            try: os.remove(path)
            except: pass
        params = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True, 'parse_mode': parse_mode}
        if reply_markup:
            params['reply_markup'] = reply_markup
        result = _tg(token, 'sendMessage', params)
        if result and result.get('ok'):
            try:
                with open(path, 'w') as f:
                    f.write(str(result['result']['message_id']))
            except: pass
        return result
    except Exception as e:
        cab_log.error(f"_send smart error: {e}")
        params = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True, 'parse_mode': parse_mode}
        if reply_markup:
            params['reply_markup'] = reply_markup
        return _tg(token, 'sendMessage', params)


def _edit(token, chat_id, msg_id, text, reply_markup=None):
    params = {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML',
              'disable_web_page_preview': True}
    if reply_markup:
        params['reply_markup'] = reply_markup
    return _tg(token, 'editMessageText', params)


def _human_bytes(b):
    try:
        b = int(b)
    except:
        return "0 B"
    if b >= 1073741824:
        return f"{b/1073741824:.2f} GB"
    if b >= 1048576:
        return f"{b/1048576:.1f} MB"
    if b >= 1024:
        return f"{b/1024:.0f} KB"
    return f"{b} B"


def _human_time(sec):
    try:
        sec = int(sec)
    except:
        return "—"
    if sec <= 0:
        return "истёк"
    h = sec // 3600
    m = (sec % 3600) // 60
    if h >= 24:
        d = h // 24
        h = h % 24
        return f"{d}д {h}ч"
    if h > 0:
        return f"{h}ч {m}мин"
    return f"{m}мин"


# ═══════════════════════════════════════════════════════════════
# ПОЛУЧЕНИЕ ДАННЫХ
# ═══════════════════════════════════════════════════════════════

def get_user_keys(user_id):
    """Возвращает список ключей: [{'name': ..., 'ts': ..., 'exp': ..., 'traffic': ..., 'limit': ...}]"""
    keys = []
    if not os.path.exists(ISSUED_DB):
        return keys

    seen = set()
    try:
        with open(ISSUED_DB) as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) < 3:
                    continue
                if parts[0] != str(user_id):
                    continue
                try:
                    ts = int(parts[1])
                except:
                    continue
                name = parts[2]
                if name in seen:
                    continue
                seen.add(name)

                # expire timestamp
                exp_ts = 0
                exp_file = f"{EXPIRE_DIR}/{name}"
                if os.path.exists(exp_file):
                    try:
                        exp_ts = int(open(exp_file).read().strip())
                    except:
                        pass

                # traffic
                used = 0
                tf = f"{TRAFFIC_DIR}/{name}"
                if os.path.exists(tf):
                    try:
                        used = int(open(tf).read().strip())
                    except:
                        pass

                limit = 0
                lf = f"{TRAFFIC_LIMITS_DIR}/{name}"
                if os.path.exists(lf):
                    try:
                        limit = int(open(lf).read().strip())
                    except:
                        pass

                # devices limit
                devices = 1
                df = f"{LIMITS_DIR}/{name}"
                if os.path.exists(df):
                    try:
                        devices = int(open(df).read().strip())
                    except:
                        pass

                keys.append({
                    'name': name,
                    'ts': ts,
                    'exp_ts': exp_ts,
                    'traffic': used,
                    'traffic_limit': limit,
                    'devices': devices,
                    'active': exp_ts == 0 or exp_ts > int(time.time())
                })
    except Exception as e:
        cab_log.error(f"get_user_keys: {e}")

    # Сортируем: активные сверху, потом по времени
    keys.sort(key=lambda k: (not k['active'], -k['ts']))
    return keys


def get_password(name):
    p = f"{PASSWORDS_DIR}/{name}"
    if os.path.exists(p):
        try:
            return open(p).read().strip()
        except:
            pass
    return None


def get_domain():
    if os.path.exists(DOMAIN_FILE):
        try:
            return open(DOMAIN_FILE).read().strip()
        except:
            pass
    return ""


def get_ws_port():
    try:
        with open('/usr/local/bin/ws-proxy.py') as f:
            for line in f:
                if 'listen_port' in line:
                    digits = ''.join(ch for ch in line if ch.isdigit())
                    if digits:
                        return digits
    except:
        pass
    return "80"


def get_random_proxy():
    if not os.path.exists(PROXIES_FILE):
        return None
    try:
        proxies = [l.strip() for l in open(PROXIES_FILE) if l.strip() and not l.startswith('#')]
        if proxies:
            import secrets
            return secrets.choice(proxies)
    except:
        pass
    return None


def get_payload():
    if os.path.exists(PAYLOAD_FILE):
        try:
            pl = open(PAYLOAD_FILE).read().strip()
            if pl:
                return pl
        except:
            pass
    return ""


def make_darktunnel_url(username, password, domain, ws_port, proxy):
    """Генерирует darktunnel:// ссылку"""
    if not (username and password and domain):
        return None
    pcfg = get_payload()
    proxy_host = proxy if proxy else ""
    try:
        pport = int(ws_port) if str(ws_port).isdigit() else 2052
    except:
        pport = 2052
    try:
        sport = int(ws_port) if str(ws_port).isdigit() else 2052
    except:
        sport = 2052

    config = {
        "type": "SSH",
        "name": "ArsenVipKeys_" + username,
        "sshTunnelConfig": {
            "sshConfig": {
                "host": domain,
                "port": sport,
                "username": username,
                "password": password
            },
            "injectConfig": {
                "mode": "PROXY",
                "serverNameIndication": "",
                "proxyHost": proxy_host,
                "proxyPort": pport,
                "payload": pcfg
            }
        }
    }
    try:
        j = json.dumps(config, ensure_ascii=False, separators=(',', ':'))
        b = base64.b64encode(j.encode('utf-8')).decode('ascii')
        return "darktunnel://" + b
    except Exception as e:
        cab_log.error(f"make_darktunnel_url: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# UI КАБИНЕТА
# ═══════════════════════════════════════════════════════════════

def show_cabinet(cfg, chat_id, user_id, first_name="", msg_id=None):
    """Главное меню кабинета — данные из БД"""
    token = cfg['BOT_TOKEN']
    user = db.get_user(user_id)
    if not user:
        user = db.upsert_user(user_id, first_name)
    name = user.get('first_name') or first_name or "друг"
    balance = float(user.get('balance') or 0)
    test_keys = db.get_test_keys(user_id, active_only=True)
    vip_keys  = db.get_vip_keys(user_id, active_only=True)
    all_test  = db.get_test_keys(user_id)
    all_vip   = db.get_vip_keys(user_id)
    active_count = len(test_keys) + len(vip_keys)
    total_count  = len(all_test) + len(all_vip)

    NL = chr(10)
    lines = [
        "👤 <b>ЛИЧНЫЙ КАБИНЕТ</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"👋 Добро пожаловать, <b>{name}</b>!",
        "",
        f"🆔 ID пользователя: <code>{user_id}</code>",
        f"💰 Текущий баланс: <b>{balance:.2f} USDT</b>",
        f"🔑 Активных ключей: <b>{active_count}</b>",
        f"👥 Приглашено рефералов: <b>{db.get_ref_count(user_id)}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    text = NL.join(lines)

    keyboard = {'inline_keyboard': [
        [{'text': f'🔑 Мои ключи ({active_count})', 'callback_data': 'cab_keys'},
         {'text': '💎 Купить VIP', 'callback_data': 'cab_buy_vip'}],
        [{'text': '💰 Баланс', 'callback_data': 'cab_balance'},
         {'text': '🎫 Промокод', 'callback_data': 'cab_promo'}],
        [{'text': '👥 Рефералы', 'callback_data': 'cab_refs'},
         {'text': '💬 Поддержка', 'url': 'https://t.me/ArsenGuro'}],
        [{'text': '🏠 В главное меню', 'callback_data': 'cab_exit'}]
    ]}

    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_my_keys(cfg, chat_id, user_id, kind='all', msg_id=None):
    """Короткий список активных ключей. kind: 'all' | 'test' | 'vip'"""
    token = cfg['BOT_TOKEN']

    test_keys = db.get_test_keys(user_id, active_only=True)
    vip_keys  = db.get_vip_keys(user_id, active_only=True)

    if kind == 'test':
        items = [('test', k) for k in test_keys]
    elif kind == 'vip':
        items = [('vip', k) for k in vip_keys]
    else:
        items = [('test', k) for k in test_keys] + [('vip', k) for k in vip_keys]

    NL = chr(10)
    lines = ["🔑 <b>МОИ КЛЮЧИ</b>", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not items:
        lines.append("❌ Нет активных ключей.")
        lines.append("")
        lines.append("🎁 Получить тест — через канал")
        lines.append("💎 Купить VIP — @ArsenGuro")
    else:
        for kk, k in items:
            if k['expires_at'] == 0:
                t = "♾ бессрочно"
            else:
                left = k['expires_at'] - int(time.time())
                t = _human_time(left) if left > 0 else "❌ истёк"
            icon = "💎" if kk == 'vip' else "🎁"
            used = _human_bytes(k['traffic_used'])
            if k['traffic_limit'] > 0:
                limit = _human_bytes(k['traffic_limit'])
                traffic_str = f"{used} / {limit}"
            else:
                traffic_str = f"{used} / ∞"
            lines.append(f"{icon} <b>{k['login']}</b>")
            lines.append(f"     ⏰ {t} · 📊 {traffic_str}")
            lines.append("")
        lines.append("<i>Тапни по ключу ниже — детали и конфиг</i>")
    text = NL.join(lines)

    keyboard = {'inline_keyboard': []}
    if not items:
        me = _tg(token, 'getMe')
        bot_u = me['result'].get('username', '') if me and me.get('ok') else ''
        keyboard['inline_keyboard'].append([
            {'text': '🎁 Получить тест', 'url': f'https://t.me/{bot_u}?start=go'}
        ])
        keyboard['inline_keyboard'].append([
            {'text': '💎 Купить VIP', 'callback_data': 'cab_buy_vip'}
        ])
    else:
        keyboard['inline_keyboard'].append([
            {'text': f"🎁 Тестовые ({len(test_keys)})", 'callback_data': 'cab_keys_test'},
            {'text': f"💎 VIP ({len(vip_keys)})", 'callback_data': 'cab_keys_vip'}
        ])
    if kind != 'all':
        keyboard['inline_keyboard'].append([
            {'text': '📋 Все ключи', 'callback_data': 'cab_keys'}
        ])
    for kk, k in items[:10]:
        icon = "💎" if kk == 'vip' else "🎁"
        keyboard['inline_keyboard'].append([
            {'text': f"{icon} {k['login']}", 'callback_data': f"cab_key:{k['login']}"}
        ])
    keyboard['inline_keyboard'].append([
        {'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}
    ])

    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_key_detail(cfg, chat_id, user_id, key_name, msg_id=None):
    """Детали ключа (из БД)"""
    token = cfg['BOT_TOKEN']

    key = db.get_test_key(key_name)
    kind = 'test'
    if not key:
        key = db.get_vip_key(key_name)
        kind = 'vip'
    if not key or int(key['tg_id']) != int(user_id):
        _send(token, chat_id, "❌ Ключ не найден")
        return

    location = cfg.get('SERVER_LOCATION', '🇩🇪 Германия')
    now = int(time.time())
    created_ts = key['created_at'] or now
    exp_ts = key['expires_at'] or 0

    from datetime import datetime
    created_str = datetime.fromtimestamp(created_ts).strftime('%d.%m.%Y %H:%M')
    if exp_ts > 0:
        exp_str = datetime.fromtimestamp(exp_ts).strftime('%d.%m.%Y %H:%M')
        left = exp_ts - now
        if left > 0:
            t = _human_time(left)
        else:
            t = "❌ истёк"
    else:
        exp_str = "♾ бессрочно"
        t = "♾ бессрочно"

    traffic = _human_bytes(key['traffic_used'])
    if key['traffic_limit'] > 0:
        traffic += f" / {_human_bytes(key['traffic_limit'])}"
    else:
        traffic += " / ∞"

    icon = "💎" if kind == 'vip' else "🎁"
    NL = chr(10)
    lines = [
        f"{icon} <b>КЛЮЧ {key_name}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📅 Создан:     {created_str}",
        f"⏰ Истекает:   {exp_str}",
        f"⏳ Осталось:   {t}",
        f"📊 Трафик:     {traffic}",
        f"📱 Устройств:  {key['devices']}",
        f"🌍 Локация:    {location}",
        "━━━━━━━━━━━━━━━━━━━━"
    ]
    text = NL.join(lines)

    is_active = exp_ts == 0 or exp_ts > now
    keyboard = {'inline_keyboard': []}
    if is_active:
        keyboard['inline_keyboard'].append([
            {'text': '📲 Получить конфиг', 'callback_data': f'cab_dt:{key_name}'}
        ])
    back_kind = 'cab_keys_vip' if kind == 'vip' else 'cab_keys_test'
    keyboard['inline_keyboard'].append([
        {'text': '⬅️ К ключам', 'callback_data': back_kind}
    ])

    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_darktunnel_url(cfg, chat_id, user_id, key_name, msg_id=None):
    """Отправляет darktunnel:// конфиг НОВЫМ сообщением"""
    token = cfg['BOT_TOKEN']

    key = db.get_test_key(key_name) or db.get_vip_key(key_name)
    if not key or int(key['tg_id']) != int(user_id):
        _send(token, chat_id, "❌ Ключ не найден")
        return
    if key['expires_at'] > 0 and key['expires_at'] < int(time.time()):
        _send(token, chat_id, "❌ Ключ истёк")
        return
    password = key['password']
    if not password:
        _send(token, chat_id, "❌ Пароль не найден")
        return

    domain = get_domain()
    ws_port = get_ws_port()
    proxy = get_random_proxy()
    dt_url = make_darktunnel_url(key_name, password, domain, ws_port, proxy)
    if not dt_url:
        _send(token, chat_id, "❌ Не удалось создать конфиг")
        return

    NL = chr(10)
    text = NL.join([
        "📲 <b>КОНФИГ DarkTunnel</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "<b>Тапни по коду ниже — он скопируется:</b>",
        "",
        f"<code>{dt_url}</code>",
        "",
        "<i>Затем открой DarkTunnel → ➕ → Импорт из буфера</i>"
    ])
    keyboard = {'inline_keyboard': [
        [{'text': '🗑 Удалить сообщение', 'callback_data': f'cab_delmsg:{key_name}'}]
    ]}
    _send(token, chat_id, text, keyboard)


def show_balance(cfg, chat_id, user_id, msg_id=None):
    """Экран баланса с последними 5 операциями"""
    token = cfg['BOT_TOKEN']
    balance = db.get_balance(user_id)
    payments = db.get_payments(user_id, limit=5, offset=0)

    NL = chr(10)
    lines = [
        "💰 <b>БАЛАНС</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"💵 Текущий баланс: <b>{balance:.2f} USDT</b>",
    ]
    if payments:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("📊 <b>Последние операции</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        for p in payments:
            amt = float(p['amount'])
            sign = "+" if amt >= 0 else ""
            icon = "🟢" if amt >= 0 else "🔴"
            method = p.get('method') or 'manual'
            labels = {
                'manual': 'Пополнение от админа',
                'referral_bonus': 'Реферальный бонус',
                'promo': 'Промокод',
                'purchase': 'Покупка',
                'usdt': 'USDT-платёж'
            }
            label = labels.get(method, method)
            from datetime import datetime as _dt
            dt = _dt.fromtimestamp(p['created_at']).strftime('%d.%m.%Y %H:%M')
            lines.append(f"{icon} <b>{sign}{amt:.2f} USDT</b>")
            lines.append(f"   {label}")
            lines.append(f"   <i>{dt}</i>")
            lines.append("")
    else:
        lines.append("")
        lines.append("<i>Пока операций нет</i>")

    text = NL.join(lines)

    kb = {'inline_keyboard': [
        [{'text': '💵 Пополнить', 'callback_data': 'cab_topup'},
         {'text': '📜 Вся история', 'callback_data': 'cab_hist:1'}],
        [{'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


def show_balance_history(cfg, chat_id, user_id, page=1, msg_id=None):
    """Полная история платежей с пагинацией"""
    token = cfg['BOT_TOKEN']
    per_page = 10
    total = db.count_payments(user_id)
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page < 1: page = 1
    if page > total_pages: page = total_pages
    offset = (page - 1) * per_page
    payments = db.get_payments(user_id, limit=per_page, offset=offset)

    NL = chr(10)
    lines = [
        f"📜 <b>ИСТОРИЯ ОПЕРАЦИЙ</b>",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"<i>Стр. {page}/{total_pages} · всего {total}</i>",
        ""
    ]
    if not payments:
        lines.append("<i>История пуста</i>")
    else:
        from datetime import datetime as _dt
        labels = {
            'manual': 'Пополнение',
            'referral_bonus': 'Реферальный бонус',
            'promo': 'Промокод',
            'purchase': 'Покупка',
            'usdt': 'USDT-платёж'
        }
        for p in payments:
            amt = float(p['amount'])
            sign = "+" if amt >= 0 else ""
            icon = "🟢" if amt >= 0 else "🔴"
            label = labels.get(p.get('method'), p.get('method', '—'))
            dt = _dt.fromtimestamp(p['created_at']).strftime('%d.%m.%y %H:%M')
            lines.append(f"{icon} <b>{sign}{amt:.2f} USDT</b> · {label}")
            lines.append(f"   <i>{dt}</i>")
            lines.append("")
    text = NL.join(lines)

    # Навигация
    nav = []
    if page > 1:
        nav.append({'text': '◀', 'callback_data': f'cab_hist:{page-1}'})
    nav.append({'text': f'{page}/{total_pages}', 'callback_data': 'noop'})
    if page < total_pages:
        nav.append({'text': '▶', 'callback_data': f'cab_hist:{page+1}'})
    kb = {'inline_keyboard': []}
    if nav:
        kb['inline_keyboard'].append(nav)
    kb['inline_keyboard'].append([{'text': '⬅️ К балансу', 'callback_data': 'cab_balance'}])

    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


def show_promo(cfg, chat_id, user_id, msg_id=None):
    """Экран промокода у юзера"""
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    lines = [
        "🎫 <b>ПРОМОКОД</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "🎁 Есть промокод?",
        "Введи его и получи бонус",
        "к своим активным ключам!",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📢 Промокоды публикуем в канале",
        "💬 Не работает? @ArsenGuro"
    ]
    text = NL.join(lines)
    keyboard = {'inline_keyboard': [
        [{'text': '✏️ Ввести промокод', 'callback_data': 'cab_promo_input'}],
        [{'text': '📢 Наш канал', 'url': 'https://t.me/ArsenVipKeys'}],
        [{'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def _parse_vip_tariffs(cfg):
    """Парсит VIP_TARIFFS из конфига. Возвращает список dict."""
    raw = cfg.get('VIP_TARIFFS', '10|2|100|1,30|5|300|1,90|13|900|1')
    tariffs = []
    for item in raw.split(','):
        parts = item.strip().split('|')
        if len(parts) < 4:
            continue
        try:
            tariffs.append({
                'days': int(parts[0]),
                'price': float(parts[1]),
                'gb': int(parts[2]),
                'devices': int(parts[3])
            })
        except:
            continue
    return tariffs


def show_buy_vip(cfg, chat_id, user_id, msg_id=None):
    """Экран покупки VIP-ключа с выбором тарифа"""
    token = cfg['BOT_TOKEN']
    tariffs = _parse_vip_tariffs(cfg)
    balance = db.get_balance(user_id)

    NL = chr(10)
    lines = [
        "💎 <b>КУПИТЬ VIP-КЛЮЧ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"💰 Твой баланс: <b>{balance:.2f} USDT</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📋 <b>Тарифы:</b>",
        ""
    ]
    kb_rows = []
    for i, t in enumerate(tariffs, 1):
        can_buy = balance >= t['price']
        mark = "✅" if can_buy else "❌"
        lines.append(f"{mark} <b>{t['days']} дней</b> — {t['price']:.0f} USDT")
        lines.append(f"   📊 {t['gb']} ГБ · 📱 {t['devices']} устр.")
        lines.append("")
        kb_rows.append([{
            'text': f"💎 {t['days']}д — {t['price']:.0f} USDT",
            'callback_data': f'cab_vip_buy:{i}'
        }])

    if any(balance < t['price'] for t in tariffs):
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚠️ Не хватает баланса? Пополни:")
        lines.append("<i>Нажми «💵 Пополнить» ниже</i>")

    text = NL.join(lines)

    kb_rows.append([
        {'text': '💵 Пополнить', 'callback_data': 'cab_topup'},
        {'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}
    ])
    kb = {'inline_keyboard': kb_rows}

    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


def show_vip_confirm(cfg, chat_id, user_id, tariff_idx, msg_id=None):
    """Шаг 2 — просим имя ключа (перед покупкой)"""
    token = cfg['BOT_TOKEN']
    tariffs = _parse_vip_tariffs(cfg)
    if tariff_idx < 1 or tariff_idx > len(tariffs):
        _send(token, chat_id, "❌ Тариф не найден")
        return
    t = tariffs[tariff_idx - 1]
    balance = db.get_balance(user_id)

    # Проверяем хватает ли баланса
    if balance < t['price']:
        diff = t['price'] - balance
        NL = chr(10)
        text = NL.join([
            "⚠️ <b>НЕ ХВАТАЕТ БАЛАНСА</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"Тариф: <b>{t['days']} дней</b> · {t['gb']} ГБ",
            f"Стоимость: <b>{t['price']:.2f} USDT</b>",
            f"У тебя: <b>{balance:.2f} USDT</b>",
            f"Не хватает: <b>{diff:.2f} USDT</b>",
            "",
            "Пополни баланс и попробуй снова"
        ])
        kb = {'inline_keyboard': [
            [{'text': '💵 Пополнить', 'callback_data': 'cab_topup'}],
            [{'text': '⬅️ К тарифам', 'callback_data': 'cab_buy_vip'}]
        ]}
        _edit(token, chat_id, msg_id, text, kb)
        return

    # Всё ок — просим имя
    NL = chr(10)
    text = NL.join([
        "💎 <b>ПОКУПКА VIP — ИМЯ КЛЮЧА</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📦 Тариф: <b>{t['days']} дней</b>",
        f"📊 Трафик: <b>{t['gb']} ГБ</b>",
        f"📱 Устройств: <b>{t['devices']}</b>",
        f"💵 Цена: <b>{t['price']:.2f} USDT</b>",
        f"💰 Баланс: <b>{balance:.2f} USDT</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "✏️ <b>Придумай имя для ключа</b>",
        "",
        "Чтобы отличать ключи (если будет несколько).",
        "",
        "📝 Правила:",
        "• Только латиница: <b>a-z, 0-9, _</b>",
        "• Минимум 5 символов",
        "",
        "Пример: <code>my_phone</code>, <code>for_mom</code>",
        "",
        "Логин будет: <code>vip_имя</code>"
    ])
    kb = {'inline_keyboard': [
        [{'text': '⬅️ Отмена', 'callback_data': 'cab_buy_vip'}]
    ]}
    _edit(token, chat_id, msg_id, text, kb)
    # Просим ввести имя через ForceReply + запоминаем pending
    try:
        db.set_pending(user_id, f'vip_name:{tariff_idx}')
    except Exception as e:
        cab_log.error(f"set_pending vip_name: {e}")
    _send(token, chat_id, "✏️ Напиши имя ключа ответом на это сообщение 👇",
          {'force_reply': True, 'selective': True})


def show_vip_final_confirm(cfg, chat_id, user_id, tariff_idx, name, msg_id=None):
    """Финальное подтверждение после ввода имени"""
    token = cfg['BOT_TOKEN']
    tariffs = _parse_vip_tariffs(cfg)
    if tariff_idx < 1 or tariff_idx > len(tariffs):
        _send(token, chat_id, "❌ Тариф не найден")
        return
    t = tariffs[tariff_idx - 1]
    balance = db.get_balance(user_id)

    NL = chr(10)
    text = NL.join([
        "💎 <b>ПОДТВЕРДИ ПОКУПКУ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"👤 Имя: <b>{name}</b>",
        f"📱 Логин: <code>vip_{name}</code>",
        "",
        f"📦 Тариф: <b>{t['days']} дней</b>",
        f"📊 Трафик: <b>{t['gb']} ГБ</b>",
        f"📱 Устройств: <b>{t['devices']}</b>",
        "",
        f"💵 Цена: <b>{t['price']:.2f} USDT</b>",
        f"💰 Баланс после: <b>{balance - t['price']:.2f} USDT</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "Подтверждаешь?"
    ])
    kb = {'inline_keyboard': [
        [{'text': f"✅ Купить за {t['price']:.0f} USDT", 'callback_data': f'cab_vip_confirm:{tariff_idx}'}],
        [{'text': '✏️ Изменить имя', 'callback_data': f'cab_vip_buy:{tariff_idx}'}],
        [{'text': '❌ Отмена', 'callback_data': 'cab_buy_vip'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)




def show_referrals(cfg, chat_id, user_id, msg_id=None):
    """Реферальная программа — условия"""
    token = cfg['BOT_TOKEN']

    user = db.get_user(user_id)
    ref_code = user['ref_code'] if user else 'unknown'
    bot_username = 'ArsenVipKeysBot'
    me = _tg(token, 'getMe')
    if me and me.get('ok'):
        bot_username = me['result'].get('username', bot_username)
    ref_link = f"https://t.me/{bot_username}?start=ref_{ref_code}"

    inv = db.get_ref_count(user_id)
    earned = db.get_ref_bonus_total(user_id)

    NL = chr(10)
    text = NL.join([
        "👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "🎁 <b>Награды за каждого друга:</b>",
        "",
        "🎁 <b>+3 дня</b> к твоему VIP-ключу",
        "    <i>— когда друг получит тестовый ключ</i>",
        "",
        "💵 <b>+1.00 USDT</b> на баланс",
        "    <i>— когда друг купит VIP-ключ</i>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "🔗 <b>Твоя ссылка:</b>",
        f"<code>{ref_link}</code>",
        "",
        f"📊 Приглашено: <b>{inv}</b>",
        f"💰 Заработано: <b>{earned:.2f} USDT</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "<i>Скопируй ссылку и отправь друзьям 👇</i>"
    ])
    keyboard = {'inline_keyboard': [
        [{'text': '📤 Поделиться', 'url': f'https://t.me/share/url?url={ref_link}&text=Забирай+VPN!'}],
        [{'text': '📋 Мои рефералы', 'callback_data': 'cab_ref_list'}],
        [{'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_ref_list(cfg, chat_id, user_id, msg_id=None):
    """Список приглашённых рефералов"""
    token = cfg['BOT_TOKEN']
    refs = db.get_ref_list(user_id)
    NL = chr(10)
    lines = [
        "👥 <b>МОИ РЕФЕРАЛЫ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<i>Всего: {len(refs)}</i>",
        ""
    ]
    if not refs:
        lines.append("<i>Пока никого нет</i>")
        lines.append("")
        lines.append("Отправь друзьям свою ссылку 👇")
    else:
        from datetime import datetime as _dt
        for r in refs:
            name = r.get('first_name') or '—'
            uname = r.get('username') or ''
            dt = _dt.fromtimestamp(r['ts']).strftime('%d.%m.%Y')
            test_ok = "✅" if r.get('test_bonus_paid') else "⏳"
            buy_ok = "✅" if r.get('bonus_paid') else "⏳"
            handle = f"@{uname}" if uname else f"id{r['invited_id']}"
            lines.append(f"👤 <b>{name}</b> · {handle}")
            lines.append(f"   🎁 тест: {test_ok} · 💵 покупка: {buy_ok}")
            lines.append(f"   <i>{dt}</i>")
            lines.append("")
    text = NL.join(lines)
    kb = {'inline_keyboard': [
        [{'text': '⬅️ К рефералам', 'callback_data': 'cab_refs'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


def show_create_key(cfg, chat_id, user_id, msg_id=None):
    """Меню создания ключа"""
    token = cfg['BOT_TOKEN']
    text = (
        f"➕ <b>СОЗДАТЬ КЛЮЧ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎁 <b>Тестовый</b> — бесплатно на 8 часов\n"
        f"💎 <b>VIP</b> — платный, без ограничений\n\n"
        f"Что создаём?"
    )
    keyboard = {'inline_keyboard': [
        [{'text': '🎁 Тестовый ключ', 'callback_data': 'cab_create_test'}],
        [{'text': '💎 VIP-ключ', 'callback_data': 'cab_create_vip'}],
        [{'text': '⬅️ Назад', 'callback_data': 'cab_main'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_help_instruction(cfg, chat_id, user_id, msg_id=None):
    """Инструкция по подключению"""
    token = cfg['BOT_TOKEN']
    text = (
        "📖 <b>ИНСТРУКЦИЯ ПО ПОДКЛЮЧЕНИЮ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>1. Скачай DarkTunnel</b>\n"
        "Google Play: DarkTunnel - SSH DNSTT V2Ray\n\n"
        "<b>2. Получи ключ в боте</b>\n"
        "Зайди в канал → нажми кнопку → получи конфиг\n\n"
        "<b>3. Скопируй darktunnel:// ссылку</b>\n"
        "Из сообщения с ключом\n\n"
        "<b>4. Открой DarkTunnel</b>\n"
        "Нажми ➕ → Импорт из буфера обмена\n\n"
        "<b>5. Нажми CONNECT</b>\n"
        "Готово! Ты в свободном интернете 🎉\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💬 Проблемы? Пиши @ArsenGuro"
    )
    keyboard = {'inline_keyboard': [
        [{'text': '⬅️ Назад', 'callback_data': 'cab_help_back'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_help_faq(cfg, chat_id, user_id, msg_id=None):
    """FAQ"""
    token = cfg['BOT_TOKEN']
    text = (
        "❓ <b>ЧАСТЫЕ ВОПРОСЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🔴 Ключ не работает?</b>\n"
        "Проверь: срок не истёк? Трафик не закончился?\n\n"
        "<b>🔴 Не подключается?</b>\n"
        "Проверь интернет, попробуй сменить Wi-Fi на моб.\n\n"
        "<b>🔴 Auth failed?</b>\n"
        "Проверь логин/пароль, скопируй заново\n\n"
        "<b>💎 Как получить VIP?</b>\n"
        "Пиши @ArsenGuro\n\n"
        "<b>📱 Сколько устройств?</b>\n"
        "По лимиту в ключе (обычно 1-5)\n\n"
        "<b>⏰ Сколько работает ключ?</b>\n"
        "Тест — 8 часов, VIP — по тарифу\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💬 Не нашёл ответ? @ArsenGuro"
    )
    keyboard = {'inline_keyboard': [
        [{'text': '⬅️ Назад', 'callback_data': 'cab_help_back'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_help_back(cfg, chat_id, user_id, msg_id=None):
    """Назад к /help"""
    token = cfg['BOT_TOKEN']
    channels = []
    # Получаем каналы
    ch_file = "/etc/UDPCustom/channels.txt"
    if os.path.exists(ch_file):
        try:
            channels = [l.strip() for l in open(ch_file) if l.strip() and not l.startswith('#')]
        except:
            pass
    primary = channels[0].lstrip('@') if channels else 'ArsenVipKeys'

    text = (
        f"📖 <b>Как получить тестовый ключ?</b>\n\n"
        f"1️⃣ Зайди в канал 👉 @{primary}\n"
        f"2️⃣ Найди пост с кнопкой <b>«🎁 Получить тест»</b>\n"
        f"3️⃣ Нажми на неё — ключ придёт в этот бот\n"
    )
    keyboard = {'inline_keyboard': [
        [{'text': '📖 Инструкция', 'callback_data': 'cab_help_instruction'},
         {'text': '❓ FAQ', 'callback_data': 'cab_help_faq'}],
        [{'text': '🎬 Видео', 'url': f'https://t.me/{primary}'},
         {'text': '👤 Кабинет', 'callback_data': 'cab_main'}],
        [{'text': f'📢 Перейти в @{primary}', 'url': f'https://t.me/{primary}'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def handle_cabinet_callback(cfg, cb_data, cb, user_id, first_name):
    """Обработчик всех callback'ов кабинета.
    Возвращает True если обработано, False если не наш callback."""
    token = cfg['BOT_TOKEN']
    chat_id = cb['message']['chat']['id']
    msg_id = cb['message']['message_id']

    # Ответ на callback (убираем «крутилку»)
    _tg(token, 'answerCallbackQuery', {'callback_query_id': cb['id']})

    if cb_data == 'cab_help_instruction':
        show_help_instruction(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_help_faq':
        show_help_faq(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_help_back':
        show_help_back(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_main':
        show_cabinet(cfg, chat_id, user_id, first_name, msg_id)
        return True
    if cb_data == 'cab_keys':
        show_my_keys(cfg, chat_id, user_id, 'all', msg_id)
        return True
    if cb_data == 'cab_keys_test':
        show_my_keys(cfg, chat_id, user_id, 'test', msg_id)
        return True
    if cb_data == 'cab_keys_vip':
        show_my_keys(cfg, chat_id, user_id, 'vip', msg_id)
        return True
    if cb_data == 'cab_buy_vip':
        show_buy_vip(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data.startswith('cab_vip_buy:'):
        try:
            idx = int(cb_data.split(':', 1)[1])
        except:
            idx = 1
        show_vip_confirm(cfg, chat_id, user_id, idx, msg_id)
        return True
    if cb_data == 'cab_balance':
        show_balance(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_topup_send':
        # Спрашиваем сколько хочет пополнить
        NL = chr(10)
        ask = NL.join([
            "💵 <b>СКОЛЬКО ХОЧЕШЬ ПОПОЛНИТЬ?</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "Отправь сумму в USDT (только цифры).",
            "",
            "Например: <code>10</code> или <code>5.5</code>",
            "",
            "<i>Минимум 1 USDT</i>"
        ])
        _edit(token, chat_id, msg_id, ask, {'inline_keyboard': [
            [{'text': '⬅️ Отмена', 'callback_data': 'cab_topup'}]
        ]})
        # Запоминаем что ждём сумму
        try:
            db.set_pending(user_id, 'topup_amount')
        except Exception as e:
            cab_log.error(f"set_pending topup: {e}")
        return True
    if cb_data == 'cab_topup':
        NL = chr(10)
        balance = db.get_balance(user_id)
        text = NL.join([
            "💵 <b>ПОПОЛНЕНИЕ БАЛАНСА</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"Твой баланс: <b>{balance:.2f} USDT</b>",
            "",
            "Для пополнения напиши админу:",
            "👉 @ArsenGuro",
            "",
            f"Укажи свой ID: <code>{user_id}</code>",
            "",
            "<i>Скоро — автоплатежи (USDT)</i>"
        ])
        kb = {'inline_keyboard': [
            [{'text': '📤 Отправить заявку админу', 'callback_data': 'cab_topup_send'}],
            [{'text': '💬 Написать @ArsenGuro', 'url': 'https://t.me/ArsenGuro'}],
            [{'text': '⬅️ К балансу', 'callback_data': 'cab_balance'}]
        ]}
        _edit(token, chat_id, msg_id, text, kb)
        return True
    if cb_data.startswith('cab_hist:'):
        try:
            page = int(cb_data.split(':', 1)[1])
        except:
            page = 1
        show_balance_history(cfg, chat_id, user_id, page, msg_id)
        return True
    if cb_data == 'cab_promo':
        show_promo(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_promo_input':
        NL = chr(10)
        text = NL.join([
            "✏️ <b>ВВОД ПРОМОКОДА</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "Отправь промокод следующим сообщением",
            "(одним словом, без пробелов)",
            "",
            "Например: <code>NEWYEAR</code>"
        ])
        _edit(token, chat_id, msg_id, text, {'inline_keyboard': [
            [{'text': '⬅️ Отмена', 'callback_data': 'cab_promo'}]
        ]})
        try:
            from bot_modules import db as _db
            _db.set_pending(user_id, 'promo_input')
        except Exception as e:
            cab_log.error(f"set_pending: {e}")
        return True
    if cb_data == 'cab_refs':
        show_referrals(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_ref_list':
        show_ref_list(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_exit':
        # Возврат в /start
        _tg(token, 'answerCallbackQuery', {
            'callback_query_id': cb['id'],
            'text': '🏠 Отправь /start чтобы вернуться'
        })
        _edit(token, chat_id, msg_id,
              "🏠 <b>Выход из кабинета</b>\n\nНапиши /start для возврата в главное меню.",
              {'inline_keyboard': []})
        return True
    if cb_data.startswith('cab_key:'):
        key_name = cb_data.split(':', 1)[1]
        show_key_detail(cfg, chat_id, user_id, key_name, msg_id)
        return True
    if cb_data.startswith('cab_delmsg:'):
        try:
            _tg(token, 'deleteMessage', {'chat_id': chat_id, 'message_id': msg_id})
        except: pass
        return True
    if cb_data.startswith('cab_dt:'):
        key_name = cb_data.split(':', 1)[1]
        show_darktunnel_url(cfg, chat_id, user_id, key_name)
        return True
    if cb_data.startswith('cab_copy:'):
        key_name = cb_data.split(':', 1)[1]
        _tg(token, 'answerCallbackQuery', {
            'callback_query_id': cb['id'],
            'text': f'📋 Логин: {key_name}',
            'show_alert': True
        })
        return True

    return False
