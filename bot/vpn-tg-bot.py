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


def create_test_user(cfg):
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
uid=$(id -u "$username"); iptables -C VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null || iptables -A VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN
exp_date=$(date -d "+$hours hours +2 days" +%Y-%m-%d)
chage -E "$exp_date" "$username"
mkdir -p /etc/UDPCustom/expire_ts
echo $(( $(date +%s) + hours * 3600 )) > "/etc/UDPCustom/expire_ts/$username"
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


def handle_start(cfg, chat_id, user_id, first_name):
    token = cfg['BOT_TOKEN']
    name = first_name or 'друг'
    channels = get_channels()
    
    if not channels:
        send_message(token, chat_id, "❌ Каналы не настроены. Обратись: @ArsenGuro")
        return
    
    primary = channels[0].lstrip('@')
    others = [ch.lstrip('@') for ch in channels[1:]]
    
    # Список спонсоров
    sponsors_list = ""
    for ch in others:
        sponsors_list += f"   👉 @{ch}\n"
    sponsors_list = sponsors_list.rstrip('\n')
    
    # Читаем шаблон
    template = get_start_text()
    if template:
        text = template.replace('{name}', name)
        text = text.replace('{primary}', primary)
        text = text.replace('{sponsors_list}', sponsors_list)
    else:
        # Fallback если файла нет
        text = (
            f"👋 Привет, {name}!\n\n"
            f"🎁 Тестовые ключи выдаются в наших каналах!\n\n"
            f"📢 Зайди: @{primary}\n"
            f"👇 Найди пост с кнопкой «🎁 Получить тест» и нажми её\n\n"
            f"💬 @ArsenGuro"
        )
    
    # Кнопки
    keyboard = {'inline_keyboard': []}
    keyboard['inline_keyboard'].append([{'text': f'📢 Основной: @{primary}', 'url': f'https://t.me/{primary}'}])
    for ch in others:
        keyboard['inline_keyboard'].append([{'text': f'📢 Спонсор: @{ch}', 'url': f'https://t.me/{ch}'}])
    keyboard['inline_keyboard'].append([{'text': '💎 Купить VIP-ключ', 'url': 'https://t.me/ArsenGuro'}])
    keyboard['inline_keyboard'].append([{'text': '💬 Поддержка', 'url': 'https://t.me/ArsenGuro'}])
    
    send_message(token, chat_id, text, reply_markup=keyboard)


def handle_test(cfg, chat_id, user_id, first_name):
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
            keyboard = {'inline_keyboard': []}
            for ch in not_sub:
                keyboard['inline_keyboard'].append([{'text': f'📢 Подписаться {ch}', 'url': f'https://t.me/{ch}'}])
            keyboard['inline_keyboard'].append([{'text': '✅ Я подписался', 'callback_data': 'get_test'}])
            send_message(token, chat_id, "⚠️ Сначала подпишись на каналы ниже, потом нажми кнопку:", reply_markup=keyboard)
            return
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        cooldown_hours = int(cfg.get('COOLDOWN_HOURS','24'))
        ok, remaining = check_cooldown(user_id, cooldown_hours)
        if not ok:
            send_message(token, chat_id, f"⏰ Попробуй через {format_time(remaining)}."); return
    send_message(token, chat_id, "⏳ Создаём аккаунт...")
    username, password = create_test_user(cfg)
    if not username:
        send_message(token, chat_id, "❌ Ошибка. Попробуй позже."); return
    record_issue(user_id, username)
    domain = get_domain(); ws_port = get_ws_port(); proxy = get_random_proxy()
    connect_line = f"{domain}:{ws_port}@{username}:{password}"
    traffic = cfg.get('TEST_TRAFFIC_GB','100'); devices = cfg.get('TEST_DEVICES','10')
    text = (f"🎉 Тестовый доступ готов!\n\n"
            f"📲 Строка для DarkTunnel:\n\n<code>{connect_line}</code>\n\n"
            f"📱 Логин: {username}\n🔑 Пароль: {password}\n"
            f"🌐 Сервер: {domain}\n🔌 Порт: {ws_port}\n")
    if proxy: text += f"🛡️ Прокси: {proxy}:80\n"
    text += f"\n⏰ {cfg.get('TEST_HOURS','8')} ч | 📊 {traffic} ГБ | 💻 {devices} устр.\n\n"
    text += f"💬 @ArsenGuro\n📢 @ArsenVipKeys"
    send_message(token, chat_id, text, parse_mode="HTML")

    # Ссылка darktunnel://
    dt_url = generate_darktunnel_url(username, password, domain, ws_port, proxy, cfg)
    if dt_url:
        send_message(token, chat_id, "🔗 Ссылка-конфиг (тап → копировать):\n\n<code>" + dt_url + "</code>", parse_mode="HTML")

    if admin_id:
        send_message(token, admin_id, f"🔔 Выдача: {username} (TG: {user_id})")
    log.info(f"Выдан тест: {username}")


