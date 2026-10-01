#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VPN Panel Telegram Bot — с переносами строк и отправкой .dark файла
"""

import os, sys, json, time, logging, subprocess, secrets, string, urllib.request, urllib.parse, mimetypes, uuid
from datetime import datetime

# Подключаем модуль администраторов
sys.path.insert(0, '/usr/local/bin')
from bot_modules.admin import get_admins, is_admin, handle_addadmin, handle_deladmin, handle_admins
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
                if t: return t.replace('{support}', get_support())
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
                if t: return t.replace('{support}', get_support())
        except: pass
    return None


def get_test_ready_text():
    """Текст 'тестовый ключ доступен' из /etc/UDPCustom/test_ready.txt"""
    p = '/etc/UDPCustom/test_ready.txt'
    if os.path.exists(p):
        try:
            with open(p) as f:
                t = f.read().strip()
                if t: return t.replace('{support}', get_support())
        except: pass
    return None


def get_test_issued_text():
    """Текст 'тестовый доступ готов' из /etc/UDPCustom/test_issued.txt"""
    p = '/etc/UDPCustom/test_issued.txt'
    if os.path.exists(p):
        try:
            with open(p) as f:
                t = f.read().strip()
                if t: return t.replace('{support}', get_support())
        except: pass
    return None


def get_support():
    """Контакты поддержки из /etc/UDPCustom/support.txt"""
    p = '/etc/UDPCustom/support.txt'
    if os.path.exists(p):
        try:
            with open(p) as f:
                t = f.read().strip()
                if t: return t
        except: pass
    return '@ArsenGuro'


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


def create_test_user(cfg, tg_id=0, hwid=None):
    for _ in range(20):
        username = "test" + gen_random(6)
        r = subprocess.run(['id', username], capture_output=True)
        if r.returncode != 0: break
    else:
        return None, None
    password = gen_random(12)
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
                                   devices=devices, traffic_limit=traffic_bytes,
                                   hwid=hwid)
                log.info(f"Test key saved to DB: {username} (tg_id={tg_id})")
            except Exception as e:
                log.error(f"DB save failed: {e}")
            return username, password
        log.error(f"Ошибка создания: {r.stderr}")
        return None, None
    except Exception as e:
        log.error(f"Exception: {e}")
        return None, None

def _validate_vip_name(name):
    """Проверяет что имя валидно: a-z, 0-9, _ (5-15 символов). Возвращает (ok, msg_or_name)."""
    import re as _re
    name = name.strip().lower()
    if len(name) < 5:
        return False, "Минимум 5 символов"
    if len(name) > 15:
        return False, "Максимум 15 символов"
    if not _re.match(r'^[a-z0-9_]+$', name):
        return False, "Только латиница (a-z), цифры и _ (подчёркивание)"
    return True, name


def _make_vip_login(name):
    """Создаёт уникальный логин vip_<name> или vip_<name>_N."""
    login = f"vip_{name}"
    import subprocess as _sp
    def _exists(l):
        r = _sp.run(['id', l], capture_output=True)
        return r.returncode == 0
    if not _exists(login):
        return login
    for i in range(2, 100):
        candidate = f"{login}_{i}"
        if len(candidate) <= 24 and not _exists(candidate):
            return candidate
    import secrets as _sec
    return f"vip_{name}_{''.join(_sec.choice('0123456789') for _ in range(4))}"


def create_vip_user(cfg, tg_id, days, price, traffic_gb, devices, custom_login=None, hwid=None):
    """Создаёт VIP-юзера: Linux-юзер vip_<tg_id>_<rnd> + запись в vip_keys."""
    import secrets as _sec, string as _str
    if custom_login:
        username = custom_login
        r = subprocess.run(['id', username], capture_output=True)
        if r.returncode == 0:
            log.error(f"create_vip_user: логин {username} уже занят")
            return None, None
    else:
        suffix = ''.join(_sec.choice(_str.ascii_lowercase + _str.digits) for _ in range(4))
        username = f"vip_{tg_id}_{suffix}"
        r = subprocess.run(['id', username], capture_output=True)
        if r.returncode == 0:
            return None, None
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
                               tariff=f"vip_{days}d", price_paid=price, paid_via='balance',
                               hwid=hwid)
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

def notify_log(cfg, text, parse_mode='HTML'):
    """Отправляет неважное уведомление через LOG-бота (support)."""
    try:
        _tok = cfg.get('LOG_BOT_TOKEN', '')
        _chat = cfg.get('LOG_CHAT_ID', '')
        if not _tok or not _chat:
            # fallback — в основной бот
            tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                'chat_id': cfg.get('ADMIN_ID', ''), 'text': text, 'parse_mode': parse_mode
            })
            return
        tg_request(_tok, 'sendMessage', {
            'chat_id': _chat, 'text': text, 'parse_mode': parse_mode
        })
    except Exception as e:
        log.error(f"notify_log: {e}")


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
        "name": (f"💎 VIP {cfg.get('SERVER_LOCATION','VPN')} {username[4:]}" if username.startswith('vip_') else f"🎁 TEST {cfg.get('SERVER_LOCATION','VPN')} {username[4:]}" if username.startswith('test') else username),
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
    b = base64.urlsafe_b64encode(j.encode("utf-8")).decode("ascii").rstrip("=")
    return "darktunnel://" + b


def handle_start(cfg, chat_id, user_id, first_name, force_verified=None):
    token = cfg['BOT_TOKEN']
    name = first_name or 'друг'
    channels = get_channels()
    
    if not channels:
        send_message(token, chat_id, f"❌  Каналы не настроены. Обратись: {get_support()}")
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
        # Пытаемся прочитать welcome.txt (редактируемый админом)
        channels_list = chr(10).join([f"👉 @{ch}" for ch in not_sub])
        welcome_tpl = get_welcome_text()
        if welcome_tpl:
            text = (welcome_tpl
                    .replace('{name}', name)
                    .replace('{channels_list}', channels_list))
        else:
            # Fallback — если файла нет
            text = (
                f"👋 Привет, {name}!\n\n"
                f"⚠️ <b>Чтобы получить тестовый ключ:</b>\n\n"
                f"1️⃣ Подпишись на все каналы ниже\n"
                f"2️⃣ Зайди в каждый, посмотри посты\n"
                f"3️⃣ Поставь лайк или реакцию 👍\n"
                f"4️⃣ Вернись и нажми «Я подписался»\n\n"
                f"<b>Ты не подписан на:</b>\n"
                + "".join([f"👉 @{ch}\n" for ch in not_sub]) +
                f"\n💎 Есть VIP-ключи — пиши {get_support()}"
            )
        keyboard = {'inline_keyboard': []}
        for ch in not_sub:
            keyboard['inline_keyboard'].append([{'text': f'📢 @{ch}', 'url': f'https://t.me/{ch}'}])
        keyboard['inline_keyboard'].append([{'text': '✅ Я подписался → Проверить', 'callback_data': 'check_verified'}])
    
    elif verified:
        # Подписан на все + verified → кнопка получить тест
        # Читаем test_ready.txt (редактируемый админом)
        tpl_ready = get_test_ready_text()
        hours = cfg.get("TEST_HOURS", "8")
        gb = cfg.get("TEST_TRAFFIC_GB", "50")
        devices = cfg.get("TEST_DEVICES", "1")
        location = cfg.get("SERVER_LOCATION", "🌍 Сервер")
        if tpl_ready:
            text = (tpl_ready
                    .replace("{name}", name)
                    .replace("{hours}", str(hours))
                    .replace("{gb}", str(gb))
                    .replace("{devices}", str(devices))
                    .replace("{location}", str(location)))
        else:
            text = (
                f"👋 Привет, {name}!\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🎁 <b>ТЕСТОВЫЙ КЛЮЧ ДОСТУПЕН</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "✅ Подписка подтверждена\n\n"
                f"📱 {hours} часов   |   📊 {gb} ГБ   |   💻 {devices} устр.\n"
                f"{location}\n\n"
                "👇 Жми кнопку и получай 🔑"
            )
        keyboard = {"inline_keyboard": [
            [{"text": "🎁 ПОЛУЧИТЬ ТЕСТ", "callback_data": "get_test"}],
            [{"text": "👤 Личный кабинет", "callback_data": "cab_main"}],
        ]}
    
    else:
        # Подписан на все, но НЕ verified → надо зайти на канал
        channels_all = [c.lstrip("@") for c in channels]
        primary_clean = channels_all[0] if channels_all else primary
        sponsors_start = channels_all[1:] if len(channels_all) > 1 else []
        sponsors_list = chr(10).join([f"   📢 @{s}" for s in sponsors_start]) if sponsors_start else "(нет спонсоров)"
        # Пытаемся прочитать start.txt
        tpl_start = get_start_text()
        NL = chr(10)
        _hours = cfg.get("TEST_HOURS", "8")
        _gb = cfg.get("TEST_TRAFFIC_GB", "50")
        _dev = cfg.get("TEST_DEVICES", "1")
        if tpl_start:
            _loc = cfg.get("SERVER_LOCATION", "")
            text = (tpl_start
                    .replace("{name}", name)
                    .replace("{primary}", primary_clean)
                    .replace("{sponsors_list}", sponsors_list)
                    .replace("{hours}", str(_hours))
                    .replace("{gb}", str(_gb))
                    .replace("{devices}", str(_dev))
                    .replace("{location}", str(_loc)))
        else:
            text = NL.join([
                f"👋 Привет, {name}!",
                "",
                "━━━━━━━━━━━━━━━━━━━━",
                "🎁 <b>БЕСПЛАТНЫЙ ТЕСТ-КЛЮЧ</b>",
                "━━━━━━━━━━━━━━━━━━━━",
                "",
                "Как получить 👇",
                "",
                f"1️⃣ Перейди в наш канал: @{primary_clean}",
                "",
                "2️⃣ Найди в канале пост с кнопкой",
                "   «🎁 Получить тест» — нажми её",
                "",
                "3️⃣ Прояви активность на постах",
                "   (лайки, реакции — это важно!)",
                "",
                "4️⃣ После этого кнопка появится",
                "   здесь, в боте — жми и получай 🔑",
                "",
                "━━━━━━━━━━━━━━━━━━━━",
                "🎁 Тест:  8 часов · 50 ГБ · 1 устр.",
                f"💎 VIP:   {get_support()}"
            ])
        kb_start = [
            [
                {"text": "\U0001F4E3 Реклама", "callback_data": "cab_ad"},
                {"text": "\U0001F464 Личный кабинет", "callback_data": "cab_main"}
            ]
        ]
        keyboard = {"inline_keyboard": kb_start}
    
    # Сохраняем message_id приветствия для авто-удаления
    # Убираем старую reply-клавиатуру (если была) + отправляем inline
    try:
        tg_request(token, 'sendMessage', {
            'chat_id': chat_id,
            'text': '\u2060',  # zero-width
            'reply_markup': {'remove_keyboard': True},
        })
    except: pass
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


def handle_test(cfg, chat_id, user_id, first_name, cb_id=None, hwid=None):
    # Если юзер пришёл из канала — редирект на channel_test
    try:
        from bot_modules import db as _db_src
        if _db_src.get_user_source(user_id) == 'channel':
            return handle_channel_test(cfg, user_id, first_name, hwid=hwid)
    except Exception as _e:
        log.error(f"handle_test redirect: {_e}")
    token = cfg['BOT_TOKEN']
    if is_blacklisted(user_id):
        send_message(token, chat_id, f"🚫 Ты в чёрном списке. {get_support()}"); return
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
    if not is_admin(cfg, user_id):
        cooldown_hours = int(cfg.get('COOLDOWN_HOURS','8'))
        ok, remaining = check_cooldown(user_id, cooldown_hours)
        if not ok:
            send_message_ttl(token, chat_id, f"⏰ Попробуй через {format_time(remaining)}.", ttl=15); return
    # --- FSM: спрашиваем HWID ---
    if hwid is None:
        _is_adm = is_admin(cfg, user_id)
        try:
            from bot_modules import db as _tdb
            _tdb.set_pending(user_id, 'test_hwid')
        except Exception as _e:
            log.error(f"set_pending test_hwid: {_e}")
        _hw_msg = (
            "\U0001F194 <b>Отправь свой HWID</b>\n"
            + "\u2501"*20 + "\n"
            "HWID \u2014 это ID устройства.\n"
            "Ключ будет работать только на этом устройстве.\n\n"
            "Как узнать:\n"
            "DarkTunnel \u2192 \u2699\uFE0F Settings \u2192 внизу <b>Hardware ID</b>\n\n"
            "\U0001F4CB Скопируй и отправь сюда:"
        )
        if _is_adm:
            _kb = {'inline_keyboard': [
                [{'text': '\u27A1\uFE0F Пропустить', 'callback_data': 'test_hwid_skip'}]
            ]}
            send_message(token, chat_id, _hw_msg, parse_mode='HTML', reply_markup=_kb)
        else:
            send_message(token, chat_id, _hw_msg, parse_mode='HTML')
        return
    username, password = create_test_user(cfg, user_id, hwid=hwid)
    if not username:
        send_message_ttl(token, chat_id, "❌ Ошибка. Попробуй позже.", ttl=15); return
    record_issue(user_id, username)
    domain = get_domain(); ws_port = get_ws_port(); proxy = get_random_proxy()
    connect_line = f"{domain}:{ws_port}@{username}:{password}"
    traffic = cfg.get('TEST_TRAFFIC_GB','50'); devices = cfg.get('TEST_DEVICES','1')
    # Читаем test_issued.txt (редактируемый админом)
    tpl_issued = get_test_issued_text()
    hours = cfg.get("TEST_HOURS", "8")
    if tpl_issued:
        text = (tpl_issued
                .replace("{username}", username)
                .replace("{hours}", str(hours))
                .replace("{gb}", str(traffic))
                .replace("{devices}", str(devices)))
    else:
        text = (f"🎉 <b>ТЕСТОВЫЙ ДОСТУП ГОТОВ</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎁 Ключ: <code>{username}</code>\n"
                f"⏰ Срок: {hours} часов\n"
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
            ]}
            # Сохраняем админ-кнопки
            admin_id = cfg.get('ADMIN_ID', '')
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
        # @username клиента
        try:
            _ch = tg_request(token, 'getChat', {'chat_id': user_id})
            _un = (_ch or {}).get('result', {}).get('username', '') or ''
            _un = ('@' + _un) if _un else '—'
        except Exception:
            _un = '—'
        admin_msg = (
            f"🎁 <b>ТЕСТ — НОВАЯ ВЫДАЧА</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Юзер: {first_name or '—'}\n"
            f"📧 TG: {_un}\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"🔑 Ключ: <code>{username}</code>\n"
            f"🌐 Сервер: {domain}\n"
            f"🔌 Порт: {ws_port}\n"
            f"⏰  {now_str}"
        )
        notify_log(cfg, admin_msg)
    log.info(f"Выдан тест: {username}")


def _ref_purchase_bonus(cfg, buyer_id, price):
    """Когда реферал купил VIP — начисляем пригласившему $1 + 5 дней к VIP (разово)."""
    try:
        from bot_modules import db as _db
    except Exception as e:
        log.error(f"_ref_purchase_bonus import: {e}")
        return
    inviter_id = _db.mark_first_purchase(buyer_id)
    if not inviter_id:
        return
    log.info(f"Ref purchase bonus: inviter={inviter_id}, buyer={buyer_id}")

    # 1. Начисляем $1 на баланс
    try:
        _db.add_balance(inviter_id, 1.0, method='referral_bonus', meta={'from_user': buyer_id})
        _db.mark_bonus_paid(buyer_id)
    except Exception as e:
        log.error(f"ref bonus balance error: {e}")

    # 2. Продлеваем VIP на 5 дней
    extended = 0
    try:
        extended = _db.extend_vip_keys(inviter_id, 5)
    except Exception as e:
        log.error(f"ref bonus extend error: {e}")

    # Уведомление
    NL = chr(10)
    if extended > 0:
        msg = NL.join([
            "💰 <b>РЕФЕРАЛЬНЫЙ БОНУС!</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "🎉 Твой реферал купил VIP-ключ!",
            "",
            "💵 <b>+1.00 USDT</b> на баланс",
            "⏰ <b>+5 дней</b> к твоему VIP-ключу",
        ])
    else:
        msg = NL.join([
            "💰 <b>РЕФЕРАЛЬНЫЙ БОНУС!</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "🎉 Твой реферал купил VIP-ключ!",
            "",
            "💵 <b>+1.00 USDT</b> на баланс",
            "",
            "⚠️ +5 дней к VIP не начислены —",
            "у тебя нет активного VIP-ключа.",
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


def _do_key_delete(cfg, cb, tg_id, key_name):
    """Удаляет ключ: userdel + чистка файлов + возврат баланса для VIP."""
    token = cfg['BOT_TOKEN']
    chat_id = cb['message']['chat']['id']
    msg_id = cb['message']['message_id']
    cb_id = cb['id']

    try:
        from bot_modules import db as _db
    except Exception as e:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'Ошибка: {e}', 'show_alert': True})
        return

    # Ищем ключ
    key = _db.get_test_key(key_name)
    kind = 'test'
    if not key:
        key = _db.get_vip_key(key_name)
        kind = 'vip'
    if not key or int(key['tg_id']) != int(tg_id):
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Ключ не найден', 'show_alert': True})
        return

    now = int(time.time())
    exp = key['expires_at'] or 0
    created = key['created_at'] or now

    # Расчёт возврата для VIP (комиссия 20%)
    refund = 0.0
    if kind == 'vip':
        price = float(key.get('price_paid') or 0)
        total_secs = max(1, exp - created) if exp > 0 else 0
        left_secs = max(0, exp - now) if exp > 0 else 0
        if total_secs > 0 and price > 0:
            refund = round(price * (left_secs / total_secs) * 0.8, 2)

    # Удаляем Linux-юзера и файлы
    import subprocess as _sp
    try:
        _sp.run(['userdel', '-f', key_name], capture_output=True, timeout=10)
    except Exception as e:
        log.error(f"userdel {key_name}: {e}")

    # Чистим файлы
    for p in [f"/etc/UDPCustom/limits/{key_name}",
              f"/etc/UDPCustom/expire_ts/{key_name}",
              f"/etc/UDPCustom/traffic/{key_name}",
              f"/etc/UDPCustom/traffic_limits/{key_name}",
              f"/etc/UDPCustom/passwords/{key_name}"]:
        try:
            if os.path.exists(p): os.remove(p)
        except: pass

    # Убираем из users.db (текстовый файл)
    try:
        _sp.run(['sed', '-i', f'/^{key_name}$/d', '/etc/UDPCustom/users.db'], capture_output=True)
    except: pass

    # Убираем maxlogins из limits.conf
    try:
        _sp.run(['sed', '-i', f'/^{key_name} .*maxlogins/d', '/etc/security/limits.conf'], capture_output=True)
    except: pass

    # Убираем iptables-правило (по uid, но uid уже удалён — пробуем очистить)
    try:
        # Не можем получить uid удалённого юзера — просто пропускаем
        pass
    except: pass

    # Удаляем из БД
    if kind == 'vip':
        _db.execute("DELETE FROM vip_keys WHERE login=?", (key_name,))
    else:
        _db.execute("DELETE FROM test_keys WHERE login=?", (key_name,))

    # Возврат баланса для VIP
    if refund > 0:
        _db.add_balance(tg_id, refund, method='manual',
                        meta={'comment': f'Возврат за удаление {key_name}'})

    # Ответ юзеру
    new_balance = _db.get_balance(tg_id)
    NL = chr(10)
    lines = [
        "✅ <b>КЛЮЧ УДАЛЁН</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📱 Логин: <code>{key_name}</code>",
    ]
    if refund > 0:
        lines.append("")
        lines.append(f"💵 Возврат: <b>+{refund:.2f} USDT</b>")
        lines.append(f"💰 Баланс: <b>{new_balance:.2f} USDT</b>")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    kb = {'inline_keyboard': [
        [{'text': '🔑 Мои ключи', 'callback_data': 'cab_keys'}],
        [{'text': '⬅️ В кабинет', 'callback_data': 'cab_main'}]
    ]}
    tg_request(token, 'editMessageText', {
        'chat_id': chat_id,
        'message_id': msg_id,
        'text': NL.join(lines),
        'parse_mode': 'HTML',
        'reply_markup': kb
    })
    tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '✅ Удалено'})

    # Уведомление админу
    admin_id = cfg.get('ADMIN_ID', '')
    if admin_id:
        user = _db.get_user(tg_id) or {}
        NL2 = chr(10)
        a_msg = NL2.join([
            "🗑 <b>УДАЛЕНИЕ КЛЮЧА</b>",
            "",
            f"👤 {user.get('first_name') or '—'} (ID {tg_id})",
            f"📱 Ключ: <code>{key_name}</code> ({kind})",
            f"💵 Возврат: <b>{refund:.2f} USDT</b>"
        ])
        # Если был возврат денег — важно (в основной), иначе — в лог
        if refund and refund > 0:
            tg_request(token, 'sendMessage', {'chat_id': admin_id, 'text': a_msg, 'parse_mode': 'HTML'})
        else:
            notify_log(cfg, a_msg)

    log.info(f"Key deleted: {key_name} ({kind}) by tg={tg_id}, refund={refund}")


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

    # Читаем имя + HWID из pending
    custom_name = None
    custom_hwid = None
    try:
        pending = _db.get_pending(tg_id)
        if pending and pending.startswith('vip_ready:'):
            parts_p = pending.split(':', 3)
            if len(parts_p) >= 3:
                custom_name = parts_p[2]
            if len(parts_p) >= 4 and parts_p[3]:
                custom_hwid = parts_p[3]
            _db.clear_pending(tg_id)
    except: pass

    if not custom_name:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Сначала введи имя ключа', 'show_alert': True})
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
    # Формируем логин из имени
    full_login = _make_vip_login(custom_name)
    username, password = create_vip_user(cfg, tg_id, t['days'], t['price'], t['gb'], t['devices'], custom_login=full_login, hwid=custom_hwid)
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


def _do_broadcast_preview(cfg, chat_id, text):
    """Сохраняет текст и показывает превью"""
    token = cfg['BOT_TOKEN']
    try:
        from bot_modules import db as _db
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка db: {e}")
        return

    # Считаем юзеров
    total = len(_db.get_all_user_ids())
    if total == 0:
        send_message(token, chat_id, "❌ Нет юзеров для рассылки")
        return

    # Сохраняем черновик
    bid = _db.create_broadcast(text)
    if not bid:
        send_message(token, chat_id, "❌ Не удалось создать черновик")
        return

    NL = chr(10)
    preview = NL.join([
        "📨 <b>ПРЕВЬЮ РАССЫЛКИ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        text,
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👥 Получателей: <b>{total}</b>",
        f"⏱ Отправка: пауза 1 мин между сообщениями",
        f"🕐 Время: ~{total} мин (~{total//60} ч)",
        "",
        "Подтверди отправку:"
    ])
    kb = {'inline_keyboard': [
        [{'text': '✅ Отправить', 'callback_data': f'broadcast_send:{bid}'}],
        [{'text': '✏️ Изменить', 'callback_data': 'adm_broadcast'},
         {'text': '❌ Отмена', 'callback_data': 'adm_main'}]
    ]}
    send_message(token, chat_id, preview, reply_markup=kb, parse_mode='HTML')


def _do_broadcast_send(cfg, cb, bid):
    """Запускает рассылку в фоне"""
    token = cfg['BOT_TOKEN']
    chat_id = cb['message']['chat']['id']
    msg_id = cb['message']['message_id']
    cb_id = cb['id']

    try:
        from bot_modules import db as _db
    except Exception as e:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'Ошибка: {e}', 'show_alert': True})
        return

    bc = _db.get_broadcast(bid)
    if not bc:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Рассылка не найдена', 'show_alert': True})
        return
    if bc['status'] not in ('draft',):
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f"⚠️ Статус: {bc['status']}", 'show_alert': True})
        return

    user_ids = _db.get_all_user_ids()
    total = len(user_ids)

    _db.update_broadcast(bid, status='running', total=total, started_at=int(time.time()))
    tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'🚀 Запущено! {total} юзеров', 'show_alert': False})

    NL = chr(10)
    text = bc['text']
    text_ok = NL.join([
        "📨 <b>РАССЫЛКА ЗАПУЩЕНА</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"👥 Получателей: <b>{total}</b>",
        f"⏱ Пауза: 1 мин",
        f"🕐 Примерно: ~{total} мин",
        "",
        "<i>Отчёт придёт по завершении</i>"
    ])
    tg_request(token, 'editMessageText', {
        'chat_id': chat_id,
        'message_id': msg_id,
        'text': text_ok,
        'parse_mode': 'HTML'
    })

    # Фоновый поток
    import threading
    def _worker():
        import time as _t
        ok = 0; fail = 0
        for i, uid in enumerate(user_ids):
            try:
                r = tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                    'chat_id': uid,
                    'text': text,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True
                })
                if r and r.get('ok'):
                    ok += 1
                else:
                    fail += 1
            except Exception as e:
                fail += 1
                log.error(f"broadcast send {uid}: {e}")
            # Обновляем прогресс каждые 10
            if (i+1) % 10 == 0:
                try:
                    _db.update_broadcast(bid, sent_ok=ok, sent_fail=fail)
                except: pass
            # Пауза 1 мин между сообщениями (кроме последнего)
            if i < len(user_ids) - 1:
                _t.sleep(60)
        # Финал
        _db.update_broadcast(bid, status='done', sent_ok=ok, sent_fail=fail, finished_at=int(_t.time()))
        NL2 = chr(10)
        report = NL2.join([
            "✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"👥 Всего: <b>{total}</b>",
            f"✅ Доставлено: <b>{ok}</b>",
            f"❌ Ошибок: <b>{fail}</b>",
            "",
            "<i>Ошибки = юзеры заблокировали бота или удалили аккаунт</i>"
        ])
        try:
            tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                'chat_id': chat_id,
                'text': report,
                'parse_mode': 'HTML'
            })
        except: pass
        log.info(f"Broadcast #{bid} done: ok={ok}, fail={fail}")

    threading.Thread(target=_worker, daemon=True).start()
    log.info(f"Broadcast #{bid} started by admin, total={total}")


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
    """Создаёт промокод. Формат: CODE [days|balance] N USES [DATE]
    Старый формат: CODE N USES [DATE] (по умолчанию days)"""
    token = cfg['BOT_TOKEN']
    from datetime import datetime as _dt
    try:
        from bot_modules import db as _db
    except Exception as e:
        send_message(token, chat_id, 'Ошибка модуля db: ' + str(e))
        return
    parts = args.strip().split()
    if len(parts) < 3:
        send_message(token, chat_id, 'Формат: <code>CODE days|balance N АКТИВАЦИЙ [ДАТА]</code>', parse_mode='HTML')
        return
    code = parts[0].strip()
    if len(code) < 3 or not code.isalnum():
        send_message(token, chat_id, 'Код: только A-Z, a-z и 0-9, минимум 3 символа')
        return

    promo_type = 'days'
    if parts[1].lower() in ('days', 'balance'):
        promo_type = parts[1].lower()
        parts = [parts[0]] + parts[2:]
        if len(parts) < 3:
            send_message(token, chat_id, 'После типа нужно указать N и АКТИВАЦИЙ', parse_mode='HTML')
            return

    try:
        value = float(parts[1].replace(',', '.'))
        uses = int(parts[2])
    except:
        send_message(token, chat_id, 'N и АКТИВАЦИЙ должны быть числами')
        return

    if value <= 0 or uses < 1:
        send_message(token, chat_id, 'N и АКТИВАЦИЙ должны быть > 0')
        return

    if promo_type == 'days' and value != int(value):
        send_message(token, chat_id, 'Для типа days — целое число дней')
        return

    expires_at = 0
    if len(parts) >= 4:
        date_str = parts[3].replace('.', '-').replace('/', '-')
        try:
            dt = _dt.strptime(date_str, '%Y-%m-%d')
            expires_at = int(dt.timestamp())
        except:
            send_message(token, chat_id, 'Дата должна быть YYYY-MM-DD (можно с точками)')
            return

    if _db.get_promo(code):
        send_message(token, chat_id, '⚠️ Промокод <code>' + code + '</code> уже существует!', parse_mode='HTML')
        return

    try:
        _db.create_promo(code, promo_type, value, max_uses=uses, expires_at=expires_at)
    except Exception as e:
        send_message(token, chat_id, 'Ошибка: ' + str(e))
        return

    if promo_type == 'days':
        bonus_str = '⏰ Бонус: <b>+' + str(int(value)) + ' дней</b> к VIP-ключу'
    else:
        bonus_str = '💰 Бонус: <b>+' + f'{value:.2f}' + ' USDT</b> на баланс'

    NL = chr(10)
    lines = [
        '✅ <b>ПРОМОКОД СОЗДАН</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '🎫 Код: <code>' + code + '</code>',
        '📦 Тип: <b>' + promo_type + '</b>',
        bonus_str,
        '👥 Активаций: <b>' + str(uses) + '</b>'
    ]
    if expires_at:
        exp_str = _dt.fromtimestamp(expires_at).strftime('%d.%m.%Y')
        lines.append('📅 До: <b>' + exp_str + '</b>')
    else:
        lines.append('📅 Действует: <b>бессрочно</b>')
    kb = {'inline_keyboard': [
        [{'text': '📤 Опубликовать в канал', 'callback_data': 'promo_pub:' + code}],
        [{'text': '🎫 К промокодам', 'callback_data': 'adm_promo_list'}]
    ]}
    tg_request(token, 'sendMessage', {
        'chat_id': chat_id,
        'text': NL.join(lines),
        'parse_mode': 'HTML',
        'reply_markup': kb
    })
def _do_promo_post_start(cfg, cb, code):
    """Просит текст поста для промокода"""
    token = cfg['BOT_TOKEN']
    chat_id = cb['message']['chat']['id']
    admin_id = cb['from']['id']
    cb_id = cb['id']

    tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
    PENDING_ACTIONS[admin_id] = 'promo_post:' + code

    NL = chr(10)
    text = NL.join([
        '📢 <b>ПУБЛИКАЦИЯ ПРОМОКОДА</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '🎫 Промокод: <code>' + code + '</code>',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '✏️ <b>Отправь текст поста ответом</b> на это сообщение 👇',
        '',
        '<i>Поддерживается HTML:</i>',
        '<code>&lt;b&gt;жирный&lt;/b&gt;</code>',
        '<code>&lt;i&gt;курсив&lt;/i&gt;</code>',
        '<code>&lt;code&gt;моно&lt;/code&gt;</code>',
        '',
        '<i>Не забудь упомянуть промокод</i> <b>' + code + '</b> <i>в тексте.</i>'
    ])

    tg_request(token, 'sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'reply_markup': {'force_reply': True, 'selective': True}
    })


def _show_promo_preview(cfg, chat_id, code, post_text):
    """Показывает превью и предлагает каналы"""
    token = cfg['BOT_TOKEN']

    channels = []
    try:
        with open('/etc/UDPCustom/channels.txt') as f:
            channels = [l.strip().lstrip('@') for l in f if l.strip() and not l.startswith('#')]
    except: pass

    if not channels:
        send_message(token, chat_id, '❌ Нет каналов в channels.txt')
        return

    NL = chr(10)
    preview = NL.join([
        '📢 <b>ПРЕВЬЮ ПОСТА</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        post_text,
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '👇 Выбери канал для публикации:'
    ])

    kb_rows = []
    for i, ch in enumerate(channels, 1):
        kb_rows.append([{'text': f'📢 @{ch}', 'callback_data': f'promo_send:{code}:{i}'}])
    kb_rows.append([{'text': '📢 Во ВСЕ каналы', 'callback_data': f'promo_send:{code}:0'}])
    kb_rows.append([
        {'text': '✏️ Изменить', 'callback_data': f'promo_pub:{code}'},
        {'text': '❌ Отмена', 'callback_data': 'adm_promo_list'}
    ])
    kb = {'inline_keyboard': kb_rows}

    tg_request(token, 'sendMessage', {
        'chat_id': chat_id,
        'text': preview,
        'parse_mode': 'HTML',
        'reply_markup': kb
    })


def _do_promo_publish(cfg, cb, code, channel_idx):
    """Публикует пост в канал(ы)"""
    token = cfg['BOT_TOKEN']
    chat_id = cb['message']['chat']['id']
    cb_id = cb['id']

    try:
        from bot_modules import db as _db
    except:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': 'Ошибка db', 'show_alert': True})
        return

    # Достаём промокод
    p = _db.get_promo(code)
    if not p:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Промокод не найден', 'show_alert': True})
        return

    # Считываем сохранённый текст из callback (или из prefs)
    # Проще: текст уже в preview, но callback его не хранит.
    # Сохраняем через extra файл:
    text_file = f'/tmp/promo_post_{code}.txt'
    try:
        with open(text_file) as f:
            post_text = f.read()
    except:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Текст поста потерялся, отправь заново', 'show_alert': True})
        return

    # Каналы
    channels = []
    try:
        with open('/etc/UDPCustom/channels.txt') as f:
            channels = [l.strip().lstrip('@') for l in f if l.strip() and not l.startswith('#')]
    except: pass

    if not channels:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Нет каналов', 'show_alert': True})
        return

    # Целевые каналы
    if channel_idx == 0:
        targets = channels
    else:
        if channel_idx < 1 or channel_idx > len(channels):
            tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Неверный канал', 'show_alert': True})
            return
        targets = [channels[channel_idx - 1]]

    # Кнопки в посте
    me = tg_request(token, 'getMe')
    bot_u = me['result'].get('username', '') if me and me.get('ok') else ''
    kb = {'inline_keyboard': [
        [{'text': '🎁 Получить тест', 'url': f'https://t.me/{bot_u}?start=go'}],
        [{'text': '🎫 Активировать промокод', 'url': f'https://t.me/{bot_u}?start=promo'}]
    ]}

    # Публикуем
    ok = 0
    errors = []
    for ch in targets:
        target = '@' + ch if not ch.startswith('@') else ch
        r = tg_request(token, 'sendMessage', {
            'chat_id': target,
            'text': post_text,
            'parse_mode': 'HTML',
            'reply_markup': kb,
            'disable_web_page_preview': True
        })
        if r and r.get('ok'):
            ok += 1
        else:
            err = r.get('description', '?') if r else 'нет ответа'
            errors.append(f'@{ch}: {err}')

    # Ответ
    if ok == len(targets):
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'✅ Опубликовано в {ok} канал(ов)'})
        result_text = f'✅ <b>ОПУБЛИКОВАНО</b>{NL2}📢 Каналов: <b>{ok}</b>'.replace('{NL2}', chr(10))
        tg_request(token, 'sendMessage', {'chat_id': chat_id, 'text': result_text, 'parse_mode': 'HTML'})
    else:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'⚠️ Опубликовано {ok}/{len(targets)}'})
        tg_request(token, 'sendMessage', {
            'chat_id': chat_id,
            'text': '⚠️ <b>Частичная публикация</b>' + chr(10) + chr(10) + chr(10).join(errors),
            'parse_mode': 'HTML'
        })

    # Удаляем временный файл
    try:
        import os as _os
        _os.remove(text_file)
    except: pass

    log.info(f'Promo {code} published to {ok}/{len(targets)} channels')


def show_promo_list(cfg, chat_id, user_id, msg_id=None):
    """Список промокодов для админа"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
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
            # Форматируем значение в зависимости от типа
            t_type = r.get('type') or 'days'
            if t_type == 'balance':
                bonus_str = f'+{float(r["value"]):.2f} USDT'
            else:
                bonus_str = f'+{int(r["value"])} дней'
            lines.append(f'   {bonus_str} · {r["uses_left"]}/{r["max_uses"]} активаций')
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


