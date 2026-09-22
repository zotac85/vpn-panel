#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VPN Panel Telegram Bot — с переносами строк и отправкой .dark файла
"""

import os, sys, json, time, logging, subprocess, secrets, string, urllib.request, urllib.parse, mimetypes, uuid
from datetime import datetime

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
        'REQUIRE_SUBSCRIPTION':'0', 'COOLDOWN_HOURS':'24', 'TEST_DAYS':'1',
        'TEST_DEVICES':'10', 'TEST_TRAFFIC_GB':'100',
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

def create_test_user(cfg):
    for _ in range(20):
        username = "test" + gen_random(6)
        r = subprocess.run(['id', username], capture_output=True)
        if r.returncode != 0: break
    else:
        return None, None
    password = gen_random(8)
    days = int(cfg.get('TEST_DAYS','1')); devices = int(cfg.get('TEST_DEVICES','10')); traffic_gb = int(cfg.get('TEST_TRAFFIC_GB','100'))
    bash_script = f'''
set -e
username="{username}"; password="{password}"; days={days}; devices={devices}; traffic_gb={traffic_gb}
useradd -M -s /bin/false "$username"; echo "$username:$password" | chpasswd
echo "$username" >> /etc/UDPCustom/users.db
sort -u -o /etc/UDPCustom/users.db /etc/UDPCustom/users.db
echo "$devices" > "/etc/UDPCustom/limits/$username"
sed -i "/^${{username}}[[:space:]]\\+hard[[:space:]]\\+maxlogins/d" /etc/security/limits.conf
echo "$username hard maxlogins $devices" >> /etc/security/limits.conf
mkdir -p /etc/UDPCustom/traffic_limits /etc/UDPCustom/traffic
bytes=$((traffic_gb * 1073741824)); echo "$bytes" > "/etc/UDPCustom/traffic_limits/$username"; echo "0" > "/etc/UDPCustom/traffic/$username"
uid=$(id -u "$username"); iptables -C VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null || iptables -A VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN
exp_date=$(date -d "+$days days" +%Y-%m-%d); chage -E "$exp_date" "$username"
echo "OK"
'''
    try:
        r = subprocess.run(['bash','-c',bash_script], capture_output=True, text=True, timeout=30)
        if 'OK' in r.stdout:
            log.info(f"Создан тестовый: {username}")
            return username, password
        log.error(f"Ошибка создания: {r.stderr}")
        return None, None
    except Exception as e:
        log.error(f"Exception: {e}")
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
    if not channel: return True
    r = tg_request(token, 'getChatMember', {'chat_id': channel, 'user_id': user_id})
    if not r or not r.get('ok'): return True
    return r.get('result',{}).get('status','') in ('member','administrator','creator')

def send_message(token, chat_id, text, reply_markup=None, parse_mode=None):
    params = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
    if reply_markup: params['reply_markup'] = reply_markup
    if parse_mode: params['parse_mode'] = parse_mode
    return tg_request(token, 'sendMessage', params)

def format_time(seconds):
    h = seconds // 3600; m = (seconds % 3600) // 60
    return f"{h} ч {m} мин" if h > 0 else f"{m} мин"

def generate_dark_config(username, password, domain, ws_port, proxy, cfg):
    """Генерирует .dark файл (JSON) для DarkTunnel"""
    payload = cfg.get('PAYLOAD','')
    # В DarkTunnel payload передаётся как есть, с [crlf] и [lf]
    config = {
        "name": f"{cfg.get('CONFIG_NAME','VPN')}_{username}",
        "message": "",
        "connected_message": cfg.get('CONNECTED_MSG','Подключено!'),
        "hardware_id_list": [],
        "lock": True,
        "lock_ssh_account": True,
        "expiration_date": 0,
        "target": f"{domain}:{ws_port}",
        "proxy": f"{proxy}:80" if proxy else "",
        "payload": payload,
        "username": username,
        "password": password
    }
    path = f"/tmp/{username}.dark"
    with open(path, 'w') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return path

def handle_start(cfg, chat_id, user_id, first_name):
    token = cfg['BOT_TOKEN']
    keyboard = {'inline_keyboard': [
        [{'text': '🎁 Получить тест', 'callback_data': 'get_test'}],
        [{'text': '💬 Поддержка', 'url': 'https://t.me/ArsenGuro'}],
        [{'text': '📢 Наш канал', 'url': 'https://t.me/ArsenVipKeys'}]
    ]}
    text = cfg.get('WELCOME_TEXT','Добро пожаловать!')
    if first_name: text = f"👋 Привет, {first_name}!\n\n{text}"
    send_message(token, chat_id, text, reply_markup=keyboard)

def handle_test(cfg, chat_id, user_id, first_name):
    token = cfg['BOT_TOKEN']
    if is_blacklisted(user_id):
        send_message(token, chat_id, "🚫 Ты в чёрном списке. Обратись в поддержку: @ArsenGuro"); return
    if cfg.get('REQUIRE_SUBSCRIPTION','0') == '1':
        if not check_subscription(token, user_id, cfg.get('CHANNEL_ID','')):
            keyboard = {'inline_keyboard': [
                [{'text': '📢 Подписаться', 'url': f"https://t.me/{cfg['CHANNEL_ID'].lstrip('@')}"}],
                [{'text': '✅ Я подписался', 'callback_data': 'get_test'}]
            ]}
            send_message(token, chat_id, "📢 Для получения теста подпишись на канал, потом нажми кнопку ниже.", reply_markup=keyboard); return
    cooldown_hours = int(cfg.get('COOLDOWN_HOURS','24'))
    ok, remaining = check_cooldown(user_id, cooldown_hours)
    if not ok:
        send_message(token, chat_id, f"⏰ Ты уже получал тест. Попробуй снова через {format_time(remaining)}."); return
    send_message(token, chat_id, "⏳ Создаём твой аккаунт, подожди 5 секунд...")
    username, password = create_test_user(cfg)
    if not username:
        send_message(token, chat_id, "❌ Ошибка при создании аккаунта. Попробуй позже или напиши @ArsenGuro"); return
    record_issue(user_id, username)
    domain = get_domain(); ws_port = get_ws_port(); proxy = get_random_proxy()
    connect_line = f"{domain}:{ws_port}@{username}:{password}"
    traffic = cfg.get('TEST_TRAFFIC_GB','100'); devices = cfg.get('TEST_DEVICES','10')
    text = (
        f"🎉 Твой тестовый доступ готов!\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📲 Строка для DarkTunnel:\n\n{connect_line}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📱 Логин : {username}\n🔑 Пароль: {password}\n"
        f"🌐 Сервер: {domain}\n🔌 Порт  : {ws_port}\n"
    )
    if proxy: text += f"🛡️ Прокси: {proxy}:80\n"
    text += f"\n⏰ Срок: 24 часа\n📊 Трафик: {traffic} ГБ\n💻 Устройств: {devices}\n\n"
    text += f"💬 @ArsenGuro\n📢 @ArsenVipKeys"
    send_message(token, chat_id, text)
    # Отправляем .dark файл
    dark_path = generate_dark_config(username, password, domain, ws_port, proxy, cfg)
    if dark_path:
        tg_send_document(token, chat_id, dark_path, caption="📁 Файл конфига для DarkTunnel")
        os.remove(dark_path)
    if cfg.get('ADMIN_ID'):
        send_message(token, cfg['ADMIN_ID'], f"🔔 Новая выдача: {username} (TG: {user_id})")
    log.info(f"Выдан тест: user_id={user_id}, username={username}")

def handle_help(cfg, chat_id):
    token = cfg['BOT_TOKEN']
    send_message(token, chat_id, "📖 Команды:\n/start — Приветствие\n/test — Получить тест\n/help — Справка\n\n💬 @ArsenGuro\n📢 @ArsenVipKeys")

def main():
    cfg = load_config()
    if not cfg.get('BOT_TOKEN'):
        log.error("BOT_TOKEN не задан"); sys.exit(1)
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
                    tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                    if cb.get('data') == 'get_test':
                        handle_test(cfg, cb['message']['chat']['id'], cb['from']['id'], cb['from'].get('first_name',''))
                    continue
                if 'message' not in upd: continue
                msg = upd['message']; chat_id = msg['chat']['id']; user_id = msg['from']['id']; first_name = msg['from'].get('first_name','')
                text = msg.get('text','')
                if text.startswith('/start'): handle_start(cfg, chat_id, user_id, first_name)
                elif text.startswith('/test'): handle_test(cfg, chat_id, user_id, first_name)
                elif text.startswith('/help'): handle_help(cfg, chat_id)
        except KeyboardInterrupt: log.info("Остановка"); break
        except Exception as e: log.error(f"Ошибка в main loop: {e}"); time.sleep(5)

if __name__ == '__main__':
    main()
