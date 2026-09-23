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


def handle_start(cfg, chat_id, user_id, first_name, force_verified=None):
    token = cfg['BOT_TOKEN']
    name = first_name or 'друг'
    channels = get_channels()
    
    if not channels:
        send_message(token, chat_id, "❌ Каналы не настроены. Обратись: @ArsenGuro")
        return
    
    primary = channels[0].lstrip('@')
    verified = force_verified if force_verified is not None else is_verified(user_id)
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
            keyboard['inline_keyboard'].append([{'text': '📢 Опубликовать пост', 'callback_data': 'admin_post'}])
    
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
            keyboard['inline_keyboard'].append([{'text': '📢 Опубликовать пост', 'callback_data': 'admin_post'}])
    
    else:
        # Подписан на все, но НЕ verified → надо зайти на канал
        text = (
            f"👋 Привет, {name}!\n\n"
            f"⚠️ <b>Осталось одно действие:</b>\n\n"
            f"1️⃣ Зайди в канал 👉 @{primary}\n"
            f"2️⃣ Посмотри последние 3 поста\n"
            f"3️⃣ Поставь лайк или реакцию 👍\n"
            f"4️⃣ Вернись и нажми «Я зашёл и поставил реакцию»\n\n"
            f"💎 Есть VIP-ключи — пиши @ArsenGuro"
        )
        keyboard = {'inline_keyboard': [
            [{'text': f'📢 Перейти в @{primary}', 'url': f'https://t.me/{primary}'}],
            [{'text': '✅ Я зашёл и поставил реакцию', 'callback_data': 'check_verified'}],
            [{'text': '💎 Купить VIP-ключ', 'url': 'https://t.me/ArsenGuro'}],
            [{'text': '💬 Поддержка', 'url': 'https://t.me/ArsenGuro'}]
        ]}
        if is_admin:
            keyboard['inline_keyboard'].append([
                {'text': '📊 Статистика', 'callback_data': 'admin_stats'},
                {'text': '👥 Пользователи', 'callback_data': 'admin_users_1'}
            ])
            keyboard['inline_keyboard'].append([{'text': '📢 Опубликовать пост', 'callback_data': 'admin_post'}])
    
    send_message(token, chat_id, text, reply_markup=keyboard, parse_mode='HTML')


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


def handle_help(cfg, chat_id):
    token = cfg['BOT_TOKEN']
    channels = get_channels()
    primary = channels[0].lstrip('@') if channels else 'ArsenVipKeys'
    
    text = (
        f"📖 <b>Как получить тестовый ключ?</b>\n\n"
        f"1️⃣ Зайди в канал 👉 @{primary}\n"
        f"2️⃣ Найди пост с кнопкой <b>«🎁 Получить тест»</b>\n"
        f"3️⃣ Нажми на неё — ключ придёт в этот бот\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💎 Есть VIP-ключи в наличии\n"
        f"💬 Поддержка: @ArsenGuro"
    )
    
    keyboard = {'inline_keyboard': [
        [{'text': f'📢 Перейти в @{primary}', 'url': f'https://t.me/{primary}'}],
        [{'text': '💎 Купить VIP-ключ', 'url': 'https://t.me/ArsenGuro'}],
        [{'text': '💬 Поддержка', 'url': 'https://t.me/ArsenGuro'}]
    ]}
    
    send_message(token, chat_id, text, reply_markup=keyboard, parse_mode='HTML')


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
    
    # Обновляем verified на 8ч (отсчёт от выдачи ключа)
    hours = int(cfg.get('TEST_HOURS', '8'))
    mark_verified(user_id, hours)
    
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


def handle_banlist(cfg, chat_id, user_id):
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    if str(user_id) != str(admin_id):
        return
    if not os.path.exists(BLACKLIST) or os.path.getsize(BLACKLIST) == 0:
        send_message(token, chat_id, "📋 Чёрный список пуст")
        return
    with open(BLACKLIST) as f:
        banned = [l.strip() for l in f if l.strip()]
    text = f"🚫 <b>Чёрный список ({len(banned)}):</b>\n\n"
    for b in banned[-30:]:
        text += f"  • <code>{b}</code>\n"
    send_message(token, chat_id, text, parse_mode='HTML')


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
        until = now + (hours * 3600)
        
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


