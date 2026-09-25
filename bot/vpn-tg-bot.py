#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VPN Panel Telegram Bot — с переносами строк и отправкой .dark файла
"""

import os, sys, json, time, logging, subprocess, secrets, string, urllib.request, urllib.parse, mimetypes, uuid
from datetime import datetime

# Подключаем модуль администраторов
sys.path.insert(0, '/usr/local/bin')
from bot_modules.admin import get_admins, is_admin, handle_addadmin, handle_deladmin, handle_admins, handle_newuser
from bot_modules.autopost import handle_autopost, start_autopost_thread, load_autopost_config
from bot_modules.cabinet import show_cabinet, handle_cabinet_callback

CONFIG_FILE = "/etc/UDPCustom/bot.conf"
ISSUED_DB = "/etc/UDPCustom/bot_issued.db"
BLACKLIST = "/etc/UDPCustom/bot_blacklist"
LOG_FILE = "/var/log/vpn-tg-bot.log"

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log = logging.getLogger()

def load_config():
    cfg = {
        'BOT_TOKEN':'', 'ADMIN_ID':'', 'CHANNEL_ID':'', 'CHANNEL_ID_2':'', 'CHANNEL_NAME_2':'',
        'REQUIRE_SUBSCRIPTION':'0', 'COOLDOWN_HOURS':'8', 'TEST_DAYS':'1',
        'TEST_DEVICES':'1', 'TEST_TRAFFIC_GB':'50',
        'WELCOME_TEXT':'🎁 Привет! Нажми /test чтобы получить тестовый доступ.',
        'SUCCESS_TEMPLATE':'🎉 Логин: {USERNAME}\n🔑 Пароль: {PASSWORD}',
        'CONFIG_NAME':'ArsenVipKeys', 'CONNECTED_MSG':'Подключено!',
        'PAYLOAD':'CONNECT http://co.nr HTTP/1.1[crlf]Host: www.icloud.com[crlf]User-Agent: microsoft.com[crlf][crlf]AN / HTTP/1.1[lf]Host: [host][lf]Connection: Upgrade[lf]Upgrade: websocket[crlf][crlf]'
    }
    if not os.path.exists(CONFIG_FILE): return cfg
    with open(CONFIG_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            k, v = line.split('=', 1)
            k = k.strip(); v = v.strip()
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"': v = v[1:-1]
            # Преобразуем \n в реальные переносы
            v = v.replace('\\n', '\n')
            cfg[k] = v
    return cfg

def tg_request(token, method, params=None, timeout=35):
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
        log.error(f"TG API error ({method}): {e}")
        return None

def tg_send_document(token, chat_id, file_path, caption=None):
    """Отправка файла через multipart/form-data"""
    boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
    with open(file_path, 'rb') as f: file_data = f.read()
    filename = os.path.basename(file_path)
    body = b''
    def add_field(name, value):
        nonlocal body
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode('utf-8')
    add_field('chat_id', str(chat_id))
    if caption: add_field('caption', caption)
    body += f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode('utf-8')
    body += file_data + b'\r\n'
    body += f'--{boundary}--\r\n'.encode('utf-8')
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        log.error(f"sendDocument error: {e}")
        return None

SMART_DIR = "/etc/UDPCustom/smart_chat"

def smart_send(token, chat_id, text, reply_markup=None, parse_mode='HTML'):
    """Отправляет сообщение, удаляя предыдущее сообщение бота в этом чате."""
    try:
        os.makedirs(SMART_DIR, exist_ok=True)
        path = f"{SMART_DIR}/{chat_id}"
        # Удаляем предыдущее
        if os.path.exists(path):
            try:
                old_id = int(open(path).read().strip())
                tg_request(token, 'deleteMessage', {'chat_id': chat_id, 'message_id': old_id})
            except: pass
            try: os.remove(path)
            except: pass
        # Отправляем новое
        params = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
        if parse_mode: params['parse_mode'] = parse_mode
        if reply_markup: params['reply_markup'] = reply_markup
        result = tg_request(token, 'sendMessage', params)
        # Запоминаем id
        if result and result.get('ok'):
            try:
                with open(path, 'w') as f:
                    f.write(str(result['result']['message_id']))
            except: pass
        return result
    except Exception as e:
        log.error(f"smart_send error: {e}")
        return None

def gen_random(length=8):
    return ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(length))

def get_server_ip():
    try:
        r = subprocess.run(['curl','-s4','--max-time','5','ifconfig.me'], capture_output=True, text=True, timeout=8)
        ip = r.stdout.strip()
        if ip: return ip
    except: pass
    try:
        r = subprocess.run(['hostname','-I'], capture_output=True, text=True, timeout=3)
        return r.stdout.split()[0]
    except: return ""

def get_domain():
    if os.path.exists('/etc/vpn-domain'):
        with open('/etc/vpn-domain') as f:
            d = f.read().strip()
            if d: return d
    if os.path.exists('/etc/.domain'):
        with open('/etc/.domain') as f:
            d = f.read().strip()
            if d: return d
    return get_server_ip()

def get_ws_port():
    try:
        with open('/usr/local/bin/ws-proxy.py') as f:
            for line in f:
                if 'listen_port' in line:
                    digits = ''.join(ch for ch in line if ch.isdigit())
                    if digits: return digits
    except: pass
    return "80"

def get_random_proxy():
    p = '/etc/UDPCustom/proxies.txt'
    if not os.path.exists(p): return None
    try:
        with open(p) as f:
            proxies = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        if proxies: return secrets.choice(proxies)
    except: pass
    return None

def get_start_text():
    """Текст /start из /etc/UDPCustom/start.txt"""
    p = '/etc/UDPCustom/start.txt'
    if os.path.exists(p):
        try:
            with open(p) as f:
                t = f.read().strip()
                if t: return t
        except: pass
    return None


def get_channels():
    """Список каналов из /etc/UDPCustom/channels.txt"""
    p = '/etc/UDPCustom/channels.txt'
    if not os.path.exists(p): return []
    try:
        with open(p) as f:
            return [l.strip() for l in f if l.strip() and not l.startswith('#')]
    except: return []


def get_welcome_text():
    """Текст приветствия из /etc/UDPCustom/welcome.txt (fallback: bot.conf)"""
    p = '/etc/UDPCustom/welcome.txt'
    if os.path.exists(p):
        try:
            with open(p) as f:
                t = f.read().strip()
                if t: return t
        except: pass
    return None


def get_payload():
    """Payload из файла /etc/UDPCustom/payload.txt"""
    p = '/etc/UDPCustom/payload.txt'
    if os.path.exists(p):
        try:
            with open(p) as f:
                pl = f.read().strip()
                if pl: return pl
        except: pass
    return None


def create_test_user(cfg, tg_id=0):
    for _ in range(20):
        username = "test" + gen_random(6)
        r = subprocess.run(['id', username], capture_output=True)
        if r.returncode != 0: break
    else:
        return None, None
    password = gen_random(8)
    hours = int(cfg.get('TEST_HOURS', '8')); devices = int(cfg.get('TEST_DEVICES','1')); traffic_gb = int(cfg.get('TEST_TRAFFIC_GB','50'))
    bash_script = f'''
set -e
username="{username}"; password="{password}"; hours={cfg.get('TEST_HOURS','8')}; devices={devices}; traffic_gb={traffic_gb}
useradd -M -s /bin/false "$username"; echo "$username:$password" | chpasswd
echo "$username" >> /etc/UDPCustom/users.db
sort -u -o /etc/UDPCustom/users.db /etc/UDPCustom/users.db
echo "$devices" > "/etc/UDPCustom/limits/$username"
sed -i "/^${{username}}[[:space:]]\\+hard[[:space:]]\\+maxlogins/d" /etc/security/limits.conf
echo "$username hard maxlogins $devices" >> /etc/security/limits.conf
mkdir -p /etc/UDPCustom/traffic_limits /etc/UDPCustom/traffic
bytes=$((traffic_gb * 1073741824)); echo "$bytes" > "/etc/UDPCustom/traffic_limits/$username"; echo "0" > "/etc/UDPCustom/traffic/$username"
uid=$(id -u "$username")
if iptables -L VPN_TRAFFIC -n >/dev/null 2>&1; then
    iptables -C VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null || iptables -A VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null || true
else
    echo "WARN: chain VPN_TRAFFIC missing" >&2
fi
exp_date=$(date -d "+$hours hours +2 days" +%Y-%m-%d)
chage -E "$exp_date" "$username"
mkdir -p /etc/UDPCustom/expire_ts
echo $(( $(date +%s) + hours * 3600 )) > "/etc/UDPCustom/expire_ts/$username"
# Сохраняем пароль для функции "Мой ключ"
mkdir -p /etc/UDPCustom/passwords
echo "$password" > "/etc/UDPCustom/passwords/$username"
chmod 600 "/etc/UDPCustom/passwords/$username"
echo "OK"
'''
    try:
        r = subprocess.run(['bash','-c',bash_script], capture_output=True, text=True, timeout=30)
        if 'OK' in r.stdout:
            log.info(f"Создан тестовый: {username}")
            try:
                from bot_modules import db
                exp_ts = int(time.time()) + hours * 3600
                traffic_bytes = traffic_gb * 1073741824
                db.create_test_key(username, tg_id, password, exp_ts,
                                   devices=devices, traffic_limit=traffic_bytes)
                log.info(f"Test key saved to DB: {username} (tg_id={tg_id})")
            except Exception as e:
                log.error(f"DB save failed: {e}")
            return username, password
        log.error(f"Ошибка создания: {r.stderr}")
        return None, None
    except Exception as e:
        log.error(f"Exception: {e}")
        return None, None

def create_vip_user(cfg, tg_id, days, price, traffic_gb, devices):
    """Создаёт VIP-юзера: Linux-юзер vip_<tg_id>_<rnd> + запись в vip_keys."""
    import secrets as _sec, string as _str
    # Генерим логин
    suffix = ''.join(_sec.choice(_str.ascii_lowercase + _str.digits) for _ in range(4))
    username = f"vip_{tg_id}_{suffix}"
    # Проверяем что не занят
    r = subprocess.run(['id', username], capture_output=True)
    if r.returncode == 0:
        return None, None
    # Пароль 12 символов
    alphabet = _str.ascii_letters + _str.digits
    password = ''.join(_sec.choice(alphabet) for _ in range(12))

    days = int(days)
    traffic_gb = int(traffic_gb)
    devices = int(devices)
    exp_ts = int(time.time()) + days * 86400
    traffic_bytes = traffic_gb * 1073741824

    bash_script = f'''
set -e
username="{username}"
password="{password}"
days={days}
devices={devices}
traffic_bytes={traffic_bytes}
useradd -M -s /bin/false "$username"
echo "$username:$password" | chpasswd
echo "$username" >> /etc/UDPCustom/users.db
sort -u -o /etc/UDPCustom/users.db /etc/UDPCustom/users.db
mkdir -p /etc/UDPCustom/limits /etc/UDPCustom/traffic /etc/UDPCustom/traffic_limits /etc/UDPCustom/expire_ts /etc/UDPCustom/passwords
echo "$devices" > "/etc/UDPCustom/limits/$username"
sed -i "/^${{username}}[[:space:]]\+hard[[:space:]]\+maxlogins/d" /etc/security/limits.conf
echo "$username hard maxlogins $devices" >> /etc/security/limits.conf
echo "$traffic_bytes" > "/etc/UDPCustom/traffic_limits/$username"
echo "0" > "/etc/UDPCustom/traffic/$username"
uid=$(id -u "$username")
if iptables -L VPN_TRAFFIC -n >/dev/null 2>&1; then
    iptables -C VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null || iptables -A VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null || true
fi
exp_date=$(date -d "+$days days +2 days" +%Y-%m-%d)
chage -E "$exp_date" "$username"
echo {exp_ts} > "/etc/UDPCustom/expire_ts/$username"
echo "$password" > "/etc/UDPCustom/passwords/$username"
chmod 600 "/etc/UDPCustom/passwords/$username"
echo "OK"
'''
    try:
        r = subprocess.run(['bash','-c',bash_script], capture_output=True, text=True, timeout=30)
        if 'OK' not in r.stdout:
            log.error(f"VIP create error: {r.stderr}")
            return None, None
        # Запись в БД
        try:
            from bot_modules import db as _db
            _db.create_vip_key(username, tg_id, password, exp_ts,
                               devices=devices, traffic_limit=traffic_bytes,
                               tariff=f"vip_{days}d", price_paid=price, paid_via='balance')
        except Exception as e:
            log.error(f"VIP DB save error: {e}")
        log.info(f"VIP создан: {username} (tg_id={tg_id}, {days}д, ${price})")
        return username, password
    except Exception as e:
        log.error(f"VIP exception: {e}")
        return None, None


def is_blacklisted(user_id):
    if not os.path.exists(BLACKLIST): return False
    with open(BLACKLIST) as f: return str(user_id) in f.read().split()

def check_cooldown(user_id, hours):
    if not os.path.exists(ISSUED_DB): return True, 0
    now = int(time.time()); cooldown = hours * 3600
    try:
        with open(ISSUED_DB) as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) < 2: continue
                if parts[0] == str(user_id):
                    ts = int(parts[1]); delta = now - ts
                    if delta < cooldown: return False, cooldown - delta
    except: pass
    return True, 0

def record_issue(user_id, username):
    with open(ISSUED_DB,'a') as f: f.write(f"{user_id}|{int(time.time())}|{username}\n")

def check_subscription(token, user_id, channel):
    """Проверка подписки. При ошибке API — считаем НЕ подписан (безопасно)."""
    if not channel: return True
    r = tg_request(token, 'getChatMember', {'chat_id': channel, 'user_id': user_id})
    
    # Если ошибка API — считаем НЕ подписан
    if not r or not r.get('ok'):
        # Логируем причину
        err = r.get('description', 'unknown') if r else 'no response'
        log.warning(f"getChatMember error for {channel}: {err}")
        return False
    
    status = r.get('result', {}).get('status', '')
    return status in ('member', 'administrator', 'creator', 'restricted')

def send_message(token, chat_id, text, reply_markup=None, parse_mode=None):
    params = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
    if reply_markup: params['reply_markup'] = reply_markup
    if parse_mode: params['parse_mode'] = parse_mode
    return tg_request(token, 'sendMessage', params)


def send_message_ttl(token, chat_id, text, ttl=15, reply_markup=None, parse_mode=None):
    """Отправляет сообщение и удаляет через ttl секунд"""
    result = send_message(token, chat_id, text, reply_markup, parse_mode)
    if result and result.get('ok'):
        msg_id = result['result']['message_id']
        import threading
        def _delete():
            import time as _t
            _t.sleep(ttl)
            try:
                tg_request(token, 'deleteMessage', {'chat_id': chat_id, 'message_id': msg_id})
            except: pass
        threading.Thread(target=_delete, daemon=True).start()
    return result

def format_time(seconds):
    h = seconds // 3600; m = (seconds % 3600) // 60
    return f"{h} ч {m} мин" if h > 0 else f"{m} мин"

def generate_darktunnel_url(username, password, domain, ws_port, proxy, cfg):
    import base64
    snic = cfg.get('SNI', '') or ''
    pcfg = get_payload() or cfg.get('PAYLOAD', '') or 'CONNECT http://co.nr HTTP/1.1[crlf]'
    proxy_host = proxy if proxy else ''
    proxy_port = int(ws_port) if str(ws_port).isdigit() else 2052
    config = {
        "type": "SSH",
        "name": (cfg.get('CONFIG_NAME','VPN') + "_" + username),
        "sshTunnelConfig": {
            "sshConfig": {
                "host": domain,
                "port": int(ws_port) if str(ws_port).isdigit() else 2052,
                "username": username,
                "password": password
            },
            "injectConfig": {
                "mode": "PROXY",
                "serverNameIndication": snic,
                "proxyHost": proxy_host,
                "proxyPort": proxy_port,
                "payload": pcfg
            }
        }
    }
    j = json.dumps(config, ensure_ascii=False, separators=(',', ':'))
    b = base64.b64encode(j.encode('utf-8')).decode('ascii')
    return "darktunnel://" + b


def handle_start(cfg, chat_id, user_id, first_name, force_verified=None):
    token = cfg['BOT_TOKEN']
    name = first_name or 'друг'
    channels = get_channels()
    
    if not channels:
        send_message(token, chat_id, "❌ Каналы не настроены. Обратись: @ArsenGuro")
        return
    
    primary = channels[0].lstrip('@')
    # verified=True только если пришёл по deep-link из канала (force_verified=True)
    # Обычный /start всегда показывает "Перейди в канал"
    verified = True if force_verified is True else False
    admin_id = cfg.get('ADMIN_ID', '')
    is_admin = str(user_id) == str(admin_id)
    
    # ПРОВЕРКА ПОДПИСКИ на все каналы (включая спонсоров)
    not_sub = []
    if cfg.get('REQUIRE_SUBSCRIPTION','0') == '1':
        for ch in channels:
            if not check_subscription(token, user_id, ch):
                not_sub.append(ch.lstrip('@'))
    
    if not_sub:
        # Не подписан на какие-то каналы
        text = (
            f"👋 Привет, {name}!\n\n"
            f"⚠️ <b>Чтобы получить тестовый ключ:</b>\n\n"
            f"1️⃣ Подпишись на все каналы ниже\n"
            f"2️⃣ Зайди в каждый, посмотри посты\n"
            f"3️⃣ Поставь лайк или реакцию 👍\n"
            f"4️⃣ Вернись и нажми «Я подписался»\n\n"
            f"<b>Ты не подписан на:</b>\n"
            + "".join([f"👉 @{ch}\n" for ch in not_sub]) +
            f"\n💎 Есть VIP-ключи — пиши @ArsenGuro"
        )
        keyboard = {'inline_keyboard': []}
        for ch in not_sub:
            keyboard['inline_keyboard'].append([{'text': f'📢 @{ch}', 'url': f'https://t.me/{ch}'}])
        keyboard['inline_keyboard'].append([{'text': '✅ Я подписался → Проверить', 'callback_data': 'check_verified'}])
        keyboard['inline_keyboard'].append([
            {'text': '💎 VIP-ключ', 'url': 'https://t.me/ArsenGuro'},
            {'text': '💬 Поддержка', 'url': 'https://t.me/ArsenGuro'}
        ])
        if is_admin:
            keyboard['inline_keyboard'].append([
                {'text': '📊 Статистика', 'callback_data': 'admin_stats'},
                {'text': '👥 Пользователи', 'callback_data': 'admin_users_1'}
            ])
            keyboard['inline_keyboard'].append([
                {'text': '📢 Пост', 'callback_data': 'admin_post'},
                {'text': '📢 Каналы', 'callback_data': 'admin_channels'}
            ])
    
    elif verified:
        # Подписан на все + verified → кнопка получить тест
        text = (
            f"👋 Привет, {name}!\n\n"
            f"🎁 Можешь получить тестовый ключ\n\n"
            f"📱 8 часов | 📊 50 ГБ | 💻 1 устройство\n"
            f"🇩🇪 Сервер Германия\n\n"
            f"👇 Жми кнопку ниже"
        )
        keyboard = {'inline_keyboard': [
            [{'text': '🎁 ПОЛУЧИТЬ ТЕСТ', 'callback_data': 'get_test'}],
            [{'text': '👤 Личный кабинет', 'callback_data': 'cab_main'}],
            [
                {'text': '💎 VIP-ключ', 'url': 'https://t.me/ArsenGuro'},
                {'text': '💬 Поддержка', 'url': 'https://t.me/ArsenGuro'}
            ]
        ]}
        if is_admin:
            keyboard['inline_keyboard'].append([
                {'text': '📊 Статистика', 'callback_data': 'admin_stats'},
                {'text': '👥 Пользователи', 'callback_data': 'admin_users_1'}
            ])
            keyboard['inline_keyboard'].append([
                {'text': '📢 Пост', 'callback_data': 'admin_post'},
                {'text': '📢 Каналы', 'callback_data': 'admin_channels'}
            ])
    
    else:
        # Подписан на все, но НЕ verified → надо зайти на канал
        channels_all = [c.lstrip('@') for c in channels]
        primary_clean = channels_all[0] if channels_all else primary
        sponsors_start = channels_all[1:] if len(channels_all) > 1 else []

        NL = chr(10)
        lines2 = [
            f"👋 Привет, {name}!",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "🎁 <b>КАК ПОЛУЧИТЬ БЕСПЛАТНЫЙ ТЕСТ</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"1️⃣ Зайди в канал @{primary_clean}",
            "2️⃣ Поставь 👍 лайки на 3 последних поста",
            "",
        ]
        if sponsors_start:
            lines2.append("3️⃣ Подпишись на спонсоров (обязательно!):")
            lines2.append("")
            for s in sponsors_start:
                lines2.append(f"   📢 @{s}")
            lines2.append("   ⚠️ Без подписки ключ не дадут")
            lines2.append("")
            lines2.append(f"4️⃣ Найди в @{primary_clean} пост с кнопкой")
            lines2.append("    «🎁 Получить тест» и нажми её")
            lines2.append("")
            lines2.append("5️⃣ Ключ прилетит сюда, в бот")
        else:
            lines2.append(f"3️⃣ Найди в @{primary_clean} пост с кнопкой")
            lines2.append("    «🎁 Получить тест» и нажми её")
            lines2.append("")
            lines2.append("4️⃣ Ключ прилетит сюда, в бот")
        lines2.append("━━━━━━━━━━━━━━━━━━━━")
        lines2.append("🎁 Тест:  8 часов · 50 ГБ · 1 устр.")
        lines2.append("💎 VIP:   @ArsenGuro")
        text = NL.join(lines2)
        sponsors_start = [c.lstrip('@') for c in channels[1:]]
        kb_start = []
        for i in range(0, len(sponsors_start), 2):
            row = [{'text': f'📢 @{sponsors_start[i]}', 'url': f'https://t.me/{sponsors_start[i]}'}]
            if i + 1 < len(sponsors_start):
                row.append({'text': f'📢 @{sponsors_start[i+1]}', 'url': f'https://t.me/{sponsors_start[i+1]}'})
            kb_start.append(row)
        kb_start.append([
            {'text': '📣 Реклама', 'url': 'https://t.me/ArsenGuro'},
            {'text': '👤 Личный кабинет', 'callback_data': 'cab_main'}
        ])
        keyboard = {'inline_keyboard': kb_start}
        if is_admin:
            keyboard['inline_keyboard'].append([
                {'text': '📊 Статистика', 'callback_data': 'admin_stats'},
                {'text': '👥 Пользователи', 'callback_data': 'admin_users_1'}
            ])
            keyboard['inline_keyboard'].append([
                {'text': '📢 Пост', 'callback_data': 'admin_post'},
                {'text': '📢 Каналы', 'callback_data': 'admin_channels'}
            ])
    
    # Сохраняем message_id приветствия для авто-удаления
    result = smart_send(token, chat_id, text, reply_markup=keyboard, parse_mode='HTML')
    if result and result.get('ok'):
        msg_id = result['result']['message_id']
        welcome_dir = '/etc/UDPCustom/welcome_msgs'
        try:
            os.makedirs(welcome_dir, exist_ok=True)
            with open(f'{welcome_dir}/{user_id}', 'w') as f:
                f.write(str(msg_id))
        except: pass
        import threading
        def _auto_del():
            import time as _t
            _t.sleep(600)
            if os.path.exists(f'{welcome_dir}/{user_id}'):
                try:
                    with open(f'{welcome_dir}/{user_id}') as f:
                        saved_id = int(f.read().strip())
                    tg_request(token, 'deleteMessage', {'chat_id': chat_id, 'message_id': saved_id})
                    os.remove(f'{welcome_dir}/{user_id}')
                except: pass
        threading.Thread(target=_auto_del, daemon=True).start()


def handle_test(cfg, chat_id, user_id, first_name, cb_id=None):
    token = cfg['BOT_TOKEN']
    if is_blacklisted(user_id):
        send_message(token, chat_id, "🚫 Ты в чёрном списке. @ArsenGuro"); return
    if cfg.get('REQUIRE_SUBSCRIPTION','0') == '1':
        channels = get_channels()
        not_sub = []
        for ch in channels:
            if not check_subscription(token, user_id, ch):
                not_sub.append(ch.lstrip('@'))
        if not_sub:
            channels_list = ", ".join([f"@{ch}" for ch in not_sub])
            if cb_id:
                tg_request(token, 'answerCallbackQuery', {
                    'callback_query_id': cb_id,
                    'text': f'❌ Ты ещё не подписался на: {channels_list}\n\nПодпишись и нажми ещё раз.',
                    'show_alert': True
                })
            else:
                keyboard = {'inline_keyboard': []}
                for ch in not_sub:
                    keyboard['inline_keyboard'].append([{'text': f'📢 @{ch}', 'url': f'https://t.me/{ch}'}])
                keyboard['inline_keyboard'].append([{'text': '✅ Я подписался → Проверить', 'callback_data': 'get_test'}])
                text = '⚠️ Сначала подпишись на каналы: ' + channels_list
                send_message(token, chat_id, text, reply_markup=keyboard)
            return
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        cooldown_hours = int(cfg.get('COOLDOWN_HOURS','8'))
        ok, remaining = check_cooldown(user_id, cooldown_hours)
        if not ok:
            send_message_ttl(token, chat_id, f"⏰ Попробуй через {format_time(remaining)}.", ttl=15); return
    send_message_ttl(token, chat_id, "⏳ Создаём аккаунт...", ttl=3)
    username, password = create_test_user(cfg, user_id)
    if not username:
        send_message_ttl(token, chat_id, "❌ Ошибка. Попробуй позже.", ttl=15); return
    record_issue(user_id, username)
    _ref_test_bonus(cfg, user_id)
    domain = get_domain(); ws_port = get_ws_port(); proxy = get_random_proxy()
    connect_line = f"{domain}:{ws_port}@{username}:{password}"
    traffic = cfg.get('TEST_TRAFFIC_GB','50'); devices = cfg.get('TEST_DEVICES','1')
    text = (f"🎉 <b>ТЕСТОВЫЙ ДОСТУП ГОТОВ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 Ключ: <code>{username}</code>\n"
            f"⏰ Срок: {cfg.get('TEST_HOURS','8')} часов\n"
            f"📊 Трафик: {traffic} ГБ\n"
            f"📱 Устройств: {devices}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 Логин, пароль и конфиг — в личном кабинете")
    # Убираем кнопку "Получить тест" из welcome-сообщения
    welcome_file = f"/etc/UDPCustom/welcome_msgs/{user_id}"
    if os.path.exists(welcome_file):
        try:
            with open(welcome_file) as f:
                w_id = int(f.read().strip())
            # Новая клавиатура без "Получить тест"
            new_kb = {'inline_keyboard': [
                [{'text': '🔑 Мой ключ', 'callback_data': 'mykey'}],
                [
                    {'text': '💎 VIP-ключ', 'url': 'https://t.me/ArsenGuro'},
                    {'text': '💬 Поддержка', 'url': 'https://t.me/ArsenGuro'}
                ]
            ]}
            # Сохраняем админ-кнопки
            admin_id = cfg.get('ADMIN_ID', '')
            if str(user_id) == str(admin_id):
                new_kb['inline_keyboard'].append([
                    {'text': '📊 Статистика', 'callback_data': 'admin_stats'},
                    {'text': '👥 Пользователи', 'callback_data': 'admin_users_1'}
                ])
                new_kb['inline_keyboard'].append([
                    {'text': '📢 Пост', 'callback_data': 'admin_post'},
                    {'text': '📢 Каналы', 'callback_data': 'admin_channels'}
                ])
            tg_request(token, 'editMessageReplyMarkup', {
                'chat_id': chat_id,
                'message_id': w_id,
                'reply_markup': new_kb
            })
            os.remove(welcome_file)
        except: pass
    
    kb_test = {'inline_keyboard': [
        [{'text': '📲 Получить конфиг', 'callback_data': f'cab_dt:{username}'}],
        [{'text': '👤 Личный кабинет', 'callback_data': 'cab_main'}]
    ]}
    smart_send(token, chat_id, text, reply_markup=kb_test, parse_mode="HTML")
    if admin_id:
        from datetime import datetime
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        admin_msg = (
            f"🔔 <b>Новая выдача из бота</b>\n\n"
            f"👤 Telegram: {first_name or '—'} (ID: {user_id})\n"
            f"📱 Логин : <code>{username}</code>\n"
            f"🔑 Пароль: <code>{password}</code>\n"
            f"🌐 Сервер: {domain}\n"
            f"🔌 Порт  : {ws_port}\n"
            f"🕐 {now_str}"
        )
        tg_request(token, 'sendMessage', {
            'chat_id': admin_id,
            'text': admin_msg,
            'parse_mode': 'HTML'
        })
    log.info(f"Выдан тест: {username}")


def _ref_purchase_bonus(cfg, buyer_id, price):
    """Когда реферал купил VIP — начисляем пригласившему $1 (разово)."""
    try:
        from bot_modules import db as _db
    except Exception as e:
        log.error(f"_ref_purchase_bonus import: {e}")
        return
    inviter_id = _db.mark_first_purchase(buyer_id)
    if not inviter_id:
        return
    log.info(f"Ref purchase bonus: inviter={inviter_id}, buyer={buyer_id}")
    # Начисляем $1
    try:
        _db.add_balance(inviter_id, 1.0, method='referral_bonus', meta={'from_user': buyer_id})
        _db.mark_bonus_paid(buyer_id)
    except Exception as e:
        log.error(f"ref bonus pay error: {e}")
        return
    # Уведомление
    NL = chr(10)
    msg = NL.join([
        "💰 <b>РЕФЕРАЛЬНЫЙ БОНУС</b>",
        "",
        "Твой реферал купил VIP-ключ!",
        "",
        "💵 <b>+1.00 USDT</b> на твой баланс",
    ])
    try:
        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
            'chat_id': inviter_id,
            'text': msg,
            'parse_mode': 'HTML'
        })
    except: pass


def _ref_test_bonus(cfg, invited_id):
    """Когда реферал получил тест — начисляем пригласившему +3 дня к VIP."""
    try:
        from bot_modules import db as _db
    except Exception as e:
        log.error(f"_ref_test_bonus import: {e}")
        return
    inviter_id = _db.mark_test_bonus(invited_id)
    if not inviter_id:
        return
    log.info(f"Ref test bonus: inviter={inviter_id}, invited={invited_id}")
    # Продлеваем VIP-ключи пригласившего на 3 дня
    extended = _db.extend_vip_keys(inviter_id, 3)
    # Уведомление
    NL = chr(10)
    if extended > 0:
        msg = NL.join([
            "🎁 <b>РЕФЕРАЛЬНЫЙ БОНУС</b>",
            "",
            "Твой реферал получил тестовый ключ!",
            "",
            "🎁 <b>+3 дня</b> к твоему VIP-ключу",
        ])
    else:
        msg = NL.join([
            "🎁 <b>РЕФЕРАЛЬНЫЙ БОНУС</b>",
            "",
            "Твой реферал получил тестовый ключ!",
            "",
            "⚠️ У тебя нет активного VIP-ключа,",
            "поэтому +3 дня не начислены.",
            "Купи VIP — и бонус за следующего реферала зачтётся."
        ])
    try:
        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
            'chat_id': inviter_id,
            'text': msg,
            'parse_mode': 'HTML'
        })
    except: pass


def _do_vip_purchase(cfg, cb, tg_id, idx):
    """Покупка VIP за баланс. cb — callback_query."""
    token = cfg['BOT_TOKEN']
    chat_id = cb['message']['chat']['id']
    msg_id = cb['message']['message_id']
    cb_id = cb['id']

    try:
        from bot_modules import db as _db
        from bot_modules.cabinet import _parse_vip_tariffs
    except Exception as e:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'Ошибка: {e}', 'show_alert': True})
        return

    tariffs = _parse_vip_tariffs(cfg)
    if idx < 1 or idx > len(tariffs):
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Тариф не найден', 'show_alert': True})
        return
    t = tariffs[idx - 1]
    price = t['price']

    # Проверяем баланс ЕЩЁ РАЗ (на случай параллельной покупки)
    balance = _db.get_balance(tg_id)
    if balance < price:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Недостаточно средств', 'show_alert': True})
        return

    # Списываем баланс
    try:
        _db.add_balance(tg_id, -price, method='purchase', meta={'tariff': f"vip_{t['days']}d", 'days': t['days']})
    except Exception as e:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'Ошибка списания: {e}', 'show_alert': True})
        return

    # Создаём ключ
    username, password = create_vip_user(cfg, tg_id, t['days'], t['price'], t['gb'], t['devices'])
    if not username:
        # Возвращаем деньги
        try:
            _db.add_balance(tg_id, price, method='manual', meta={'comment': 'Откат покупки VIP (ошибка создания)'})
        except: pass
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Ошибка создания ключа. Баланс возвращён.', 'show_alert': True})
        return

    # Показываем успех
    NL = chr(10)
    text = NL.join([
        "🎉 <b>VIP-КЛЮЧ СОЗДАН!</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"💎 Логин: <code>{username}</code>",
        f"🔑 Пароль: <code>{password}</code>",
        "",
        f"⏰ Срок: <b>{t['days']} дней</b>",
        f"📊 Трафик: <b>{t['gb']} ГБ</b>",
        f"📱 Устройств: <b>{t['devices']}</b>",
        "",
        f"💵 Списано: <b>{price:.2f} USDT</b>",
        f"💰 Баланс: <b>{_db.get_balance(tg_id):.2f} USDT</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📲 Конфиг — в <b>Личном кабинете</b>"
    ])
    kb = {'inline_keyboard': [
        [{'text': '🔑 Мои ключи', 'callback_data': 'cab_keys'}],
        [{'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}]
    ]}
    tg_request(token, 'editMessageText', {
        'chat_id': chat_id,
        'message_id': msg_id,
        'text': text,
        'parse_mode': 'HTML',
        'reply_markup': kb
    })
    tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '✅ Ключ создан!'})

    # Уведомление админу
    admin_id = cfg.get('ADMIN_ID', '')
    if admin_id:
        user = _db.get_user(tg_id) or {}
        NL2 = chr(10)
        a_msg = NL2.join([
            "💰 <b>ПОКУПКА VIP</b>",
            "",
            f"👤 Имя: {user.get('first_name') or '—'}",
            f"🆔 ID: <code>{tg_id}</code>",
            f"📱 @{user.get('username') or '—'}",
            "",
            f"📦 {t['days']}д / {t['gb']}ГБ",
            f"💵 {price:.2f} USDT",
            f"📱 Ключ: <code>{username}</code>"
        ])
        tg_request(token, 'sendMessage', {'chat_id': admin_id, 'text': a_msg, 'parse_mode': 'HTML'})

    log.info(f"VIP покупка: {username} | {t['days']}д | {price} USDT | tg={tg_id}")

    # Реферальный бонус пригласившему (разово)
    try:
        _ref_purchase_bonus(cfg, tg_id, price)
    except Exception as e:
        log.error(f"ref purchase call error: {e}")


def _do_addbalance(cfg, chat_id, args):
    """Начисляет баланс: ID СУММА [КОММЕНТАРИЙ]"""
    token = cfg['BOT_TOKEN']
    try:
        from bot_modules import db as _db
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка db: {e}")
        return

    parts = args.strip().split(maxsplit=2)
    if len(parts) < 2:
        send_message(token, chat_id, "❌ Формат: <code>ID СУММА [КОММЕНТАРИЙ]</code>", parse_mode='HTML')
        return
    if not parts[0].isdigit():
        send_message(token, chat_id, "❌ ID должен быть числом")
        return
    target_id = int(parts[0])
    try:
        amount = float(parts[1].replace(',', '.'))
    except:
        send_message(token, chat_id, "❌ СУММА должна быть числом (можно с минусом)")
        return
    if amount == 0:
        send_message(token, chat_id, "❌ Сумма не может быть 0")
        return
    comment = parts[2] if len(parts) > 2 else ""

    # Проверяем что юзер есть
    user = _db.get_user(target_id)
    if not user:
        send_message(token, chat_id, f"❌ Юзер <code>{target_id}</code> не найден в БД", parse_mode='HTML')
        return

    # Начисляем
    new_balance = _db.add_balance(target_id, amount, method='manual',
                                  meta={'comment': comment, 'by_admin': chat_id})
    # Если это первая покупка через баланс - обработаем позже (см. mark_first_purchase)

    NL = chr(10)
    sign = "+" if amount >= 0 else ""
    lines = [
        "✅ <b>БАЛАНС ОБНОВЛЁН</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"👤 Юзер: <code>{target_id}</code>",
        f"💵 Изменение: <b>{sign}{amount:.2f} USDT</b>",
        f"💰 Новый баланс: <b>{new_balance:.2f} USDT</b>"
    ]
    if comment:
        lines.append(f"💬 Комментарий: {comment}")
    send_message(token, chat_id, NL.join(lines), parse_mode='HTML')

    # Уведомляем юзера
    if amount >= 0:
        u_msg = NL.join([
            "💰 <b>БАЛАНС ПОПОЛНЕН</b>",
            "",
            f"Зачислено: <b>+{amount:.2f} USDT</b>",
            f"Баланс: <b>{new_balance:.2f} USDT</b>"
        ])
    else:
        u_msg = NL.join([
            "⚠️ <b>СПИСАНИЕ С БАЛАНСА</b>",
            "",
            f"Списано: <b>{amount:.2f} USDT</b>",
            f"Баланс: <b>{new_balance:.2f} USDT</b>"
        ])
    try:
        tg_request(token, 'sendMessage', {
            'chat_id': target_id,
            'text': u_msg,
            'parse_mode': 'HTML'
        })
    except: pass


def _do_newpromo(cfg, chat_id, args):
    """Создаёт промокод: CODE DAYS USES [DATE YYYY-MM-DD]"""
    token = cfg['BOT_TOKEN']
    from datetime import datetime as _dt
    try:
        from bot_modules import db as _db
    except Exception as e:
        send_message(token, chat_id, 'Ошибка модуля db: ' + str(e))
        return
    parts = args.strip().split()
    if len(parts) < 3:
        send_message(token, chat_id, 'Формат: <code>CODE ДНЕЙ АКТИВАЦИЙ [ДАТА]</code>', parse_mode='HTML')
        return
    code = parts[0].strip()
    if len(code) < 3 or not code.isalnum():
        send_message(token, chat_id, 'Код: только A-Z и 0-9, минимум 3 символа')
        return
    try:
        days = int(parts[1]); uses = int(parts[2])
    except:
        send_message(token, chat_id, 'ДНЕЙ и АКТИВАЦИЙ должны быть числами')
        return
    if days < 1 or uses < 1:
        send_message(token, chat_id, 'ДНЕЙ и АКТИВАЦИЙ должны быть > 0')
        return
    expires_at = 0
    if len(parts) >= 4:
        try:
            dt = _dt.strptime(parts[3], '%Y-%m-%d')
            expires_at = int(dt.timestamp())
        except:
            send_message(token, chat_id, 'Дата должна быть YYYY-MM-DD')
            return
    if _db.get_promo(code):
        send_message(token, chat_id, '⚠️ Промокод <code>' + code + '</code> уже существует!', parse_mode='HTML')
        return
    try:
        _db.create_promo(code, 'days', days, max_uses=uses, expires_at=expires_at)
    except Exception as e:
        send_message(token, chat_id, 'Ошибка: ' + str(e))
        return
    lines = ['✅ <b>ПРОМОКОД СОЗДАН</b>', '━━━━━━━━━━━━━━━━━━━━', '', '🎫 Код: <code>' + code + '</code>', '⏰ Бонус: <b>+' + str(days) + ' дней</b>', '👥 Активаций: <b>' + str(uses) + '</b>']
    if expires_at:
        exp_str = _dt.fromtimestamp(expires_at).strftime('%d.%m.%Y')
        lines.append('📅 До: <b>' + exp_str + '</b>')
    else:
        lines.append('📅 Действует: <b>бессрочно</b>')
    send_message(token, chat_id, chr(10).join(lines), parse_mode='HTML')


def show_promo_list(cfg, chat_id, user_id, msg_id=None):
    """Список промокодов для админа"""
    token = cfg['BOT_TOKEN']
    if str(user_id) != str(cfg.get('ADMIN_ID', '')):
        send_message(token, chat_id, '🚫 Только для админа.')
        return
    try:
        from bot_modules import db as _db
    except Exception as e:
        send_message(token, chat_id, 'Ошибка db: ' + str(e))
        return

    import time as _t
    from datetime import datetime as _dt
    rows = _db.query('SELECT code, type, value, uses_left, max_uses, expires_at FROM promo_codes ORDER BY created_at DESC')
    NL = chr(10)
    if not rows:
        text = NL.join(['🎫 <b>ПРОМОКОДЫ</b>', '━━━━━━━━━━━━━━━━━━━━', '', '❌ Пока нет промокодов'])
        kb = {'inline_keyboard': [
            [{'text': '➕ Создать промокод', 'callback_data': 'adm_newpromo'}],
            [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
        ]}
    else:
        now = int(_t.time())
        lines = [f'🎫 <b>ПРОМОКОДЫ ({len(rows)})</b>', '━━━━━━━━━━━━━━━━━━━━', '']
        for r in rows:
            is_expired = r['expires_at'] and r['expires_at'] < now
            is_used = r['uses_left'] == 0
            if is_expired:
                status = '⏰ истёк'
            elif is_used:
                status = '🚫 исчерпан'
            else:
                status = '🟢 активен'
            lines.append(f'🎁 <code>{r["code"]}</code> — {status}')
            lines.append(f'   +{int(r["value"])} дней · {r["uses_left"]}/{r["max_uses"]} активаций')
            if r['expires_at']:
                exp_str = _dt.fromtimestamp(r['expires_at']).strftime('%d.%m.%Y')
                lines.append(f'   📅 до {exp_str}')
            else:
                lines.append('   📅 бессрочно')
            lines.append('')
        text = NL.join(lines)

        kb_list = []
        for r in rows[:10]:
            kb_list.append([{'text': f'🗑 {r["code"]}', 'callback_data': f'adm_promo_del:{r["code"]}'}])
        kb_list.append([
            {'text': '➕ Создать промокод', 'callback_data': 'adm_newpromo'},
            {'text': '🔄 Обновить', 'callback_data': 'adm_promo_list'}
        ])
        kb_list.append([{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}])
        kb = {'inline_keyboard': kb_list}

    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')


def show_admin_panel(cfg, chat_id, user_id, msg_id=None):
    """Админ-панель"""
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        send_message(token, chat_id, '🚫 Только для админа.')
        return
    total_users = 0
    try:
        import sqlite3 as _sq
        _c = _sq.connect('/etc/UDPCustom/vpn.db')
        total_users = _c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        _c.close()
    except: pass
    NLx = chr(10)
    lines = ['⚙️ <b>АДМИН-ПАНЕЛЬ</b>', '━━━━━━━━━━━━━━━━━━━━', '', '👤 ID: <code>' + str(user_id) + '</code>', '📊 Юзеров: <b>' + str(total_users) + '</b>', '', '━━━━━━━━━━━━━━━━━━━━', 'Выбери раздел 👇']
    text = NLx.join(lines)
    keyboard = {'inline_keyboard': [
        [{'text': '📊 Статистика', 'callback_data': 'admin_stats'},
         {'text': '👥 Пользователи', 'callback_data': 'admin_users_1'}],
        [{'text': '📢 Опубликовать', 'callback_data': 'admin_post'},
         {'text': '📢 Каналы', 'callback_data': 'admin_channels'}],
        [{'text': '⚙️ Сервисы', 'callback_data': 'manage_services'},
         {'text': '🚫 Бан-лист', 'callback_data': 'admin_banlist'}],
        [{'text': '🎫 Промокоды', 'callback_data': 'adm_promo_list'},
         {'text': '📨 Рассылка', 'callback_data': 'adm_broadcast'}],
        [{'text': '💰 Начислить баланс', 'callback_data': 'admin_addbalance'}],
        [{'text': '👤 Личный кабинет', 'callback_data': 'cab_main'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': keyboard})
    else:
        smart_send(token, chat_id, text, reply_markup=keyboard, parse_mode='HTML')


def handle_help(cfg, chat_id):
    token = cfg['BOT_TOKEN']
    channels = get_channels()
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
    smart_send(token, chat_id, text, reply_markup=keyboard, parse_mode='HTML')




def post_to_channel(cfg, chat_id, user_id):
    """Публикует пост с кнопкой в канал"""
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    
    # Только админ
    if str(user_id) != str(admin_id):
        send_message(token, chat_id, "🚫 Команда только для админа.")
        return
    
    # Читаем текст поста
    post_file = '/etc/UDPCustom/post.txt'
    if not os.path.exists(post_file):
        send_message(token, chat_id, "❌ Файл post.txt не найден")
        return
    
    with open(post_file) as f:
        post_text = f.read().strip()
    
    # Убираем визуальный маркер кнопки из текста
    post_text = post_text.replace('[🎁 Получить тест]', '').strip()
    
    # Канал для публикации — первый из channels.txt
    channels = get_channels()
    if not channels:
        send_message(token, chat_id, "❌ Нет каналов в channels.txt")
        return
    
    # Кнопка — deep link
    bot_me = tg_request(token, 'getMe')
    bot_username = bot_me.get('result', {}).get('username', '') if bot_me else ''
    keyboard = {
        'inline_keyboard': [
            [{'text': '🎁 Получить тест', 'url': f'https://t.me/{bot_username}?start=from_channel', 'style': 'success'}]
        ]
    }
    
    # Публикуем ВО ВСЕ каналы
    success_count = 0
    errors = []
    for ch in channels:
        target_channel = ch if ch.startswith('@') else '@' + ch
        primary_clean = target_channel.lstrip('@')
        
        # Спонсоры = все КРОМЕ текущего канала
        sponsors = [c2.lstrip('@') for c2 in channels if c2.lstrip('@') != primary_clean]
        sponsors_list = ", ".join([f"@{s}" for s in sponsors]) if sponsors else "—"
        
        # Подстановка переменных
        personalized = post_text.replace('{sponsors_list}', sponsors_list)
        personalized = personalized.replace('{primary}', primary_clean)
        
        result = tg_request(token, 'sendMessage', {
            'chat_id': target_channel,
            'text': personalized,
            'reply_markup': keyboard,
            'parse_mode': 'HTML'
        })
        if result and result.get('ok'):
            success_count += 1
            log.info(f"Пост опубликован в {target_channel}")
        else:
            error = result.get('description', 'unknown') if result else 'no response'
            errors.append(f"{target_channel}: {error}")
            log.error(f"Ошибка публикации в {target_channel}: {error}")
    
    if success_count == len(channels):
        send_message(token, chat_id, f"✅ Пост опубликован во все каналы ({success_count}/{len(channels)})")
    elif success_count > 0:
        err_text = "\n".join(errors)
        send_message(token, chat_id, f"⚠️ Опубликовано в {success_count}/{len(channels)}\n\nОшибки:\n{err_text}")
    else:
        err_text = "\n".join(errors)
        send_message(token, chat_id, f"❌ Не удалось опубликовать ни в один канал\n\n{err_text}")


def handle_channel_test(cfg, user_id, first_name):
    """Обработка кнопки из КАНАЛА — проверка спонсора + выдача в личку"""
    token = cfg['BOT_TOKEN']
    
    # Проверяем чёрный список
    if is_blacklisted(user_id):
        tg_request(token, 'sendMessage', {
            'chat_id': user_id,
            'text': "🚫 Ты в чёрном списке. Обратись: @ArsenGuro"
        })
        return
    
    # Проверяем кулдаун
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        cooldown_hours = int(cfg.get('COOLDOWN_HOURS', '8'))
        ok, remaining = check_cooldown(user_id, cooldown_hours)
        if not ok:
            send_message_ttl(token, user_id, f"⏰ Ты уже получал тест. Попробуй через {format_time(remaining)}.", ttl=15)
            return
    
    # Проверяем подписку на канал СПОНСОРА (@vpnbalkan)
    channels = get_channels()
    not_sub = []
    for ch in channels:
        # Первый канал (основной) пропускаем — юзер уже там
        if ch.strip('@') in [c.strip('@') for c in channels[:1]]:
            continue
        if not check_subscription(token, user_id, ch):
            not_sub.append(ch.lstrip('@'))
    
    if not_sub:
        # Отправляем в личку — надо подписаться
        keyboard = {'inline_keyboard': []}
        for ch in not_sub:
            keyboard['inline_keyboard'].append([{'text': f'📢 {ch}', 'url': f'https://t.me/{ch}'}])
        keyboard['inline_keyboard'].append([{'text': '✅ Я подписался → Получить тест', 'callback_data': 'get_test'}])
        
        text = (
            "⚠️ Осталось подписаться на канал спонсора!\n\n"
            "👇 Подпишись и нажми кнопку ниже"
        )
        tg_request(token, 'sendMessage', {
            'chat_id': user_id,
            'text': text,
            'reply_markup': keyboard
        })
        return
    
    # Всё ОК — создаём аккаунт
    username, password = create_test_user(cfg, user_id)
    if not username:
        send_message_ttl(token, user_id, "❌ Ошибка создания. Попробуй позже.", ttl=15)
        return
    
    record_issue(user_id, username)
    _ref_test_bonus(cfg, user_id)
    
    
    domain = get_domain()
    ws_port = get_ws_port()
    proxy = get_random_proxy()
    dt_url = generate_darktunnel_url(username, password, domain, ws_port, proxy, cfg)
    traffic = cfg.get('TEST_TRAFFIC_GB', '50')
    devices = cfg.get('TEST_DEVICES', '1')
    hours = cfg.get('TEST_HOURS', '8')
    
    is_admin = str(user_id) == str(admin_id)
    
    # ─── Одно красивое сообщение ───
    text = (
        f"🎉 <b>Тестовый доступ готов!</b>\n\n"
        f"📱 Логин : <code>{username}</code>\n"
        f"🔑 Пароль: <code>{password}</code>\n"
        f"🌐 Сервер: {domain}\n"
        f"🔌 Порт  : {ws_port}\n"
    )
    if proxy:
        text += f"🛡️ Прокси: {proxy}:80\n"
    text += f"\n⏰ {hours} ч | 📊 {traffic} ГБ | 💻 {devices} устр.\n"
    
    if dt_url:
        text += f"\n🔗 <b>Ссылка-конфиг:</b>\n<code>{dt_url}</code>\n"
    
    if is_admin:
        channels = get_channels()
        ch_name = channels[0].lstrip('@') if channels else 'ArsenVipKeys'
        from datetime import datetime
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        text += f"\n━━━━━━━━━━━━━━━━━━\n"
        text += f"✅ Ключ получен с канала @{ch_name}\n"
        text += f"🕐 {now_str}\n"
    
    text += f"\n💬 @ArsenGuro\n📢 @ArsenVipKeys"
    
    # Убираем кнопку "Получить тест" из welcome-сообщения
    welcome_file = f"/etc/UDPCustom/welcome_msgs/{user_id}"
    if os.path.exists(welcome_file):
        try:
            with open(welcome_file) as f:
                w_id = int(f.read().strip())
            new_kb = {'inline_keyboard': [
                [{'text': '🔑 Мой ключ', 'callback_data': 'mykey'}],
                [
                    {'text': '💎 VIP-ключ', 'url': 'https://t.me/ArsenGuro'},
                    {'text': '💬 Поддержка', 'url': 'https://t.me/ArsenGuro'}
                ]
            ]}
            tg_request(token, 'editMessageReplyMarkup', {
                'chat_id': user_id,
                'message_id': w_id,
                'reply_markup': new_kb
            })
            os.remove(welcome_file)
        except: pass
    send_message_ttl(token, user_id, text, ttl=1800, parse_mode='HTML')
    
    # Уведомляем админа — только если это НЕ админ
    if not is_admin and admin_id:
        from datetime import datetime
        channels = get_channels()
        ch_name = channels[0].lstrip('@') if channels else 'ArsenVipKeys'
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        admin_msg = (
            f"🔔 <b>Новая выдача из канала @{ch_name}</b>\n\n"
            f"👤 Telegram: {first_name or '—'} (ID: {user_id})\n"
            f"📱 Логин : <code>{username}</code>\n"
            f"🔑 Пароль: <code>{password}</code>\n"
            f"🕐 {now_str}"
        )
        tg_request(token, 'sendMessage', {
            'chat_id': admin_id,
            'text': admin_msg,
            'parse_mode': 'HTML'
        })
    
    log.info(f"Выдан тест из канала: {username} (user_id={user_id})")


def handle_stats(cfg, chat_id, user_id, mode='keys', msg_id=None):
    """Статистика: переключение ключи/трафик"""
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        send_message(token, chat_id, "🚫 Команда только для админа.")
        return
    
    from datetime import datetime, timedelta
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0).timestamp()
    week_start = (now - timedelta(days=7)).timestamp()
    month_start = (now - timedelta(days=30)).timestamp()
    
    total = 0
    today_cnt = 0
    week_cnt = 0
    month_cnt = 0
    week_users = {}
    users_all = set()
    
    if os.path.exists(ISSUED_DB):
        with open(ISSUED_DB) as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) < 3: continue
                try: ts = int(parts[1])
                except: continue
                uid = parts[0]
                total += 1
                users_all.add(uid)
                if ts >= today_start: today_cnt += 1
                if ts >= week_start:
                    week_cnt += 1
                    week_users[uid] = week_users.get(uid, 0) + 1
                if ts >= month_start: month_cnt += 1
    
    # Активные
    active = 0
    if os.path.exists(USERS_DB):
        now_ts = int(time.time())
        with open(USERS_DB) as f:
            for u in f:
                u = u.strip()
                if not u: continue
                ts_file = f"{EXPIRE_DIR}/{u}"
                if os.path.exists(ts_file):
                    try:
                        exp = int(open(ts_file).read().strip())
                        if exp > now_ts: active += 1
                    except: pass
    
    # Топ-5 по ключам за неделю
    top_users = sorted([(u, c2) for u, c2 in week_users.items() if str(u) != str(admin_id)],
                       key=lambda x: x[1], reverse=True)[:5]
    
    # Хелпер трафика
    def human(b):
        if b >= 1073741824: return f"{b/1073741824:.1f} GB"
        if b >= 1048576: return f"{b/1048576:.0f} MB"
        if b >= 1024: return f"{b/1024:.0f} KB"
        return f"{b} B"
    
    # Топ-5 по трафику
    traffic_data = []
    traffic_dir = "/etc/UDPCustom/traffic"
    if os.path.exists(traffic_dir):
        try:
            for fname in os.listdir(traffic_dir):
                fpath = os.path.join(traffic_dir, fname)
                if not os.path.isfile(fpath): continue
                try:
                    b = int(open(fpath).read().strip())
                    if b > 0: traffic_data.append((fname, b))
                except: pass
        except: pass
    traffic_data.sort(key=lambda x: x[1], reverse=True)
    top_traffic = traffic_data[:5]
    
    # TG-ID по имени
    user_id_by_name = {}
    if os.path.exists(ISSUED_DB):
        with open(ISSUED_DB) as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 3:
                    user_id_by_name[parts[2]] = parts[0]
    
    # ─── Формируем текст в зависимости от режима ───
    if mode == 'keys':
        text = (
            f"📊 <b>СТАТИСТИКА БОТА</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📤 <b>Выдачи</b>\n"
            f"  Всего    · <b>{total}</b>\n"
            f"  Сегодня  · <b>{today_cnt}</b>\n"
            f"  7 дней   · <b>{week_cnt}</b>\n"
            f"  30 дней  · <b>{month_cnt}</b>\n\n"
            f"👥 <b>Пользователи</b>\n"
            f"  Уникальных · <b>{len(users_all)}</b>\n"
            f"  Активных   · <b>{active}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 <b>ТОП-5 ПО КЛЮЧАМ</b> · 7 дней\n\n"
        )
        if top_users:
            medals = ["🥇", "🥈", "🥉", "4.", "5."]
            for i, (u, c2) in enumerate(top_users):
                medal = medals[i] if i < len(medals) else f"{i+1}."
                text += f"  {medal} <code>{u}</code> · <b>{c2}</b>\n"
        else:
            text += "  <i>За неделю выдач не было</i>\n"
    else:
        text = (
            f"📊 <b>СТАТИСТИКА БОТА</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📈 <b>ТОП-5 ПО ТРАФИКУ</b> · за всё время\n\n"
        )
        if top_traffic:
            medals = ["🥇", "🥈", "🥉", "4.", "5."]
            for i, (name, b) in enumerate(top_traffic):
                medal = medals[i] if i < len(medals) else f"{i+1}."
                text += f"  {medal} <code>{name}</code> · <b>{human(b)}</b>\n"
        else:
            text += "  <i>Пока нет данных</i>\n"
    
    # ─── Кнопки ───
    keyboard = {'inline_keyboard': []}
    
    if mode == 'keys':
        keyboard['inline_keyboard'].append([
            {'text': '✅ 🏆 Ключи', 'callback_data': 'noop'},
            {'text': '📊 Трафик', 'callback_data': 'admin_stats_traffic'}
        ])
        # Кнопки написать для топ-ключей
        for u, c2 in top_users[:3]:
            keyboard['inline_keyboard'].append([
                {'text': f'💬 Написать {u[-4:]} ({c2})', 'url': f'tg://user?id={u}'}
            ])
    else:
        keyboard['inline_keyboard'].append([
            {'text': '🏆 Ключи', 'callback_data': 'admin_stats_keys'},
            {'text': '✅ 📊 Трафик', 'callback_data': 'noop'}
        ])
        # Кнопки написать для топ-трафика
        for name, b in top_traffic[:3]:
            uid = user_id_by_name.get(name)
            if uid:
                keyboard['inline_keyboard'].append([
                    {'text': f'💬 {name} ({human(b)})', 'url': f'tg://user?id={uid}'}
                ])
    
    keyboard['inline_keyboard'].append([{'text': '🔄 Обновить', 'callback_data': f'admin_stats_{mode}'}])
    keyboard['inline_keyboard'].append([{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}])
    
    # Отправка или редактирование
    if msg_id:
        tg_request(token, 'editMessageText', {
            'chat_id': chat_id,
            'message_id': msg_id,
            'text': text,
            'parse_mode': 'HTML',
            'reply_markup': keyboard
        })
    else:
        tg_request(token, 'sendMessage', {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'reply_markup': keyboard
        })


def handle_ban(cfg, chat_id, user_id, args):
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        send_message(token, chat_id, "🚫 Только для админа.")
        return
    if not args:
        send_message(token, chat_id, "❌ Формат: /ban 1234567890")
        return
    target = args.strip().split()[0]
    if not target.isdigit():
        send_message(token, chat_id, "❌ ID должен быть числом")
        return
    if is_blacklisted(target):
        send_message(token, chat_id, f"⚠️ {target} уже в бане")
        return
    with open(BLACKLIST, 'a') as f:
        f.write(target + "\n")
    send_message(token, chat_id, f"✅ Забанен: <code>{target}</code>", parse_mode='HTML')
    log.info(f"BAN: {target} by admin")


def handle_unban(cfg, chat_id, user_id, args):
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        return
    if not args:
        send_message(token, chat_id, "❌ Формат: /unban 1234567890")
        return
    target = args.strip().split()[0]
    if not os.path.exists(BLACKLIST):
        send_message(token, chat_id, "Список пуст")
        return
    with open(BLACKLIST) as f:
        lines = f.readlines()
    new_lines = [l for l in lines if l.strip() != target]
    if len(new_lines) == len(lines):
        send_message(token, chat_id, f"⚠️ {target} не в бане")
        return
    with open(BLACKLIST, 'w') as f:
        f.writelines(new_lines)
    send_message(token, chat_id, f"✅ Разбанен: <code>{target}</code>", parse_mode='HTML')
    log.info(f"UNBAN: {target} by admin")


def handle_banlist(cfg, chat_id, user_id, msg_id=None):
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        return
    if not os.path.exists(BLACKLIST) or os.path.getsize(BLACKLIST) == 0:
        kb = {'inline_keyboard': [[{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]]}
        if msg_id:
            tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': "📋 Чёрный список пуст", 'reply_markup': kb})
        else:
            send_message(token, chat_id, "📋 Чёрный список пуст", reply_markup=kb)
        return
    with open(BLACKLIST) as f:
        banned = [l.strip() for l in f if l.strip()]
    text = f"🚫 <b>Чёрный список ({len(banned)}):</b>\n\n"
    for b in banned[-30:]:
        text += f"  • <code>{b}</code>\n"
    kb = {'inline_keyboard': [
        [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        send_message(token, chat_id, text, reply_markup=kb, parse_mode='HTML')


VERIFIED_DB = "/etc/UDPCustom/verified_users.db"


def is_verified(user_id):
    """Проверяет, verified ли юзер СЕЙЧАС (с учётом таймаута 8ч)"""
    if not os.path.exists(VERIFIED_DB): return False
    try:
        now = int(time.time())
        with open(VERIFIED_DB) as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) < 2: continue
                if parts[0] == str(user_id):
                    try:
                        return now < int(parts[1])
                    except: return False
    except: pass
    return False


def mark_verified(user_id, hours=8):
    """Помечает юзера verified на N часов"""
    try:
        now = int(time.time())
        until = int(now + (hours * 3600))
        
        # Убираем старые записи этого юзера
        lines = []
        if os.path.exists(VERIFIED_DB):
            with open(VERIFIED_DB) as f:
                lines = [l for l in f.readlines() if not l.startswith(f"{user_id}|")]
        
        # Добавляем новую
        lines.append(f"{user_id}|{until}\n")
        
        with open(VERIFIED_DB, 'w') as f:
            f.writelines(lines)
    except Exception as e:
        log.error(f"mark_verified error: {e}")


USERS_DB = "/etc/UDPCustom/users.db"
EXPIRE_DIR = "/etc/UDPCustom/expire_ts"
LIMITS_DIR = "/etc/UDPCustom/limits"


def get_users_stats():
    """Возвращает список юзеров с инфой: (username, exp_ts, is_expired)"""
    users = []
    if not os.path.exists(USERS_DB): return users
    now = int(time.time())
    try:
        with open(USERS_DB) as f:
            for line in f:
                u = line.strip()
                if not u: continue
                ts_file = f"{EXPIRE_DIR}/{u}"
                exp_ts = 0
                if os.path.exists(ts_file):
                    try:
                        exp_ts = int(open(ts_file).read().strip())
                    except: pass
                is_expired = exp_ts > 0 and exp_ts < now
                users.append({'name': u, 'exp_ts': exp_ts, 'expired': is_expired})
    except: pass
    return users


def handle_users(cfg, chat_id, user_id, page=1, msg_id=None):
    """Список юзеров с пагинацией"""
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        send_message(token, chat_id, "🚫 Только для админа.")
        return
    
    users = get_users_stats()
    if not users:
        send_message(token, chat_id, "📋 Список пуст.")
        return
    
    per_page = 20
    total = len(users)
    total_pages = (total + per_page - 1) // per_page
    if page < 1: page = 1
    if page > total_pages: page = total_pages
    
    start = (page - 1) * per_page
    end = min(start + per_page, total)
    
    active = sum(1 for u in users if not u['expired'])
    expired = total - active
    
    text = f"👥 <b>Пользователи</b> (стр. {page}/{total_pages})\n"
    text += f"Всего: <b>{total}</b> | Активных: <b>{active}</b> | Истёкших: <b>{expired}</b>\n\n"
    
    for u in users[start:end]:
        icon = "🟢" if not u['expired'] else "🔴"
        name = u['name']
        if u['exp_ts']:
            left = u['exp_ts'] - int(time.time())
            if left > 0:
                h = left // 3600
                if h < 24:
                    time_left = f"{h}ч"
                else:
                    time_left = f"{h//24}д"
            else:
                time_left = "истёк"
        else:
            time_left = "∞"
        text += f"{icon} <code>{name}</code> — {time_left}\n"
    
    keyboard = {'inline_keyboard': []}
    nav_row = []
    if page > 1:
        nav_row.append({'text': '◀', 'callback_data': f'admin_users_{page-1}'})
    nav_row.append({'text': f'{page}/{total_pages}', 'callback_data': 'noop'})
    if page < total_pages:
        nav_row.append({'text': '▶', 'callback_data': f'admin_users_{page+1}'})
    keyboard['inline_keyboard'].append(nav_row)
    keyboard['inline_keyboard'].append([
        {'text': '➕ Добавить юзера', 'callback_data': 'admin_newuser'},
        {'text': '🗑️ Удалить истёкших', 'callback_data': 'admin_cleanup'}
    ])
    keyboard['inline_keyboard'].append([
        {'text': '🚫 Бан-лист', 'callback_data': 'admin_banlist'},
        {'text': '🔄 Обновить', 'callback_data': f'admin_users_{page}'}
    ])
    keyboard['inline_keyboard'].append([{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}])
    
    if msg_id:
        tg_request(token, 'editMessageText', {
            'chat_id': chat_id,
            'message_id': msg_id,
            'text': text,
            'reply_markup': keyboard,
            'parse_mode': 'HTML'
        })
    else:
        tg_request(token, 'sendMessage', {
            'chat_id': chat_id,
            'text': text,
            'reply_markup': keyboard,
            'parse_mode': 'HTML'
        })


def handle_cleanup(cfg, chat_id, user_id):
    """Удалить всех истёкших"""
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        send_message(token, chat_id, "🚫 Только для админа.")
        return
    
    users = get_users_stats()
    expired = [u for u in users if u['expired']]
    
    if not expired:
        send_message(token, chat_id, "✅ Нет истёкших для удаления.")
        return
    
    removed = 0
    failed = 0
    for u in expired:
        name = u['name']
        try:
            subprocess.run(['userdel', '-f', name], capture_output=True, timeout=10)
            # Удаляем следы
            for p in [f"/etc/UDPCustom/limits/{name}", f"/etc/UDPCustom/expire_ts/{name}", 
                      f"/etc/UDPCustom/traffic/{name}", f"/etc/UDPCustom/traffic_limits/{name}"]:
                try: os.remove(p)
                except: pass
            # Убираем из users.db
            subprocess.run(['sed', '-i', f'/^{name}$/d', USERS_DB], capture_output=True)
            # Убираем maxlogins
            subprocess.run(['sed', '-i', f'/^{name}\s\+hard\s\+maxlogins/d', '/etc/security/limits.conf'], capture_output=True)
            removed += 1
        except:
            failed += 1
    
    send_message(token, chat_id, f"✅ Удалено истёкших: <b>{removed}</b>\n" + (f"⚠️ Ошибок: {failed}" if failed else ""), parse_mode='HTML')
    log.info(f"CLEANUP via bot: removed={removed}, failed={failed}")


PROXIES_FILE = "/etc/UDPCustom/proxies.txt"
DOMAIN_FILE = "/etc/vpn-domain"
PAYLOAD_FILE = "/etc/UDPCustom/payload.txt"




def handle_addproxy(cfg, chat_id, user_id, args):
    """Добавить прокси: /addproxy 1.2.3.4"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    args = args.strip()
    if not args:
        send_message(token, chat_id, "📖 Формат: <code>/addproxy 1.2.3.4</code>", parse_mode='HTML'); return
    ip = args.split()[0]
    # Простая валидация IP
    if not ip.replace('.', '').isdigit() or ip.count('.') != 3:
        send_message(token, chat_id, f"❌ Неверный IP: {ip}"); return
    try:
        with open(PROXIES_FILE, 'a') as f:
            f.write(ip + "\n")
        # Сортируем и убираем дубли
        ips = sorted(set(l.strip() for l in open(PROXIES_FILE) if l.strip()))
        with open(PROXIES_FILE, 'w') as f:
            f.write("\n".join(ips) + "\n")
        send_message(token, chat_id, f"✅ Прокси добавлен: <code>{ip}</code>\nВсего: <b>{len(ips)}</b>", parse_mode='HTML')
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_delproxy(cfg, chat_id, user_id, args):
    """Удалить прокси: /delproxy 2"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    args = args.strip()
    if not args or not args.isdigit():
        send_message(token, chat_id, "📖 Формат: <code>/delproxy 2</code>", parse_mode='HTML'); return
    n = int(args)
    try:
        ips = [l.strip() for l in open(PROXIES_FILE) if l.strip()]
        if n < 1 or n > len(ips):
            send_message(token, chat_id, f"❌ Нет прокси №{n}"); return
        removed = ips.pop(n-1)
        with open(PROXIES_FILE, 'w') as f:
            f.write("\n".join(ips) + "\n" if ips else "")
        send_message(token, chat_id, f"✅ Удалён: <code>{removed}</code>\nОсталось: <b>{len(ips)}</b>", parse_mode='HTML')
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_proxies(cfg, chat_id, user_id):
    """Список прокси"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    try:
        if not os.path.exists(PROXIES_FILE):
            send_message(token, chat_id, "❌ Файл proxies.txt не найден"); return
        ips = [l.strip() for l in open(PROXIES_FILE) if l.strip()]
        if not ips:
            send_message(token, chat_id, "📋 Список прокси пуст"); return
        text = f"🔒 <b>Прокси ({len(ips)}):</b>\n\n"
        for i, ip in enumerate(ips, 1):
            text += f"<b>{i}.</b> <code>{ip}</code>\n"
        text += f"\n<i>Добавить: /addproxy IP\nУдалить: /delproxy N</i>"
        send_message(token, chat_id, text, parse_mode='HTML')
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_setdomain(cfg, chat_id, user_id, args):
    """Изменить домен: /setdomain de.example.com"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    d = args.strip().replace('https://', '').replace('http://', '').split('/')[0].split(':')[0]
    if not d or '.' not in d:
        send_message(token, chat_id, "📖 Формат: <code>/setdomain de.example.com</code>", parse_mode='HTML'); return
    try:
        with open(DOMAIN_FILE, 'w') as f:
            f.write(d + "\n")
        send_message(token, chat_id, f"✅ Домен изменён: <code>{d}</code>", parse_mode='HTML')
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_domain(cfg, chat_id, user_id):
    """Показать текущий домен"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    try:
        d = open(DOMAIN_FILE).read().strip() if os.path.exists(DOMAIN_FILE) else "не задан"
        send_message(token, chat_id, f"🌐 <b>Домен:</b> <code>{d}</code>\n\n<i>Изменить: /setdomain new.domain.com</i>", parse_mode='HTML')
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_setpayload(cfg, chat_id, user_id, args):
    """Изменить payload"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    pl = args.strip()
    if not pl:
        send_message(token, chat_id, "📖 Формат: <code>/setpayload CONNECT http://...</code>", parse_mode='HTML'); return
    try:
        with open(PAYLOAD_FILE, 'w') as f:
            f.write(pl + "\n")
        send_message(token, chat_id, f"✅ Payload изменён ({len(pl)} символов)")
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_payload(cfg, chat_id, user_id):
    """Показать payload"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    try:
        pl = open(PAYLOAD_FILE).read().strip() if os.path.exists(PAYLOAD_FILE) else "не задан"
        text = f"📦 <b>Payload ({len(pl)} символов):</b>\n\n<code>{pl}</code>\n\n<i>Изменить: /setpayload ...</i>"
        send_message(token, chat_id, text, parse_mode='HTML')
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_services(cfg, chat_id, user_id, msg_id=None):
    """SSH WS управление: статус + кнопки"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    
    import subprocess
    services = ['ws-proxy', 'masterdnsvpn', 'udp-custom', 'udpgw']
    text = "⚙️ <b>SSH WS УПРАВЛЕНИЕ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "<b>Статус сервисов:</b>\n"
    for s in services:
        try:
            r = subprocess.run(['systemctl', 'is-active', s], capture_output=True, text=True, timeout=3)
            status = r.stdout.strip()
            icon = "🟢" if status == "active" else "🔴"
            text += f"  {icon} <code>{s}</code> — {status}\n"
        except:
            text += f"  ❓ <code>{s}</code> — unknown\n"
    
    try:
        d = open(DOMAIN_FILE).read().strip() if os.path.exists(DOMAIN_FILE) else "—"
    except: d = "—"
    try:
        ips = [l.strip() for l in open(PROXIES_FILE) if l.strip()] if os.path.exists(PROXIES_FILE) else []
        proxy_cnt = len(ips)
    except: proxy_cnt = 0
    try:
        pl = open(PAYLOAD_FILE).read().strip() if os.path.exists(PAYLOAD_FILE) else ""
        pl_len = len(pl)
    except: pl_len = 0
    
    text += f"\n<b>Текущие настройки:</b>\n"
    text += f"  🌐 Домен: <code>{d}</code>\n"
    text += f"  🔒 Прокси: <b>{proxy_cnt}</b> шт.\n"
    text += f"  📦 Payload: <b>{pl_len}</b> симв.\n"
    
    keyboard = {'inline_keyboard': [
        [{'text': '🌐 Домен', 'callback_data': 'manage_domain'},
         {'text': '🔒 Прокси', 'callback_data': 'manage_proxies'},
         {'text': '📦 Payload', 'callback_data': 'manage_payload'}],
        [{'text': '🔄 Перезапустить WS', 'callback_data': 'restart_ws'}],
        [{'text': '🔄 Обновить', 'callback_data': 'manage_services'}],
        [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
    ]}
    
    if msg_id:
        tg_request(token, 'editMessageText', {
            'chat_id': chat_id,
            'message_id': msg_id,
            'text': text,
            'parse_mode': 'HTML',
            'reply_markup': keyboard
        })
    else:
        tg_request(token, 'sendMessage', {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'reply_markup': keyboard
        })


def handle_restart(cfg, chat_id, user_id, args):
    """Перезапуск сервиса: /restart ws-proxy"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    s = args.strip()
    if not s:
        send_message(token, chat_id, "📖 Сервисы: <code>ws-proxy</code>, <code>masterdnsvpn</code>, <code>udp-custom</code>, <code>udpgw</code>", parse_mode='HTML'); return
    allowed = ['ws-proxy', 'masterdnsvpn', 'udp-custom', 'udpgw']
    if s not in allowed:
        send_message(token, chat_id, f"❌ Сервис <code>{s}</code> не разрешён", parse_mode='HTML'); return
    import subprocess
    try:
        subprocess.run(['systemctl', 'restart', s], capture_output=True, timeout=10)
        send_message(token, chat_id, f"✅ Перезапущен: <code>{s}</code>", parse_mode='HTML')
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка: {e}")