def handle_help(cfg, chat_id):
    token = cfg['BOT_TOKEN']
    send_message(token, chat_id, "📖 Команды:\n/start — Приветствие\n/test — Получить тест\n/help — Справка\n\n💬 @ArsenGuro\n📢 @ArsenVipKeys")

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
    
    target_channel = channels[0]
    if not target_channel.startswith('@'):
        target_channel = '@' + target_channel
    
    # Кнопка
    keyboard = {
        'inline_keyboard': [
            [{'text': '🎁 Получить тест', 'callback_data': 'channel_test'}]
        ]
    }
    
    # Отправляем в канал
    result = tg_request(token, 'sendMessage', {
        'chat_id': target_channel,
        'text': post_text,
        'reply_markup': keyboard
    })
    
    if result and result.get('ok'):
        send_message(token, chat_id, f"✅ Пост опубликован в {target_channel}")
        log.info(f"Пост опубликован в {target_channel}")
    else:
        error = result.get('description', 'неизвестная ошибка') if result else 'нет ответа'
        send_message(token, chat_id, f"❌ Ошибка публикации: {error}")
        log.error(f"Ошибка публикации: {error}")


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
        cooldown_hours = int(cfg.get('COOLDOWN_HOURS', '24'))
        ok, remaining = check_cooldown(user_id, cooldown_hours)
        if not ok:
            tg_request(token, 'sendMessage', {
                'chat_id': user_id,
                'text': f"⏰ Ты уже получал тест. Попробуй через {format_time(remaining)}."
            })
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
    username, password = create_test_user(cfg)
    if not username:
        send_message(token, user_id, "❌ Ошибка создания. Попробуй позже.")
        return
    
    record_issue(user_id, username)
    
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
    
    send_message(token, user_id, text, parse_mode='HTML')
    
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
                    # Кнопка из ЛИЧКИ → обычный /test
                    elif cb_data == 'get_test':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                            'callback_query_id': cb['id'],
                            'text': '⏳ Создаём ключ...',
                            'show_alert': False
                        })
                        handle_test(cfg, cb['message']['chat']['id'], cb_user_id, cb_first_name)
                    else:
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                    continue
                if 'message' not in upd: continue
                msg = upd['message']; chat_id = msg['chat']['id']; user_id = msg['from']['id']; first_name = msg['from'].get('first_name','')
                text = msg.get('text','')
                if text.startswith('/start'): handle_start(cfg, chat_id, user_id, first_name)
                elif text.startswith('/test'): handle_test(cfg, chat_id, user_id, first_name)
                elif text.startswith('/post'): post_to_channel(cfg, chat_id, user_id)
                elif text.startswith('/help'): handle_help(cfg, chat_id)
        except KeyboardInterrupt: log.info("Остановка"); break
        except Exception as e: log.error(f"Ошибка в main loop: {e}"); time.sleep(5)

if __name__ == '__main__':
    main()