def handle_users(cfg, chat_id, user_id, page=1):
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
        {'text': '🗑️ Удалить истёкших', 'callback_data': 'admin_cleanup'},
        {'text': '🚫 Бан-лист', 'callback_data': 'admin_banlist'}
    ])
    keyboard['inline_keyboard'].append([{'text': '🔄 Обновить', 'callback_data': f'admin_users_{page}'}])
    
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


def is_admin(cfg, user_id):
    return str(user_id) == str(cfg.get('ADMIN_ID', ''))


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


def handle_services(cfg, chat_id, user_id):
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
        [{'text': '🔄 Обновить', 'callback_data': 'manage_services'}]
    ]}
    
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


def main():
    cfg = load_config()
    if not cfg.get('BOT_TOKEN'):
        log.error("BOT_TOKEN не задан"); sys.exit(1)
    # Команды для ВСЕХ юзеров
    tg_request(cfg['BOT_TOKEN'], 'setMyCommands', {'commands': [
        {'command': 'start', 'description': '👋 Начать'},
        {'command': 'help', 'description': '📖 Как получить ключ'}
    ]})
    
    # Команды ТОЛЬКО для админа (scope: chat)
    admin_id = cfg.get('ADMIN_ID', '')
    if admin_id:
        tg_request(cfg['BOT_TOKEN'], 'setMyCommands', {
            'commands': [
                {'command': 'start', 'description': '👋 Начать'},
                {'command': 'stats', 'description': '📊 Статистика'},
                {'command': 'users', 'description': '👥 Пользователи'},
                {'command': 'services', 'description': '⚙️ SSH WS управление'},
                {'command': 'post', 'description': '📢 Опубликовать пост'},
                {'command': 'help', 'description': '📖 Справка'}
            ],
            'scope': {'type': 'chat', 'chat_id': int(admin_id)}
        })
    
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
                    elif cb_data == 'admin_stats':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_stats(cfg, cb['message']['chat']['id'], cb_user_id, 'keys')
                    elif cb_data == 'admin_stats_keys':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_stats(cfg, cb['message']['chat']['id'], cb_user_id, 'keys', cb['message']['message_id'])
                    elif cb_data == 'admin_stats_traffic':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_stats(cfg, cb['message']['chat']['id'], cb_user_id, 'traffic', cb['message']['message_id'])
                    elif cb_data == 'admin_banlist':
                        handle_banlist(cfg, cb['message']['chat']['id'], cb_user_id)
                    elif cb_data == 'admin_post':
                        post_to_channel(cfg, cb['message']['chat']['id'], cb_user_id)
                    elif cb_data == 'manage_services':
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                        handle_services(cfg, cb['message']['chat']['id'], cb_user_id)
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
                        handle_users(cfg, cb['message']['chat']['id'], cb_user_id, pg)
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
                            hours = int(cfg.get('TEST_HOURS', '8'))
                            mark_verified(cb_user_id, hours)
                            tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {
                                'callback_query_id': cb['id'],
                                'text': '✅ Отлично! Теперь можешь получить тест.',
                                'show_alert': True
                            })
                            handle_start(cfg, cb['message']['chat']['id'], cb_user_id, cb_first_name, True)
                    # Кнопка из ЛИЧКИ → обычный /test
                    elif cb_data == 'get_test':
                        handle_test(cfg, cb['message']['chat']['id'], cb_user_id, cb_first_name, cb['id'])
                    else:
                        tg_request(cfg['BOT_TOKEN'], 'answerCallbackQuery', {'callback_query_id': cb['id']})
                    continue
                if 'message' not in upd: continue
                msg = upd['message']; chat_id = msg['chat']['id']; user_id = msg['from']['id']; first_name = msg['from'].get('first_name','')
                text = msg.get('text','')
                if text.startswith('/start'):
                    # Проверяем deep link параметр (пришёл из канала)
                    if 'from_channel' in text:
                        hours = int(cfg.get('TEST_HOURS', '8'))
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
                elif text.startswith('/restart'): handle_restart(cfg, chat_id, user_id, text[8:].strip())
                elif text.startswith('/help'): handle_help(cfg, chat_id)
        except KeyboardInterrupt: log.info("Остановка"); break
        except Exception as e: log.error(f"Ошибка в main loop: {e}"); time.sleep(5)

if __name__ == '__main__':
    main()