CHANNELS_FILE = "/etc/UDPCustom/channels.txt"


def handle_channels(cfg, chat_id, user_id, msg_id=None):
    """Список каналов с ролями"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    
    channels = get_channels()
    if not channels:
        kb = {'inline_keyboard': [[{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]]}
        if msg_id:
            tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': "📢 <b>Каналов нет.</b>\n\n<i>Добавить: /addchannel @name</i>", 'reply_markup': kb, 'parse_mode': 'HTML'})
        else:
            send_message(token, chat_id, "📢 <b>Каналов нет.</b>\n\n<i>Добавить: /addchannel @name</i>", reply_markup=kb, parse_mode='HTML')
        return
    
    text = f"📢 <b>Каналы ({len(channels)}):</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, ch in enumerate(channels, 1):
        ch_clean = ch.lstrip('@')
        if i == 1:
            text += f"<b>{i}.</b> <code>@{ch_clean}</code> — 🎯 <b>Основной</b>\n"
        else:
            text += f"<b>{i}.</b> <code>@{ch_clean}</code> — 📢 Спонсор\n"
    
    text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"<i>Добавить: /addchannel @name</i>\n"
    text += f"<i>Удалить: /delchannel N</i>"
    kb = {'inline_keyboard': [
        [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        send_message(token, chat_id, text, reply_markup=kb, parse_mode='HTML')
    


PENDING_ACTIONS = {}


def handle_addchannel(cfg, chat_id, user_id, args):
    """Добавить канал: /addchannel @name ИЛИ через ForceReply"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    
    args = args.strip()
    
    # Если аргумент НЕ передан — просим через ForceReply
    if not args:
        PENDING_ACTIONS[user_id] = 'addchannel'
        tg_request(token, 'sendMessage', {
            'chat_id': chat_id,
            'text': "📢 <b>Отправь username канала</b>\n\nПример: <code>@MyChannel</code>\n\n<i>Ответь на это сообщение (свайп влево)</i>",
            'parse_mode': 'HTML',
            'reply_markup': {'force_reply': True, 'selective': True}
        })
        return
    
    # Есть аргумент — обрабатываем сразу
    _do_addchannel(token, chat_id, args)


