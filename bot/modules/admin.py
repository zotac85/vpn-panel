#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Модуль администраторов"""
import os
import json
import logging
import urllib.request

ADMINS_FILE = "/etc/UDPCustom/admins.txt"
CONFIG_FILE = "/etc/UDPCustom/bot.conf"
LOG_FILE = "/var/log/vpn-tg-bot.log"

# Свой логгер — независимый от главного
admin_log = logging.getLogger("admin_module")
if not admin_log.handlers:
    admin_log.setLevel(logging.INFO)
    _h = logging.FileHandler(LOG_FILE)
    _h.setFormatter(logging.Formatter('%(asctime)s [ADMIN] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    admin_log.addHandler(_h)


def _tg_request(token, method, params=None, timeout=35):
    """Мини-версия Telegram API"""
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
        admin_log.error(f"TG API ({method}): {e}")
        return None


def _send_message(token, chat_id, text, reply_markup=None, parse_mode=None):
    params = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
    if reply_markup: params['reply_markup'] = reply_markup
    if parse_mode: params['parse_mode'] = parse_mode
    return _tg_request(token, 'sendMessage', params)


def _load_config():
    """Fallback: чтение ADMIN_ID из bot.conf"""
    cfg = {'ADMIN_ID': ''}
    if not os.path.exists(CONFIG_FILE): return cfg
    try:
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line: continue
                k, v = line.split('=', 1)
                k = k.strip(); v = v.strip()
                if len(v) >= 2 and v[0] == '"' and v[-1] == '"': v = v[1:-1]
                cfg[k] = v
    except: pass
    return cfg


def get_admins():
    """Список ID всех админов"""
    admins = []
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE) as f:
                admins = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        except: pass
    if not admins:
        cfg = _load_config()
        aid = cfg.get('ADMIN_ID', '')
        if aid:
            admins = [aid]
    return admins


def is_admin(cfg, user_id):
    """Проверка: юзер — админ?"""
    return str(user_id) in get_admins()


def handle_addadmin(cfg, chat_id, user_id, args):
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        _send_message(token, chat_id, "🚫 Только для админа."); return
    args = args.strip()
    if not args or not args.isdigit():
        _send_message(token, chat_id, "📖 Формат: <code>/addadmin 123456789</code>", parse_mode='HTML'); return
    
    new_id = args
    admins = get_admins()
    if new_id in admins:
        _send_message(token, chat_id, f"⚠️ <code>{new_id}</code> уже админ", parse_mode='HTML'); return
    
    try:
        with open(ADMINS_FILE, 'a') as f:
            f.write(new_id + "\n")
        admins.append(new_id)
        _send_message(token, chat_id, f"✅ Добавлен админ: <code>{new_id}</code>\nВсего: <b>{len(admins)}</b>", parse_mode='HTML')
        admin_log.info(f"ADD {new_id} by {user_id}")
    except Exception as e:
        _send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_deladmin(cfg, chat_id, user_id, args):
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        _send_message(token, chat_id, "🚫 Только для админа."); return
    args = args.strip()
    if not args or not args.isdigit():
        _send_message(token, chat_id, "📖 Формат: <code>/deladmin 123456789</code>", parse_mode='HTML'); return
    
    target = args
    admins = get_admins()
    if target not in admins:
        _send_message(token, chat_id, f"⚠️ <code>{target}</code> не админ", parse_mode='HTML'); return
    
    if target == str(user_id):
        _send_message(token, chat_id, "❌ Нельзя удалить самого себя"); return
    
    if len(admins) <= 1:
        _send_message(token, chat_id, "❌ Нельзя удалить последнего админа"); return
    
    admins.remove(target)
    try:
        with open(ADMINS_FILE, 'w') as f:
            for a in admins:
                f.write(a + "\n")
        _send_message(token, chat_id, f"✅ Удалён админ: <code>{target}</code>\nОсталось: <b>{len(admins)}</b>", parse_mode='HTML')
        admin_log.info(f"DEL {target} by {user_id}")
    except Exception as e:
        _send_message(token, chat_id, f"❌ Ошибка: {e}")


def handle_admins(cfg, chat_id, user_id):
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        _send_message(token, chat_id, "🚫 Только для админа."); return
    
    admins = get_admins()
    text = f"👑 <b>Админы ({len(admins)}):</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, a in enumerate(admins, 1):
        mark = " ⭐ (вы)" if str(a) == str(user_id) else ""
        text += f"<b>{i}.</b> <code>{a}</code>{mark}\n"
    text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"<i>Добавить: /addadmin ID</i>\n"
    text += f"<i>Удалить: /deladmin ID</i>"
    _send_message(token, chat_id, text, parse_mode='HTML')

def handle_newuser(cfg, chat_id, user_id, args):
    """Создать юзера: /newuser login password days devices gb"""
    token = cfg['BOT_TOKEN']
    if not is_admin(cfg, user_id):
        _send_message(token, chat_id, "🚫 Только для админа."); return
    
    args = args.strip()
    if not args:
        _send_message(token, chat_id,
            "📖 <b>Формат создания юзера:</b>\n\n"
            "<code>/newuser логин пароль дни устройства ГБ</code>\n\n"
            "<b>Пример:</b>\n"
            "<code>/newuser test1 pass123 30 5 100</code>\n\n"
            "Где:\n"
            "  • логин — имя юзера\n"
            "  • пароль — пароль\n"
            "  • дни — срок (0 = бессрочно)\n"
            "  • устройства — лимит устройств\n"
            "  • ГБ — лимит трафика (0 = без лимита)",
            parse_mode='HTML')
        return
    
    parts = args.split()
    if len(parts) < 2:
        _send_message(token, chat_id, "❌ Минимум 2 параметра: логин и пароль"); return
    
    login = parts[0]
    password = parts[1]
    days = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    devices = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 3
    gb = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
    
    # Валидация логина
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9_-]{2,20}$', login):
        _send_message(token, chat_id, "❌ Логин: только a-z, A-Z, 0-9, _ и -, 2-20 символов"); return
    
    # Проверка что не существует (Linux + наша база)
    import subprocess
    exists_linux = subprocess.run(['id', '-u', login], capture_output=True).returncode == 0
    exists_db = False
    if os.path.exists('/etc/UDPCustom/users.db'):
        with open('/etc/UDPCustom/users.db') as f:
            exists_db = login in [l.strip() for l in f if l.strip()]
    
    if exists_linux or exists_db:
        _send_message(token, chat_id, f"❌ Юзер <code>{login}</code> уже существует", parse_mode='HTML'); return
    try:
        # Создаём Linux-юзера
        subprocess.run(['useradd', '-M', '-s', '/bin/false', login], check=True, timeout=10)
        subprocess.run(['chpasswd'], input=f"{login}:{password}", text=True, capture_output=True, timeout=10)
        
        # В users.db
        with open('/etc/UDPCustom/users.db', 'a') as f:
            f.write(login + "\n")
        
        # Лимит устройств
        os.makedirs('/etc/UDPCustom/limits', exist_ok=True)
        with open(f'/etc/UDPCustom/limits/{login}', 'w') as f:
            f.write(str(devices))
        
        # Трафик
        os.makedirs('/etc/UDPCustom/traffic', exist_ok=True)
        os.makedirs('/etc/UDPCustom/traffic_limits', exist_ok=True)
        bytes_limit = gb * 1073741824
        with open(f'/etc/UDPCustom/traffic_limits/{login}', 'w') as f:
            f.write(str(bytes_limit))
        with open(f'/etc/UDPCustom/traffic/{login}', 'w') as f:
            f.write("0")
        
        # Expire timestamp
        os.makedirs('/etc/UDPCustom/expire_ts', exist_ok=True)
        if days > 0:
            import time as _time
            exp_ts = int(_time.time()) + (days * 86400)
            with open(f'/etc/UDPCustom/expire_ts/{login}', 'w') as f:
                f.write(str(exp_ts))
        
        # chage -E (+2 дня для страховки)
        subprocess.run(['chage', '-E', '+2 days' if days == 0 else f'+{days+2} days', login], capture_output=True, timeout=10)
        
        # maxlogins
        subprocess.run(['sed', '-i', f'/^{login}.*hard.*maxlogins/d', '/etc/security/limits.conf'], capture_output=True)
        with open('/etc/security/limits.conf', 'a') as f:
            f.write(f"{login} hard maxlogins {devices}\n")
        
        # iptables — если цепочка активна
        uid = subprocess.run(['id', '-u', login], capture_output=True, text=True).stdout.strip()
        if uid:
            subprocess.run(['iptables', '-C', 'VPN_TRAFFIC', '-m', 'owner', '--uid-owner', uid, '-j', 'RETURN'], capture_output=True)
            if subprocess.run(['iptables', '-C', 'VPN_TRAFFIC', '-m', 'owner', '--uid-owner', uid, '-j', 'RETURN'], capture_output=True).returncode != 0:
                subprocess.run(['iptables', '-A', 'VPN_TRAFFIC', '-m', 'owner', '--uid-owner', uid, '-j', 'RETURN'], capture_output=True)
        
        # Ответ
        exp_str = f"{days} дней" if days > 0 else "бессрочно"
        traffic_str = f"{gb} ГБ" if gb > 0 else "без лимита"
        _send_message(token, chat_id,
            f"✅ <b>Пользователь создан!</b>\n\n"
            f"📱 Логин: <code>{login}</code>\n"
            f"🔑 Пароль: <code>{password}</code>\n"
            f"⏰ Срок: {exp_str}\n"
            f"📱 Устройств: {devices}\n"
            f"📊 Трафик: {traffic_str}",
            parse_mode='HTML')
        admin_log.info(f"NEW USER: {login} by {user_id}")
    except Exception as e:
        _send_message(token, chat_id, f"❌ Ошибка: {e}")
        admin_log.error(f"newuser error: {e}")
