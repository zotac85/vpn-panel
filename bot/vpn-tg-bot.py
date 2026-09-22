#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VPN Panel Telegram Bot
Автоматическая выдача тестовых аккаунтов
"""

import os
import sys
import json
import time
import logging
import subprocess
import secrets
import string
import urllib.request
import urllib.parse
from datetime import datetime

# ─── Пути ───
CONFIG_FILE = "/etc/UDPCustom/bot.conf"
ISSUED_DB = "/etc/UDPCustom/bot_issued.db"
BLACKLIST = "/etc/UDPCustom/bot_blacklist"
LOG_FILE = "/var/log/vpn-tg-bot.log"
LOCK_FILE = "/var/run/vpn-tg-bot.lock"

# ─── Logging ───
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger()


# ═══════════════════════════════════════════════════════════════
# КОНФИГ
# ═══════════════════════════════════════════════════════════════
def load_config():
    cfg = {
        'BOT_TOKEN': '',
        'ADMIN_ID': '',
        'CHANNEL_ID': '',
        'REQUIRE_SUBSCRIPTION': '0',
        'COOLDOWN_HOURS': '24',
        'TEST_DAYS': '1',
        'TEST_DEVICES': '10',
        'TEST_TRAFFIC_GB': '100',
        'WELCOME_TEXT': '🎁 Привет! Нажми /test чтобы получить тестовый доступ.',
        'SUCCESS_TEMPLATE': '🎉 Логин: {USERNAME}\n🔑 Пароль: {PASSWORD}'
    }
    if not os.path.exists(CONFIG_FILE):
        log.error(f"Config not found: {CONFIG_FILE}")
        sys.exit(1)

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                v = v[1:-1]
            cfg[k] = v
    return cfg


# ═══════════════════════════════════════════════════════════════
# TELEGRAM API
# ═══════════════════════════════════════════════════════════════
def tg_request(token, method, params=None, timeout=35):
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        if params:
            data = json.dumps(params).encode('utf-8')
            req = urllib.request.Request(
                url, data=data,
                headers={'Content-Type': 'application/json'}
            )
        else:
            req = urllib.request.Request(url)

        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        log.error(f"TG API error ({method}): {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# УТИЛИТЫ
# ═══════════════════════════════════════════════════════════════
def gen_random(length=8):
    """Случайная строка a-z0-9"""
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_server_ip():
    """Внешний IP сервера"""
    try:
        r = subprocess.run(
            ['curl', '-s4', '--max-time', '5', 'ifconfig.me'],
            capture_output=True, text=True, timeout=8
        )
        ip = r.stdout.strip()
        if ip:
            return ip
    except Exception:
        pass
    try:
        r = subprocess.run(
            ['hostname', '-I'], capture_output=True, text=True, timeout=3
        )
        return r.stdout.split()[0]
    except Exception:
        return ""


def get_domain():
    """Домен, если задан"""
    if os.path.exists('/etc/.domain'):
        with open('/etc/.domain') as f:
            return f.read().strip()
    return get_server_ip()


# ═══════════════════════════════════════════════════════════════
# СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ
# ═══════════════════════════════════════════════════════════════
def create_test_user(cfg):
    """
    Создаёт тестовый аккаунт через shell.
    Возвращает (username, password) или (None, None) при ошибке.
    """
    # Уникальное имя
    for _ in range(20):
        username = "test" + gen_random(6)
        if not os.path.exists(f"/etc/passwd"):
            break
        r = subprocess.run(['id', username], capture_output=True)
        if r.returncode != 0:
            break
    else:
        log.error("Не удалось сгенерировать уникальное имя")
        return None, None

    password = gen_random(8)
    days = int(cfg.get('TEST_DAYS', '1'))
    devices = int(cfg.get('TEST_DEVICES', '10'))
    traffic_gb = int(cfg.get('TEST_TRAFFIC_GB', '100'))

    # Bash-скрипт для создания (запускается от root)
    bash_script = f'''
set -e
username="{username}"
password="{password}"
days={days}
devices={devices}
traffic_gb={traffic_gb}

# Создаём юзера
useradd -M -s /bin/false "$username"
echo "$username:$password" | chpasswd

# База юзеров
echo "$username" >> /etc/UDPCustom/users.db
sort -u -o /etc/UDPCustom/users.db /etc/UDPCustom/users.db

# Лимит устройств
echo "$devices" > "/etc/UDPCustom/limits/$username"

# maxlogins
sed -i "/^${{username}}[[:space:]]\\+hard[[:space:]]\\+maxlogins/d" /etc/security/limits.conf
echo "$username hard maxlogins $devices" >> /etc/security/limits.conf

# Лимит трафика
mkdir -p /etc/UDPCustom/traffic_limits /etc/UDPCustom/traffic
bytes=$((traffic_gb * 1073741824))
echo "$bytes" > "/etc/UDPCustom/traffic_limits/$username"
echo "0" > "/etc/UDPCustom/traffic/$username"

# iptables правило
uid=$(id -u "$username")
iptables -C VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null || \\
    iptables -A VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN

# Срок действия
exp_date=$(date -d "+$days days" +%Y-%m-%d)
chage -E "$exp_date" "$username"

echo "OK"
'''

    try:
        r = subprocess.run(
            ['bash', '-c', bash_script],
            capture_output=True, text=True, timeout=30
        )
        if 'OK' in r.stdout:
            log.info(f"Создан тестовый: {username}")
            return username, password
        else:
            log.error(f"Ошибка создания: {r.stderr}")
            return None, None
    except Exception as e:
        log.error(f"Exception при создании: {e}")
        return None, None


# ═══════════════════════════════════════════════════════════════
# АНТИ-АБУЗ
# ═══════════════════════════════════════════════════════════════
def is_blacklisted(user_id):
    if not os.path.exists(BLACKLIST):
        return False
    with open(BLACKLIST) as f:
        return str(user_id) in f.read().split()


def check_cooldown(user_id, hours):
    """Проверяет, не получал ли юзер тест за последние N часов"""
    if not os.path.exists(ISSUED_DB):
        return True, 0  # OK

    now = int(time.time())
    cooldown = hours * 3600

    try:
        with open(ISSUED_DB) as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) < 2:
                    continue
                if parts[0] == str(user_id):
                    ts = int(parts[1])
                    delta = now - ts
                    if delta < cooldown:
                        remaining = cooldown - delta
                        return False, remaining
    except Exception as e:
        log.error(f"Ошибка check_cooldown: {e}")
    return True, 0


def record_issue(user_id, username):
    with open(ISSUED_DB, 'a') as f:
        f.write(f"{user_id}|{int(time.time())}|{username}\n")


# ═══════════════════════════════════════════════════════════════
# ПРОВЕРКА ПОДПИСКИ
# ═══════════════════════════════════════════════════════════════
def check_subscription(token, user_id, channel):
    if not channel:
        return True
    r = tg_request(token, 'getChatMember', {
        'chat_id': channel,
        'user_id': user_id
    })
    if not r or not r.get('ok'):
        return True  # Не блокируем при ошибке API
    status = r.get('result', {}).get('status', '')
    return status in ('member', 'administrator', 'creator')


# ═══════════════════════════════════════════════════════════════
# ОТПРАВКА СООБЩЕНИЙ
# ═══════════════════════════════════════════════════════════════
def send_message(token, chat_id, text, reply_markup=None, parse_mode=None):
    params = {
        'chat_id': chat_id,
        'text': text,
        'disable_web_page_preview': True
    }
    if reply_markup:
        params['reply_markup'] = reply_markup
    if parse_mode:
        params['parse_mode'] = parse_mode
    return tg_request(token, 'sendMessage', params)


def format_time(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h} ч {m} мин"
    return f"{m} мин"


# ═══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ КОМАНД
# ═══════════════════════════════════════════════════════════════
def handle_start(cfg, chat_id, user_id, first_name):
    token = cfg['BOT_TOKEN']
    keyboard = {
        'inline_keyboard': [
            [{'text': '🎁 Получить тест', 'callback_data': 'get_test'}],
            [{'text': '💬 Поддержка', 'url': 'https://t.me/ArsenGuro'}],
            [{'text': '📢 Наш канал', 'url': 'https://t.me/ArsenVipKeys'}]
        ]
    }
    text = cfg.get('WELCOME_TEXT', 'Добро пожаловать!')
    if first_name:
        text = f"👋 Привет, {first_name}!\n\n{text}"
    send_message(token, chat_id, text, reply_markup=keyboard)


def handle_test(cfg, chat_id, user_id, first_name):
    token = cfg['BOT_TOKEN']

    # Чёрный список
    if is_blacklisted(user_id):
        send_message(token, chat_id,
            "🚫 Ты в чёрном списке. Обратись в поддержку: @ArsenGuro")
        return

    # Подписка
    if cfg.get('REQUIRE_SUBSCRIPTION', '0') == '1':
        if not check_subscription(token, user_id, cfg.get('CHANNEL_ID', '')):
            send_message(token, chat_id,
                f"📢 Для получения теста подпишись на канал: {cfg['CHANNEL_ID']}\n\n"
                f"После подписки нажми /test снова.",
                reply_markup={'inline_keyboard': [
                    [{'text': '📢 Подписаться', 'url': f"https://t.me/{cfg['CHANNEL_ID'].lstrip('@')}"}],
                    [{'text': '✅ Я подписался', 'callback_data': 'get_test'}]
                ]})
            return

    # Кулдаун
    cooldown_hours = int(cfg.get('COOLDOWN_HOURS', '24'))
    ok, remaining = check_cooldown(user_id, cooldown_hours)
    if not ok:
        send_message(token, chat_id,
            f"⏰ Ты уже получал тест. Попробуй снова через {format_time(remaining)}.")
        return

    # Уведомляем о процессе
    send_message(token, chat_id, "⏳ Создаём твой аккаунт, подожди 5 секунд...")

    # Создаём
    username, password = create_test_user(cfg)
    if not username:
        send_message(token, chat_id,
            "❌ Ошибка при создании аккаунта. Попробуй позже или напиши @ArsenGuro")
        return

    # Записываем
    record_issue(user_id, username)

    # Отправляем юзеру
    server = get_domain()
    traffic = cfg.get('TEST_TRAFFIC_GB', '100')
    devices = cfg.get('TEST_DEVICES', '10')

    template = cfg.get('SUCCESS_TEMPLATE', '🎉 Логин: {USERNAME}\n🔑 Пароль: {PASSWORD}')
    text = template.format(
        USERNAME=username,
        PASSWORD=password,
        SERVER=server,
        TRAFFIC=traffic,
        DEVICES=devices
    )
    send_message(token, chat_id, text)

    # Уведомляем админа
    admin_id = cfg.get('ADMIN_ID', '')
    if admin_id:
        admin_msg = (
            f"🔔 Новая выдача теста\n\n"
            f"👤 Telegram: {first_name or 'unknown'} (ID: {user_id})\n"
            f"📱 Логин: {username}\n"
            f"🔑 Пароль: {password}\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        send_message(token, admin_id, admin_msg)

    log.info(f"Выдан тест: user_id={user_id}, username={username}")


def handle_help(cfg, chat_id):
    token = cfg['BOT_TOKEN']
    text = (
        "📖 Доступные команды:\n\n"
        "/start — Приветствие\n"
        "/test — Получить тестовый доступ\n"
        "/help — Эта справка\n\n"
        "💬 Поддержка: @ArsenGuro\n"
        "📢 Канал: @ArsenVipKeys"
    )
    send_message(token, chat_id, text)


# ═══════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════
def main():
    cfg = load_config()

    if not cfg.get('BOT_TOKEN'):
        log.error("BOT_TOKEN не задан в конфиге!")
        sys.exit(1)

    log.info("━━━ VPN Telegram Bot запущен ━━━")
    log.info(f"Token: ...{cfg['BOT_TOKEN'][-8:]}")
    log.info(f"Admin ID: {cfg.get('ADMIN_ID', 'не задан')}")
    log.info(f"Channel: {cfg.get('CHANNEL_ID', 'не задан')}")

    # Удаляем webhook (чтобы работал long polling)
    tg_request(cfg['BOT_TOKEN'], 'deleteWebhook')

    offset = 0
    while True:
        try:
            updates = tg_request(cfg['BOT_TOKEN'], 'getUpdates', {
                'offset': offset,
                'timeout': 30,
                'allowed_updates': ['message', 'callback_query']
            })

            if not updates or not updates.get('ok'):
                time.sleep(3)
                continue

            for upd in updates.get('result', []):
                offset = upd['update_id'] + 1

                # Callback (кнопки)
                if 'callback_query' in upd:
                    cb = upd['callback_query']
                    user_id = cb['from']['id']
                    chat_id = cb['message']['chat']['id']
                    first_name = cb['from'].get('first_name', '')
                    data = cb.get('data', '')
                    tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery',
                              {'callback_query_id': cb['id']})
                    if data == 'get_test':
                        handle_test(cfg, chat_id, user_id, first_name)
                    continue

                # Обычное сообщение
                if 'message' not in upd:
                    continue
                msg = upd['message']
                chat_id = msg['chat']['id']
                user_id = msg['from']['id']
                first_name = msg['from'].get('first_name', '')
                text = msg.get('text', '')

                if text.startswith('/start'):
                    handle_start(cfg, chat_id, user_id, first_name)
                elif text.startswith('/test'):
                    handle_test(cfg, chat_id, user_id, first_name)
                elif text.startswith('/help'):
                    handle_help(cfg, chat_id)

        except KeyboardInterrupt:
            log.info("Остановка по Ctrl+C")
            break
        except Exception as e:
            log.error(f"Ошибка в main loop: {e}")
            time.sleep(5)


if __name__ == '__main__':
    main()
