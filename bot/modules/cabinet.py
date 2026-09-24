#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Модуль личного кабинета пользователя"""
import os
import json
import time
import base64
import logging
import urllib.request

# ─── Пути ───
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
    """Главное меню кабинета"""
    token = cfg['BOT_TOKEN']
    name = first_name or "друг"

    keys = get_user_keys(user_id)
    active_count = sum(1 for k in keys if k['active'])
    total_count = len(keys)

    text = (
        f"👤 <b>ЛИЧНЫЙ КАБИНЕТ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👋 Добро пожаловать, <b>{name}</b>!\n\n"
        f"🆔 ID пользователя: <code>{user_id}</code>\n"
        f"💰 Текущий баланс: <b>0.00 USDT</b>\n"
        f"🔑 Активных ключей: <b>{active_count}</b>\n"
        f"📊 Всего создано ключей: <b>{total_count}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    keyboard = {'inline_keyboard': [
        [{'text': f'🔑 Мои ключи ({active_count})', 'callback_data': 'cab_keys'},
         {'text': '➕ Создать ключ', 'callback_data': 'cab_create'}],
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


def show_my_keys(cfg, chat_id, user_id, msg_id=None):
    """Список ключей пользователя"""
    token = cfg['BOT_TOKEN']
    keys = get_user_keys(user_id)

    if not keys:
        text = (
            f"🔑 <b>МОИ КЛЮЧИ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"❌ У тебя пока нет ключей.\n\n"
            f"Создай первый через <b>«➕ Создать ключ»</b>!"
        )
        keyboard = {'inline_keyboard': [
            [{'text': '➕ Создать ключ', 'callback_data': 'cab_create'}],
            [{'text': '⬅️ Назад', 'callback_data': 'cab_main'}]
        ]}
    else:
        text = (
            f"🔑 <b>МОИ КЛЮЧИ</b> ({len(keys)})\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        for i, k in enumerate(keys[:10], 1):
            if k['active']:
                left = k['exp_ts'] - int(time.time()) if k['exp_ts'] > 0 else 0
                icon = "🟢"
                info = f"⏰ {_human_time(left)}" if k['exp_ts'] > 0 else "♾ бессрочно"
            else:
                icon = "🔴"
                info = "истёк"
            traffic_info = _human_bytes(k['traffic'])
            text += f"{icon} <code>{k['name']}</code> — {info} • {traffic_info}\n"

        keyboard = {'inline_keyboard': []}
        # Кнопки для каждого активного ключа
        for k in keys[:5]:
            if k['active']:
                keyboard['inline_keyboard'].append([
                    {'text': f"🔑 {k['name']}",
                     'callback_data': f"cab_key:{k['name']}"}
                ])
        keyboard['inline_keyboard'].append([
            {'text': '➕ Создать ключ', 'callback_data': 'cab_create'}
        ])
        keyboard['inline_keyboard'].append([
            {'text': '⬅️ Назад', 'callback_data': 'cab_main'}
        ])

    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_key_detail(cfg, chat_id, user_id, key_name, msg_id=None):
    """Детали одного ключа"""
    token = cfg['BOT_TOKEN']

    # Проверим что ключ реально принадлежит юзеру
    keys = get_user_keys(user_id)
    key = next((k for k in keys if k['name'] == key_name), None)
    if not key:
        _send(token, chat_id, "❌ Ключ не найден")
        return

    password = get_password(key_name)
    domain = get_domain()
    ws_port = get_ws_port()
    proxy = get_random_proxy()

    left = key['exp_ts'] - int(time.time()) if key['exp_ts'] > 0 else 0
    if key['exp_ts'] == 0:
        time_str = "♾ бессрочно"
    elif left > 0:
        time_str = _human_time(left)
    else:
        time_str = "❌ истёк"

    traffic_str = _human_bytes(key['traffic'])
    if key['traffic_limit'] > 0:
        traffic_str += f" / {_human_bytes(key['traffic_limit'])}"

    text = (
        f"🔑 <b>КЛЮЧ: {key_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 Логин: <code>{key_name}</code>\n"
        f"🔑 Пароль: <code>{password or '—'}</code>\n"
        f"🌐 Сервер: <code>{domain}</code>\n"
        f"🔌 Порт: <code>{ws_port}</code>\n"
    )
    if proxy:
        text += f"🛡️ Прокси: <code>{proxy}:80</code>\n"
    text += (
        f"\n⏰ Осталось: <b>{time_str}</b>\n"
        f"📊 Трафик: <b>{traffic_str}</b>\n"
        f"📱 Устройств: <b>{key['devices']}</b>\n"
    )

    keyboard = {'inline_keyboard': []}

    # Кнопка darktunnel-ссылки (если активен и есть пароль)
    if key['active'] and password:
        dt_url = make_darktunnel_url(key_name, password, domain, ws_port, proxy)
        if dt_url:
            # Telegram имеет лимит 64 символа на URL, поэтому делаем через callback
            keyboard['inline_keyboard'].append([
                {'text': '📲 Показать конфиг DarkTunnel', 'callback_data': f'cab_dt:{key_name}'}
            ])

    keyboard['inline_keyboard'].append([
        {'text': '📋 Скопировать логин', 'callback_data': f'cab_copy:{key_name}'}
    ])
    keyboard['inline_keyboard'].append([
        {'text': '⬅️ К ключам', 'callback_data': 'cab_keys'}
    ])

    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_darktunnel_url(cfg, chat_id, user_id, key_name, msg_id=None):
    """Показать только darktunnel:// ссылку"""
    token = cfg['BOT_TOKEN']

    keys = get_user_keys(user_id)
    key = next((k for k in keys if k['name'] == key_name), None)
    if not key or not key['active']:
        _send(token, chat_id, "❌ Ключ не найден или истёк")
        return

    password = get_password(key_name)
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

    text = (
        f"📲 <b>Ссылка-конфиг для DarkTunnel</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Тапни и скопируй:</b>\n\n"
        f"<code>{dt_url}</code>\n\n"
        f"Вставь в DarkTunnel → Конфиг"
    )
    keyboard = {'inline_keyboard': [
        [{'text': '⬅️ К ключу', 'callback_data': f'cab_key:{key_name}'}]
    ]}
    _send(token, chat_id, text, keyboard)


def show_balance(cfg, chat_id, user_id, msg_id=None):
    """Заглушка баланса"""
    token = cfg['BOT_TOKEN']
    text = (
        f"💰 <b>БАЛАНС</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💵 Текущий баланс: <b>0.00 USDT</b>\n\n"
        f"⚠️ Пополнение скоро будет доступно.\n"
        f"Пока что VIP-ключи выдаются вручную — пиши @ArsenGuro"
    )
    keyboard = {'inline_keyboard': [
        [{'text': '💬 Написать админу', 'url': 'https://t.me/ArsenGuro'}],
        [{'text': '⬅️ Назад', 'callback_data': 'cab_main'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_promo(cfg, chat_id, user_id, msg_id=None):
    """Заглушка промокода"""
    token = cfg['BOT_TOKEN']
    text = (
        f"🎫 <b>ПРОМОКОД</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚠️ Раздел скоро будет доступен.\n\n"
        f"Следи за анонсами в канале @ArsenVipKeys"
    )
    keyboard = {'inline_keyboard': [
        [{'text': '📢 Наш канал', 'url': 'https://t.me/ArsenVipKeys'}],
        [{'text': '⬅️ Назад', 'callback_data': 'cab_main'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_referrals(cfg, chat_id, user_id, msg_id=None):
    """Заглушка рефералов"""
    token = cfg['BOT_TOKEN']
    ref_link = f"https://t.me/ArsenVipKeysBot?start=ref_{user_id}"
    text = (
        f"👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎁 Пригласи друга → получи <b>+3 дня</b> к ключу!\n\n"
        f"🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"📊 Приглашено: <b>0</b>\n"
        f"🎁 Получено бонусов: <b>+0 дней</b>"
    )
    keyboard = {'inline_keyboard': [
        [{'text': '📤 Поделиться', 'url': f'https://t.me/share/url?url={ref_link}&text=Забирай+бесплатный+VPN!'}],
        [{'text': '⬅️ Назад', 'callback_data': 'cab_main'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


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
        show_my_keys(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_create':
        show_create_key(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_balance':
        show_balance(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_promo':
        show_promo(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_refs':
        show_referrals(cfg, chat_id, user_id, msg_id)
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
