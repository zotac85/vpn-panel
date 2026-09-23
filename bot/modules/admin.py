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
