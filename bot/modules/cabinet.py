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
    """Умный чат: редактирует предыдущее сообщение (не скрывает reply-клавиатуру)."""
    try:
        os.makedirs(SMART_DIR, exist_ok=True)
        path = f"{SMART_DIR}/{chat_id}"
        old_id = None
        if os.path.exists(path):
            try:
                old_id = int(open(path).read().strip())
            except: pass
        # 1) Пробуем отредактировать старое (сохраняет reply-клавиатуру)
        if old_id:
            r = _edit(token, chat_id, old_id, text, reply_markup)
            if r and r.get('ok'):
                return r
            # если edit упал (не изменилось / удалено) — падаем на новый send
        # 2) Новое сообщение
        params = {'chat_id': chat_id, 'text': text,
                  'disable_web_page_preview': True, 'parse_mode': parse_mode}
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
        params = {'chat_id': chat_id, 'text': text,
                  'disable_web_page_preview': True, 'parse_mode': parse_mode}
        if reply_markup:
            params['reply_markup'] = reply_markup
        return _tg(token, 'sendMessage', params)



def _edit(token, chat_id, msg_id, text, reply_markup=None):
    params = {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML',
              'disable_web_page_preview': True}
    if reply_markup:
        params['reply_markup'] = reply_markup
    r = _tg(token, 'editMessageText', params)
    # Обновляем SMART_DIR чтобы _send знал актуальный msg_id
    if r and r.get('ok'):
        try:
            os.makedirs(SMART_DIR, exist_ok=True)
            with open(f"{SMART_DIR}/{chat_id}", 'w') as _f:
                _f.write(str(msg_id))
        except: pass
    return r


def _send_new(token, chat_id, text, reply_markup=None, parse_mode='HTML'):
    """Удаляет старое бот-сообщение и шлёт новое (для команд)."""
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
        params = {'chat_id': chat_id, 'text': text,
                  'disable_web_page_preview': True, 'parse_mode': parse_mode}
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
        cab_log.error(f"_send_new error: {e}")
        return None


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


def _format_config_name(username, loc='VPN'):
    """Красивое имя для DarkTunnel."""
    u = username.lower()
    if u.startswith('test'):
        try:
            row = db.query_one("SELECT created_at FROM test_keys WHERE login=?", (username,))
            if row and row.get('created_at'):
                from datetime import datetime as _dt
                date_str = _dt.fromtimestamp(row['created_at']).strftime('%d.%m')
                return f"🎁 TEST {loc} {date_str}"
        except: pass
        suffix = username[4:]
        return f"🎁 TEST {loc} {suffix}" if suffix else f"🎁 TEST {loc}"
    if u.startswith('vip_'):
        suffix = username[4:]
        parts = suffix.split('_')
        if len(parts) > 1 and parts[0].isdigit():
            suffix = parts[-1]
        return f"💎 VIP {loc} {suffix}" if suffix else f"💎 VIP {loc}"
    return f"⭐  {username}"

def make_darktunnel_url(username, password, domain, ws_port, proxy, loc='VPN'):
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
        "name": _format_config_name(username, loc),
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
        b = base64.urlsafe_b64encode(j.encode("utf-8")).decode("ascii").rstrip("=")
        return "darktunnel://" + b
    except Exception as e:
        cab_log.error(f"make_darktunnel_url: {e}")
        return None
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
         {'text': '💰 Баланс', 'callback_data': 'cab_balance'},
         {'text': '🎫 Промокод', 'callback_data': 'cab_promo'}],
        [{'text': '💎 DarkTunnel', 'callback_data': 'cab_buy_vip'},
         {'text': '💎 HttpCustom', 'callback_data': 'cab_udp_soon'},
         {'text': '💎 WhiteDns', 'callback_data': 'cab_whitedns'}],
        [{'text': '👥 Рефералы', 'callback_data': 'cab_refs'},
         {'text': '\U0001F6DF Помощь', 'callback_data': 'cab_help'},
         {'text': '🏠 Меню', 'callback_data': 'cab_exit'}]
    ]}

    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send_new(token, chat_id, text, keyboard)