def _do_addchannel(token, chat_id, args):
    """Внутренняя: добавляет канал"""
    ch = args.strip().split()[0]
    if not ch.startswith('@'):
        ch = '@' + ch
    
    # Проверяем через Telegram API
    test = tg_request(token, 'getChat', {'chat_id': ch})
    if not test or not test.get('ok'):
        err = test.get('description', 'unknown') if test else 'no response'
        send_message(token, chat_id, f"❌ Не удалось получить канал: {err}\n\nУбедись что:\n• Username правильный\n• Бот добавлен в канал")
        return
    
    try:
        channels = get_channels()
        if ch in channels:
            send_message(token, chat_id, f"⚠️ Канал {ch} уже в списке"); return
        
        with open(CHANNELS_FILE, 'a') as f:
            f.write(ch + "\n")
        channels.append(ch)
        send_message(token, chat_id, f"✅ Добавлен канал: <code>{ch}</code>\nВсего: <b>{len(channels)}</b>\n\n⚠️ Не забудь сделать бота админом!", parse_mode='HTML')
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_delchannel(cfg, chat_id, user_id, args):
    """Удалить канал: /delchannel N ИЛИ через ForceReply"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    
    args = args.strip()
    
    if not args:
        PENDING_ACTIONS[user_id] = 'delchannel'
        tg_request(token, 'sendMessage', {
            'chat_id': chat_id,
            'text': "🗑️ <b>Отправь номер канала для удаления</b>\n\nПосмотреть: /channels\n\n<i>Ответь на это сообщение</i>",
            'parse_mode': 'HTML',
            'reply_markup': {'force_reply': True, 'selective': True}
        })
        return
    
    _do_delchannel(token, chat_id, args)


def _do_delchannel(token, chat_id, args):
    """Внутренняя: удаляет канал"""
    if not args.isdigit():
        send_message(token, chat_id, "❌ Номер должен быть числом"); return
    
    n = int(args)
    try:
        channels = get_channels()
        if n < 1 or n > len(channels):
            send_message(token, chat_id, f"❌ Нет канала №{n}"); return
        
        removed = channels.pop(n-1)
        with open(CHANNELS_FILE, 'w') as f:
            for ch in channels:
                f.write(ch + "\n")
        send_message(token, chat_id, f"✅ Удалён: <code>{removed}</code>\nОсталось: <b>{len(channels)}</b>", parse_mode='HTML')
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_mykey(cfg, chat_id, user_id):
    """Показать последний активный ключ юзера"""
    token = cfg['BOT_TOKEN']
    
    # Ищем последний ключ в bot_issued.db
    if not os.path.exists(ISSUED_DB):
        send_message_ttl(token, chat_id, "🔑 У тебя нет активных ключей.\n\nПолучи тест через /start", ttl=30)
        return
    
    last_username = None
    last_ts = 0
    try:
        with open(ISSUED_DB) as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) < 3: continue
                if parts[0] == str(user_id):
                    try:
                        ts = int(parts[1])
                        if ts > last_ts:
                            last_ts = ts
                            last_username = parts[2]
                    except: pass
    except: pass
    
    if not last_username:
        send_message_ttl(token, chat_id, "🔑 У тебя нет активных ключей.\n\nПолучи тест через /start", ttl=30)
        return
    
    # Проверяем что не истёк
    ts_file = f"/etc/UDPCustom/expire_ts/{last_username}"
    if os.path.exists(ts_file):
        try:
            exp_ts = int(open(ts_file).read().strip())
            if exp_ts < int(time.time()):
                send_message_ttl(token, chat_id, f"⏰ Твой ключ <code>{last_username}</code> истёк.\n\nПолучи новый тест через /start", ttl=30, parse_mode='HTML')
                return
        except: pass
    
    # Читаем пароль
    pwd_file = f"/etc/UDPCustom/passwords/{last_username}"
    if not os.path.exists(pwd_file):
        send_message_ttl(token, chat_id,
            f"⚠️ <b>Информация о пароле недоступна</b>\n\n"
            f"Логин: <code>{last_username}</code>\n\n"
            f"Это старый ключ (до обновления).\n"
            f"Получи новый тест через /start 👇",
            ttl=30, parse_mode='HTML')
        return
    
    try:
        password = open(pwd_file).read().strip()
    except:
        send_message_ttl(token, chat_id, "❌ Ошибка чтения пароля", ttl=30)
        return
    
    # Формируем данные
    domain = get_domain()
    ws_port = get_ws_port()
    proxy = get_random_proxy()
    dt_url = generate_darktunnel_url(last_username, password, domain, ws_port, proxy, cfg)
    
    # Остаток времени
    if os.path.exists(ts_file):
        try:
            exp_ts = int(open(ts_file).read().strip())
            left = exp_ts - int(time.time())
            if left > 0:
                h = left // 3600
                m = (left % 3600) // 60
                time_left = f"{h}ч {m}мин"
            else:
                time_left = "истёк"
        except:
            time_left = "?"
    else:
        time_left = "?"
    
    text = (
        f"🔑 <b>Твой последний ключ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 Логин: <code>{last_username}</code>\n"
        f"🔑 Пароль: <code>{password}</code>\n"
        f"🌐 Сервер: {domain}\n"
        f"🔌 Порт: {ws_port}\n"
    )
    if proxy:
        text += f"🛡️ Прокси: {proxy}:80\n"
    text += f"⏰ Осталось: {time_left}\n"
    if dt_url:
        text += f"\n🔗 <b>Ссылка-конфиг:</b>\n<code>{dt_url}</code>"
    
    send_message_ttl(token, chat_id, text, ttl=1800, parse_mode='HTML')


def main():
    cfg = load_config()
    if not cfg.get('BOT_TOKEN'):
        log.error("BOT_TOKEN не задан"); sys.exit(1)
    # Команды для ВСЕХ юзеров
    tg_request(cfg['BOT_TOKEN'], 'setMyCommands', {'commands': [
        {'command': 'start', 'description': '👋 Начать'},
        {'command': 'cabinet', 'description': '👤 Личный кабинет'},
        {'command': 'help', 'description': '📖 Как получить ключ'}
    ]})
    
    # Команды ТОЛЬКО для админа (scope: chat)
    admin_id = cfg.get('ADMIN_ID', '')
    if admin_id:
        tg_request(cfg['BOT_TOKEN'], 'setMyCommands', {
            'commands': [
                {'command': 'start', 'description': '👋 Начать'},
                {'command': 'admin', 'description': '⚙️ Админ-панель'},
                {'command': 'cabinet', 'description': '👤 Личный кабинет'},
                {'command': 'help', 'description': '📖 Справка'}
            ],
            'scope': {'type': 'chat', 'chat_id': int(admin_id)}
        })
    
    # Запускаем автопостинг
    start_autopost_thread(cfg['BOT_TOKEN'], {})
    log.info("Autopost поток запущен")
    
    log.info("━━━ VPN Telegram Bot запущен ━━━")
    log.info(f"Token: ...{cfg['BOT_TOKEN'][-8:]}")
    tg_request(cfg['BOT_TOKEN'], 'deleteWebhook')
    offset = 0
    while True:
        try:
            updates = tg_request(cfg['BOT_TOKEN'], 'getUpdates', {'offset': offset, 'timeout': 30, 'allowed_updates': ['message', 'callback_query']})
            if not updates or not updates.get('ok'): time.sleep(3); continue
            for upd in updates.get('result', []):
                offset = upd['update_id'] + 1
                if 'callback_query' in upd:
                    cb = upd['callback_query']
                    cb_data = cb.get('data', '')
                    cb_user_id = cb['from']['id']
                    cb_first_name = cb['from'].get('first_name', '')
                    cb_chat_type = cb['message']['chat']['type']

                    # Кнопка из КАНАЛА → popup + выдача в личку
                    if cb_data == 'channel_test':
                        bot_me = tg_request(cfg['BOT_TOKEN'], 'getMe')
                        bot_username = bot_me.get('result', {}).get('username', 'ArsenVipKeysBot') if bot_me else 'ArsenVipKeysBot'
                        popup_text = '✅ Запрос принят!\n\n📱 Открой @' + bot_username + ' — там твой ключ или кнопка «Подписаться»'
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                            'callback_query_id': cb['id'],
                            'text': popup_text,
                            'show_alert': True,
                            'cache_time': 3
                        })
                        handle_channel_test(cfg, cb_user_id, cb_first_name)
                    # Админ-кнопки
                    elif cb_data == 'adm_main':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_admin_panel(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data == 'adm_newpromo':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        PENDING_ACTIONS[cb_user_id] = 'newpromo'
                        NLx = chr(10)
                        instr = NLx.join([
                            '🎫 <b>СОЗДАНИЕ ПРОМОКОДА</b>',
                            '━━━━━━━━━━━━━━━━━━━━',
                            '',
                            'Формат:',
                            '<code>CODE ДНЕЙ АКТИВАЦИЙ [ДАТА]</code>',
                            '',
                            'CODE — A-Z, 0-9, от 3 символов',
                            'ДНЕЙ — на сколько дней продлевает',
                            'АКТИВАЦИЙ — сколько юзеров могут активировать',
                            'ДАТА — необязательно (YYYY-MM-DD)',
                            '',
                            'Примеры:',
                            '<code>NEWYEAR 3 100</code>',
                            '<code>SUMMER 7 50 2026-12-31</code>',
                            '',
                            'Отправь ответ на это сообщение 👇'
                        ])
                        smart_send(cfg['BOT_TOKEN'], cb['message']['chat']['id'], instr, reply_markup={'force_reply': True, 'selective': True}, parse_mode='HTML')
                        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                            'chat_id': cb['message']['chat']['id'],
                            'text': '<i>Передумал? Жми кнопку ниже</i>',
                            'parse_mode': 'HTML',
                            'reply_markup': {'inline_keyboard': [
                                [{'text': '⬅️ Отмена', 'callback_data': 'adm_main'}]
                            ]}
                        })
                    elif cb_data == 'adm_promo_list':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_promo_list(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data.startswith('adm_promo_del:'):
                        code = cb_data.split(':', 1)[1]
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        NLx = chr(10)
                        text = NLx.join([
                            '🗑 <b>УДАЛИТЬ ПРОМОКОД ' + code + '?</b>',
                            '',
                            'Действие необратимо.'
                        ])
                        kb = {'inline_keyboard': [
                            [{'text': '✅ Да, удалить', 'callback_data': 'adm_promo_delok:' + code}],
                            [{'text': '⬅️ Отмена', 'callback_data': 'adm_promo_list'}]
                        ]}
                        tg_request(cfg['BOT_TOKEN'], 'editMessageText', {
                            'chat_id': cb['message']['chat']['id'],
                            'message_id': cb['message']['message_id'],
                            'text': text,
                            'parse_mode': 'HTML',
                            'reply_markup': kb
                        })
                    elif cb_data.startswith('adm_promo_delok:'):
                        code = cb_data.split(':', 1)[1]
                        try:
                            from bot_modules import db as _db
                            _db.execute('DELETE FROM promo_codes WHERE code=?', (code,))
                            tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                                'callback_query_id': cb['id'],
                                'text': '✅ ' + code + ' удалён'
                            })
                        except Exception as e:
                            tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                                'callback_query_id': cb['id'],
                                'text': '❌ Ошибка: ' + str(e)
                            })
                        show_promo_list(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data == 'adm_broadcast':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id'], 'text': '🚧 В разработке'})
                    elif cb_data == 'admin_addbalance':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        PENDING_ACTIONS[cb_user_id] = 'addbalance'
                        NLx = chr(10)
                        instr = NLx.join([
                            '💰 <b>НАЧИСЛЕНИЕ БАЛАНСА</b>',
                            '━━━━━━━━━━━━━━━━━━━━',
                            '',
                            'Формат:',
                            '<code>ID СУММА [КОММЕНТАРИЙ]</code>',
                            '',
                            'ID — Telegram ID юзера',
                            'СУММА — USDT (можно с минусом для списания)',
                            'КОММЕНТАРИЙ — необязательно',
                            '',
                            'Примеры:',
                            '<code>1738878748 5</code>',
                            '<code>1738878748 -3 штраф</code>',
                            '<code>1738878748 10 бонус за активность</code>',
                            '',
                            'Отправь ответ на это сообщение 👇'
                        ])
                        smart_send(cfg['BOT_TOKEN'], cb['message']['chat']['id'], instr,
                                   reply_markup={'force_reply': True, 'selective': True},
                                   parse_mode='HTML')
                    elif cb_data == 'admin_stats':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_stats(cfg, cb['message']['chat']['id'], cb_user_id, 'keys', cb['message']['message_id'])
                    elif cb_data == 'admin_stats_keys':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_stats(cfg, cb['message']['chat']['id'], cb_user_id, 'keys', cb['message']['message_id'])
                    elif cb_data == 'admin_stats_traffic':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_stats(cfg, cb['message']['chat']['id'], cb_user_id, 'traffic', cb['message']['message_id'])
                    elif cb_data == 'admin_banlist':
                        handle_banlist(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data == 'admin_post':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        # Подменю управления постом
                        ap = load_autopost_config()
                        status = "🟢 Вкл" if ap.get('ENABLED') == '1' else "🔴 Выкл"
                        mode = ap.get('MODE', 'interval')
                        if mode == 'time':
                            mode_str = f"📅 {ap.get('TIMES', '—')}"
                        else:
                            mode_str = f"⏰ Каждые {ap.get('INTERVAL_HOURS', '12')}ч"
                        
                        text = (
                            f"📢 <b>УПРАВЛЕНИЕ ПОСТОМ</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"Автопостинг: <b>{status}</b>\n"
                            f"Режим: <b>{mode_str}</b>\n\n"
                            f"Выбери действие 👇"
                        )
                        keyboard = {'inline_keyboard': [
                            [{'text': '📤 Опубликовать сейчас', 'callback_data': 'post_now'}],
                            [
                                {'text': '▶️ Включить', 'callback_data': 'autopost_on'},
                                {'text': '⏸️ Выключить', 'callback_data': 'autopost_off'}
                            ],
                            [
                                {'text': '⏰ Каждые 6ч', 'callback_data': 'autopost_6'},
                                {'text': '⏰ Каждые 12ч', 'callback_data': 'autopost_12'}
                            ],
                            [{'text': '📅 Настроить время', 'callback_data': 'autopost_time'}],
                            [{'text': '🔄 Обновить', 'callback_data': 'admin_post'}],
                            [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
                        ]}
                        smart_send(cfg['BOT_TOKEN'], cb['message']['chat']['id'], text, reply_markup=keyboard, parse_mode='HTML')
                    elif cb_data == 'post_now':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        post_to_channel(cfg, cb['message']['chat']['id'], cb_user_id)
                    elif cb_data == 'autopost_on':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id'], 'text': '✅ Включено'})
                        handle_autopost(cfg, cb['message']['chat']['id'], cb_user_id, 'on')
                    elif cb_data == 'autopost_off':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id'], 'text': '⏸️ Выключено'})
                        handle_autopost(cfg, cb['message']['chat']['id'], cb_user_id, 'off')
                    elif cb_data == 'autopost_6':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id'], 'text': '⏰ 6 часов'})
                        handle_autopost(cfg, cb['message']['chat']['id'], cb_user_id, 'every 6')
                    elif cb_data == 'autopost_12':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id'], 'text': '⏰ 12 часов'})
                        handle_autopost(cfg, cb['message']['chat']['id'], cb_user_id, 'every 12')
                    elif cb_data == 'autopost_time':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                            'chat_id': cb['message']['chat']['id'],
                            'text': "📅 <b>Отправь время через запятую:</b>\n\nПример: <code>/autopost time 10:00,22:00</code>",
                            'parse_mode': 'HTML'
                        })
                    elif cb_data == 'manage_services':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_services(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data == 'manage_domain':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_domain(cfg, cb['message']['chat']['id'], cb_user_id)
                    elif cb_data == 'manage_proxies':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_proxies(cfg, cb['message']['chat']['id'], cb_user_id)
                    elif cb_data == 'manage_payload':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_payload(cfg, cb['message']['chat']['id'], cb_user_id)
                    elif cb_data == 'restart_ws':
                        import subprocess as _sp
                        try:
                            _sp.run(['systemctl', 'restart', 'ws-proxy'], capture_output=True, timeout=10)
                            tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                                'callback_query_id': cb['id'],
                                'text': '✅ ws-proxy перезапущен',
                                'show_alert': True
                            })
                        except Exception as e:
                            tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                                'callback_query_id': cb['id'],
                                'text': f'❌ Ошибка: {e}',
                                'show_alert': True
                            })
                    elif cb_data == 'admin_channels':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_channels(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data == 'admin_manage':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                            'callback_query_id': cb['id']
                        })
                        manage_text = (
                            "⚙️ <b>Управление сервером</b>\n\n"
                            "<b>🔒 Прокси:</b>\n"
                            "<code>/proxies</code> — список\n"
                            "<code>/addproxy 1.2.3.4</code> — добавить\n"
                            "<code>/delproxy 2</code> — удалить №2\n\n"
                            "<b>🌐 Домен:</b>\n"
                            "<code>/domain</code> — показать\n"
                            "<code>/setdomain de.example.com</code> — изменить\n\n"
                            "<b>📦 Payload:</b>\n"
                            "<code>/payload</code> — показать\n"
                            "<code>/setpayload CONNECT ...</code> — изменить\n\n"
                            "<b>⚙️ Сервисы:</b>\n"
                            "<code>/services</code> — статус\n"
                            "<code>/restart ws-proxy</code> — перезапуск\n\n"
                            "<b>👥 Пользователи:</b>\n"
                            "<code>/users</code> — список\n"
                            "<code>/cleanup</code> — удалить истёкших\n\n"
                            "<b>🚫 Модерация:</b>\n"
                            "<code>/ban 123</code> | <code>/unban 123</code> | <code>/banlist</code>"
                        )
                        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                            'chat_id': cb['message']['chat']['id'],
                            'text': manage_text,
                            'parse_mode': 'HTML'
                        })
                    elif cb_data == 'mykey':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_mykey(cfg, cb['message']['chat']['id'], cb_user_id)
                    elif cb_data.startswith('cab_vip_confirm:'):
                        try:
                            idx = int(cb_data.split(':', 1)[1])
                        except:
                            idx = 1
                        _do_vip_purchase(cfg, cb, cb_user_id, idx)
                        continue
                    elif cb_data.startswith('cab_'):
                        handle_cabinet_callback(cfg, cb_data, cb, cb_user_id, cb_first_name)
                        continue
                    elif cb_data == 'admin_newuser':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        instructions = (
                            "➕ <b>СОЗДАНИЕ ЮЗЕРА</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━\n\n"
                            "Отправь команду одной строкой:\n\n"
                            "<code>/newuser логин пароль дни устройства ГБ</code>\n\n"
                            "<b>Пример:</b>\n"
                            "<code>/newuser test1 pass123 30 5 100</code>\n\n"
                            "<b>Параметры:</b>\n"
                            "  📱 Логин — 2-20 символов\n"
                            "  🔑 Пароль — любой\n"
                            "  ⏰ Дни — 0 = бессрочно\n"
                            "  📱 Устройства — число\n"
                            "  📊 ГБ — 0 = без лимита"
                        )
                        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                            'chat_id': cb['message']['chat']['id'],
                            'text': instructions,
                            'parse_mode': 'HTML'
                        })
                    elif cb_data == 'admin_cleanup':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                            'callback_query_id': cb['id'],
                            'text': '🗑️ Удаляем истёкших...',
                            'show_alert': False
                        })
                        handle_cleanup(cfg, cb['message']['chat']['id'], cb_user_id)
                    elif cb_data.startswith('admin_users_'):
                        pg = cb_data.replace('admin_users_', '')
                        try: pg = int(pg)
                        except: pg = 1
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                            'callback_query_id': cb['id']
                        })
                        handle_users(cfg, cb['message']['chat']['id'], cb_user_id, pg, cb['message']['message_id'])
                    elif cb_data == 'noop':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                            'callback_query_id': cb['id']
                        })
                    # Юзер нажал "Я зашёл и поставил реакцию"
                    elif cb_data == 'check_verified':
                        channels = get_channels()
                        not_sub = []
                        for ch in channels:
                            if not check_subscription(cfg['BOT_TOKEN'], cb_user_id, ch):
                                not_sub.append(ch.lstrip('@'))
                        if not_sub:
                            # Показываем alert (popup) вместо нового сообщения
                            channels_list = ", ".join([f"@{ch}" for ch in not_sub])
                            tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                                'callback_query_id': cb['id'],
                                'text': f'❌ Ты ещё не подписался на: {channels_list}\n\nПодпишись и нажми кнопку ещё раз.',
                                'show_alert': True
                            })
                        else:
                            # Подписан — но verified НЕ ставим
                            # Verified ставится только через deep-link из поста
                            tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                                'callback_query_id': cb['id'],
                                'text': '✅ Подписка есть! Теперь зайди в канал и нажми кнопку под постом.',
                                'show_alert': True
                            })
                            handle_start(cfg, cb['message']['chat']['id'], cb_user_id, cb_first_name, False)
                    # Кнопка из ЛИЧКИ → обычный /test
                    elif cb_data == 'get_test':
                        handle_test(cfg, cb['message']['chat']['id'], cb_user_id, cb_first_name, cb['id'])
                    else:
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                    continue
                if 'message' not in upd: continue
                msg = upd['message']; chat_id = msg['chat']['id']; user_id = msg['from']['id']; first_name = msg['from'].get('first_name','')
                text = msg.get('text','')
                
                # Обработка ввода промокода
                try:
                    from bot_modules import db as _db
                    pending = _db.get_pending(user_id)
                except: pending = None
                if pending == 'topup_amount' and text and not text.startswith('/'):
                    _db.clear_pending(user_id)
                    # Парсим сумму
                    try:
                        amount = float(text.strip().replace(',', '.'))
                    except:
                        send_message(cfg['BOT_TOKEN'], chat_id, "❌ Отправь число. Например: <code>10</code>", parse_mode='HTML')
                        continue
                    if amount < 1:
                        send_message(cfg['BOT_TOKEN'], chat_id, "❌ Минимум 1 USDT")
                        continue
                    if amount > 10000:
                        send_message(cfg['BOT_TOKEN'], chat_id, "❌ Слишком большая сумма. Максимум 10000 USDT")
                        continue

                    # Отправляем заявку админу
                    user = _db.get_user(user_id) or {}
                    admin_id = cfg.get('ADMIN_ID', '')
                    balance = _db.get_balance(user_id)
                    first_name = user.get('first_name') or '—'
                    username = user.get('username') or ''
                    NLx = chr(10)
                    admin_msg = NLx.join([
                        "💵 <b>ЗАЯВКА НА ПОПОЛНЕНИЕ</b>",
                        "━━━━━━━━━━━━━━━━━━━━",
                        "",
                        f"👤 Имя: <b>{first_name}</b>",
                        f"🆔 ID: <code>{user_id}</code>",
                        f"📱 Username: @{username}" if username else "📱 Username: —",
                        f"💰 Текущий баланс: <b>{balance:.2f} USDT</b>",
                        "",
                        f"💵 Хочет пополнить: <b>{amount:.2f} USDT</b>",
                        "",
                        "━━━━━━━━━━━━━━━━━━━━",
                        f"Начислить: /admin → 💰 Начислить баланс",
                        f"Ввести: <code>{user_id} {amount:.2f}</code>"
                    ])
                    kb_admin = {'inline_keyboard': [
                        [{'text': '💰 Начислить баланс', 'callback_data': 'admin_addbalance'}]
                    ]}
                    try:
                        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                            'chat_id': admin_id,
                            'text': admin_msg,
                            'parse_mode': 'HTML',
                            'reply_markup': kb_admin
                        })
                    except Exception as e:
                        log.error(f"topup admin send: {e}")

                    # Подтверждение юзеру
                    NLx2 = chr(10)
                    ok_text = NLx2.join([
                        "✅ <b>ЗАЯВКА ОТПРАВЛЕНА</b>",
                        "",
                        f"Сумма: <b>{amount:.2f} USDT</b>",
                        "",
                        "Админ получил заявку и свяжется с тобой.",
                        "Если долго нет ответа — напиши @ArsenGuro"
                    ])
                    send_message(cfg['BOT_TOKEN'], chat_id, ok_text, parse_mode='HTML')
                    continue

                if pending == 'promo_input' and text and not text.startswith('/'):
                    _db.clear_pending(user_id)
                    code = text.strip()
                    ok, reason, value = _db.use_promo(code, user_id)
                    if ok:
                        # Продление = value дней
                        msg_text = (f"🎉 <b>ПРОМОКОД АКТИВИРОВАН!</b>\n\n"
                                    f"Код: <code>{code}</code>\n"
                                    f"Бонус: <b>+{int(value)} дней</b> к VIP-ключу\n\n"
                                    f"Проверь свои ключи в /cabinet")
                    else:
                        reasons = {
                            'not_found': '❌ Промокод не найден',
                            'expired': '⏰ Промокод истёк',
                            'exhausted': '🚫 Промокод больше не действует',
                            'already_used': '⚠️ Ты уже использовал этот промокод',
                            'no_vip_key': '⚠️ У тебя нет активного VIP-ключа.\n\nПромокод даёт дни только к VIP. Купи VIP: @ArsenGuro'
                        }
                        msg_text = reasons.get(reason, '❌ Ошибка активации')
                    send_message(cfg['BOT_TOKEN'], chat_id, msg_text, parse_mode='HTML')
                    continue

                # Обработка ответа на ForceReply
                if user_id in PENDING_ACTIONS and msg.get('reply_to_message'):
                    action = PENDING_ACTIONS.pop(user_id)
                    if action == 'addchannel':
                        _do_addchannel(cfg['BOT_TOKEN'], chat_id, text)
                    elif action == 'delchannel':
                        _do_delchannel(cfg['BOT_TOKEN'], chat_id, text)
                    elif action == 'newpromo':
                        _do_newpromo(cfg, chat_id, text)
                    elif action == 'addbalance':
                        _do_addbalance(cfg, chat_id, text)
                    continue
                if text.startswith('/start'):
                    # Обработка реферальной ссылки
                    import re as _re
                    ref_match = _re.search(r'ref_([a-zA-Z0-9]+)', text)
                    if ref_match:
                        ref_code = ref_match.group(1)
                        try:
                            from bot_modules import db as _db
                            # Сначала создаём/обновляем юзера
                            _db.upsert_user(user_id, first_name, msg['from'].get('username', ''))
                            inviter = _db.find_by_ref_code(ref_code)
                            if inviter and str(inviter['tg_id']) != str(user_id):
                                if _db.set_ref_by(user_id, inviter['tg_id']):
                                    log.info(f"Referral: {user_id} → {inviter['tg_id']} (code={ref_code})")
                                    # Уведомляем пригласившего
                                    try:
                                        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                                            'chat_id': inviter['tg_id'],
                                            'text': f"👥 <b>НОВЫЙ РЕФЕРАЛ!</b>\n\nПо твоей ссылке пришёл новый юзер.\n\nПолучишь <b>+3 дня</b> когда он получит тест и <b>+1 USDT</b> когда купит VIP.",
                                            'parse_mode': 'HTML'
                                        })
                                    except: pass
                        except Exception as e:
                            log.error(f"ref_ error: {e}")
                    # Проверяем deep link параметр (пришёл из канала)
                    if 'from_channel' in text:
                        mins = int(cfg.get('VERIFIED_MINUTES', '60'))
                        hours = mins / 60
                        mark_verified(user_id, hours)
                        log.info(f"Юзер {user_id} verified через канал (на {hours}ч)")
                        handle_start(cfg, chat_id, user_id, first_name, True)
                    else:
                        handle_start(cfg, chat_id, user_id, first_name)
                elif text.startswith('/test'): handle_test(cfg, chat_id, user_id, first_name)
                elif text.startswith('/post'): post_to_channel(cfg, chat_id, user_id)
                elif text.startswith('/stats'): handle_stats(cfg, chat_id, user_id)
                elif text.startswith('/banlist'): handle_banlist(cfg, chat_id, user_id)
                elif text.startswith('/unban'): handle_unban(cfg, chat_id, user_id, text[6:].strip())
                elif text.startswith('/ban'): handle_ban(cfg, chat_id, user_id, text[4:].strip())
                elif text.startswith('/users'): handle_users(cfg, chat_id, user_id, 1)
                elif text.startswith('/cleanup'): handle_cleanup(cfg, chat_id, user_id)
                elif text.startswith('/addproxy'): handle_addproxy(cfg, chat_id, user_id, text[9:].strip())
                elif text.startswith('/delproxy'): handle_delproxy(cfg, chat_id, user_id, text[9:].strip())
                elif text.startswith('/proxies'): handle_proxies(cfg, chat_id, user_id)
                elif text.startswith('/setdomain'): handle_setdomain(cfg, chat_id, user_id, text[10:].strip())
                elif text.startswith('/domain'): handle_domain(cfg, chat_id, user_id)
                elif text.startswith('/setpayload'): handle_setpayload(cfg, chat_id, user_id, text[11:].strip())
                elif text.startswith('/payload'): handle_payload(cfg, chat_id, user_id)
                elif text.startswith('/services'): handle_services(cfg, chat_id, user_id)
                elif text.startswith('/channels'): handle_channels(cfg, chat_id, user_id)
                elif text.startswith('/addchannel'): handle_addchannel(cfg, chat_id, user_id, text[11:].strip())
                elif text.startswith('/delchannel'): handle_delchannel(cfg, chat_id, user_id, text[11:].strip())
                elif text.startswith('/admins'): handle_admins(cfg, chat_id, user_id)
                elif text.startswith('/addadmin'): handle_addadmin(cfg, chat_id, user_id, text[9:].strip())
                elif text.startswith('/deladmin'): handle_deladmin(cfg, chat_id, user_id, text[9:].strip())
                elif text.startswith('/newuser'): handle_newuser(cfg, chat_id, user_id, text[8:].strip())
                elif text.startswith('/autopost'): handle_autopost(cfg, chat_id, user_id, text[9:].strip())
                elif text.startswith('/restart'): handle_restart(cfg, chat_id, user_id, text[8:].strip())
                elif text.startswith('/cabinet'): show_cabinet(cfg, chat_id, user_id, first_name)
                elif text.startswith('/admin'): show_admin_panel(cfg, chat_id, user_id)
                elif text.startswith('/help'): handle_help(cfg, chat_id)
        except KeyboardInterrupt: log.info("Остановка"); break
        except Exception as e: log.error(f"Ошибка в main loop: {e}"); time.sleep(5)

if __name__ == '__main__':
    main()
