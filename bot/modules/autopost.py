#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Модуль автопостинга"""
import os
import json
import time
import logging
import threading
import urllib.request

CONFIG_FILE = "/etc/UDPCustom/autopost.conf"
MSGS_DIR = "/etc/UDPCustom/autopost_msgs"
POST_FILE = "/etc/UDPCustom/post.txt"
CHANNELS_FILE = "/etc/UDPCustom/channels.txt"

auto_log = logging.getLogger("autopost")
if not auto_log.handlers:
    auto_log.setLevel(logging.INFO)
    _h = logging.FileHandler("/var/log/vpn-tg-bot.log")
    _h.setFormatter(logging.Formatter('%(asctime)s [AUTOPOST] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    auto_log.addHandler(_h)


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
        auto_log.error(f"TG ({method}): {e}")
        return None


def _send(token, chat_id, text, reply_markup=None, parse_mode=None):
    params = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
    if reply_markup: params['reply_markup'] = reply_markup
    if parse_mode: params['parse_mode'] = parse_mode
    return _tg(token, 'sendMessage', params)


def load_autopost_config():
    cfg = {'ENABLED': '0', 'INTERVAL_HOURS': '12', 'TIMES': '', 'MODE': 'interval', 'LAST_POST': '0'}
    if not os.path.exists(CONFIG_FILE):
        return cfg
    try:
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line: continue
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip()
    except: pass
    return cfg


def save_autopost_config(cfg):
    try:
        with open(CONFIG_FILE, 'w') as f:
            for k, v in cfg.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        auto_log.error(f"save config error: {e}")


def _get_channels():
    if not os.path.exists(CHANNELS_FILE): return []
    try:
        with open(CHANNELS_FILE) as f:
            return [l.strip() for l in f if l.strip() and not l.startswith('#')]
    except: return []


def _get_bot_username(token):
    r = _tg(token, 'getMe')
    return r.get('result', {}).get('username', '') if r else ''


def _delete_prev_post(token, channel, channel_id_safe):
    """Удаляет предыдущий пост бота в канале"""
    os.makedirs(MSGS_DIR, exist_ok=True)
    msg_file = f"{MSGS_DIR}/{channel_id_safe}"
    if os.path.exists(msg_file):
        try:
            with open(msg_file) as f:
                msg_id = int(f.read().strip())
            _tg(token, 'deleteMessage', {'chat_id': channel, 'message_id': msg_id})
            auto_log.info(f"Удалён предыдущий пост в {channel}")
        except Exception as e:
            auto_log.warning(f"delete prev post ({channel}): {e}")
        try: os.remove(msg_file)
        except: pass


def _save_post_id(channel, channel_id_safe, msg_id):
    os.makedirs(MSGS_DIR, exist_ok=True)
    try:
        with open(f"{MSGS_DIR}/{channel_id_safe}", 'w') as f:
            f.write(str(msg_id))
    except: pass


def publish_post(token):
    """Публикует пост во все каналы, удаляя предыдущий"""
    if not os.path.exists(POST_FILE):
        auto_log.error("post.txt не найден")
        return False
    with open(POST_FILE) as f:
        post_text = f.read().strip()
    post_text = post_text.replace('[🎁 Получить тест]', '').strip()
    
    channels = _get_channels()
    if not channels:
        auto_log.error("channels.txt пуст")
        return False
    
    bot_username = _get_bot_username(token)
    if not bot_username:
        auto_log.error("Не удалось получить username бота")
        return False
    
    keyboard = {'inline_keyboard': [
        [{'text': '🎁 Получить тест', 'url': f'https://t.me/{bot_username}?start=from_channel', 'style': 'success'}]
    ]}
    
    success = 0
    for ch in channels:
        target = ch if ch.startswith('@') else '@' + ch
        safe = target.lstrip('@')
        
        # Удаляем предыдущий пост
        _delete_prev_post(token, target, safe)
        
        # Подстановка переменных
        primary_clean = target.lstrip('@')
        sponsors = [c2.lstrip('@') for c2 in channels if c2.lstrip('@') != primary_clean]
        sponsors_list = ", ".join([f"@{s}" for s in sponsors]) if sponsors else "—"
        personalized = post_text.replace('{sponsors_list}', sponsors_list).replace('{primary}', primary_clean)
        
        r = _send(token, target, personalized, keyboard, parse_mode='HTML')
        if r and r.get('ok'):
            msg_id = r['result']['message_id']
            _save_post_id(target, safe, msg_id)
            success += 1
            auto_log.info(f"Опубликован пост в {target} (msg_id={msg_id})")
        else:
            err = r.get('description', 'unknown') if r else 'no response'
            auto_log.error(f"Ошибка публикации в {target}: {err}")
    
    return success > 0


def _should_post(cfg, now):
    """Проверяет, надо ли публиковать сейчас"""
    last = int(cfg.get('LAST_POST', '0'))
    
    if cfg.get('MODE') == 'time':
        # Режим конкретного времени (например "10:00,22:00")
        times = [t.strip() for t in cfg.get('TIMES', '').split(',') if t.strip()]
        if not times: return False
        cur_hm = time.strftime('%H:%M', time.localtime(now))
        # Проверяем, попадаем ли мы в одну из минут (не более 60 сек отклонение)
        for t in times:
            if cur_hm == t and (now - last) > 60:
                return True
        return False
    else:
        # Режим интервала (каждые N часов)
        interval_sec = int(cfg.get('INTERVAL_HOURS', '12')) * 3600
        return (now - last) >= interval_sec


def autopost_loop(token, bot_state):
    """Поток планировщика. Каждую минуту проверяет расписание."""
    auto_log.info("Autopost поток запущен")
    while True:
        try:
            time.sleep(60)  # проверка каждую минуту
            cfg = load_autopost_config()
            if cfg.get('ENABLED') != '1':
                continue
            now = int(time.time())
            if _should_post(cfg, now):
                auto_log.info("Пора публиковать пост")
                if publish_post(token):
                    cfg['LAST_POST'] = str(now)
                    save_autopost_config(cfg)
        except Exception as e:
            auto_log.error(f"loop error: {e}")


def start_autopost_thread(token, bot_state):
    """Запускает поток автопостинга"""
    t = threading.Thread(target=autopost_loop, args=(token, bot_state), daemon=True)
    t.start()
    return t


def handle_autopost(cfg, chat_id, user_id, args):
    """Управление автопостингом: /autopost on|off|status|every N|time HH:MM,HH:MM"""
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    
    # Проверка админа через admins.txt
    admins = []
    if os.path.exists('/etc/UDPCustom/admins.txt'):
        with open('/etc/UDPCustom/admins.txt') as f:
            admins = [l.strip() for l in f if l.strip()]
    if str(user_id) not in admins and str(user_id) != str(admin_id):
        _send(token, chat_id, "🚫 Только для админа.")
        return
    
    args = args.strip().lower()
    ap = load_autopost_config()
    
    if not args or args == 'status':
        status = "🟢 Включен" if ap.get('ENABLED') == '1' else "🔴 Выключен"
        mode = ap.get('MODE', 'interval')
        if mode == 'time':
            mode_str = f"📅 По времени: {ap.get('TIMES', '—')}"
        else:
            mode_str = f"⏰ Каждые {ap.get('INTERVAL_HOURS', '12')} ч"
        last = int(ap.get('LAST_POST', '0'))
        last_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(last)) if last > 0 else "—"
        text = (
            f"📮 <b>АВТОПОСТИНГ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Статус: <b>{status}</b>\n"
            f"Режим: <b>{mode_str}</b>\n"
            f"Последний пост: {last_str}\n\n"
            f"<b>Команды:</b>\n"
            f"  <code>/autopost on</code> — включить (12ч)\n"
            f"  <code>/autopost off</code> — выключить\n"
            f"  <code>/autopost every 6</code> — каждые 6 часов\n"
            f"  <code>/autopost time 10:00,22:00</code> — в 10:00 и 22:00\n"
            f"  <code>/autopost now</code> — опубликовать сейчас"
        )
        _send(token, chat_id, text, parse_mode='HTML')
        return
    
    if args == 'on':
        ap['ENABLED'] = '1'
        ap['MODE'] = 'interval'
        if not ap.get('INTERVAL_HOURS'): ap['INTERVAL_HOURS'] = '12'
        ap['LAST_POST'] = '0'  # опубликует через минуту
        save_autopost_config(ap)
        _send(token, chat_id, f"✅ Автопостинг ВКЛЮЧЕН (каждые {ap['INTERVAL_HOURS']}ч)\nПервый пост — в течение минуты.")
        return
    
    if args == 'off':
        ap['ENABLED'] = '0'
        save_autopost_config(ap)
        _send(token, chat_id, "🔴 Автопостинг ВЫКЛЮЧЕН")
        return
    
    if args.startswith('every'):
        parts = args.split()
        if len(parts) < 2 or not parts[1].isdigit():
            _send(token, chat_id, "📖 Формат: <code>/autopost every 6</code>", parse_mode='HTML')
            return
        hours = int(parts[1])
        if hours < 1 or hours > 168:
            _send(token, chat_id, "❌ Интервал: 1-168 часов")
            return
        ap['ENABLED'] = '1'
        ap['MODE'] = 'interval'
        ap['INTERVAL_HOURS'] = str(hours)
        save_autopost_config(ap)
        _send(token, chat_id, f"✅ Автопостинг: каждые <b>{hours} ч</b>", parse_mode='HTML')
        return
    
    if args.startswith('time'):
        times_raw = args[4:].strip()
        if not times_raw:
            _send(token, chat_id, "📖 Формат: <code>/autopost time 10:00,22:00</code>", parse_mode='HTML')
            return
        # Валидация
        import re as _re
        times = [t.strip() for t in times_raw.split(',') if t.strip()]
        valid = []
        for t in times:
            if _re.match(r'^\d{1,2}:\d{2}$', t):
                h, m = t.split(':')
                h, m = int(h), int(m)
                if 0 <= h < 24 and 0 <= m < 60:
                    valid.append(f"{h:02d}:{m:02d}")
        if not valid:
            _send(token, chat_id, "❌ Неверный формат времени. Пример: <code>10:00,22:00</code>", parse_mode='HTML')
            return
        ap['ENABLED'] = '1'
        ap['MODE'] = 'time'
        ap['TIMES'] = ','.join(valid)
        save_autopost_config(ap)
        _send(token, chat_id, f"✅ Автопостинг по времени: <b>{', '.join(valid)}</b>", parse_mode='HTML')
        return
    
    if args == 'now':
        _send(token, chat_id, "⏳ Публикуем сейчас...")
        if publish_post(token):
            ap['LAST_POST'] = str(int(time.time()))
            save_autopost_config(ap)
            _send(token, chat_id, "✅ Пост опубликован во все каналы")
        else:
            _send(token, chat_id, "❌ Ошибка публикации")
        return
    
    _send(token, chat_id, "📖 Используй: /autopost on|off|status|every N|time HH:MM,HH:MM|now")