EDIT_FILES = {
    'welcome': {'file': 'welcome.txt', 'name': '👋 Приветствие', 'ph': '{name}, {channels_list}'},
    'start': {'file': 'start.txt', 'name': '📖 Как получить тест', 'ph': '{name}, {primary}, {sponsors_list}, {hours}, {gb}, {devices}, {location}, {support}'},
    'test_ready': {'file': 'test_ready.txt', 'name': '🎁 Тест доступен', 'ph': '{name}, {hours}, {gb}, {devices}, {location}'},
    'test_issued': {'file': 'test_issued.txt', 'name': '🎉 Тест готов', 'ph': '{username}, {hours}, {gb}, {devices}'},
    'help': {'file': 'help.txt', 'name': '🏠 Меню /help', 'ph': '{primary}'},
    'help_instruction': {'file': 'help_instruction.txt', 'name': '📲 Инструкция', 'ph': '{primary}, {support}, {hours}, {gb}, {devices}, {location}'},
    'help_faq': {'file': 'help_faq.txt', 'name': '❓  FAQ', 'ph': '{primary}, {support}, {hours}, {gb}, {devices}, {location}'},
    'vip_buy': {'file': 'vip_buy.txt', 'name': '💎 Купить VIP', 'ph': '{balance}, {tariffs}'},
    'post': {'file': 'post.txt', 'name': '📢 Пост', 'ph': '{primary}, {sponsors_list}, {hours}, {gb}, {devices}, {location}, {support}'},
    'ref_post': {'file': 'ref_post.txt', 'name': '📤 Реферальный пост', 'ph': '{bot_name}, {primary}, {sponsors_list}, {hours}, {gb}, {devices}, {location}, {support}'},
    'rate': {'file': 'rate.txt', 'name': '💰 Курс USDT', 'ph': '(число)'},
    'ssh_banner': {'file': 'ssh_banner.txt', 'name': '🖥️ SSH-баннер', 'ph': '(HTML: h5, h6, font)'},
}