def show_my_keys(cfg, chat_id, user_id, kind='all', msg_id=None):
    """Короткий список активных ключей с кнопкой удаления. kind: 'all' | 'test' | 'vip'"""
    token = cfg['BOT_TOKEN']

    test_keys = db.get_test_keys(user_id, active_only=True)
    vip_keys  = db.get_vip_keys(user_id, active_only=True)

    if kind == 'test':
        items = [('test', k) for k in test_keys]
        title = "🎁 ТЕСТОВЫЕ КЛЮЧИ"
    elif kind == 'vip':
        items = [('vip', k) for k in vip_keys]
        title = "💎 VIP-КЛЮЧИ"
    else:
        items = [('test', k) for k in test_keys] + [('vip', k) for k in vip_keys]
        title = "🔑 МОИ КЛЮЧИ"

    NL = chr(10)
    lines = [f"{title} ({len(items)})", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not items:
        lines.append("❌ Нет активных ключей")
        lines.append("")
        # Читаем каналы
        channels = []
        try:
            with open("/etc/UDPCustom/channels.txt") as f:
                channels = [l.strip().lstrip('@') for l in f if l.strip() and not l.startswith('#')]
        except: pass
        primary = channels[0] if channels else "ArsenVipKeys"
        sponsors = channels[1:] if len(channels) > 1 else []
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🎁 <b>КАК ПОЛУЧИТЬ БЕСПЛАТНЫЙ ТЕСТ</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(f"1️⃣ Зайди в канал @{primary}")
        lines.append("2️⃣ Поставь 👍 лайки на 3 последних поста")
        lines.append("")
        if sponsors:
            lines.append("3️⃣ Подпишись на спонсоров (обязательно!):")
            lines.append("")
            for s in sponsors:
                lines.append(f"   📢 @{s}")
            lines.append("   ⚠️ Без подписки ключ не дадут")
            lines.append("")
            lines.append(f"4️⃣ Найди в @{primary} пост с кнопкой")
            lines.append("   «🎁 Получить тест» и нажми её")
            lines.append("")
            lines.append("5️⃣ Ключ прилетит сюда, в бот")
        else:
            lines.append(f"3️⃣ Найди в @{primary} пост с кнопкой")
            lines.append("   «🎁 Получить тест» и нажми её")
            lines.append("")
            lines.append("4️⃣ Ключ прилетит сюда, в бот")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🎁 Тест:  8 часов · 50 ГБ · 1 устр.")
        lines.append(f"💎 VIP:   {_get_support()}")
    else:
        for kk, k in items:
            if k['expires_at'] == 0:
                t = "♾ бессрочно"
            else:
                left = k['expires_at'] - int(time.time())
                t = _human_time(left) if left > 0 else "❌ истёк"
            used = _human_bytes(k['traffic_used'])
            if k['traffic_limit'] > 0:
                limit = _human_bytes(k['traffic_limit'])
                traffic_str = f"{used} / {limit}"
            else:
                traffic_str = f"{used} / ∞"
            icon = "💎" if kk == 'vip' else "🎁"
            name_line = k.get('client_name') or ''
            lines.append(f"{icon} <b>{k['login']}</b>")
            lines.append(f"     ⏰ {t} · 📊 {traffic_str}")
            lines.append("")
        lines.append("<i>Тапни по ключу — детали и конфиг</i>")
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
        # Кнопки: ключ + сброс пароля + удалить в одном ряду
        for kk, k in items[:10]:
            icon = "💎" if kk == 'vip' else "🎁"
            keyboard['inline_keyboard'].append([
                {'text': f"{icon} {k['login']}", 'callback_data': f"cab_key:{k['login']}"},
                {'text': '🔄', 'callback_data': f"cab_key_reset:{k['login']}"},
                {'text': '🗑', 'callback_data': f"cab_key_del:{k['login']}"}
            ])
    keyboard['inline_keyboard'].append([
        {'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}
    ])

    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def show_key_reset_confirm(cfg, chat_id, user_id, key_name, msg_id=None):
    """Подтверждение обновления конфига (HWID + пароль)."""
    token = cfg['BOT_TOKEN']
    key = db.get_test_key(key_name) or db.get_vip_key(key_name)
    if not key or int(key['tg_id']) != int(user_id):
        _send(token, chat_id, "\u274C  Ключ не найден")
        return
    NL = chr(10)
    text = NL.join([
        "\U0001F504 <b>ОБНОВИТЬ КОНФИГ?</b>",
        "\u2501"*20,
        "",
        f"\U0001F511 Логин: <code>{key_name}</code>",
        "",
        "\u2501"*20,
        "\u26A0\uFE0F <b>Важно!</b>",
        "",
        "Будет создан новый конфиг,",
        "привязанный к <b>текущему устройству</b>.",
        "",
        "\U0001F4F2 <b>Пригодится, если:</b>",
        "  \u2022 сменил телефон",
        "  \u2022 переустановил приложение",
        "  \u2022 сменился HWID",
        "",
        "Старый конфиг <b>перестанет работать</b>.",
    ])
    kb = {'inline_keyboard': [
        [{'text': '\U0001F504 Обновить', 'callback_data': f'cab_key_resethwid:{key_name}'}],
        [{'text': '\u2B05\uFE0F Отмена', 'callback_data': f'cab_key:{key_name}'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)



def ask_key_hwid(cfg, chat_id, user_id, key_name, msg_id=None):
    """Просит HWID для обновления конфига. Сохраняет pending."""
    token = cfg['BOT_TOKEN']
    key = db.get_test_key(key_name) or db.get_vip_key(key_name)
    if not key or int(key['tg_id']) != int(user_id):
        _send(token, chat_id, "\u274C  Ключ не найден")
        return
    try:
        db.set_pending(user_id, f'cab_key_hwid:{key_name}')
    except Exception as e:
        cab_log.error(f"set_pending cab_key_hwid: {e}")
    NL = chr(10)
    text = NL.join([
        "\U0001F194 <b>Отправь свой HWID</b>",
        "\u2501"*20,
        "HWID \u2014 это ID устройства.",
        "Новый конфиг будет привязан к нему.",
        "",
        "Как узнать:",
        "DarkTunnel \u2192 \u2699\uFE0F Settings \u2192 внизу <b>Hardware ID</b>",
        "",
        "\U0001F4CB Скопируй и отправь сюда:",
    ])
    kb = {'inline_keyboard': [
        [{'text': '\u2B05\uFE0F Отмена', 'callback_data': f'cab_key:{key_name}'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


def do_key_reset_hwid(cfg, chat_id, user_id, key_name, new_hwid, msg_id=None):
    """Меняет пароль Linux-юзера + обновляет hwid и password в БД."""
    import subprocess as _sp
    import secrets as _sec
    import string as _str
    import os as _os
    token = cfg['BOT_TOKEN']
    key = db.get_test_key(key_name) or db.get_vip_key(key_name)
    if not key or int(key['tg_id']) != int(user_id):
        _send(token, chat_id, "\u274C  Ключ не найден")
        return
    alphabet = _str.ascii_letters + _str.digits
    new_password = ''.join(_sec.choice(alphabet) for _ in range(12))
    try:
        _sp.run(['chpasswd'], input=f"{key_name}:{new_password}",
                text=True, capture_output=True, timeout=10)
    except Exception as e:
        cab_log.error(f"chpasswd error: {e}")
    try:
        with open(f"{PASSWORDS_DIR}/{key_name}", 'w') as f:
            f.write(new_password)
        _os.chmod(f"{PASSWORDS_DIR}/{key_name}", 0o600)
    except Exception as e:
        cab_log.error(f"password file error: {e}")
    try:
        db.update_key_hwid_password(key_name, new_hwid, new_password)
    except Exception as e:
        cab_log.error(f"db update error: {e}")
    NL = chr(10)
    text = NL.join([
        "\u2705  <b>КОНФИГ ОБНОВЛЁН</b>",
        "\u2501"*20,
        "",
        f"\U0001F511 Логин: <code>{key_name}</code>",
        "",
        "\u2501"*20,
        "\U0001F4F2 <b>Что делать:</b>",
        "1. Удали старый конфиг из DarkTunnel",
        "2. Нажми \u00ab\U0001F4F2 Получить конфиг\u00bb ниже",
        "3. Импортируй новый и подключись",
    ])
    kb = {'inline_keyboard': [
        [{'text': '\U0001F4F2 Получить конфиг', 'callback_data': f'cab_dt:{key_name}'}],
        [{'text': '\u2B05\uFE0F К ключу', 'callback_data': f'cab_key:{key_name}'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)
    cab_log.info(f"Key config reset (hwid+pw): {key_name} by tg={user_id}")


def show_key_delete_confirm(cfg, chat_id, user_id, key_name, msg_id=None):
    """Подтверждение удаления ключа с расчётом возврата"""
    token = cfg['BOT_TOKEN']

    # Ищем ключ
    key = db.get_test_key(key_name)
    kind = 'test'
    if not key:
        key = db.get_vip_key(key_name)
        kind = 'vip'
    if not key or int(key['tg_id']) != int(user_id):
        _send(token, chat_id, "❌ Ключ не найден")
        return

    now = int(time.time())
    exp = key['expires_at'] or 0
    created = key['created_at'] or now

    # Считаем остаток
    if exp == 0:
        left_days = None
    elif exp > now:
        left_days = (exp - now) / 86400
    else:
        left_days = 0

    # Считаем возврат для VIP
    refund = 0.0
    if kind == 'vip':
        price = float(key.get('price_paid') or 0)
        total_secs = max(1, exp - created) if exp > 0 else 0
        left_secs = max(0, exp - now) if exp > 0 else 0
        if total_secs > 0 and price > 0:
            refund = price * (left_secs / total_secs) * 0.8
            refund = round(refund, 2)

    NL = chr(10)
    icon = "💎" if kind == 'vip' else "🎁"
    lines = [
        "🗑 <b>УДАЛИТЬ КЛЮЧ?</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"{icon} Логин: <code>{key_name}</code>",
    ]
    if exp > 0 and left_days is not None:
        if left_days >= 1:
            lines.append(f"⏰ Осталось: <b>{left_days:.0f} дней</b>")
        else:
            hours = int(left_days * 24)
            lines.append(f"⏰ Осталось: <b>{hours} ч</b>")
    elif exp == 0:
        lines.append("⏰ Срок: <b>бессрочно</b>")

    if kind == 'vip':
        lines.append(f"💰 Куплено за: <b>{float(key.get('price_paid') or 0):.2f} USDT</b>")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        if refund > 0:
            lines.append(f"💵 Возврат на баланс: <b>{refund:.2f} USDT</b>")
            lines.append(f"<i>(пропорционально остатку срока)</i>")
        else:
            lines.append("💵 Возврат: <b>0.00 USDT</b>")
    else:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚠️ <i>Тестовые ключи бесплатны — возврат не положен</i>")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if kind == "vip" and refund > 0:
        lines.append("")
        lines.append("⚠️ <b>Важно!</b> С возврата удерживается комиссия <b>20%</b>")
        lines.append("   (это покрывает расходы на выпуск и обслуживание ключа)")
    lines.append("Это действие нельзя отменить.")
    text = NL.join(lines)

    btn_text = f"✅ Удалить" + (f" (+{refund:.2f} USDT)" if refund > 0 else "")
    kb = {'inline_keyboard': [
        [{'text': btn_text, 'callback_data': f'cab_key_delok:{key_name}'}],
        [{'text': '⬅️ Отмена', 'callback_data': 'cab_keys'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


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


def _build_dark_url_for_key(cfg, key_name):
    """Возвращает darktunnel:// или None."""
    key = db.get_test_key(key_name) or db.get_vip_key(key_name)
    if not key:
        return None, None
    password = key['password']
    if not password:
        return None, None
    domain = get_domain()
    ws_port = get_ws_port()
    proxy = get_random_proxy()
    try:
        _hwid = key['hwid']
    except (KeyError, IndexError, TypeError):
        _hwid = None
    _loc = cfg.get("SERVER_LOCATION", "VPN")
    if _hwid:
        try:
            from bot_modules import dark_gen
            _proxy_str = proxy or '162.159.228.0'
            _proxyhost = _proxy_str.split(':')[0] if ':' in _proxy_str else _proxy_str
            if key_name.startswith('vip_'):
                _cfg_name = f"\U0001F48E VIP {_loc} {key_name[4:]}"
            elif key_name.startswith('test'):
                _cfg_name = f"\U0001F381 TEST {_loc} {key_name[4:]}"
            else:
                _cfg_name = f"\u2B50  {key_name}"
            dt_url = dark_gen.generate(
                hwid=_hwid, host=domain, port=str(ws_port),
                user=key_name, pw=password,
                proxyhost=_proxyhost, proxyport=str(ws_port),
                name=_cfg_name,
            )
            return dt_url, _cfg_name
        except Exception as e:
            cab_log.error(f"_build_dark_url: {e}")
            return None, None
    return None, None


def send_dark_file(cfg, chat_id, user_id, key_name):
    """Сохраняет darktunnel:// в .dark и отправляет как документ."""
    import os as _os, tempfile
    token = cfg['BOT_TOKEN']
    key = db.get_test_key(key_name) or db.get_vip_key(key_name)
    if not key or int(key['tg_id']) != int(user_id):
        _send(token, chat_id, "\u274C  Ключ не найден")
        return
    if key['expires_at'] > 0 and key['expires_at'] < int(time.time()):
        _send(token, chat_id, "\u274C  Ключ истёк")
        return
    dt_url, cfg_name = _build_dark_url_for_key(cfg, key_name)
    if not dt_url:
        _send(token, chat_id, "\u274C  Не удалось создать конфиг (нужен HWID)")
        return
    # Сохраняем как .dark
    safe_name = key_name.replace('/', '_')
    fname = f"{safe_name}.dark"
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix='.dark')
        with _os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(dt_url)
        # Отправляем через curl (multipart)
        import subprocess
        cmd = [
            'curl', '-s', '-X', 'POST',
            f'https://api.telegram.org/bot{token}/sendDocument',
            '-F', f'chat_id={chat_id}',
            '-F', f'document=@{tmp_path};filename={fname}',
            '-F', f'caption=\U0001F4E5 <b>{fname}</b>\n\nСкачай и открой через DarkTunnel \u2192 \u22EE \u2192 Import \u2192 File',
            '-F', 'parse_mode=HTML',
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        cab_log.info(f"dark file sent: {fname}")
    except Exception as e:
        cab_log.error(f"send_dark_file: {e}")
        _send(token, chat_id, f"\u274C  Ошибка отправки: {e}")
    finally:
        if tmp_path and _os.path.exists(tmp_path):
            try: _os.remove(tmp_path)
            except: pass


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
    # HWID ключа (если есть)
    try:
        _hwid = key['hwid']
    except (KeyError, IndexError, TypeError):
        _hwid = None
    _loc = cfg.get("SERVER_LOCATION", "VPN")
    if _hwid:
        # Зашифрованный конфиг с привязкой к устройству
        try:
            from bot_modules import dark_gen
            _proxy_str = proxy or '162.159.228.0'
            _proxyhost = _proxy_str.split(':')[0] if ':' in _proxy_str else _proxy_str
            if key_name.startswith('vip_'):
                _cfg_name = f"💎 VIP {_loc} {key_name[4:]}"
            elif key_name.startswith('test'):
                _cfg_name = f"🎁 TEST {_loc} {key_name[4:]}"
            else:
                _cfg_name = f"⭐ {key_name}"
            dt_url = dark_gen.generate(
                hwid=_hwid,
                host=domain,
                port=str(ws_port),
                user=key_name,
                pw=password,
                proxyhost=_proxyhost,
                proxyport=str(ws_port),
                name=_cfg_name,
            )
            cab_log.info(f"dark_gen encrypted config for {key_name} (hwid={_hwid[:8]}...)")
        except Exception as e:
            cab_log.error(f"dark_gen generate error: {e}")
            dt_url = None
    else:
        # Открытый конфиг (старый способ)
        dt_url = make_darktunnel_url(key_name, password, domain, ws_port, proxy, _loc)
    if not dt_url:
        _send(token, chat_id, "❌   Не удалось создать конфиг")
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
        [{'text': '\U0001F4E5 Скачать .dark файл ещё раз', 'callback_data': f'cab_darkfile:{key_name}'}],
        [{'text': '\U0001F5D1 Удалить сообщение', 'callback_data': f'cab_delmsg:{key_name}'}]
    ]}
    _send(token, chat_id, text, keyboard)
    # Сразу шлём .dark файл (только если конфиг зашифрован)
    try:
        if dt_url and 'encryptedLockedConfig' in dt_url:
            send_dark_file(cfg, chat_id, user_id, key_name)
    except Exception as _e:
        cab_log.error(f"auto send_dark_file: {_e}")


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
        f"💬 Не работает? {_get_support()}"
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


def _get_support():
    """Контакты поддержки из /etc/UDPCustom/support.txt"""
    try:
        with open('/etc/UDPCustom/support.txt') as f:
            t = f.read().strip()
            return t if t else '@ArsenGuro'
    except: return '@ArsenGuro'


def _get_rate():
    """Читает курс из /etc/UDPCustom/rate.txt (USDT → манат)."""
    try:
        with open('/etc/UDPCustom/rate.txt') as f:
            return float(f.read().strip())
    except:
        return 20.0


def _parse_vip_tariffs(cfg):
    """Парсит VIP_TARIFFS из конфига. Возвращает список dict."""
    raw = cfg.get('VIP_TARIFFS', '15|2.5|100|1,30|5|300|1,90|13|900|1')
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

    # Генерим текст тарифов
    tariffs_lines = []
    kb_rows = []
    for i, t in enumerate(tariffs, 1):
        can_buy = balance >= t['price']
        mark = "✅ " if can_buy else "❌ "
        tariffs_lines.append(f"{mark} <b>{t['days']} дней</b> — {t['price']:.0f} USDT")
        tariffs_lines.append(f"   📊 {t['gb']} ГБ · 📱 {t['devices']} устр.")
        tariffs_lines.append("")
        kb_rows.append([{
            'text': f"💎 {t['days']}д — {t['price']:.0f} USDT",
            'callback_data': f'cab_vip_buy:{i}'
        }])
    tariffs_text = chr(10).join(tariffs_lines).rstrip()

    # Читаем шаблон из файла
    tpl = None
    try:
        with open('/etc/UDPCustom/vip_buy.txt') as f:
            tpl = f.read().strip()
    except: pass

    if tpl:
        text = (tpl
                .replace('{balance}', f"{balance:.2f}")
                .replace('{tariffs}', tariffs_text))
    else:
        NL = chr(10)
        text = NL.join([
            "💎 <b>КУПИТЬ VIP-КЛЮЧ</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"💰 Твой баланс: <b>{balance:.2f} USDT</b>",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "📋 <b>Тарифы:</b>",
            "",
            tariffs_text
        ])

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
        "💎 <b>Награда за друга, купившего VIP:</b>",
        "",
        "   💵 <b>+1.00 USDT</b> на баланс",
        "   ⏰ <b>+5 дней</b> к твоему VIP-ключу",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "🔗 <b>Твоя ссылка:</b>",
        f"<code>{ref_link}</code>",
        "",
        f"📊 Приглашено: <b>{inv}</b>",
        f"💰 Заработано: <b>{earned:.2f} USDT</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "<i>Поделись ссылкой с друзьями 👇</i>"
    ])
    keyboard = {'inline_keyboard': [
        [{'text': '📤 Поделиться', 'callback_data': 'cab_share_ref'}],
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


def _apply_placeholders(text, cfg):
    """Подставляет все поддерживаемые плейсхолдеры в текст."""
    if not text:
        return text
    # Каналы
    try:
        with open('/etc/UDPCustom/channels.txt') as f:
            _chs = [l.strip().lstrip('@') for l in f if l.strip() and not l.startswith('#')]
    except:
        _chs = []
    _primary = _chs[0] if _chs else ''
    _sponsors = [c for c in _chs if c != _primary]
    _sponsors_list = ', '.join('@' + s for s in _sponsors) if _sponsors else '—'
    # bot.conf
    _hours = cfg.get('TEST_HOURS', '')
    _gb = cfg.get('TEST_TRAFFIC_GB', '')
    _devices = cfg.get('TEST_DEVICES', '')
    _location = cfg.get('SERVER_LOCATION', '')
    _bot_name = cfg.get('CONFIG_NAME', 'VPN')
    return (text
        .replace('{support}', _get_support())
        .replace('{primary}', _primary)
        .replace('{sponsors_list}', _sponsors_list)
        .replace('{bot_name}', str(_bot_name))
        .replace('{hours}', str(_hours))
        .replace('{gb}', str(_gb))
        .replace('{devices}', str(_devices))
        .replace('{location}', str(_location)))


def _get_help_text(cfg=None):
    """Главный экран /help"""
    try:
        with open('/etc/UDPCustom/help.txt') as f:
            t = f.read().strip()
            return _apply_placeholders(t, cfg or {}) if t else None
    except: return None


def _get_help_instruction(cfg=None):
    """Инструкция подключения"""
    try:
        with open('/etc/UDPCustom/help_instruction.txt') as f:
            t = f.read().strip()
            return _apply_placeholders(t, cfg or {}) if t else None
    except: return None


def _get_help_faq(cfg=None):
    """FAQ"""
    try:
        with open('/etc/UDPCustom/help_faq.txt') as f:
            t = f.read().strip()
            if not t: return None
            return _apply_placeholders(t, cfg or {})
    except: return None


def show_help_instruction(cfg, chat_id, user_id, msg_id=None):
    """Инструкция по подключению"""
    token = cfg['BOT_TOKEN']
    text = _get_help_instruction(cfg)
    if not text:
        text = "📖 <b>Инструкция</b>\n\nОтредактируй /etc/UDPCustom/help_instruction.txt"
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
    text = _get_help_faq(cfg)
    if not text:
        text = "❓ <b>FAQ</b>\n\nОтредактируй /etc/UDPCustom/help_faq.txt"
    keyboard = {'inline_keyboard': [
        [{'text': '⬅️ Назад', 'callback_data': 'cab_help_back'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, keyboard)
    else:
        _send(token, chat_id, text, keyboard)


def _get_help_generic(fname, cfg=None):
    try:
        with open(fname) as f:
            t = f.read().strip()
            if not t: return None
            return _apply_placeholders(t, cfg or {})
    except: return None


def _help_back_kb():
    return {'inline_keyboard': [
        [{'text': '\u2B05\uFE0F Назад', 'callback_data': 'cab_help'}]
    ]}


def show_help_darktunnel(cfg, chat_id, user_id, msg_id=None):
    token = cfg['BOT_TOKEN']
    text = _get_help_generic('/etc/UDPCustom/help_darktunnel.txt', cfg) or \
        "\u2699\uFE0F <b>DarkTunnel</b>\n\nОтредактируй /etc/UDPCustom/help_darktunnel.txt"
    kb = _help_back_kb()
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


def show_help_httpcustom(cfg, chat_id, user_id, msg_id=None):
    token = cfg['BOT_TOKEN']
    text = _get_help_generic('/etc/UDPCustom/help_httpcustom.txt', cfg) or \
        "\u2699\uFE0F <b>HttpCustom</b>\n\nОтредактируй /etc/UDPCustom/help_httpcustom.txt"
    kb = _help_back_kb()
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


def show_help_whitedns(cfg, chat_id, user_id, msg_id=None):
    token = cfg['BOT_TOKEN']
    text = _get_help_generic('/etc/UDPCustom/help_whitedns.txt', cfg) or \
        "\u2699\uFE0F <b>WhiteDns</b>\n\nОтредактируй /etc/UDPCustom/help_whitedns.txt"
    kb = _help_back_kb()
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


def show_help_video(cfg, chat_id, user_id, msg_id=None):
    token = cfg['BOT_TOKEN']
    text = _get_help_generic('/etc/UDPCustom/help_video.txt', cfg) or \
        "\U0001F3AC <b>Видео</b>\n\nОтредактируй /etc/UDPCustom/help_video.txt"
    kb = _help_back_kb()
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


def show_ad(cfg, chat_id, user_id, msg_id=None):
    """Раздел Реклама — условия спонсорства."""
    token = cfg['BOT_TOKEN']
    try:
        with open('/etc/UDPCustom/ad.txt') as f:
            text = f.read().strip()
        if not text:
            text = "\U0001F4E3 <b>Реклама</b>\n\nОтредактируй /etc/UDPCustom/ad.txt"
        text = _apply_placeholders(text, cfg)
    except Exception as e:
        cab_log.error(f"show_ad: {e}")
        text = "\U0001F4E3 <b>Реклама</b>\n\nОтредактируй /etc/UDPCustom/ad.txt"
    kb = {'inline_keyboard': [
        [{'text': '\U0001F4AC Поддержка', 'url': f'https://t.me/{_get_support().lstrip(chr(64))}'}],
        [{'text': '\U0001F3E0 Меню', 'callback_data': 'cab_exit'}],
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send_new(token, chat_id, text, kb)


def show_help_back(cfg, chat_id, user_id, msg_id=None):
    """Главное меню Помощи."""
    token = cfg['BOT_TOKEN']
    ch_file = "/etc/UDPCustom/channels.txt"
    channels = []
    if os.path.exists(ch_file):
        try:
            channels = [l.strip() for l in open(ch_file) if l.strip() and not l.startswith('#')]
        except: pass
    primary = channels[0].lstrip('@') if channels else 'ArsenVipKeys'
    support = _get_support().lstrip('@') if hasattr(_get_support, '__call__') else 'ArsenSupportBot'
    text = "\U0001F4D6 <b>ПОМОЩЬ</b>"
    kb = {'inline_keyboard': [
        [{'text': '\u2699\uFE0F DarkTunnel', 'callback_data': 'cab_help_darktunnel'},
         {'text': '\u2699\uFE0F HttpCustom', 'callback_data': 'cab_help_httpcustom'},
         {'text': '\u2699\uFE0F WhiteDns', 'callback_data': 'cab_help_whitedns'}],
        [{'text': '\u2753 Вопросы', 'callback_data': 'cab_help_faq'},
         {'text': '\U0001F3AC Видео', 'callback_data': 'cab_help_video'},
         {'text': '\U0001F4AC Поддержка', 'url': f'https://t.me/{support}'}],
        [{'text': '\U0001F464 Кабинет', 'callback_data': 'cab_main'},
         {'text': f'\U0001F4E2 Канал', 'url': f'https://t.me/{primary}'},
         {'text': '\U0001F3E0 Меню', 'callback_data': 'cab_exit'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send_new(token, chat_id, text, kb)



def handle_cabinet_callback(cfg, cb_data, cb, user_id, first_name):
    """Обработчик всех callback'ов кабинета.
    Возвращает True если обработано, False если не наш callback."""
    token = cfg['BOT_TOKEN']
    chat_id = cb['message']['chat']['id']
    msg_id = cb['message']['message_id']

    # Тосты для разных callback'ов
    _toast = None
    if cb_data.startswith('cab_key_resethwid:'):
        _toast = '🔄 Пароль обновлён'
    elif cb_data.startswith('cab_key_reset:'):
        _toast = '⚠️ Подтверди сброс'
    elif cb_data.startswith('cab_key_del:'):
        _toast = '⚠️ Подтверди удаление'
    elif cb_data.startswith('cab_dt:'):
        _toast = '📲 Генерирую конфиг...'
    # Ответ на callback (убираем «крутилку»)
    if _toast:
        _tg(token, 'answerCallbackQuery', {'callback_query_id': cb['id'], 'text': _toast})
    else:
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
    if cb_data == 'cab_ad':
        show_ad(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_help':
        show_help_back(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_help_darktunnel':
        show_help_darktunnel(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_help_httpcustom':
        show_help_httpcustom(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_help_whitedns':
        show_help_whitedns(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_help_video':
        show_help_video(cfg, chat_id, user_id, msg_id)
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
        try:
            db.clear_pending(user_id)
        except: pass
        show_buy_vip(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_udp_soon':
        _udp_text = (
            "🛡 <b>VIP UDP — скоро будет!</b>" + chr(10) + chr(10) +
            "🚧 Раздел в разработке." + chr(10) +
            "Следи за обновлениями в канале."
        )
        _udp_kb = {'inline_keyboard': [
            [{'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}]
        ]}
        if msg_id:
            _edit(token, chat_id, msg_id, _udp_text, _udp_kb)
        else:
            _send(token, chat_id, _udp_text, _udp_kb)
        return True
    if cb_data == 'cab_whitedns':
        show_whitedns_menu(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_wd_de':
        show_whitedns_profiles(cfg, chat_id, user_id, 0, msg_id)
        return True
    if cb_data == 'cab_wd_fi':
        show_whitedns_profiles(cfg, chat_id, user_id, 1, msg_id)
        return True
    if cb_data == 'cab_wd_se':
        show_whitedns_profiles(cfg, chat_id, user_id, 2, msg_id)
        return True
    if cb_data.startswith('cab_wd_prof:'):
        try:
            _parts = cb_data.split(':')
            _prof = int(_parts[1])
            _srv = int(_parts[2])
        except:
            _prof, _srv = 0, 0
        show_whitedns_confirm(cfg, chat_id, user_id, _srv, _prof, msg_id)
        return True
    if cb_data.startswith('cab_wd_send:'):
        try:
            _parts = cb_data.split(':')
            _srv = int(_parts[1])
            _prof = int(_parts[2])
        except:
            _srv, _prof = 0, 0
        send_whitedns_files(cfg, chat_id, user_id, _srv, _prof, first_name or '')
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
            f"💰 Текущий баланс: <b>{balance:.2f} USDT</b>",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "Выбери способ пополнения:"
        ])
        kb = {'inline_keyboard': [
            [{'text': '⭐ Telegram Stars', 'callback_data': 'cab_topup_stars'}],
            [{'text': '💳 Ручное (TMCELL)', 'callback_data': 'cab_topup_manual'}],
            [{'text': '🤖 Крипто-бот', 'callback_data': 'cab_topup_crypto'}],
            [{'text': '⬅️ К балансу', 'callback_data': 'cab_balance'}]
        ]}
        _edit(token, chat_id, msg_id, text, kb)
        return True
    if cb_data == 'cab_topup_stars':
        NL = chr(10)
        _rate = 0.015  # будет читаться из конфига
        _smin = 1
        _smax = 100
        try:
            with open('/etc/UDPCustom/bot.conf') as _f:
                for _l in _f:
                    if _l.startswith('STAR_RATE='):
                        _rate = float(_l.split('=',1)[1].strip().strip('"'))
                    elif _l.startswith('STAR_MIN='):
                        _smin = float(_l.split('=',1)[1].strip().strip('"'))
                    elif _l.startswith('STAR_MAX='):
                        _smax = float(_l.split('=',1)[1].strip().strip('"'))
        except: pass
        text = NL.join([
            "⭐ <b>ПОПОЛНЕНИЕ ЧЕРЕЗ STARS</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"💡 Курс: <b>1 Star ≈ {_rate} USDT</b>",
            "",
            "Введи сумму в USDT для пополнения баланса.",
            "",
            f"📊 Мин: <b>{_smin:.0f}</b> · Макс: <b>{_smax:.0f}</b> USDT",
            "",
            "Например: <code>5</code>"
        ])
        kb = {'inline_keyboard': [
            [{'text': '⬅️ Отмена', 'callback_data': 'cab_topup'}]
        ]}
        _edit(token, chat_id, msg_id, text, kb)
        # Запоминаем что ждём сумму для Stars
        db.set_pending(user_id, 'stars_amount')
        return True
    if cb_data == 'cab_topup_manual':
        NL = chr(10)
        rate = _get_rate()
        text = NL.join([
            "💳 <b>ПОПОЛНЕНИЕ ЧЕРЕЗ TMCELL</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "📋 <b>ИНСТРУКЦИЯ:</b>",
            "",
            f"1️⃣ Напиши админу {_get_support()}",
            "   Уточни <b>АКТУАЛЬНЫЙ</b> номер TMCELL",
            "   (номер может меняться)",
            "",
            "2️⃣ Переведи нужную сумму на этот номер",
            "",
            "3️⃣ Вернись сюда и нажми кнопку",
            "   «📸 Отправить чек»",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💵 Курс: <b>1 USDT ≈ {rate:.0f} манат</b>",
            "",
            "⚠️ <b>Важно:</b> уточни номер у админа",
            "ПЕРЕД переводом!"
        ])
        kb = {'inline_keyboard': [
            [{'text': f'💬 Написать {_get_support()}', 'url': f'https://t.me/{_get_support().lstrip(chr(64))}'}],
            [{'text': '📸 Отправить чек', 'callback_data': 'cab_topup_photo'}],
            [{'text': '⬅️ Назад', 'callback_data': 'cab_topup'}]
        ]}
        _edit(token, chat_id, msg_id, text, kb)
        return True
    if cb_data == 'cab_topup_crypto':
        NL = chr(10)
        text = NL.join([
            "🤖 <b>КРИПТО-БОТ</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "🚧 <b>Скоро будет доступно!</b>",
            "",
            "Автоматическое пополнение через USDT",
            "(TRC-20 / ERC-20) прямо в бота.",
            "",
            f"Пока — пиши {_get_support()}"
        ])
        kb = {'inline_keyboard': [
            [{'text': f'💬 {_get_support()}', 'url': f'https://t.me/{_get_support().lstrip(chr(64))}'}],
            [{'text': '⬅️ Назад', 'callback_data': 'cab_topup'}]
        ]}
        _edit(token, chat_id, msg_id, text, kb)
        return True
    if cb_data == 'cab_topup_photo':
        NL = chr(10)
        text = NL.join([
            "📸 <b>ОТПРАВКА ЧЕКА (шаг 1/2)</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "Отправь скриншот из приложения",
            "с <b>успешным переводом</b>.",
            "",
            "⚠️ На скрине должно быть видно:",
            "• Сумма перевода",
            "• Номер получателя",
            "• Дата/время",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "Просто отправь <b>фото</b> следующим",
            "сообщением 👇"
        ])
        kb = {'inline_keyboard': [
            [{'text': '⬅️ Отмена', 'callback_data': 'cab_topup_manual'}]
        ]}
        _edit(token, chat_id, msg_id, text, kb)
        try:
            db.set_pending(user_id, 'topup_check')
        except Exception as e:
            cab_log.error(f"set_pending topup_check: {e}")
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
    if cb_data == 'cab_share_ref':
        # Отправляем сообщение с кнопкой — юзер должен forward-нуть
        user = db.get_user(user_id)
        ref_code = user['ref_code'] if user else ''
        me = _tg(token, 'getMe')
        bot_u = me['result'].get('username', 'ArsenVipKeysBot') if me and me.get('ok') else 'ArsenVipKeysBot'
        ref_link = f"https://t.me/{bot_u}?start=ref_{ref_code}"
        NL = chr(10)
        share_msg = NL.join([
            "📤 <b>ПОДЕЛИСЬ С ДРУЗЬЯМИ</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "👇 Перешли это сообщение друзьям",
            "или в свой канал/группу",
            "",
            "🎁 За каждого друга — бонус 💰"
        ])
        _send(token, chat_id, share_msg)
        # Само рекламное сообщение — из ref_post.txt
        try:
            with open('/etc/UDPCustom/ref_post.txt') as _rf:
                ad_text = _rf.read().strip()
            ad_text = _apply_placeholders(ad_text, cfg)
        except Exception:
            ad_text = '⚡  <b>' + cfg.get('CONFIG_NAME', 'VPN') + ' — VPN который работает!</b>'
        ad_kb = {'inline_keyboard': [
            [{'text': '🎁 Получить ключ', 'url': ref_link}]
        ]}
        _tg(token, 'sendMessage', {
            'chat_id': chat_id,
            'text': ad_text,
            'parse_mode': 'HTML',
            'reply_markup': ad_kb,
            'disable_web_page_preview': True
        })
        return True
    if cb_data == 'cab_ref_list':
        show_ref_list(cfg, chat_id, user_id, msg_id)
        return True
    if cb_data == 'cab_exit':
        # Возврат в главное меню (/start)
        _tg(token, 'answerCallbackQuery', {'callback_query_id': cb['id']})
        try:
            import sys as _sys
            _main = _sys.modules.get('__main__')
            if _main and hasattr(_main, 'handle_start'):
                _main.handle_start(cfg, chat_id, user_id, first_name or '')
            else:
                _send_new(token, chat_id, 'Напиши /start для возврата', {'inline_keyboard': []})
        except Exception as _e:
            cab_log.error(f'cab_exit: {_e}')
            _send_new(token, chat_id, 'Напиши /start для возврата', {'inline_keyboard': []})
        return True

    if cb_data.startswith('cab_key_reset:'):
        key_name = cb_data.split(':', 1)[1]
        show_key_reset_confirm(cfg, chat_id, user_id, key_name, msg_id)
        return True
    if cb_data.startswith('cab_key_resethwid:'):
        key_name = cb_data.split(':', 1)[1]
        ask_key_hwid(cfg, chat_id, user_id, key_name, msg_id)
        return True
    if cb_data.startswith('cab_key_del:'):
        key_name = cb_data.split(':', 1)[1]
        show_key_delete_confirm(cfg, chat_id, user_id, key_name, msg_id)
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
    if cb_data.startswith('cab_darkfile:'):
        key_name = cb_data.split(':', 1)[1]
        send_dark_file(cfg, chat_id, user_id, key_name)
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

# ──────────────────────────────────────────────────────────────
# WHITEDNS — меню (заготовка, логика будет добавлена)
# ──────────────────────────────────────────────────────────────
def show_whitedns_menu(cfg, chat_id, user_id, msg_id=None):
    """Меню WhiteDNS. Проверка VIP + выбор сервера."""
    token = cfg['BOT_TOKEN']
    vip_keys = db.get_vip_keys(user_id, active_only=True)
    has_vip = len(vip_keys) > 0
    NL = chr(10)
    if not has_vip:
        text = NL.join([
            "📡 <b>WHITEDNS — БОНУС К VIP</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "🔒 Раздел откроется <b>автоматически</b>",
            "после покупки <b>Vip ключа 💎 DarkTunnel</b>.",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "🎁 <b>ЧТО ТЫ ПОЛУЧАЕШЬ:</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "💎 <b>Купил 1 Vip ключ DarkTunnel → получаешь 2 входа:</b>",
            "",
            "1️⃣ <b>Vip ключ 💎 DarkTunnel</b> — основной VPN",
            "   (работает как обычно)",
            "",
            "2️⃣ <b>WhiteDNS</b> — второй VPN",
            "   🎁 <b>в подарок</b>, для мобильного",
            "   интернета и обхода блокировок",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "📦 <b>ЧТО ВНУТРИ WhiteDNS:</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "🌐 <b>3 сервера на выбор:</b>",
            "   🇩🇪 Германия  ·  🇫🇮 Финляндия  ·  🇸🇪 Швеция",
            "",
            "⚙️ <b>3 профиля под твой интернет:</b>",
            "   📱 3G — мобильная сеть (LTE/4G/5G)",
            "   📶 WiFi — домашний роутер",
            "   🖥 ADSL — проводной интернет",
            "",
            "📲 <b>Готовые конфиги — загрузил и работает</b>",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "💡 <b>ЗАЧЕМ ЭТО НУЖНО:</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "✅ <b>Два VPN по цене одного</b>",
            "   Платишь за Vip ключ 💎 DarkTunnel один раз —",
            "   пользуешься двумя сервисами.",
            "",
            "✅ <b>Страховка</b>",
            "   Если 💎 DarkTunnel не работает —",
            "   переключаешься на WhiteDNS.",
            "",
            "✅ <b>Больше устройств</b>",
            "   Разные протоколы — разные сети.",
            "   Мобильный + домашний Wi-Fi без проблем.",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "💎 <b>Оформи Vip ключ DarkTunnel</b> — раздел откроется сам.",
            "Купить: кнопка ниже 👇",
        ])
        kb = {'inline_keyboard': [
            [{'text': '💎 Vip ключ DarkTunnel', 'callback_data': 'cab_buy_vip'}],
            [{'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}]
        ]}
    else:
        _srv = _wd_c_read_servers()
        _srv_lines = []
        for _i in range(3):
            _ok = bool(_srv[_i]) and bool(_wd_c_read_file(WD_RES_PATHS[_i]))
            _srv_lines.append(WD_SRV_NAMES[_i] + (' — ✅ активен' if _ok else ' — ⏳ настройка'))
        text = NL.join([
            "📡 <b>WHITEDNS ДОСТУП</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "✅  Твой VIP активен",
            "",
            "📌 <b>КАК ПОЛУЧИТЬ:</b>",
            "1️⃣ Выбери сервер",
            "2️⃣ Выбери профиль",
            "3️⃣ Подтверди и получи файлы",
            "",
            "━━ 🌐 <b>СЕРВЕРЫ</b> ━━",
        ] + _srv_lines + [
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "1️⃣ <b>ВЫБЕРИ СЕРВЕР:</b>",
        ])
        kb = {'inline_keyboard': [
            [{'text': '🇩🇪 Германия', 'callback_data': 'cab_wd_de'},
             {'text': '🇫🇮 Финляндия', 'callback_data': 'cab_wd_fi'}],
            [{'text': '🇸🇪 Швеция', 'callback_data': 'cab_wd_se'}],
            [{'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}]
        ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)


# ──────────────────────────────────────────────────────────────
# WHITEDNS — клиентские функции
# ──────────────────────────────────────────────────────────────
WD_SRV_NAMES = ['🇩🇪 Германия', '🇫🇮 Финляндия', '🇸🇪 Швеция']
WD_PROF_NAMES = ['📱 3G', '📶 WiFi', '🖥 ADSL']
WD_RES_PATHS = [
    '/etc/UDPCustom/whitedns_resolvers_de.txt',
    '/etc/UDPCustom/whitedns_resolvers_fi.txt',
    '/etc/UDPCustom/whitedns_resolvers_se.txt',
]
WD_SET_PATHS = [
    '/etc/UDPCustom/whitedns_settings_3g.txt',
    '/etc/UDPCustom/whitedns_settings_wifi.txt',
    '/etc/UDPCustom/whitedns_settings_adsl.txt',
]
WD_SRV_FILE = '/etc/UDPCustom/whitedns_servers.txt'
WD_ISSUED_LOG = '/etc/UDPCustom/whitedns_issued.log'

def _wd_c_read_servers():
    result = ['', '', '']
    try:
        with open(WD_SRV_FILE) as f:
            lines = [l.rstrip(chr(10)) for l in f]
        for i in range(min(3, len(lines))):
            result[i] = lines[i]
    except:
        pass
    return result

def _wd_c_read_file(path):
    try:
        with open(path) as f:
            return f.read().rstrip(chr(10))
    except:
        return ''

def _wd_c_log(user_id, username, server_idx, prof_idx):
    from datetime import datetime as _dt
    try:
        with open(WD_ISSUED_LOG, 'a') as f:
            f.write(str(user_id) + '|' + str(username) + '|' + WD_SRV_NAMES[server_idx] + '|' + WD_PROF_NAMES[prof_idx] + '|' + _dt.now().strftime('%F %H:%M') + chr(10))
    except: pass

def show_whitedns_profiles(cfg, chat_id, user_id, server_idx, msg_id=None):
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    if server_idx < 0 or server_idx > 2:
        server_idx = 0
    text = NL.join([
        WD_SRV_NAMES[server_idx] + ' — <b>WHITEDNS</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '2️⃣ <b>ВЫБЕРИ ПРОФИЛЬ:</b>',
        '',
        '📱 3G   — мобильная сеть',
        '📶 WiFi — домашний Wi-Fi',
        '🖥 ADSL — проводной интернет',
    ])
    kb = {'inline_keyboard': [
        [{'text': '📱 3G', 'callback_data': 'cab_wd_prof:0:' + str(server_idx)},
         {'text': '📶 WiFi', 'callback_data': 'cab_wd_prof:1:' + str(server_idx)},
         {'text': '🖥 ADSL', 'callback_data': 'cab_wd_prof:2:' + str(server_idx)}],
        [{'text': '⬅️ Назад', 'callback_data': 'cab_whitedns'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)

def show_whitedns_confirm(cfg, chat_id, user_id, server_idx, prof_idx, msg_id=None):
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    if server_idx < 0 or server_idx > 2:
        server_idx = 0
    if prof_idx < 0 or prof_idx > 2:
        prof_idx = 0
    res = _wd_c_read_file(WD_RES_PATHS[server_idx])
    res_count = len([l for l in res.split(chr(10)) if l.strip()]) if res else 0
    text = NL.join([
        '⚠️ <b>ПРОВЕРЬ ВЫБОР</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '📌 <b>Ты выбрал:</b>',
        '',
        '🌐 Сервер: ' + WD_SRV_NAMES[server_idx],
        '⚙️ Профиль: ' + WD_PROF_NAMES[prof_idx],
        '🔢 Резолверы: ' + WD_SRV_NAMES[server_idx] + ' (' + str(res_count) + ' IP)',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '⚠️ Импортировать нужно ИМЕННО в эти разделы:',
        '',
        '🔗 conection → «Connection»',
        '⚙️ setings → «Setting»',
        '🔢 resolvers → «Resolver»',
        '',
        '❌ Перепутаешь — не заработает!',
    ])
    kb = {'inline_keyboard': [
        [{'text': '✅ ДА, ВСЁ ВЕРНО', 'callback_data': 'cab_wd_send:' + str(server_idx) + ':' + str(prof_idx)}],
        [{'text': '❌ Отмена', 'callback_data': 'cab_whitedns'}]
    ]}
    if msg_id:
        _edit(token, chat_id, msg_id, text, kb)
    else:
        _send(token, chat_id, text, kb)

def _wd_send_txt_file(token, chat_id, filename, content, caption=''):
    """Отправляет текстовый файл через Telegram sendDocument."""
    import tempfile
    import subprocess
    import os as _os
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix='.txt')
        with _os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        cmd = [
            'curl', '-s', '-X', 'POST',
            'https://api.telegram.org/bot' + token + '/sendDocument',
            '-F', 'chat_id=' + str(chat_id),
            '-F', 'document=@' + tmp_path + ';filename=' + filename,
        ]
        if caption:
            cmd += ['-F', 'caption=' + caption, '-F', 'parse_mode=HTML']
        subprocess.run(cmd, capture_output=True, timeout=30)
    except Exception as e:
        pass
    finally:
        if tmp_path and _os.path.exists(tmp_path):
            try:
                _os.remove(tmp_path)
            except: pass

def send_whitedns_files(cfg, chat_id, user_id, server_idx, prof_idx, username=''):
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    if server_idx < 0 or server_idx > 2:
        server_idx = 0
    if prof_idx < 0 or prof_idx > 2:
        prof_idx = 0
    servers = _wd_c_read_servers()
    conn_data = servers[server_idx] if servers[server_idx] else ''
    settings_data = _wd_c_read_file(WD_SET_PATHS[prof_idx])
    resolvers_data = _wd_c_read_file(WD_RES_PATHS[server_idx])
    srv_name = WD_SRV_NAMES[server_idx]
    prof_name = WD_PROF_NAMES[prof_idx]
    if not conn_data:
        _send(token, chat_id, '❌ <b>Сервер не настроен.</b>' + NL + 'Попробуй другой сервер.', {'inline_keyboard': [[{'text': '⬅️ Назад', 'callback_data': 'cab_whitedns'}]]})
        return
    if not settings_data:
        _send(token, chat_id, '❌ <b>Профиль не настроен.</b>' + NL + 'Выбери другой профиль.', {'inline_keyboard': [[{'text': '⬅️ Назад', 'callback_data': 'cab_whitedns'}]]})
        return
    if not resolvers_data:
        _send(token, chat_id, '❌ <b>Резолверы не настроены.</b>' + NL + 'Попробуй другой сервер.', {'inline_keyboard': [[{'text': '⬅️ Назад', 'callback_data': 'cab_whitedns'}]]})
        return
    intro = NL.join([
        '📡 <b>WHITEDNS — ГОТОВО!</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        'Сейчас придут <b>3 файла в .txt</b>.',
        '📂 Открой их через X-Plore',
        '   или любой файловый менеджер.',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '⚠️ <b>КАЖДЫЙ В СВОЙ РАЗДЕЛ:</b>',
        '',
        '🔗 conection.txt → «Connection»',
        '⚙️ setings.txt → «Setting»',
        '🔢 resolvers.txt → «Resolver»',
        '',
        '❌  Перепутаешь — не заработает!',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        '📂 X-Plore (Google Play):',
        'https://play.google.com/store/apps/details?id=com.lonelycatgames.Xplore',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        '📱 Сервер: ' + srv_name,
        '⚙️ Профиль: ' + prof_name,
    ])
    _send(token, chat_id, intro)
    flag = srv_name.split(' ')[0]
    _wd_send_txt_file(token, chat_id, flag + ' conection.txt', conn_data,
        '🔗 <b>conection.txt</b> — ' + srv_name + chr(10) + '➡️ Импортируй в раздел «Connection»')
    _wd_send_txt_file(token, chat_id, 'setings.txt', settings_data,
        '⚙️ <b>setings.txt</b> — ' + prof_name + chr(10) + '➡️ Импортируй в раздел «Setting»')
    _wd_send_txt_file(token, chat_id, flag + ' resolvers.txt', resolvers_data,
        '🔢 <b>resolvers.txt</b> — ' + srv_name + chr(10) + '➡️ Импортируй в раздел «Resolver»')
    _wd_c_log(user_id, username or '', server_idx, prof_idx)
    try:
        admin_id = cfg.get('ADMIN_ID', '')
        if admin_id:
            from datetime import datetime as _dt
            # @username клиента через getChat
            try:
                _chat = _tg(token, 'getChat', {'chat_id': user_id})
                _tg_uname = (_chat or {}).get('result', {}).get('username', '') or ''
                _tg_uname = ('@' + _tg_uname) if _tg_uname else '—'
            except Exception:
                _tg_uname = '—'
            # Логин ключа клиента (первый активный VIP)
            try:
                _vk = db.get_vip_keys(user_id, active_only=True)
                _key_login = _vk[0]['login'] if _vk else '—'
            except Exception:
                _key_login = '—'
            adm_msg = NL.join([
                '📡 <b>WHITEDNS — НОВАЯ ВЫДАЧА</b>',
                '━━━━━━━━━━━━━━━━━━━━',
                '👤 Юзер: ' + (username or '—'),
                '📧 TG: ' + _tg_uname,
                '🆔 ID: <code>' + str(user_id) + '</code>',
                '🔑 Ключ: <code>' + _key_login + '</code>',
                '🌐 Сервер: ' + srv_name,
                '⚙️ Профиль: ' + prof_name,
                '⏰ ' + _dt.now().strftime('%F %H:%M'),
            ])
            # Лог через LOG-бота (support), не в основной чат
            _log_tok = cfg.get('LOG_BOT_TOKEN', '')
            _log_chat = cfg.get('LOG_CHAT_ID', '')
            if _log_tok and _log_chat:
                _tg(_log_tok, 'sendMessage', {
                    'chat_id': _log_chat,
                    'text': adm_msg,
                    'parse_mode': 'HTML',
                })
            else:
                _send(token, str(admin_id), adm_msg)
    except: pass