def show_edit_texts_menu(cfg, chat_id, user_id, msg_id=None):
    """Список файлов для редактирования"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, '🚫 Только для админа.')
        return
    NL = chr(10)
    text = NL.join([
        '📝 <b>РЕДАКТИРОВАНИЕ ТЕКСТОВ</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        'Выбери текст для изменения:',
        '',
        '<i>Файлы хранятся в /etc/UDPCustom/</i>'
    ])
    kb_rows = []
    keys = list(EDIT_FILES.keys())
    for i in range(0, len(keys), 2):
        row = []
        k1 = keys[i]
        row.append({'text': EDIT_FILES[k1]['name'], 'callback_data': 'adm_edit_txt:' + k1})
        if i + 1 < len(keys):
            k2 = keys[i + 1]
            row.append({'text': EDIT_FILES[k2]['name'], 'callback_data': 'adm_edit_txt:' + k2})
        kb_rows.append(row)
    kb_rows.append([{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}])
    kb = {'inline_keyboard': kb_rows}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')


def show_edit_text_file(cfg, chat_id, user_id, key, msg_id=None):
    """Показ файла для редактирования"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        return
    if key not in EDIT_FILES:
        send_message(token, chat_id, '❌ Файл не найден')
        return
    info = EDIT_FILES[key]
    path = '/etc/UDPCustom/' + info['file']
    try:
        with open(path) as f:
            content = f.read()
            # Для SSH-баннера — экранируем HTML чтобы Telegram не падал
            if key == 'ssh_banner':
                content = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    except Exception as e:
        content = '❌ Не удалось прочитать: ' + str(e)
    NL = chr(10)
    text = NL.join([
        '📝 <b>' + info['name'] + '</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '📁 Файл: <code>' + info['file'] + '</code>',
        '💡 Плейсхолдеры: <code>' + info['ph'] + '</code>',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        '📄 <b>Текущее содержимое:</b>',
        '',
        content,
        '',
        '━━━━━━━━━━━━━━━━━━━━'
    ])
    kb = {'inline_keyboard': [
        [{'text': '✏️ Редактировать', 'callback_data': 'adm_edit_go:' + key}],
        [{'text': '🔄 Обновить', 'callback_data': 'adm_edit_txt:' + key}],
        [{'text': '⬅️ К списку', 'callback_data': 'adm_edit_texts'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')


# ──────────────────────────────────────────────────────────────
# WHITEDNS — админка
# ──────────────────────────────────────────────────────────────
WD_SS = '/etc/UDPCustom/whitedns_servers.txt'
WD_RES = '/etc/UDPCustom/whitedns_resolvers.txt'
WD_S3 = '/etc/UDPCustom/whitedns_settings_3g.txt'
WD_SW = '/etc/UDPCustom/whitedns_settings_wifi.txt'
WD_SA = '/etc/UDPCustom/whitedns_settings_adsl.txt'
WD_LOG = '/etc/UDPCustom/whitedns_issued.log'

def _wd_count_lines(path):
    try:
        with open(path) as f:
            return len([l for l in f if l.strip()])
    except:
        return 0

def show_wd_stats(cfg, chat_id, user_id, msg_id=None):
    """Статистика WhiteDNS."""
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    issued = _wd_count_lines(WD_LOG)
    servers = _wd_count_lines(WD_SS)
    resolvers = _wd_count_lines(WD_RES)
    # Последние 5 выдач
    last5 = []
    try:
        with open(WD_LOG) as f:
            lines_all = [l.strip() for l in f if l.strip()]
            last5 = lines_all[-5:][::-1]
    except:
        pass
    txt = [
        '📊 <b>WHITEDNS СТАТИСТИКА</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '📤 Выдано конфигов: <b>' + str(issued) + '</b>',
        '🌐 Серверов: <b>' + str(servers) + '</b>',
        '🔢 Резолверов: <b>' + str(resolvers) + '</b>',
        '',
    ]
    if last5:
        txt.append('━━ Последние 5 ━━')
        for row in last5:
            txt.append('• ' + row)
    else:
        txt.append('Пока выдач не было.')
    text = NL.join(txt)
    kb = {'inline_keyboard': [
        [{'text': '🗑 Очистить лог', 'callback_data': 'wd_stats_clear'}],
        [{'text': '⬅️ Назад', 'callback_data': 'adm_whitedns'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')

def _wd_prof_path(idx):
    return [
        '/etc/UDPCustom/whitedns_settings_3g.txt',
        '/etc/UDPCustom/whitedns_settings_wifi.txt',
        '/etc/UDPCustom/whitedns_settings_adsl.txt'
    ][idx]

def _wd_read_profile(idx):
    try:
        with open(_wd_prof_path(idx)) as f:
            return f.read().rstrip(chr(10))
    except:
        return ''

def _wd_save_profile(idx, txt):
    import os as _os
    path = _wd_prof_path(idx)
    with open(path, 'w') as f:
        f.write(txt + chr(10))
    try:
        _os.chmod(path, 0o600)
    except: pass

def show_wd_profile_edit(cfg, chat_id, user_id, idx, msg_id=None):
    """Экран редактирования одного профиля (0=3G, 1=WiFi, 2=ADSL)."""
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    names = ['📱 3G', '📶 WiFi', '🖥 ADSL']
    cur = _wd_read_profile(idx)
    cnt = len([l for l in cur.split(chr(10)) if l.strip()]) if cur else 0
    if cur:
        preview = cur[:500]
        if len(cur) > 500:
            preview += NL + '... (обрезано)'
        block = '<pre>' + preview + '</pre>'
    else:
        block = '❌ пока пусто'
    text = NL.join([
        '✏️ <b>ПРОФИЛЬ: ' + names[idx] + '</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        'Строк: <b>' + str(cnt) + '</b>',
        '',
        block,
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        'Отправь новое содержимое сообщением.',
        'Или отправь <code>-</code> чтобы очистить.',
    ])
    kb = {'inline_keyboard': [
        [{'text': '🗑 Очистить', 'callback_data': 'wd_prof_clear_' + str(idx)}],
        [{'text': '⬅️ Назад', 'callback_data': 'wd_profiles'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')

def show_wd_profiles(cfg, chat_id, user_id, msg_id=None):
    """Меню профилей WhiteDNS (3G/WiFi/ADSL)."""
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    def _cnt(path):
        try:
            with open(path) as f:
                return len([l for l in f if l.strip()])
        except:
            return 0
    c3 = _cnt(WD_S3)
    cw = _cnt(WD_SW)
    ca = _cnt(WD_SA)
    text = NL.join([
        '⚙️ <b>ПРОФИЛИ НАСТРОЕК</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '📱 3G   : ' + (str(c3) + ' стр. ✅' if c3 else '❌ пусто'),
        '📶 WiFi : ' + (str(cw) + ' стр. ✅' if cw else '❌ пусто'),
        '🖥 ADSL : ' + (str(ca) + ' стр. ✅' if ca else '❌ пусто'),
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        'Выбери профиль для редактирования:',
    ])
    kb = {'inline_keyboard': [
        [{'text': '📱 3G', 'callback_data': 'wd_prof_3g'},
         {'text': '📶 WiFi', 'callback_data': 'wd_prof_wifi'},
         {'text': '🖥 ADSL', 'callback_data': 'wd_prof_adsl'}],
        [{'text': '⬅️ Назад', 'callback_data': 'adm_whitedns'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')

def _wd_read_resolvers(idx):
    """Читает резолверы для сервера idx (0=de, 1=fi, 2=se)."""
    paths = [
        '/etc/UDPCustom/whitedns_resolvers_de.txt',
        '/etc/UDPCustom/whitedns_resolvers_fi.txt',
        '/etc/UDPCustom/whitedns_resolvers_se.txt'
    ]
    try:
        with open(paths[idx]) as f:
            return [l.strip() for l in f if l.strip()]
    except:
        return []

def _wd_res_path(idx):
    return [
        '/etc/UDPCustom/whitedns_resolvers_de.txt',
        '/etc/UDPCustom/whitedns_resolvers_fi.txt',
        '/etc/UDPCustom/whitedns_resolvers_se.txt'
    ][idx]

def show_wd_resolvers(cfg, chat_id, user_id, msg_id=None):
    """Резолверы WhiteDNS — по 3 серверам."""
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    names = ['🇩🇪 Германия', '🇫🇮 Финляндия', '🇸🇪 Швеция']
    txt = ['🔢 <b>РЕЗОЛВЕРЫ WHITEDNS</b>', '━━━━━━━━━━━━━━━━━━━━', '']
    for i, name in enumerate(names):
        c = len(_wd_read_resolvers(i))
        if c:
            txt.append(name + ' — <b>' + str(c) + '</b> IP ✅')
        else:
            txt.append(name + ' — ❌ пусто')
    txt.append('')
    txt.append('━━━━━━━━━━━━━━━━━━━━')
    txt.append('Нажми на сервер, чтобы отредактировать список.')
    text = NL.join(txt)
    kb = {'inline_keyboard': [
        [{'text': '🇩🇪 Германия', 'callback_data': 'wd_res_edit_0'},
         {'text': '🇫🇮 Финляндия', 'callback_data': 'wd_res_edit_1'},
         {'text': '🇸🇪 Швеция', 'callback_data': 'wd_res_edit_2'}],
        [{'text': '⬅️ Назад', 'callback_data': 'adm_whitedns'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')

def show_wd_resolver_edit(cfg, chat_id, user_id, idx, msg_id=None):
    """Экран редактирования резолверов одного сервера."""
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    names = ['🇩🇪 Германия', '🇫🇮 Финляндия', '🇸🇪 Швеция']
    res = _wd_read_resolvers(idx)
    if res:
        preview = chr(10).join(res[:5])
        if len(res) > 5:
            preview += chr(10) + '... (ещё ' + str(len(res) - 5) + ')'
        preview_block = '<pre>' + preview + '</pre>'
    else:
        preview_block = '❌ пока пусто'
    text = NL.join([
        '✏️ <b>РЕЗОЛВЕРЫ: ' + names[idx] + '</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        'Всего IP: <b>' + str(len(res)) + '</b>',
        '',
        preview_block,
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        'Отправь список IP — по одному на строку.',
        'Или отправь <code>-</code> чтобы очистить.',
    ])
    kb = {'inline_keyboard': [
        [{'text': '🗑 Очистить', 'callback_data': 'wd_res_clear_' + str(idx)}],
        [{'text': '⬅️ Назад', 'callback_data': 'wd_resolvers'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')

def _wd_read_servers():
    """Читает 3 строки серверов. Возвращает список из 3 строк (или '')."""
    result = ['', '', '']
    try:
        with open(WD_SS) as f:
            lines = [l.rstrip(chr(10)) for l in f]
        for i in range(min(3, len(lines))):
            result[i] = lines[i]
    except:
        pass
    return result

def _wd_save_servers(servers):
    """Сохраняет 3 строки серверов."""
    with open(WD_SS, 'w') as f:
        f.write(chr(10).join(servers) + chr(10))

def show_wd_servers(cfg, chat_id, user_id, msg_id=None):
    """Список 3 серверов WhiteDNS."""
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    servers = _wd_read_servers()
    names = ['🇩🇪 Германия', '🇫🇮 Финляндия', '🇸🇪 Швеция']
    txt = ['🌐 <b>СЕРВЕРЫ WHITEDNS</b>', '━━━━━━━━━━━━━━━━━━━━', '']
    for i, name in enumerate(names):
        if servers[i]:
            txt.append(name + ' — ✅  настроено')
        else:
            txt.append(name + ' — ❌  пусто')
        txt.append('')
    txt.append('━━━━━━━━━━━━━━━━━━━━')
    txt.append('Нажми на сервер, чтобы отредактировать.')
    text = NL.join(txt)
    kb = {'inline_keyboard': [
        [{'text': '🇩🇪 Германия', 'callback_data': 'wd_srv_edit_0'},
         {'text': '🇫🇮 Финляндия', 'callback_data': 'wd_srv_edit_1'},
         {'text': '🇸🇪 Швеция', 'callback_data': 'wd_srv_edit_2'}],
        [{'text': '⬅️ Назад', 'callback_data': 'adm_whitedns'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')

def show_wd_server_edit(cfg, chat_id, user_id, idx, msg_id=None):
    """Экран редактирования одного сервера."""
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    servers = _wd_read_servers()
    names = ['🇩🇪 Германия', '🇫🇮 Финляндия', '🇸🇪 Швеция']
    cur = servers[idx] if idx < len(servers) else ''
    if cur:
        _prev = cur[:500]
        if len(cur) > 500:
            _prev += NL + '... (обрезано)'
        preview = '<pre>' + _prev + '</pre>'
    else:
        preview = '❌ пока пусто'
    text = NL.join([
        '✏️ <b>РЕДАКТИРОВАНИЕ: ' + names[idx] + '</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        'Текущее значение:',
        preview,
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        'Отправь новое значение сообщением.',
        '',
        'Или отправь <code>-</code> чтобы очистить.',
    ])
    kb = {'inline_keyboard': [
        [{'text': '🗑 Очистить', 'callback_data': 'wd_srv_clear_' + str(idx)}],
        [{'text': '⬅️ Назад', 'callback_data': 'wd_servers'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')

def show_adm_whitedns(cfg, chat_id, user_id, msg_id=None):
    """Меню WhiteDNS в админке."""
    token = cfg['BOT_TOKEN']
    NL = chr(10)
    issued = _wd_count_lines(WD_LOG)
    srv = _wd_read_servers()
    srv_names = ['🇩🇪 Германия', '🇫🇮 Финляндия', '🇸🇪 Швеция']
    srv_ready = sum(1 for s in srv if s)
    res_counts = [len(_wd_read_resolvers(i)) for i in range(3)]
    res_ready = sum(1 for c in res_counts if c)
    p3 = _wd_count_lines(WD_S3)
    pw = _wd_count_lines(WD_SW)
    pa = _wd_count_lines(WD_SA)
    prof_ready = sum(1 for x in (p3, pw, pa) if x)
    lines = [
        '📡 <b>WHITEDNS УПРАВЛЕНИЕ</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '📊 Выдано конфигов: <b>' + str(issued) + '</b>',
        '',
        '━━ 🌐 Серверы (' + str(srv_ready) + '/3) ━━',
    ]
    for i, name in enumerate(srv_names):
        lines.append(name + ' — ' + ('✅' if srv[i] else '❌ пусто'))
    lines.append('')
    lines.append('━━ 🔢 Резолверы (' + str(res_ready) + '/3) ━━')
    for i, name in enumerate(srv_names):
        c = res_counts[i]
        lines.append(name + ' — ' + (str(c) + ' IP ✅' if c else '❌ пусто'))
    lines.append('')
    lines.append('━━ ⚙️ Профили (' + str(prof_ready) + '/3) ━━')
    lines.append('📱 3G   : ' + (str(p3) + ' стр. ✅' if p3 else '❌ пусто'))
    lines.append('📶 WiFi : ' + (str(pw) + ' стр. ✅' if pw else '❌ пусто'))
    lines.append('🖥 ADSL : ' + (str(pa) + ' стр. ✅' if pa else '❌ пусто'))
    lines.append('')
    lines.append('━━━━━━━━━━━━━━━━━━━━')
    text = NL.join(lines)
    kb = {'inline_keyboard': [
        [{'text': '🌐 Серверы (' + str(srv_ready) + '/3)', 'callback_data': 'wd_servers'},
         {'text': '🔢 Резолверы (' + str(res_ready) + '/3)', 'callback_data': 'wd_resolvers'}],
        [{'text': '⚙️ Профили (' + str(prof_ready) + '/3)', 'callback_data': 'wd_profiles'},
         {'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')

def show_admin_panel(cfg, chat_id, user_id, msg_id=None):
    """Админ-панель"""
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if not is_admin(cfg, user_id):
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
         {'text': '👥 Пользователи', 'callback_data': 'admin_users_1'},
         {'text': '👑 Админы', 'callback_data': 'adm_admins'}],
        [{'text': '💰 Баланс', 'callback_data': 'admin_addbalance'},
         {'text': '🎫 Промокоды', 'callback_data': 'adm_promo_list'},
         {'text': '📨 Рассылка', 'callback_data': 'adm_broadcast'}],
        [{'text': '📢 Пост', 'callback_data': 'admin_post'},
         {'text': '📢 Каналы', 'callback_data': 'admin_channels'},
         {'text': '📝 Тексты', 'callback_data': 'adm_edit_texts'}],
        [{'text': '⚙️ SSH WS', 'callback_data': 'manage_services'},
         {'text': '⚙️ UDP Custom', 'callback_data': 'adm_udp_soon'},
         {'text': '⚙️ WhiteDNS', 'callback_data': 'adm_whitedns'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': keyboard})
    else:
        smart_send(token, chat_id, text, reply_markup=keyboard, parse_mode='HTML')


def handle_help(cfg, chat_id):
    """Открывает раздел Помощи (тот же, что из кабинета)."""
    try:
        from bot_modules.cabinet import show_help_back
        show_help_back(cfg, chat_id, 0)
    except Exception as e:
        log.error(f"handle_help: {e}")
        send_message(cfg['BOT_TOKEN'], chat_id, "❌ Ошибка открытия помощи")



def post_to_channel(cfg, chat_id, user_id):
    """Публикует пост с кнопкой в канал"""
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    
    # Только админ
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Команда только для админа.")
        return
    
    # Читаем текст поста
    post_file = '/etc/UDPCustom/post.txt'
    if not os.path.exists(post_file):
        send_message(token, chat_id, "❌ Файл post.txt не найден")
        return
    
    with open(post_file) as f:
        post_text = f.read().strip().replace('{support}', get_support())
    
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
        _hours = cfg.get('TEST_HOURS', '')
        _gb = cfg.get('TEST_TRAFFIC_GB', '')
        _devices = cfg.get('TEST_DEVICES', '')
        _location = cfg.get('SERVER_LOCATION', '')
        personalized = post_text.replace('{sponsors_list}', sponsors_list)
        personalized = personalized.replace('{primary}', primary_clean)
        personalized = personalized.replace('{hours}', _hours)
        personalized = personalized.replace('{gb}', _gb)
        personalized = personalized.replace('{devices}', _devices)
        personalized = personalized.replace('{location}', _location)
        
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


def handle_channel_test(cfg, user_id, first_name, hwid=None):
    """Обработка кнопки из КАНАЛА — проверка спонсора + выдача в личку"""
    token = cfg['BOT_TOKEN']
    
    # Проверяем чёрный список
    if is_blacklisted(user_id):
        tg_request(token, 'sendMessage', {
            'chat_id': user_id,
            'text': f"🚫 Ты в чёрном списке. Обратись: {get_support()}"
        })
        return
    
    # Проверяем кулдаун
    admin_id = cfg.get('ADMIN_ID', '')
    if not is_admin(cfg, user_id):
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
    # --- FSM: спрашиваем HWID ---
    if hwid is None:
        _is_adm = is_admin(cfg, user_id)
        try:
            from bot_modules import db as _tdb
            _tdb.set_pending(user_id, 'test_hwid_ch')
        except Exception as _e:
            log.error(f"set_pending test_hwid: {_e}")
        _hw_msg = (
            "\U0001F194 <b>Отправь свой HWID</b>\n"
            + "\u2501"*20 + "\n"
            "HWID \u2014 это ID устройства.\n"
            "Ключ будет работать только на этом устройстве.\n\n"
            "Как узнать:\n"
            "DarkTunnel \u2192 \u2699\uFE0F Settings \u2192 внизу <b>Hardware ID</b>\n\n"
            "\U0001F4CB Скопируй и отправь сюда:"
        )
        if _is_adm:
            _kb = {'inline_keyboard': [
                [{'text': '\u27A1\uFE0F Пропустить', 'callback_data': 'test_hwid_skip'}]
            ]}
            tg_request(token, 'sendMessage', {'chat_id': user_id, 'text': _hw_msg, 'parse_mode': 'HTML', 'reply_markup': _kb})
        else:
            tg_request(token, 'sendMessage', {'chat_id': user_id, 'text': _hw_msg, 'parse_mode': 'HTML'})
        return
    username, password = create_test_user(cfg, user_id, hwid=hwid)
    if not username:
        send_message_ttl(token, user_id, "❌ Ошибка создания. Попробуй позже.", ttl=15)
        return
    
    record_issue(user_id, username)
    
    
    domain = get_domain()
    ws_port = get_ws_port()
    proxy = get_random_proxy()
    if hwid:
        try:
            from bot_modules import dark_gen
            _proxy_str = proxy or '162.159.228.0'
            _proxyhost = _proxy_str.split(':')[0] if ':' in _proxy_str else _proxy_str
            _loc = cfg.get("SERVER_LOCATION", "VPN")
            _cfg_name = (f"\U0001F381 TEST {_loc} {username[4:]}" if username.startswith('test') else username)
            dt_url = dark_gen.generate(
                hwid=hwid, host=domain, port=str(ws_port),
                user=username, pw=password,
                proxyhost=_proxyhost, proxyport=str(ws_port),
                name=_cfg_name,
            )
            log.info(f"channel_test dark_gen ok for {username}")
        except Exception as _e:
            log.error(f"channel_test dark_gen error: {_e}")
            dt_url = generate_darktunnel_url(username, password, domain, ws_port, proxy, cfg)
    else:
        dt_url = generate_darktunnel_url(username, password, domain, ws_port, proxy, cfg)
    traffic = cfg.get('TEST_TRAFFIC_GB', '50')
    devices = cfg.get('TEST_DEVICES', '1')
    hours = cfg.get('TEST_HOURS', '8')
    
    _is_adm_local = str(user_id) == str(admin_id)
    
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
    
    if _is_adm_local:
        channels = get_channels()
        ch_name = channels[0].lstrip('@') if channels else 'ArsenVipKeys'
        from datetime import datetime
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        text += f"\n━━━━━━━━━━━━━━━━━━\n"
        text += f"✅ Ключ получен с канала @{ch_name}\n"
        text += f"🕐 {now_str}\n"
    
    text += f"\n💬 {get_support()}\n📢 @ArsenVipKeys"
    
    # Убираем кнопку "Получить тест" из welcome-сообщения
    welcome_file = f"/etc/UDPCustom/welcome_msgs/{user_id}"
    if os.path.exists(welcome_file):
        try:
            with open(welcome_file) as f:
                w_id = int(f.read().strip())
            new_kb = {'inline_keyboard': [
                [{'text': '🔑 Мой ключ', 'callback_data': 'mykey'}],
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
    if not _is_adm_local and admin_id:
        from datetime import datetime
        channels = get_channels()
        ch_name = channels[0].lstrip('@') if channels else 'ArsenVipKeys'
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            _ch2 = tg_request(token, 'getChat', {'chat_id': user_id})
            _un2 = (_ch2 or {}).get('result', {}).get('username', '') or ''
            _un2 = ('@' + _un2) if _un2 else '—'
        except Exception:
            _un2 = '—'
        admin_msg = (
            f"🎁 <b>ТЕСТ из канала @{ch_name} — НОВАЯ ВЫДАЧА</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Юзер: {first_name or '—'}\n"
            f"📧 TG: {_un2}\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"🔑 Ключ: <code>{username}</code>\n"
            f"⏰  {now_str}"
        )
        notify_log(cfg, admin_msg)
    
    log.info(f"Выдан тест из канала: {username} (user_id={user_id})")


def _stats_human_bytes(b):
    try: b = int(b)
    except: return "0 B"
    if b >= 1073741824: return f"{b/1073741824:.1f} GB"
    if b >= 1048576: return f"{b/1048576:.0f} MB"
    if b >= 1024: return f"{b/1024:.0f} KB"
    return f"{b} B"


def _stats_human_time(sec):
    try: sec = int(sec)
    except: return "—"
    if sec <= 0: return "истёк"
    h = sec // 3600
    if h >= 24:
        d = h // 24
        h = h % 24
        return f"{d}д {h}ч"
    return f"{h}ч"


def handle_stats(cfg, chat_id, user_id, mode='main', msg_id=None):
    """Статистика на БД: main | traffic"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Команда только для админа.")
        return

    try:
        from bot_modules import db as _db
    except Exception as e:
        send_message(token, chat_id, f"Ошибка db: {e}")
        return

    now = int(time.time())
    week_ago = now - 7 * 86400
    month_ago = now - 30 * 86400
    NL = chr(10)

    if mode == 'traffic':
        # Топ-5 по трафику (test + vip)
        tests = _db.query("SELECT login, tg_id, traffic_used, traffic_limit, expires_at FROM test_keys WHERE traffic_used > 0 ORDER BY traffic_used DESC LIMIT 5")
        vips  = _db.query("SELECT login, tg_id, traffic_used, traffic_limit, expires_at FROM vip_keys WHERE traffic_used > 0 ORDER BY traffic_used DESC LIMIT 5")
        all_keys = []
        for k in tests: k['kind'] = '🎁'; all_keys.append(k)
        for k in vips:  k['kind'] = '💎'; all_keys.append(k)
        all_keys.sort(key=lambda x: x.get('traffic_used') or 0, reverse=True)
        top = all_keys[:5]

        lines_txt = [
            "📈 <b>ТОП-5 ПО ТРАФИКУ</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            ""
        ]
        if not top:
            lines_txt.append("<i>Пока нет данных о трафике</i>")
        else:
            medals = ["🥇", "🥈", "🥉", "4.", "5."]
            for i, k in enumerate(top):
                m = medals[i]
                tg_id = k.get('tg_id') or 0
                user = _db.get_user(tg_id) if tg_id else None
                uname = ''
                if user and user.get('username'):
                    uname = f"@{user['username']}"
                elif user and user.get('first_name'):
                    uname = user['first_name']
                else:
                    uname = f"id{tg_id}" if tg_id else "—"
                used = _stats_human_bytes(k.get('traffic_used') or 0)
                limit = k.get('traffic_limit') or 0
                limit_str = f" / {_stats_human_bytes(limit)}" if limit > 0 else ""
                exp = k.get('expires_at') or 0
                t_left = _stats_human_time(exp - now) if exp > 0 else "♾"

                lines_txt.append(f"{m} {k['kind']} <code>{k['login']}</code>")
                lines_txt.append(f"   👤 {uname}")
                lines_txt.append(f"   📊 {used}{limit_str} · ⏰ {t_left}")
                lines_txt.append("")
        lines_txt.append("━━━━━━━━━━━━━━━━━━━━")
        text = NL.join(lines_txt)

        kb = {'inline_keyboard': [
            [{'text': '📊 Общая', 'callback_data': 'admin_stats'},
             {'text': '✅ 📈 Трафик', 'callback_data': 'noop'}],
            [{'text': '🔄 Обновить', 'callback_data': 'admin_stats_traffic'}],
            [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
        ]}
    else:
        # Основные цифры
        total_users = _db.query_one("SELECT COUNT(*) as n FROM users")['n']
        new_7d = _db.query_one("SELECT COUNT(*) as n FROM users WHERE registered_at >= ?", (week_ago,))['n']

        # Активные = есть хотя бы 1 активный ключ (test или vip)
        active_users = _db.query_one("""
            SELECT COUNT(DISTINCT tg_id) as n FROM (
                SELECT tg_id FROM test_keys WHERE expires_at = 0 OR expires_at > ?
                UNION
                SELECT tg_id FROM vip_keys WHERE expires_at = 0 OR expires_at > ?
            )""", (now, now))['n']

        # Ключи
        test_total  = _db.query_one("SELECT COUNT(*) as n FROM test_keys")['n']
        test_active = _db.query_one("SELECT COUNT(*) as n FROM test_keys WHERE expires_at = 0 OR expires_at > ?", (now,))['n']
        vip_total   = _db.query_one("SELECT COUNT(*) as n FROM vip_keys")['n']
        vip_active  = _db.query_one("SELECT COUNT(*) as n FROM vip_keys WHERE expires_at = 0 OR expires_at > ?", (now,))['n']

        # Финансы
        balances_sum = _db.query_one("SELECT COALESCE(SUM(balance),0) as s FROM users")['s'] or 0
        income_30d = _db.query_one("SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE method='purchase' AND amount > 0 AND created_at >= ?", (month_ago,))['s'] or 0
        income_all = _db.query_one("SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE method='purchase' AND amount > 0")['s'] or 0

        # Рефералы
        refs_total = _db.query_one("SELECT COUNT(*) as n FROM referrals")['n']
        ref_paid = _db.query_one("SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE method='referral_bonus'")['s'] or 0
        promo_used = _db.query_one("SELECT COUNT(*) as n FROM promo_used")['n']

        # Топ-5 по балансу
        top_balance = _db.query("""
            SELECT tg_id, first_name, username, balance
            FROM users WHERE balance > 0
            ORDER BY balance DESC LIMIT 5
        """)

        lines_txt = [
            "📊 <b>СТАТИСТИКА</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "👥 <b>ЮЗЕРЫ</b>",
            f"   Всего: <b>{total_users}</b>",
            f"   📅 Новых за 7д: <b>{new_7d}</b>",
            f"   🟢 Активных: <b>{active_users}</b>",
            "",
            "🔑 <b>КЛЮЧИ</b>",
            f"   🎁 Тестовых: <b>{test_total}</b> (🟢 {test_active})",
            f"   💎 VIP: <b>{vip_total}</b> (🟢 {vip_active})",
            "",
            "💵 <b>ФИНАНСЫ</b>",
            f"   На балансах: <b>{float(balances_sum):.2f} USDT</b>",
            f"   📈 Доход 30д: <b>{float(income_30d):.2f} USDT</b>",
            f"   💰 Всего дохода: <b>{float(income_all):.2f} USDT</b>",
            "",
            "👥 <b>РЕФЕРАЛЫ</b>",
            f"   Всего: <b>{refs_total}</b>",
            f"   💵 Выплачено: <b>{float(ref_paid):.2f} USDT</b>",
            f"   🎫 Промо активаций: <b>{promo_used}</b>",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "🏆 <b>ТОП-5 ПО БАЛАНСУ</b>",
            ""
        ]
        if not top_balance:
            lines_txt.append("<i>Пока ни у кого нет баланса</i>")
        else:
            medals = ["🥇", "🥈", "🥉", "4.", "5."]
            for i, u in enumerate(top_balance):
                m = medals[i]
                name = u.get('first_name') or ''
                uname = u.get('username') or ''
                handle = f"@{uname}" if uname else (name or f"id{u['tg_id']}")
                bal = float(u.get('balance') or 0)
                lines_txt.append(f"{m} {handle} · <b>{bal:.2f} USDT</b>")
        lines_txt.append("")
        lines_txt.append("━━━━━━━━━━━━━━━━━━━━")
        text = NL.join(lines_txt)

        kb = {'inline_keyboard': [
            [{'text': '✅ 📊 Общая', 'callback_data': 'noop'},
             {'text': '📈 Трафик', 'callback_data': 'admin_stats_traffic'}],
            [{'text': '🔄 Обновить', 'callback_data': 'admin_stats'}],
            [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
        ]}

    if msg_id:
        tg_request(token, 'editMessageText', {
            'chat_id': chat_id,
            'message_id': msg_id,
            'text': text,
            'parse_mode': 'HTML',
            'reply_markup': kb
        })
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')



def handle_ban(cfg, chat_id, user_id, args):
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if not is_admin(cfg, user_id):
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
    if not is_admin(cfg, user_id):
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
    if not is_admin(cfg, user_id):
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


def show_users_menu(cfg, chat_id, user_id, msg_id=None):
    """Главный экран управления юзерами"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа.")
        return
    try:
        from bot_modules import db as _db
    except Exception as e:
        send_message(token, chat_id, f"Ошибка db: {e}")
        return

    now = int(time.time())
    # TG-юзеры
    tg_total = _db.query_one("SELECT COUNT(*) as n FROM users")['n']
    # Тестовые
    test_total = _db.query_one("SELECT COUNT(*) as n FROM test_keys")['n']
    test_active = _db.query_one("SELECT COUNT(*) as n FROM test_keys WHERE expires_at=0 OR expires_at > ?", (now,))['n']
    # VIP
    vip_total = _db.query_one("SELECT COUNT(*) as n FROM vip_keys")['n']
    vip_active = _db.query_one("SELECT COUNT(*) as n FROM vip_keys WHERE expires_at=0 OR expires_at > ?", (now,))['n']

    NL = chr(10)
    lines_txt = [
        "👥 <b>УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"👤 TG-юзеров: <b>{tg_total}</b>",
        "",
        f"🎁 Тестовые ключи: <b>{test_total}</b>",
        f"     🟢 активных: <b>{test_active}</b>",
        "",
        f"💎 VIP-ключи: <b>{vip_total}</b>",
        f"     🟢 активных: <b>{vip_active}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "Выбери раздел 👇"
    ]
    text = NL.join(lines_txt)

    kb = {'inline_keyboard': [
        [{'text': f'🎁 Тестовые ({test_total})', 'callback_data': 'adm_users_test:1'},
         {'text': f'💎 VIP ({vip_total})', 'callback_data': 'adm_users_vip:1'}],
        [{'text': f'👤 TG-юзеры ({tg_total})', 'callback_data': 'adm_users_tg:1'}],
        [{'text': '🗑️ Удалить истёкших', 'callback_data': 'admin_cleanup'}],
        [{'text': '🚫 Бан-лист', 'callback_data': 'admin_banlist'}],
        [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
    ]}

    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')


def _fmt_key_row(key, kind):
    """Форматирует одну строку ключа."""
    now = int(time.time())
    exp = key.get('expires_at') or 0
    if exp == 0:
        t = "♾ бессрочно"
    elif exp > now:
        left = exp - now
        h = left // 3600
        if h < 24:
            t = f"{h}ч"
        else:
            t = f"{h//24}д"
    else:
        t = "❌ истёк"
    used = key.get('traffic_used') or 0
    limit = key.get('traffic_limit') or 0
    def human(b):
        try: b = int(b)
        except: return "0"
        if b >= 1073741824: return f"{b/1073741824:.1f}G"
        if b >= 1048576: return f"{b/1048576:.0f}M"
        if b >= 1024: return f"{b/1024:.0f}K"
        return f"{b}B"
    traffic = f"{human(used)}/{human(limit)}" if limit > 0 else f"{human(used)}/∞"
    icon = "💎" if kind == 'vip' else "🎁"
    tg_id = key.get('tg_id') or 0
    return f"{icon} <code>{key['login']}</code>", f"   ⏰ {t} · 📊 {traffic} · 👤 <code>{tg_id}</code>"


def show_users_test(cfg, chat_id, user_id, page=1, msg_id=None):
    """Список тестовых ключей"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        return
    try:
        from bot_modules import db as _db
    except: return

    per_page = 5
    now = int(time.time())
    total = _db.query_one("SELECT COUNT(*) as n FROM test_keys")['n']
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page < 1: page = 1
    if page > total_pages: page = total_pages
    offset = (page - 1) * per_page

    keys = _db.query("SELECT * FROM test_keys ORDER BY created_at DESC LIMIT ? OFFSET ?", (per_page, offset))

    NL = chr(10)
    lines_txt = [
        "🎁 <b>ТЕСТОВЫЕ КЛЮЧИ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<i>Стр. {page}/{total_pages} · всего {total}</i>",
        ""
    ]
    if not keys:
        lines_txt.append("<i>Пусто</i>")
    else:
        for k in keys:
            head, sub = _fmt_key_row(k, 'test')
            lines_txt.append(head)
            lines_txt.append(sub)
            lines_txt.append("")
    text = NL.join(lines_txt)

    nav = []
    if page > 1:
        nav.append({'text': '◀', 'callback_data': f'adm_users_test:{page-1}'})
    nav.append({'text': f'{page}/{total_pages}', 'callback_data': 'noop'})
    if page < total_pages:
        nav.append({'text': '▶', 'callback_data': f'adm_users_test:{page+1}'})

    kb = {'inline_keyboard': []}
    if nav: kb['inline_keyboard'].append(nav)
    kb['inline_keyboard'].append([
        {'text': '🎁 Тестовые', 'callback_data': 'adm_users_test:1'},
        {'text': '💎 VIP', 'callback_data': 'adm_users_vip:1'}
    ])
    kb['inline_keyboard'].append([
        {'text': '⬅️ К разделам', 'callback_data': 'adm_users_menu'}
    ])

    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')


def show_users_vip(cfg, chat_id, user_id, page=1, msg_id=None):
    """Список VIP-ключей"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        return
    try:
        from bot_modules import db as _db
    except: return

    per_page = 5
    total = _db.query_one("SELECT COUNT(*) as n FROM vip_keys")['n']
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page < 1: page = 1
    if page > total_pages: page = total_pages
    offset = (page - 1) * per_page

    keys = _db.query("SELECT * FROM vip_keys ORDER BY created_at DESC LIMIT ? OFFSET ?", (per_page, offset))

    NL = chr(10)
    lines_txt = [
        "💎 <b>VIP-КЛЮЧИ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<i>Стр. {page}/{total_pages} · всего {total}</i>",
        ""
    ]
    if not keys:
        lines_txt.append("<i>Пусто</i>")
    else:
        for k in keys:
            head, sub = _fmt_key_row(k, 'vip')
            lines_txt.append(head)
            lines_txt.append(sub)
            if k.get('tariff'):
                lines_txt.append(f"   📦 {k['tariff']} · {k.get('price_paid', 0):.2f} USDT")
            lines_txt.append("")
    text = NL.join(lines_txt)

    nav = []
    if page > 1:
        nav.append({'text': '◀', 'callback_data': f'adm_users_vip:{page-1}'})
    nav.append({'text': f'{page}/{total_pages}', 'callback_data': 'noop'})
    if page < total_pages:
        nav.append({'text': '▶', 'callback_data': f'adm_users_vip:{page+1}'})

    kb = {'inline_keyboard': []}
    if nav: kb['inline_keyboard'].append(nav)
    kb['inline_keyboard'].append([
        {'text': '🎁 Тестовые', 'callback_data': 'adm_users_test:1'},
        {'text': '💎 VIP', 'callback_data': 'adm_users_vip:1'}
    ])
    kb['inline_keyboard'].append([
        {'text': '⬅️ К разделам', 'callback_data': 'adm_users_menu'}
    ])

    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')


def show_users_tg(cfg, chat_id, user_id, page=1, msg_id=None):
    """Список TG-юзеров"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        return
    try:
        from bot_modules import db as _db
    except: return

    per_page = 5
    total = _db.query_one("SELECT COUNT(*) as n FROM users")['n']
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page < 1: page = 1
    if page > total_pages: page = total_pages
    offset = (page - 1) * per_page

    users_list = _db.query("SELECT * FROM users ORDER BY registered_at DESC LIMIT ? OFFSET ?", (per_page, offset))

    NL = chr(10)
    lines_txt = [
        "👤 <b>TG-ЮЗЕРЫ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<i>Стр. {page}/{total_pages} · всего {total}</i>",
        ""
    ]
    if not users_list:
        lines_txt.append("<i>Пусто</i>")
    else:
        from datetime import datetime as _dt
        for u in users_list:
            name = u.get('first_name') or '—'
            uname = u.get('username') or ''
            handle = f"@{uname}" if uname else f"id{u['tg_id']}"
            balance = float(u.get('balance') or 0)
            # Считаем ключи: активные/всего
            _now = int(time.time())
            test_all = _db.query_one("SELECT COUNT(*) as n FROM test_keys WHERE tg_id=?", (u['tg_id'],))['n']
            test_act = _db.query_one("SELECT COUNT(*) as n FROM test_keys WHERE tg_id=? AND (expires_at=0 OR expires_at > ?)", (u['tg_id'], _now))['n']
            vip_all = _db.query_one("SELECT COUNT(*) as n FROM vip_keys WHERE tg_id=?", (u['tg_id'],))['n']
            vip_act = _db.query_one("SELECT COUNT(*) as n FROM vip_keys WHERE tg_id=? AND (expires_at=0 OR expires_at > ?)", (u['tg_id'], _now))['n']
            dt = ''
            if u.get('registered_at'):
                dt = _dt.fromtimestamp(u['registered_at']).strftime('%d.%m.%y')
            lines_txt.append(f"👤 <b>{name}</b> · {handle}")
            lines_txt.append(f"   🆔 <code>{u['tg_id']}</code>")
            lines_txt.append(f"   💰 {balance:.2f} USDT")
            lines_txt.append(f"   🎁 {test_act}/{test_all}   💎 {vip_act}/{vip_all}")
            if dt:
                lines_txt.append(f"   📅 {dt}")
            lines_txt.append("")
    text = NL.join(lines_txt)

    nav = []
    if page > 1:
        nav.append({'text': '◀', 'callback_data': f'adm_users_tg:{page-1}'})
    nav.append({'text': f'{page}/{total_pages}', 'callback_data': 'noop'})
    if page < total_pages:
        nav.append({'text': '▶', 'callback_data': f'adm_users_tg:{page+1}'})

    kb = {'inline_keyboard': []}
    if nav: kb['inline_keyboard'].append(nav)
    kb['inline_keyboard'].append([
        {'text': '⬅️ К разделам', 'callback_data': 'adm_users_menu'}
    ])

    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')


def handle_users(cfg, chat_id, user_id, page=1, msg_id=None):
    """Алиас для совместимости — ведёт на меню юзеров"""
    show_users_menu(cfg, chat_id, user_id, msg_id)


def handle_cleanup(cfg, chat_id, user_id):
    """Удалить всех истёкших"""
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if not is_admin(cfg, user_id):
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
    if not ip.replace('.', '').isdigit() or ip.count('.') != 3:
        send_message(token, chat_id, f"❌  Неверный IP: {ip}"); return
    try:
        with open(PROXIES_FILE, 'a') as f:
            f.write(ip + chr(10))
        ips = sorted(set(l.strip() for l in open(PROXIES_FILE) if l.strip()))
        with open(PROXIES_FILE, 'w') as f:
            f.write(chr(10).join(ips) + chr(10))
        send_message(token, chat_id, f"✅  Прокси добавлен: <code>{ip}</code>" + chr(10) + f"Всего: <b>{len(ips)}</b>", parse_mode='HTML')
    except Exception as e:
        send_message(token, chat_id, f"❌  Ошибка: {e}")


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
    """Список каналов с кнопками управления"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        send_message(token, chat_id, "🚫 Только для админа."); return
    channels = get_channels()
    NL = chr(10)
    if not channels:
        text = NL.join([
            "📢 <b>КАНАЛОВ НЕТ</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "Добавь первый канал — он станет основным."
        ])
    else:
        lines_txt = [
            f"📢 <b>УПРАВЛЕНИЕ КАНАЛАМИ ({len(channels)})</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            ""
        ]
        for i, ch in enumerate(channels, 1):
            ch_clean = ch.lstrip('@')
            if i == 1:
                lines_txt.append(f"<b>{i}.</b> <code>@{ch_clean}</code> — 🎯 <b>Основной</b>")
            else:
                lines_txt.append(f"<b>{i}.</b> <code>@{ch_clean}</code> — 📢 Спонсор")
        lines_txt.append("")
        lines_txt.append("━━━━━━━━━━━━━━━━━━━━")
        lines_txt.append("<i>Основной — первый канал. Остальные — обязательные спонсоры.</i>")
        text = NL.join(lines_txt)

    kb = {'inline_keyboard': [
        [{'text': '➕ Добавить канал', 'callback_data': 'adm_ch_add'}],
        [{'text': '🗑 Удалить канал', 'callback_data': 'adm_ch_del'}],
        [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
    ]}
    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')


def show_delete_channels(cfg, chat_id, user_id, msg_id=None):
    """Экран удаления каналов"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        return
    channels = get_channels()
    NL = chr(10)
    if not channels:
        text = "📢 Каналов нет"
        kb = {'inline_keyboard': [[{'text': '⬅️ Назад', 'callback_data': 'admin_channels'}]]}
    else:
        lines_txt = [
            "🗑 <b>УДАЛИТЬ КАНАЛ</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "Выбери канал для удаления:",
            ""
        ]
        if len(channels) > 1:
            lines_txt.append("<i>⚠️ Основной удалить нельзя.</i>")
            lines_txt.append("<i>Сначала сделай другой канал основным — удали текущий основной, после чего следующий станет первым.</i>")
        else:
            lines_txt.append("<i>⚠️ Это единственный канал — его нельзя удалить.</i>")
        text = NL.join(lines_txt)

        kb_rows = []
        for i, ch in enumerate(channels, 1):
            ch_clean = ch.lstrip('@')
            if i == 1:
                continue  # Основной пропускаем
            kb_rows.append([{'text': f"🗑 @{ch_clean}", 'callback_data': f'adm_ch_delok:{i}'}])
        kb_rows.append([{'text': '⬅️ Назад', 'callback_data': 'admin_channels'}])
        kb = {'inline_keyboard': kb_rows}

    if msg_id:
        tg_request(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        smart_send(token, chat_id, text, reply_markup=kb, parse_mode='HTML')


def do_delete_channel(cfg, cb, idx):
    """Удаляет канал по номеру (1-based)"""
    token = cfg['BOT_TOKEN']
    chat_id = cb['message']['chat']['id']
    cb_id = cb['id']
    if idx == 1:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '🚫 Основной удалить нельзя', 'show_alert': True})
        return
    try:
        with open('/etc/UDPCustom/channels.txt') as f:
            channels = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    except:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Ошибка чтения', 'show_alert': True})
        return
    if idx < 1 or idx > len(channels):
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Канал не найден', 'show_alert': True})
        return
    removed = channels.pop(idx - 1)
    try:
        with open('/etc/UDPCustom/channels.txt', 'w') as f:
            for ch in channels:
                f.write(ch + chr(10))
    except Exception as e:
        tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'❌ {e}', 'show_alert': True})
        return
    tg_request(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'✅ {removed} удалён'})
    # Показываем обновлённый список
    show_delete_channels(cfg, chat_id, cb['from']['id'], cb['message']['message_id'])
    log.info(f'Channel deleted: {removed}')


def show_add_channel(cfg, chat_id, user_id):
    """Инструкция добавления канала"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        return
    PENDING_ACTIONS[user_id] = 'addchannel_new'
    NL = chr(10)
    text = NL.join([
        "➕ <b>ДОБАВИТЬ КАНАЛ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "Отправь username канала ответом на это сообщение.",
        "",
        "📌 Форматы:",
        "• <code>@MyChannel</code>",
        "• <code>MyChannel</code>",
        "• <code>https://t.me/MyChannel</code>",
        "",
        "⚠️ Бот должен быть админом канала!",
        "",
        "👇 Отправь ответом:"
    ])
    tg_request(token, 'sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'reply_markup': {'force_reply': True, 'selective': True}
    })



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


def _do_addchannel_new(token, chat_id, raw_args):
    """Добавляет канал с разными форматами (кнопка из админки)"""
    NL = chr(10)
    raw = (raw_args or '').strip()
    if not raw:
        send_message(token, chat_id, '❌ Пустой ввод')
        return

    # Обрабатываем форматы
    ch = raw
    if ch.startswith('https://t.me/'):
        ch = ch[len('https://t.me/'):]
    elif ch.startswith('t.me/'):
        ch = ch[len('t.me/'):]
    elif ch.startswith('http://t.me/'):
        ch = ch[len('http://t.me/'):]
    # Убираем @ в начале
    ch = ch.lstrip('@').split('/')[0].split('?')[0].strip()
    if not ch:
        send_message(token, chat_id, '❌ Неверный формат')
        return

    ch = '@' + ch

    # Проверяем через Telegram API
    test = tg_request(token, 'getChat', {'chat_id': ch})
    if not test or not test.get('ok'):
        err = test.get('description', 'unknown') if test else 'нет ответа'
        send_message(token, chat_id, f"❌ Не удалось получить канал: {err}" + NL + NL + "Проверь что:" + NL + "• Username правильный" + NL + "• Бот добавлен в канал как админ")
        return

    # Читаем каналы
    try:
        with open('/etc/UDPCustom/channels.txt') as f:
            channels = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    except:
        channels = []

    if ch in channels:
        send_message(token, chat_id, f"⚠️ Канал <code>{ch}</code> уже в списке", parse_mode='HTML')
        return

    channels.append(ch)
    try:
        with open('/etc/UDPCustom/channels.txt', 'w') as f:
            for c in channels:
                f.write(c + NL)
    except Exception as e:
        send_message(token, chat_id, f"❌ Ошибка сохранения: {e}")
        return

    # Определяем роль
    if len(channels) == 1:
        role = '🎯 Основной'
    else:
        role = f'📢 Спонсор #{len(channels) - 1}'

    # Результат
    result = NL.join([
        '✅ <b>КАНАЛ ДОБАВЛЕН</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        f'📢 <code>{ch}</code>',
        f'📍 Роль: {role}',
        '',
        f'📊 Всего каналов: <b>{len(channels)}</b>'
    ])
    kb = {'inline_keyboard': [
        [{'text': '📢 К каналам', 'callback_data': 'admin_channels'},
         {'text': '➕ Добавить ещё', 'callback_data': 'adm_ch_add'}],
        [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
    ]}
    tg_request(token, 'sendMessage', {
        'chat_id': chat_id,
        'text': result,
        'parse_mode': 'HTML',
        'reply_markup': kb
    })
    log.info(f'Channel added: {ch}')



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

                # === Telegram Stars: pre_checkout ===
                if 'pre_checkout_query' in upd:
                    _pcq = upd['pre_checkout_query']
                    tg_request(cfg['BOT_TOKEN'], 'answerPreCheckoutQuery', {
                        'pre_checkout_query_id': _pcq['id'],
                        'ok': True
                    })
                    log.info(f'Pre-checkout OK for {_pcq["from"]["id"]}')
                    continue

                # === Telegram Stars: successful_payment ===
                if 'message' in upd and 'successful_payment' in upd['message']:
                    _sp = upd['message']['successful_payment']
                    _sp_user = upd['message']['from']['id']
                    _sp_stars = _sp['total_amount']
                    _sp_payload = _sp.get('invoice_payload', '')
                    try:
                        from bot_modules import db as _dbs
                        # Читаем pending stars_invoice
                        _pend = _dbs.get_pending(_sp_user) or ''
                        _amt = 0.0
                        if _pend.startswith('stars_invoice:'):
                            _p = _pend.split(':')
                            _amt = float(_p[1])
                        _dbs.clear_pending(_sp_user)
                        if _amt > 0:
                            _new_bal = _dbs.add_balance(_sp_user, _amt, method='stars', meta={'stars': _sp_stars, 'payload': _sp_payload})
                            NLsp = chr(10)
                            _ok = NLsp.join([
                            '✅ <b>ПЛАТЁЖ ПОЛУЧЕН</b>',
                            '━━━━━━━━━━━━━━━━━━━━',
                            '',
                            f'💵 Зачислено: <b>{_amt:.2f} USDT</b>',
                            f'💰 Баланс: <b>{_new_bal:.2f} USDT</b>'
                            ])
                            send_message(cfg['BOT_TOKEN'], _sp_user, _ok)
                            # Уведомляем админа
                            _adm = cfg.get('ADMIN_ID', '')
                            if _adm:
                                try:
                                    _u = _dbs.get_user(_sp_user) or {}
                                    tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                                        'chat_id': _adm,
                                        'text': f'⭐ <b>STARS ОПЛАТА</b>' + chr(10) + chr(10) + f'👤 {_u.get("first_name") or "—"}' + chr(10) + f'🆔 <code>{_sp_user}</code>' + chr(10) + f'⭐ {_sp_stars} Stars' + chr(10) + f'💵 +{_amt:.2f} USDT',
                                        'parse_mode': 'HTML'
                                    })
                                except: pass
                                log.info(f'Stars topup: user={_sp_user} amt={_amt} stars={_sp_stars}')
                        else:
                            log.warning(f'Stars payment без pending: user={_sp_user} stars={_sp_stars}')
                    except Exception as _e:
                        log.error(f'Stars payment error: {_e}')
                    continue

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
                            '📦 <b>Формат:</b>',
                            '<code>CODE ТИП N АКТИВАЦИЙ [ДАТА]</code>',
                            '',
                            'CODE — буквы/цифры, от 3 символов',
                            'ТИП — <b>days</b> или <b>balance</b>',
                            'N — сколько даёт',
                            'АКТИВАЦИЙ — сколько юзеров',
                            'ДАТА — необязательно (YYYY-MM-DD)',
                            '',
                            '━━━━━━━━━━━━━━━━━━━━',
                            '📋 <b>Примеры:</b>',
                            '',
                            '🎁 <b>Промокод на дни:</b>',
                            '<code>WINTER days 3 100</code>',
                            '   → +3 дня к VIP, 100 активаций',
                            '',
                            '💰 <b>Промокод на USDT:</b>',
                            '<code>BONUS balance 1 50</code>',
                            '   → +1 USDT на баланс, 50 активаций',
                            '',
                            '📅 <b>С датой окончания:</b>',
                            '<code>SUMMER days 7 50 2026-12-31</code>',
                            '',
                            '━━━━━━━━━━━━━━━━━━━━',
                            '⚠️ Регистр букв важен!',
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
                    elif cb_data.startswith('promo_pub:'):
                        _code = cb_data.split(':', 1)[1]
                        _do_promo_post_start(cfg, cb, _code)
                        continue
                    elif cb_data.startswith('promo_send:'):
                        _parts = cb_data.split(':')
                        _code = _parts[1]
                        _idx = int(_parts[2]) if len(_parts) > 2 else 0
                        _do_promo_publish(cfg, cb, _code, _idx)
                        continue
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
                    elif cb_data.startswith('broadcast_send:'):
                        try:
                            bid = int(cb_data.split(':', 1)[1])
                        except:
                            bid = 0
                        if bid > 0:
                            _do_broadcast_send(cfg, cb, bid)
                        continue
                    elif cb_data == 'adm_admins':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        # Показываем список админов + инструкция
                        try:
                            from bot_modules.admin import get_admins
                            admins = get_admins()
                        except:
                            admins = [str(cfg.get('ADMIN_ID', ''))]
                        NLx = chr(10)
                        lines = [
                            "👑 <b>АДМИНЫ</b>",
                            "━━━━━━━━━━━━━━━━━━━━",
                            ""
                        ]
                        for i, a in enumerate(admins, 1):
                            marker = " ⭐ (вы)" if str(a) == str(cb_user_id) else ""
                            # Получаем имя через getChat
                            name_info = ""
                            try:
                                r = tg_request(cfg['BOT_TOKEN'], 'getChat', {'chat_id': int(a)})
                                if r and r.get('ok'):
                                    res = r.get('result', {})
                                    fname = res.get('first_name', '') or ''
                                    lname = res.get('last_name', '') or ''
                                    uname = res.get('username', '') or ''
                                    full_name = (fname + ' ' + lname).strip()
                                    if uname:
                                        name_info = f" · @{uname}"
                                    elif full_name:
                                        name_info = f" · {full_name}"
                            except: pass
                            lines.append(f"<b>{i}.</b> <code>{a}</code>{name_info}{marker}")
                        lines.append("")
                        lines.append("━━━━━━━━━━━━━━━━━━━━")
                        lines.append("➕ <b>Добавить:</b>")
                        lines.append("<code>/addadmin 123456789</code>")
                        lines.append("")
                        lines.append("➖ <b>Удалить:</b>")
                        lines.append("<code>/deladmin 123456789</code>")
                        lines.append("")
                        lines.append("📌 <b>Как узнать ID:</b>")
                        lines.append("• Перешли сообщение юзера в @idbot")
                        lines.append("• Или пусть откроет @userinfobot")
                        kb = {'inline_keyboard': [
                            [{'text': '🔄 Обновить', 'callback_data': 'adm_admins'}],
                            [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
                        ]}
                        tg_request(cfg['BOT_TOKEN'], 'editMessageText', {
                            'chat_id': cb['message']['chat']['id'],
                            'message_id': cb['message']['message_id'],
                            'text': NLx.join(lines),
                            'parse_mode': 'HTML',
                            'reply_markup': kb
                        })
                    elif cb_data == 'adm_edit_texts':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_edit_texts_menu(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                        continue
                    elif cb_data.startswith('adm_edit_txt:'):
                        _key = cb_data.split(':', 1)[1]
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_edit_text_file(cfg, cb['message']['chat']['id'], cb_user_id, _key, cb['message']['message_id'])
                        continue
                    elif cb_data.startswith('adm_edit_go:'):
                        _key = cb_data.split(':', 1)[1]
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        if _key in EDIT_FILES:
                            _info = EDIT_FILES[_key]
                            PENDING_ACTIONS[cb_user_id] = 'edit_text:' + _key
                            NLx = chr(10)
                            _instr = NLx.join([
                                '📝 <b>РЕДАКТИРОВАНИЕ: ' + _info['name'] + '</b>',
                                '━━━━━━━━━━━━━━━━━━━━',
                                '',
                                '📁 Файл: <code>' + _info['file'] + '</code>',
                                '💡 Плейсхолдеры: <code>' + _info['ph'] + '</code>',
                                '',
                                '⚠️ Текущее содержимое будет <b>полностью заменено</b>.',
                                '',
                                '✏️ Отправь новый текст ответом на это сообщение 👇'
                            ])
                            tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                                'chat_id': cb['message']['chat']['id'],
                                'text': _instr,
                                'parse_mode': 'HTML',
                                'reply_markup': {'force_reply': True, 'selective': True}
                            })
                        continue
                    elif cb_data == 'adm_broadcast':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        PENDING_ACTIONS[cb_user_id] = 'broadcast_text'
                        NLx = chr(10)
                        instr = NLx.join([
                            '📨 <b>РАССЫЛКА</b>',
                            '━━━━━━━━━━━━━━━━━━━━',
                            '',
                            'Отправь текст, который уйдёт всем юзерам.',
                            '',
                            '📝 <b>Поддерживается HTML:</b>',
                            '• <code>&lt;b&gt;жирный&lt;/b&gt;</code>',
                            '• <code>&lt;i&gt;курсив&lt;/i&gt;</code>',
                            '• <code>&lt;code&gt;моноширинный&lt;/code&gt;</code>',
                            '• <code>&lt;a href="url"&gt;ссылка&lt;/a&gt;</code>',
                            '',
                            '⚠️ Перед отправкой покажу превью.',
                            '',
                            'Отправь ответ на это сообщение 👇'
                        ])
                        smart_send(cfg['BOT_TOKEN'], cb['message']['chat']['id'], instr,
                                   reply_markup={'force_reply': True, 'selective': True},
                                   parse_mode='HTML')
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
                        handle_stats(cfg, cb['message']['chat']['id'], cb_user_id, 'main', cb['message']['message_id'])
                    elif cb_data == 'admin_stats_keys':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_stats(cfg, cb['message']['chat']['id'], cb_user_id, 'main', cb['message']['message_id'])
                    elif cb_data == 'admin_stats_traffic':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_stats(cfg, cb['message']['chat']['id'], cb_user_id, 'traffic', cb['message']['message_id'])
                    elif cb_data == 'adm_udp_soon':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        _ut = ('🛡 <b>UDP Custom — скоро будет!</b>' + chr(10) + chr(10) +
                               '🚧 Раздел в разработке.')
                        _uk = {'inline_keyboard': [
                            [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
                        ]}
                        tg_request(cfg['BOT_TOKEN'], 'editMessageText', {
                            'chat_id': cb['message']['chat']['id'],
                            'message_id': cb['message']['message_id'],
                            'text': _ut, 'parse_mode': 'HTML', 'reply_markup': _uk
                        })
                    elif cb_data == 'adm_whitedns':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_adm_whitedns(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data == 'wd_servers':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_wd_servers(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data == 'wd_resolvers':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_wd_resolvers(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data == 'wd_profiles':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_wd_profiles(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data == 'wd_stats':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_wd_stats(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                    elif cb_data.startswith('wd_srv_edit_'):
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        try:
                            _idx = int(cb_data.rsplit('_', 1)[1])
                        except:
                            _idx = 0
                        try:
                            from bot_modules import db as _wddb
                            _wddb.set_pending(cb_user_id, 'wd_srv_edit:' + str(_idx))
                        except: pass
                        show_wd_server_edit(cfg, cb['message']['chat']['id'], cb_user_id, _idx, cb['message']['message_id'])
                    elif cb_data.startswith('wd_srv_clear_'):
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id'], 'text': '🗑 Очищено'})
                        try:
                            _idx = int(cb_data.rsplit('_', 1)[1])
                        except:
                            _idx = 0
                        _servers = _wd_read_servers()
                        _servers[_idx] = ''
                        _wd_save_servers(_servers)
                        show_wd_server_edit(cfg, cb['message']['chat']['id'], cb_user_id, _idx, cb['message']['message_id'])
                    elif cb_data.startswith('wd_res_edit_'):
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        try:
                            _idx = int(cb_data.rsplit('_', 1)[1])
                        except:
                            _idx = 0
                        try:
                            from bot_modules import db as _wddb
                            _wddb.set_pending(cb_user_id, 'wd_res_edit:' + str(_idx))
                        except: pass
                        show_wd_resolver_edit(cfg, cb['message']['chat']['id'], cb_user_id, _idx, cb['message']['message_id'])
                    elif cb_data.startswith('wd_res_clear_'):
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id'], 'text': '🗑 Очищено'})
                        try:
                            _idx = int(cb_data.rsplit('_', 1)[1])
                        except:
                            _idx = 0
                        try:
                            open(_wd_res_path(_idx), 'w').close()
                        except:
                            pass
                        show_wd_resolver_edit(cfg, cb['message']['chat']['id'], cb_user_id, _idx, cb['message']['message_id'])
                    elif cb_data in ('wd_prof_3g', 'wd_prof_wifi', 'wd_prof_adsl'):
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        _pidx = {'wd_prof_3g': 0, 'wd_prof_wifi': 1, 'wd_prof_adsl': 2}[cb_data]
                        try:
                            from bot_modules import db as _wddb
                            _wddb.set_pending(cb_user_id, 'wd_prof_edit:' + str(_pidx))
                        except: pass
                        show_wd_profile_edit(cfg, cb['message']['chat']['id'], cb_user_id, _pidx, cb['message']['message_id'])
                    elif cb_data.startswith('wd_prof_clear_'):
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id'], 'text': '🗑 Очищено'})
                        try:
                            _pidx = int(cb_data.rsplit('_', 1)[1])
                        except:
                            _pidx = 0
                        _wd_save_profile(_pidx, '')
                        show_wd_profile_edit(cfg, cb['message']['chat']['id'], cb_user_id, _pidx, cb['message']['message_id'])
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
                    elif cb_data == 'adm_ch_add':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_add_channel(cfg, cb['message']['chat']['id'], cb_user_id)
                        continue
                    elif cb_data == 'adm_ch_del':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_delete_channels(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                        continue
                    elif cb_data.startswith('adm_ch_delok:'):
                        try:
                            _idx = int(cb_data.split(':', 1)[1])
                        except: _idx = 0
                        do_delete_channel(cfg, cb, _idx)
                        continue
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
                    elif cb_data.startswith('cab_key_delok:'):
                        key_name = cb_data.split(':', 1)[1]
                        _do_key_delete(cfg, cb, cb_user_id, key_name)
                        continue
                    elif cb_data == 'stars_pay':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        # Читаем pending stars_confirm
                        try:
                            from bot_modules import db as _dbs
                            _pend = _dbs.get_pending(cb_user_id) or ''
                        except: _pend = ''
                        if not _pend.startswith('stars_confirm:'):
                            send_message(cfg['BOT_TOKEN'], cb['message']['chat']['id'], '❌ Сессия истекла. Начни заново')
                            continue
                        try:
                            _parts = _pend.split(':')
                            _amt = float(_parts[1])
                            _stars = int(_parts[2])
                        except:
                            send_message(cfg['BOT_TOKEN'], cb['message']['chat']['id'], '❌ Ошибка сессии')
                            continue
                        # Отправляем счёт
                        import time as _t
                        _payload = f'stars_{cb_user_id}_{int(_t.time())}'
                        _prices = [{'label': f'Пополнение на {_amt:.2f} USDT', 'amount': _stars}]
                        _inv = tg_request(cfg['BOT_TOKEN'], 'sendInvoice', {
                            'chat_id': cb_user_id,
                            'title': 'Пополнение баланса',
                            'description': f'Пополнение на {_amt:.2f} USDT через Telegram Stars',
                            'payload': _payload,
                            'currency': 'XTR',
                            'prices': json.dumps(_prices),
                            'provider_token': ''
                        })
                        if _inv and _inv.get('ok'):
                            # Сохраняем в pending на случай перезапуска
                            try:
                                _dbs.set_pending(cb_user_id, f'stars_invoice:{_amt}:{_stars}:{_payload}')
                            except: pass
                            log.info(f'Stars invoice: user={cb_user_id} amt={_amt} stars={_stars}')
                        else:
                            _err = _inv.get('description', '?') if _inv else 'нет ответа'
                            send_message(cfg['BOT_TOKEN'], cb['message']['chat']['id'], f'❌ Ошибка счёта: {_err}')
                            log.error(f'Stars invoice error: {_err}')
                        continue
                    elif cb_data.startswith('vip_hwid_skip:'):
                        # Админ пропустил ввод HWID
                        try:
                            _parts_skip = cb_data.split(':', 2)
                            _tariff_skip = int(_parts_skip[1])
                        except:
                            _tariff_skip = 1
                        _name_skip = _parts_skip[2] if len(_parts_skip) > 2 else ""
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        try:
                            from bot_modules import db as _dbsk
                            _dbsk.clear_pending(cb_user_id)
                            _dbsk.set_pending(cb_user_id, f'vip_ready:{_tariff_skip}:{_name_skip}:')
                        except: pass
                        try:
                            from bot_modules.cabinet import show_vip_final_confirm as _svfc
                            _svfc(cfg, cb['message']['chat']['id'], cb_user_id, _tariff_skip, _name_skip)
                        except Exception as _e:
                            log.error(f"show_vip_final_confirm (skip): {_e}")
                        continue
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
                    elif cb_data == 'adm_users_menu':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_users_menu(cfg, cb['message']['chat']['id'], cb_user_id, cb['message']['message_id'])
                        continue
                    elif cb_data.startswith('adm_users_test:'):
                        try:
                            pg = int(cb_data.split(':', 1)[1])
                        except: pg = 1
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_users_test(cfg, cb['message']['chat']['id'], cb_user_id, pg, cb['message']['message_id'])
                        continue
                    elif cb_data.startswith('adm_users_vip:'):
                        try:
                            pg = int(cb_data.split(':', 1)[1])
                        except: pg = 1
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_users_vip(cfg, cb['message']['chat']['id'], cb_user_id, pg, cb['message']['message_id'])
                        continue
                    elif cb_data.startswith('adm_users_tg:'):
                        try:
                            pg = int(cb_data.split(':', 1)[1])
                        except: pg = 1
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        show_users_tg(cfg, cb['message']['chat']['id'], cb_user_id, pg, cb['message']['message_id'])
                        continue
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
                    # Пропустить HWID (только админ)
                    elif cb_data == 'test_hwid_skip':
                        if not is_admin(cfg, cb_user_id):
                            tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                                'callback_query_id': cb['id'],
                                'text': '\u274C Только для админа',
                                'show_alert': True
                            })
                            continue
                        try:
                            from bot_modules import db as _tdbs
                            _tdbs.clear_pending(cb_user_id)
                        except: pass
                        handle_test(cfg, cb['message']['chat']['id'], cb_user_id, cb_first_name, cb['id'], hwid='')
                    # Кнопка из ЛИЧКИ → обычный /test
                    elif cb_data == 'get_test':
                        handle_test(cfg, cb['message']['chat']['id'], cb_user_id, cb_first_name, cb['id'])
                    else:
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                    continue
                if 'message' not in upd: continue
                msg = upd['message']; chat_id = msg['chat']['id']; user_id = msg['from']['id']; first_name = msg['from'].get('first_name','')
                text = msg.get('text','')

                # === PHOTO handler (чек пополнения) ===
                try:
                    from bot_modules import db as _dbp
                    _pend_ph = _dbp.get_pending(user_id)
                except: _pend_ph = None

                if 'photo' in msg:
                    if _pend_ph == 'topup_check':
                        _file_id = msg['photo'][-1]['file_id']
                        _dbp.set_pending(user_id, 'topup_amount:' + _file_id)
                        NLp = chr(10)
                        ask = NLp.join([
                            "✅ <b>ФОТО ПОЛУЧЕНО</b>",
                            "",
                            "━━━━━━━━━━━━━━━━━━━━",
                            "📝 <b>ШАГ 2/2</b>",
                            "━━━━━━━━━━━━━━━━━━━━",
                            "",
                            "Напиши сумму в <b>USDT</b>, которую",
                            "нужно зачислить на баланс.",
                            "",
                            "Например: <code>5</code> или <code>10.5</code>",
                            "",
                            "💡 Курс: 1 USDT ≈ 20 манат",
                            "Например, за 100 манат → ~5 USDT"
                        ])
                        send_message(cfg['BOT_TOKEN'], chat_id, ask, parse_mode='HTML')
                        continue
                    else:
                        NLp2 = chr(10)
                        hint = NLp2.join([
                            "⚠️ <b>Чтобы отправить чек:</b>",
                            "",
                            "1. /cabinet → 💰 Баланс",
                            "2. 💵 Пополнить → 💳 Ручное (TMCELL)",
                            "3. 📸 Отправить чек",
                            "",
                            "И тогда отправь фото 👇"
                        ])
                        send_message(cfg['BOT_TOKEN'], chat_id, hint, parse_mode='HTML')
                        continue

                if ('document' in msg or 'sticker' in msg) and _pend_ph == 'topup_check':
                    send_message(cfg['BOT_TOKEN'], chat_id,
                        "⚠️ Отправь именно <b>фото</b> (скриншот), не файл и не стикер.",
                        parse_mode='HTML')
                    continue
                
                # Обработка ввода промокода
                try:
                    from bot_modules import db as _db
                    pending = _db.get_pending(user_id)
                except: pending = None
                if pending and pending.startswith('wd_srv_edit:') and text and not text.startswith('/'):
                    _db.clear_pending(user_id)
                    try:
                        _idx = int(pending.split(':', 1)[1])
                    except:
                        _idx = 0
                    _txt = text.strip()
                    _servers = _wd_read_servers()
                    if _txt == '-':
                        _servers[_idx] = ''
                    else:
                        _servers[_idx] = _txt
                    _wd_save_servers(_servers)
                    NLx = chr(10)
                    _ok_msg = NLx.join([
                        '✅ <b>Сохранено</b>',
                        '━━━━━━━━━━━━━━━━━━━━',
                        'Новое значение записано.',
                    ])
                    _kb = {'inline_keyboard': [
                        [{'text': '⬅️ К серверам', 'callback_data': 'wd_servers'}]
                    ]}
                    tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                        'chat_id': user_id, 'text': _ok_msg, 'parse_mode': 'HTML', 'reply_markup': _kb
                    })
                    continue
                if pending and pending.startswith('wd_res_edit:') and text and not text.startswith('/'):
                    _db.clear_pending(user_id)
                    try:
                        _idx = int(pending.split(':', 1)[1])
                    except:
                        _idx = 0
                    _txt = text.strip()
                    _path = _wd_res_path(_idx)
                    if _txt == '-':
                        open(_path, 'w').close()
                    else:
                        with open(_path, 'w') as _wf:
                            _wf.write(_txt + chr(10))
                    try:
                        import os as _os
                        _os.chmod(_path, 0o600)
                    except: pass
                    _cnt = len([l for l in _txt.split(chr(10)) if l.strip()]) if _txt != '-' else 0
                    NLx = chr(10)
                    _ok_msg = NLx.join([
                        '✅ <b>Сохранено</b>',
                        '━━━━━━━━━━━━━━━━━━━━',
                        'IP в файле: <b>' + str(_cnt) + '</b>',
                    ])
                    _kb = {'inline_keyboard': [
                        [{'text': '⬅️ К резолверам', 'callback_data': 'wd_resolvers'}]
                    ]}
                    tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                        'chat_id': user_id, 'text': _ok_msg, 'parse_mode': 'HTML', 'reply_markup': _kb
                    })
                    continue
                if pending and pending.startswith('wd_prof_edit:') and text and not text.startswith('/'):
                    _db.clear_pending(user_id)
                    try:
                        _pidx = int(pending.split(':', 1)[1])
                    except:
                        _pidx = 0
                    _txt = text.strip()
                    if _txt == '-':
                        _wd_save_profile(_pidx, '')
                    else:
                        _wd_save_profile(_pidx, _txt)
                    _cnt = 0 if _txt == '-' else len([l for l in _txt.split(chr(10)) if l.strip()])
                    NLx = chr(10)
                    _ok_msg = NLx.join([
                        '✅ <b>Профиль сохранён</b>',
                        '━━━━━━━━━━━━━━━━━━━━',
                        'Строк: <b>' + str(_cnt) + '</b>',
                    ])
                    _kb = {'inline_keyboard': [
                        [{'text': '⬅️ К профилям', 'callback_data': 'wd_profiles'}]
                    ]}
                    tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                        'chat_id': user_id, 'text': _ok_msg, 'parse_mode': 'HTML', 'reply_markup': _kb
                    })
                    continue
                if pending and pending.startswith('vip_name:') and text and not text.startswith('/'):
                    _db.clear_pending(user_id)
                    try:
                        tariff_idx = int(pending.split(':', 1)[1])
                    except:
                        tariff_idx = 1
                    # Валидация имени
                    ok, result = _validate_vip_name(text)
                    if not ok:
                        NLx = chr(10)
                        err_msg = NLx.join([
                            "❌ <b>Неверное имя</b>",
                            "",
                            f"{result}",
                            "",
                            "📝 Правила:",
                            "• Только a-z, 0-9, _",
                            "• Минимум 5 символов",
                            "• Максимум 15 символов",
                            "",
                            "Попробуй ещё раз:"
                        ])
                        from bot_modules.cabinet import _send as _csend
                        _cancel_kb = {'inline_keyboard': [[{'text': '\u274C Отмена', 'callback_data': 'cab_buy_vip'}]]}
                        _csend(cfg['BOT_TOKEN'], chat_id, err_msg, reply_markup=_cancel_kb)
                        # Снова запрашиваем
                        try:
                            from bot_modules import db as _db2
                            _db2.set_pending(user_id, f'vip_name:{tariff_idx}')
                        except: pass
                        continue
                    name = result
                    # NEW: запрашиваем HWID (обязательно для клиента)
                    try:
                        from bot_modules.admin import is_admin as _is_adm
                        _adm = _is_adm(cfg, user_id)
                    except Exception:
                        _adm = False
                    _hw_kb = None
                    if _adm:
                        _hw_msg = chr(10).join([
                            "📱 <b>ВВЕДИ HWID</b>",
                            "━━━━━━━━━━━━━━━━━━━━",
                            "",
                            "Ты админ. Выбери:",
                            "• <b>Ввести HWID</b> — зашифрованный с привязкой",
                            "• <b>Пропустить</b> — открытый конфиг",
                            "",
                            "Введи HWID или нажми кнопку:",
                        ])
                        _hw_kb = {'inline_keyboard': [
                            [{'text': '➡️ Пропустить',
                              'callback_data': f'vip_hwid_skip:{tariff_idx}:{name}'}]
                        ]}
                    else:
                        _hw_msg = chr(10).join([
                            "📱 <b>ВВЕДИ HWID</b>",
                            "━━━━━━━━━━━━━━━━━━━━",
                            "",
                            "HWID — это ID устройства.",
                            "Ключ будет работать только на этом устройстве.",
                            "",
                            "Как узнать:",
                            "DarkTunnel → ⚙️ Settings → внизу <b>Hardware ID</b>",
                            "",
                            "📋 Скопируй и отправь сюда:",
                        ])
                    if _hw_kb:
                        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                            'chat_id': chat_id, 'text': _hw_msg,
                            'parse_mode': 'HTML', 'reply_markup': _hw_kb
                        })
                    else:
                        send_message(cfg['BOT_TOKEN'], chat_id, _hw_msg, parse_mode='HTML')
                    try:
                        _db.set_pending(user_id, f'vip_hwid:{tariff_idx}:{name}')
                    except: pass
                    continue

                if pending == 'test_hwid_ch' and text and not text.startswith('/'):
                    _db.clear_pending(user_id)
                    _in = text.strip()
                    _clean = _in.replace(':', '').replace(' ', '').replace('-', '')
                    if not __import__('re').match(r'^[0-9A-Fa-f]{40}$', _clean):
                        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {'chat_id': chat_id, 'text': '\u274C   HWID должен быть 40 hex-символов. Попробуй снова:', 'parse_mode': 'HTML'})
                        try:
                            _db.set_pending(user_id, 'test_hwid_ch')
                        except: pass
                        continue
                    handle_channel_test(cfg, user_id, first_name, hwid=_in)
                    continue
                if pending == 'test_hwid' and text and not text.startswith('/'):
                    _db.clear_pending(user_id)
                    _in = text.strip()
                    _clean = _in.replace(':', '').replace(' ', '').replace('-', '')
                    if not __import__('re').match(r'^[0-9A-Fa-f]{40}$', _clean):
                        send_message(cfg['BOT_TOKEN'], chat_id, '\u274C   HWID должен быть 40 hex-символов. Попробуй снова:', parse_mode='HTML')
                        try:
                            _db.set_pending(user_id, 'test_hwid')
                        except: pass
                        continue
                    handle_test(cfg, chat_id, user_id, first_name, hwid=_in)
                    continue
                if pending and pending.startswith('cab_key_hwid:') and text and not text.startswith('/'):
                    _db.clear_pending(user_id)
                    _key_name = pending.split(':', 1)[1]
                    _in = text.strip()
                    _clean = _in.replace(':', '').replace(' ', '').replace('-', '')
                    if not __import__('re').match(r'^[0-9A-Fa-f]{40}$', _clean):
                        send_message(cfg['BOT_TOKEN'], chat_id, '\u274C   HWID должен быть 40 hex-символов. Попробуй снова:', parse_mode='HTML')
                        try:
                            _db.set_pending(user_id, 'cab_key_hwid:' + _key_name)
                        except: pass
                        continue
                    try:
                        from bot_modules.cabinet import do_key_reset_hwid as _dkrh
                        _dkrh(cfg, chat_id, user_id, _key_name, _in)
                    except Exception as _e:
                        log.error(f'cab_key_hwid handler: {_e}')
                        send_message(cfg['BOT_TOKEN'], chat_id, f'\u274C   Ошибка: {_e}')
                    continue
                if pending and pending.startswith('vip_hwid:') and text and not text.startswith('/'):
                    _db.clear_pending(user_id)
                    _parts = pending.split(':', 2)
                    try:
                        _tariff_idx = int(_parts[1])
                    except:
                        _tariff_idx = 1
                    _name = _parts[2] if len(_parts) > 2 else ""
                    try:
                        from bot_modules.admin import is_admin as _is_adm2
                        _adm2 = _is_adm2(cfg, user_id)
                    except Exception:
                        _adm2 = False
                    _hwid_in = text.strip()
                    if _hwid_in == "-" and _adm2:
                        _hwid_val = None
                    elif _hwid_in == "-" and not _adm2:
                        send_message(cfg['BOT_TOKEN'], chat_id, "❌  HWID обязателен. Введи значение.", parse_mode='HTML')
                        try:
                            _db.set_pending(user_id, f'vip_hwid:{_tariff_idx}:{_name}')
                        except: pass
                        continue
                    else:
                        _clean = _hwid_in.replace(":", "").replace(" ", "").replace("-", "")
                        if not __import__('re').match(r'^[0-9A-Fa-f]{40}$', _clean):
                            send_message(cfg['BOT_TOKEN'], chat_id, "❌  HWID должен быть 40 hex-символов:", parse_mode='HTML')
                            try:
                                _db.set_pending(user_id, f'vip_hwid:{_tariff_idx}:{_name}')
                            except: pass
                            continue
                        _hwid_val = _hwid_in
                    try:
                        from bot_modules.cabinet import show_vip_final_confirm
                        show_vip_final_confirm(cfg, chat_id, user_id, _tariff_idx, _name)
                    except Exception as e:
                        log.error(f"show_vip_final_confirm: {e}")
                        send_message(cfg['BOT_TOKEN'], chat_id, f"❌  Ошибка: {e}")
                    try:
                        _hwid_store = _hwid_val if _hwid_val else ""
                        _db.set_pending(user_id, f'vip_ready:{_tariff_idx}:{_name}:{_hwid_store}')
                    except: pass
                    continue

                if pending == 'stars_amount' and text and not text.startswith('/'):
                    import math as _math
                    # Читаем конфиг
                    _rate = 0.015
                    _smin = 1.0
                    _smax = 100.0
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
                    try:
                        _amt = float(text.strip().replace(',', '.'))
                    except:
                        send_message(cfg['BOT_TOKEN'], chat_id, '❌ Отправь число. Например: <code>5</code>', parse_mode='HTML')
                        continue
                    if _amt < _smin:
                        send_message(cfg['BOT_TOKEN'], chat_id, f'❌ Минимум {_smin:.0f} USDT')
                        continue
                    if _amt > _smax:
                        send_message(cfg['BOT_TOKEN'], chat_id, f'❌ Максимум {_smax:.0f} USDT')
                        continue
                    # Считаем Stars (округление вверх)
                    _stars = int(_math.ceil(_amt / _rate))
                    # Запоминаем в pending
                    _db.set_pending(user_id, 'stars_confirm:' + str(_amt) + ':' + str(_stars))
                    NLs = chr(10)
                    _msg = NLs.join([
                        '⭐ <b>ПОДТВЕРЖДЕНИЕ ОПЛАТЫ</b>',
                        '━━━━━━━━━━━━━━━━━━━━',
                        '',
                        f'💵 К зачислению: <b>{_amt:.2f} USDT</b>',
                        f'⭐ К оплате: <b>{_stars} Stars</b>',
                        f'📊 Курс: 1 Star = {_rate} USDT',
                        '',
                        '━━━━━━━━━━━━━━━━━━━━',
                        '<i>Оплата через Telegram Stars</i>'
                    ])
                    _kb = {'inline_keyboard': [
                        [{'text': f'✅ Оплатить {_stars} ⭐', 'callback_data': 'stars_pay'}],
                        [{'text': '⬅️ Отмена', 'callback_data': 'cab_topup_stars'}]
                    ]}
                    send_message(cfg['BOT_TOKEN'], chat_id, _msg, reply_markup=_kb)
                    continue

                if pending and pending.startswith('topup_amount:') and text and not text.startswith('/'):
                    _file_id = pending.split(':', 1)[1]
                    try:
                        amount = float(text.strip().replace(',', '.'))
                    except:
                        send_message(cfg['BOT_TOKEN'], chat_id, '❌ Отправь число. Например: <code>10</code>', parse_mode='HTML')
                        continue
                    if amount < 1:
                        send_message(cfg['BOT_TOKEN'], chat_id, '❌ Минимум 1 USDT')
                        continue
                    if amount > 10000:
                        send_message(cfg['BOT_TOKEN'], chat_id, '❌ Слишком большая сумма. Максимум 10000 USDT')
                        continue
                    # Всё ок — чистим pending
                    _db.clear_pending(user_id)
                    user = _db.get_user(user_id) or {}
                    admin_id = cfg.get('ADMIN_ID', '')
                    balance = _db.get_balance(user_id)
                    u_name = user.get('first_name') or '—'
                    u_uname = user.get('username') or ''
                    # 1. Отправляем фото по file_id (forward не сработает — фото в другом сообщении)
                    try:
                        tg_request(cfg['BOT_TOKEN'], 'sendPhoto', {
                            'chat_id': admin_id,
                            'photo': _file_id,
                            'caption': f'💵 Чек от {u_name} (ID {user_id})'
                        })
                    except Exception as e:
                        log.error(f'topup sendPhoto error: {e}')
                    # 2. Уведомление админу
                    NLx = chr(10)
                    admin_msg = NLx.join([
                        "💵 <b>НОВАЯ ЗАЯВКА НА ПОПОЛНЕНИЕ</b>",
                        "━━━━━━━━━━━━━━━━━━━━",
                        "",
                        f"👤 Имя: <b>{u_name}</b>",
                        f"🆔 ID: <code>{user_id}</code>",
                        f"📱 Username: @{u_uname}" if u_uname else "📱 Username: —",
                        f"💰 Баланс до: <b>{balance:.2f} USDT</b>",
                        "",
                        f"💵 Хочет получить: <b>{amount:.2f} USDT</b>",
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
                        log.error(f'topup admin send: {e}')
                    # 3. Подтверждение юзеру
                    NLx2 = chr(10)
                    ok_text = NLx2.join([
                        "✅ <b>ЗАЯВКА ОТПРАВЛЕНА</b>",
                        "",
                        "━━━━━━━━━━━━━━━━━━━━",
                        "📸 Фото чека: ✅",
                        f"💵 Сумма: <b>{amount:.2f} USDT</b>",
                        "━━━━━━━━━━━━━━━━━━━━",
                        "",
                        "Админ проверит и пополнит баланс",
                        "в течение 15-30 минут.",
                        "",
                        f"💬 {get_support()} — если долго нет ответа"
                    ])
                    kb_ok = {'inline_keyboard': [
                        [{'text': '👤 Личный кабинет', 'callback_data': 'cab_main'}]
                    ]}
                    tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                        'chat_id': chat_id,
                        'text': ok_text,
                        'parse_mode': 'HTML',
                        'reply_markup': kb_ok
                    })
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
                            'no_vip_key': f'⚠️ У тебя нет активного VIP-ключа.\n\nПромокод даёт дни только к VIP. Купи VIP: {get_support()}'
                        }
                        msg_text = reasons.get(reason, '❌ Ошибка активации')
                    send_message(cfg['BOT_TOKEN'], chat_id, msg_text, parse_mode='HTML')
                    continue

                # Обработка ответа на ForceReply
                if user_id in PENDING_ACTIONS and msg.get('reply_to_message'):
                    action = PENDING_ACTIONS.pop(user_id)
                    if action == 'addchannel':
                        _do_addchannel(cfg['BOT_TOKEN'], chat_id, text)
                    elif action == 'addchannel_new':
                        _do_addchannel_new(cfg['BOT_TOKEN'], chat_id, text)
                    elif action == 'delchannel':
                        _do_delchannel(cfg['BOT_TOKEN'], chat_id, text)
                    elif action == 'newpromo':
                        _do_newpromo(cfg, chat_id, text)
                    elif action == 'addbalance':
                        _do_addbalance(cfg, chat_id, text)
                    elif action == 'broadcast_text':
                        _do_broadcast_preview(cfg, chat_id, text)
                    elif action.startswith('promo_post:'):
                        _pcode = action.split(':', 1)[1]
                        # Сохраняем текст во временный файл (для публикации)
                        try:
                            with open(f'/tmp/promo_post_{_pcode}.txt', 'w') as _pf:
                                _pf.write(text)
                        except Exception as _pe:
                            log.error(f'promo_post save: {_pe}')
                        _show_promo_preview(cfg, chat_id, _pcode, text)
                    elif action.startswith('edit_text:'):
                        _key = action.split(':', 1)[1]
                        if _key in EDIT_FILES:
                            _info = EDIT_FILES[_key]
                            _path = '/etc/UDPCustom/' + _info['file']
                            try:
                                with open(_path, 'w') as _f:
                                    _f.write(text)
                                    # Для SSH-баннера — перезапуск SSH
                                    if _key == 'ssh_banner':
                                        import subprocess as _sp
                                        _sp.run(['systemctl', 'restart', 'ssh'], capture_output=True, timeout=10)
                                        _sp.run(['systemctl', 'restart', 'sshd'], capture_output=True, timeout=10)
                                NLx = chr(10)
                                _ok = NLx.join([
                                    '✅ <b>ТЕКСТ СОХРАНЁН</b>',
                                    '━━━━━━━━━━━━━━━━━━━━',
                                    '',
                                    '📁 Файл: <code>' + _info['file'] + '</code>',
                                    '✏️ Размер: <b>' + str(len(text)) + '</b> символов',
                                    '',
                                    '🔄 Бот подхватит изменения автоматически'
                                ])
                                kb = {'inline_keyboard': [
                                    [{'text': '📝 К списку', 'callback_data': 'adm_edit_texts'}],
                                    [{'text': '🏠 В админ-панель', 'callback_data': 'adm_main'}]
                                ]}
                                tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                                    'chat_id': chat_id,
                                    'text': _ok,
                                    'parse_mode': 'HTML',
                                    'reply_markup': kb
                                })
                            except Exception as _e:
                                send_message(cfg['BOT_TOKEN'], chat_id, '❌ Ошибка сохранения: ' + str(_e))
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
                                        ref_name = msg['from'].get('first_name', '') or 'Юзер'
                                        ref_uname = msg['from'].get('username', '') or ''
                                        ref_handle = f"@{ref_uname}" if ref_uname else f"id{user_id}"
                                        NLx = chr(10)
                                        notif = NLx.join([
                                            "👥 <b>НОВЫЙ РЕФЕРАЛ!</b>",
                                            "━━━━━━━━━━━━━━━━━━━━",
                                            "",
                                            f"👤 <b>{ref_name}</b> · {ref_handle}",
                                            "",
                                            "💎 Когда купит VIP, ты получишь:",
                                            "   💵 +1 USDT на баланс",
                                            "   ⏰ +5 дней к своему VIP"
                                        ])
                                        tg_request(cfg['BOT_TOKEN'], 'sendMessage', {
                                            'chat_id': inviter['tg_id'],
                                            'text': notif,
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
                        try:
                            from bot_modules import db as _dbsrc
                            _dbsrc.set_user_source(user_id, 'channel')
                        except Exception as _e:
                            log.error(f"set_user_source ch: {_e}")
                        log.info(f"Юзер {user_id} verified через канал (на {hours}ч)")
                        handle_start(cfg, chat_id, user_id, first_name, True)
                    else:
                        try:
                            from bot_modules import db as _dbsrc
                            _dbsrc.set_user_source(user_id, 'bot')
                        except Exception as _e:
                            log.error(f"set_user_source bot: {_e}")
                        handle_start(cfg, chat_id, user_id, first_name)
                elif text == '\U0001F4F2 Тест' or text.startswith('/test'): handle_test(cfg, chat_id, user_id, first_name)
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
                elif text.startswith('/autopost'): handle_autopost(cfg, chat_id, user_id, text[9:].strip())
                elif text.startswith('/restart'): handle_restart(cfg, chat_id, user_id, text[8:].strip())
                elif text == '\U0001F464 Кабинет' or text.startswith('/cabinet'): show_cabinet(cfg, chat_id, user_id, first_name)
                elif text == '\u2699\uFE0F Админка' or text.startswith('/admin'): show_admin_panel(cfg, chat_id, user_id)
                elif text == '\U0001F381 Помощь' or text.startswith('/help'): handle_help(cfg, chat_id)
        except KeyboardInterrupt: log.info("Остановка"); break
        except Exception as e: log.error(f"Ошибка в main loop: {e}"); time.sleep(5)

if __name__ == '__main__':
    main()
