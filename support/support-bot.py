#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram Support Bot с автоответами из FAQ"""
import os
import sys
import json
import time
import logging
import urllib.request
import threading

sys.path.insert(0, '/usr/local/bin')
from bot_modules import support_db as sdb

CONFIG_FILE = "/etc/UDPCustom/support_bot.conf"
FAQ_FILE = "/etc/UDPCustom/help_faq.txt"
KEYWORDS_FILE = "/etc/UDPCustom/faq_keywords.txt"
LOG_FILE = "/var/log/vpn-support-bot.log"

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log = logging.getLogger()


# ═══════════════════════════════════════════════════════════════
# КОНФИГ
# ═══════════════════════════════════════════════════════════════

def load_config():
    cfg = {
        'BOT_TOKEN': '',
        'ADMIN_ID': '',
        'MAIN_BOT': 'ArsenVipKeysBot',
        'SUPPORT_BOT': 'ArsenSupportBot',
        'AUTO_CLOSE_HOURS': '1',
    }
    if not os.path.exists(CONFIG_FILE):
        return cfg
    with open(CONFIG_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip(); v = v.strip()
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                v = v[1:-1]
            cfg[k] = v
    return cfg


# ═══════════════════════════════════════════════════════════════
# TELEGRAM API
# ═══════════════════════════════════════════════════════════════

def tg(token, method, params=None, timeout=35):
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
        log.error(f"TG ({method}): {e}")
        return None


def send(token, chat_id, text, reply_markup=None, parse_mode='HTML'):
    params = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
    if parse_mode: params['parse_mode'] = parse_mode
    if reply_markup: params['reply_markup'] = reply_markup
    return tg(token, 'sendMessage', params)


# ═══════════════════════════════════════════════════════════════
# FAQ — ЧТЕНИЕ И ПОИСК
# ═══════════════════════════════════════════════════════════════

def parse_faq():
    """Парсит help_faq.txt на блоки. Возвращает dict: {title: full_block}"""
    if not os.path.exists(FAQ_FILE):
        return {}
    try:
        with open(FAQ_FILE) as f:
            content = f.read()
    except:
        return {}

    blocks = {}
    # Блоки разделяются "────────────────────" или начинаются с "🔴", "💎", "📱" и т.д.
    # Проще: разбиваем по "\n────────" и берём первый абзац как заголовок
    parts = content.split('\n────────────────────\n')
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Заголовок — первая строка, содержащая <b>...</b>
        lines = p.split('\n')
        title = None
        for l in lines:
            l_clean = l.replace('<b>', '').replace('</b>', '').strip()
            if l_clean.startswith('🔴') or l_clean.startswith('💎') or l_clean.startswith('📱') or l_clean.startswith('🗑') or l_clean.startswith('🔐'):
                title = l_clean
                break
        if title:
            blocks[title] = p
    return blocks


def parse_keywords():
    """Читает faq_keywords.txt. Возвращает list of (list_words, block_title)"""
    if not os.path.exists(KEYWORDS_FILE):
        return []
    result = []
    try:
        with open(KEYWORDS_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '|' not in line:
                    continue
                words_str, title = line.split('|', 1)
                words = [w.strip().lower() for w in words_str.split(',') if w.strip()]
                if words:
                    result.append((words, title.strip()))
    except: pass
    return result


def find_faq_answer(text):
    """Ищет блок FAQ по ключевым словам. Возвращает (block_text, block_title) или (None, None)"""
    if not text:
        return None, None
    text_lower = text.lower()
    blocks = parse_faq()
    keywords = parse_keywords()

    for words, title in keywords:
        for w in words:
            if w in text_lower:
                # Нашли — ищем блок с этим заголовком
                for btitle, btext in blocks.items():
                    # Сравниваем по началу (эмодзи + первые слова)
                    if btitle.startswith(title[:20]) or title in btitle:
                        return btext, title
                # Если блок не нашли — вернём просто заголовок
                return f"<b>{title}</b>", title
    return None, None


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def handle_message(cfg, msg, token, admin_id):
    """Обработка входящего сообщения"""
    chat_id = msg['chat']['id']
    user_id = msg['from']['id']
    first_name = msg['from'].get('first_name', '') or ''
    username = msg['from'].get('username', '') or ''
    text = msg.get('text', '')

    # === Проверка: админ редактирует FAQ? ===
    if str(user_id) == str(admin_id) and user_id in PENDING_FAQ_EDIT and text:
        _idx = PENDING_FAQ_EDIT.pop(user_id)
        save_faq_block(cfg, chat_id, _idx, text)
        return

    # === Проверка: админ отвечает в тикет? ===
    if str(user_id) == str(admin_id) and user_id in PENDING_TICKET_REPLY and text and not text.startswith('/'):
        _tid = PENDING_TICKET_REPLY.get(user_id)
        _tk = sdb.get_ticket(_tid)
        if _tk:
            _client_id = _tk["user_id"]
            sdb.add_message(_tid, user_id, _client_id, text, is_admin=1)
            try:
                send(token, _client_id, text)
            except: pass
            # Просто тишина — как в обычном чате
            pass
        return

    # Сохраняем юзера
    sdb.upsert_user(user_id, username, first_name)

    # === АДМИН пишет (reply на сообщение клиента) ===
    if str(user_id) == str(admin_id):
        # /cancel — выход из режима ответа
        if text.startswith('/cancel'):
            if user_id in PENDING_TICKET_REPLY:
                _tid = PENDING_TICKET_REPLY.pop(user_id)
                NLx = chr(10)
                send(token, chat_id, NLx.join([
                    f'🚪 <b>Вышел из режима ответа</b>',
                    '',
                    f'Тикет #{_tid} остаётся открытым.',
                    'Клиент может писать — сообщения придут тебе.'
                ]))
            else:
                send(token, chat_id, '🚪 Ты не в режиме ответа')
            return
        reply = msg.get('reply_to_message')
        if reply:
            reply_text = reply.get('text', '') or reply.get('caption', '')
            # Ищем ticket_id в тексте reply
            import re as _re
            m = _re.search(r'#(\d+)', reply_text)
            if m:
                ticket_id = int(m.group(1))
                tk = sdb.get_ticket(ticket_id)
                if tk:
                    client_id = tk['user_id']
                    # Отправляем клиенту
                    send(token, client_id, text)
                    # Логируем
                    sdb.add_message(ticket_id, user_id, client_id, text, is_admin=1)
                    # Включаем серию — следующие сообщения тоже уйдут
                    PENDING_TICKET_REPLY[user_id] = ticket_id
                    return
        # Если не reply — показываем статистику/меню админа
        if text.startswith('/start') or text.startswith('/admin'):
            show_admin_menu(cfg, chat_id)
        return

    # === КЛИЕНТ пишет ===
    if text.startswith('/start'):
        welcome_client(cfg, chat_id, first_name)
        return
    if text.startswith('/help'):
        show_help(cfg, chat_id)
        return

    # Пустое сообщение
    if not text:
        send(token, chat_id, '🤖 Отправь текстовый вопрос, я постараюсь помочь.')
        return

    # Проверяем: у клиента уже есть открытый тикет?
    tk = sdb.get_open_ticket(user_id)
    if tk:
        # Есть открытый тикет — сразу пересылаем админу
        sdb.add_message(tk['id'], user_id, admin_id, text, is_admin=0)
        forward_to_admin(cfg, tk['id'], user_id, first_name, username, text, is_followup=True)
        return

    # Ищем ответ в FAQ
    answer, title = find_faq_answer(text)
    if answer:
        # Подставляем плейсхолдеры в найденный ответ
        _sup = ''
        try:
            with open('/etc/UDPCustom/support.txt') as _f:
                _sup = _f.read().strip() or '@ArsenGuro'
        except: _sup = '@ArsenGuro'
        _hours = cfg.get('TEST_HOURS', '8')
        answer = (answer
                  .replace('{support}', _sup)
                  .replace('{hours}', str(_hours)))
        sdb.faq_hit(title or 'unknown')
        # Сохраняем какой блок показан (для feedback)
        try:
            with open(f'/tmp/support_last_block_{user_id}.txt', 'w') as f:
                f.write(title or '')
        except: pass
        # Сохраняем что юзер спросил (для кнопки "Нет")
        sdb.upsert_user(user_id, username, first_name)
        # Кэшируем "последний текст" в tickets? Нет — используем callback_data с текстом
        # Проще: сохраняем в файл /tmp/support_last_<uid>
        try:
            with open(f'/tmp/support_last_{user_id}.txt', 'w') as f:
                f.write(text)
        except: pass

        NL = chr(10)
        out = NL.join([
            '🔍 <b>Нашёл ответ на твой вопрос:</b>',
            '',
            '━━━━━━━━━━━━━━━━━━━━',
            answer,
            '━━━━━━━━━━━━━━━━━━━━',
            '',
            '❓ Это помогло?'
        ])
        kb = {'inline_keyboard': [
            [{'text': '✅ Да, спасибо', 'callback_data': 'faq_ok'},
             {'text': '❌ Нет, нужна помощь', 'callback_data': 'faq_no'}]
        ]}
        send(token, chat_id, out, reply_markup=kb)
    else:
        # Не нашли — сразу создаём тикет
        ticket_id = sdb.create_ticket(user_id, text)
        sdb.add_message(ticket_id, user_id, admin_id, text, is_admin=0)
        forward_to_admin(cfg, ticket_id, user_id, first_name, username, text, is_followup=False)
        NL = chr(10)
        out = NL.join([
            '🤖 К сожалению, я не знаю ответ на этот вопрос.',
            '',
            '📨 Передал твоё сообщение в поддержку.',
            'Обычно отвечаем в течение 1-2 часов.',
            '',
            f'🎫 Тикет: #{ticket_id}'
        ])
        send(token, chat_id, out)


def show_help(cfg, chat_id):
    """Экран /help"""
    token = cfg['BOT_TOKEN']
    main_bot = cfg.get('MAIN_BOT', 'ArsenVipKeysBot')
    NL = chr(10)
    text = NL.join([
        '❓ <b>КАК ПОЛЬЗОВАТЬСЯ БОТОМ</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        f'Я бот поддержки <b>{main_bot}</b>.',
        '',
        '📌 <b>Что я умею:</b>',
        '• Отвечаю на частые вопросы',
        '• Передаю сложные вопросы админу',
        '• Отвечаем в течение 1-2 часов',
        '',
        '💬 <b>Как задать вопрос:</b>',
        'Просто напиши его текстом.',
        '',
        'Например:',
        '• «Ключ не работает»',
        '• «Забыл пароль»',
        '• «Как купить VIP»',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        f'🤖 <b>Основной бот:</b> @{main_bot}',
        '   <i>Получить ключ, личный кабинет</i>'
    ])
    kb = {'inline_keyboard': [
        [{'text': f'🤖 @{main_bot}', 'url': f'https://t.me/{main_bot}'}]
    ]}
    send(token, chat_id, text, reply_markup=kb)


def welcome_client(cfg, chat_id, first_name):
    """Приветствие клиента"""
    token = cfg['BOT_TOKEN']
    main_bot = cfg.get('MAIN_BOT', 'ArsenVipKeysBot')
    NL = chr(10)
    text = NL.join([
        f'👋 Привет, <b>{first_name}</b>!',
        '',
        'Я бот поддержки. Помогу с вопросами по VPN.',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        '💬 <b>Просто напиши свой вопрос</b>',
        '',
        'Например:',
        '• «Ключ не работает»',
        '• «Забыл пароль»',
        '• «Как получить VIP»',
        '',
        '🤖 Сначала поищу ответ в FAQ.',
        'Если не найду — передам человеку.',
        '━━━━━━━━━━━━━━━━━━━━'
    ])
    kb = {'inline_keyboard': [
        [{'text': '🤖 Основной бот', 'url': f'https://t.me/{main_bot}'}]
    ]}
    send(token, chat_id, text, reply_markup=kb)


def forward_to_admin(cfg, ticket_id, user_id, first_name, username, text, is_followup=False):
    """Пересылает тикет админу"""
    token = cfg['BOT_TOKEN']
    admin_id = cfg.get('ADMIN_ID', '')
    NL = chr(10)
    if is_followup:
        header = f'👤 <b>{first_name or "Клиент"}</b> · #{ticket_id}'
    else:
        header = f'🆕 <b>{first_name or "Клиент"}</b> · тикет #{ticket_id}'
    out = NL.join([
        header,
        '',
        text
    ])
    send(token, admin_id, out)


def show_admin_menu(cfg, chat_id):
    """Меню админа в боте поддержки"""
    token = cfg['BOT_TOKEN']
    stats = sdb.get_stats()
    NL = chr(10)
    out = NL.join([
        '⚙️ <b>АДМИН-ПАНЕЛЬ ПОДДЕРЖКИ</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        f'👥 Юзеров: <b>{stats["total_users"]}</b>',
        f'🎫 Всего тикетов: <b>{stats["total_tickets"]}</b>',
        f'🟢 Открытых: <b>{stats["open_tickets"]}</b>',
        f'✅ Закрытых: <b>{stats["closed_tickets"]}</b>',
        f'🤖 FAQ-ответов: <b>{stats["faq_hits"]}</b>',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        'Выбери раздел:'
    ])
    kb = {'inline_keyboard': [
        [{'text': f'📋 Активные тикеты ({stats["open_tickets"]})', 'callback_data': 'adm_tickets'}],
        [{'text': '📊 FAQ статистика', 'callback_data': 'adm_faq_stats'}],
        [{'text': '📝 Управление FAQ', 'callback_data': 'adm_faq_edit'}],
        [{'text': '🔄 Обновить', 'callback_data': 'adm_refresh'}]
    ]}
    send(token, chat_id, out, reply_markup=kb)


def handle_callback(cfg, cb, token, admin_id):
    """Обработка callback_query"""
    data = cb.get('data', '')
    user_id = cb['from']['id']
    chat_id = cb['message']['chat']['id']
    msg_id = cb['message']['message_id']
    cb_id = cb['id']

    if data == 'faq_ok':
        # Помогло
        _block = ''
        try:
            with open(f'/tmp/support_last_block_{user_id}.txt') as f:
                _block = f.read().strip()
        except: pass
        if _block:
            sdb.faq_feedback(_block, helped=True)
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '👍 Рад помочь!'})
        tg(token, 'editMessageReplyMarkup', {'chat_id': chat_id, 'message_id': msg_id, 'reply_markup': {'inline_keyboard': []}})
        return

    if data == 'faq_no':
        # Не помогло — создаём тикет с последним текстом
        _block = ''
        try:
            with open(f'/tmp/support_last_block_{user_id}.txt') as f:
                _block = f.read().strip()
        except: pass
        if _block:
            sdb.faq_feedback(_block, helped=False)
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
        # Читаем последний текст
        text = ''
        try:
            with open(f'/tmp/support_last_{user_id}.txt') as f:
                text = f.read().strip()
        except: pass
        if not text:
            text = '(не указано)'
        first_name = cb['from'].get('first_name', '') or ''
        username = cb['from'].get('username', '') or ''
        ticket_id = sdb.create_ticket(user_id, text)
        sdb.add_message(ticket_id, user_id, admin_id, text, is_admin=0)
        forward_to_admin(cfg, ticket_id, user_id, first_name, username, text, is_followup=False)
        NL = chr(10)
        out = NL.join([
            '📨 <b>Передал твой вопрос в поддержку</b>',
            '',
            'Обычно отвечаем в течение 1-2 часов.',
            '',
            f'🎫 Тикет: <code>#{ticket_id}</code>'
        ])
        tg(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': out, 'parse_mode': 'HTML'})
        return


    if data == 'adm_tickets':
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
        show_active_tickets(cfg, chat_id, msg_id)
        return
    if data.startswith('adm_ticket:') and not data.startswith('adm_ticket_'):
        tid = data.split(':', 1)[1]
        try: tid = int(tid)
        except: return
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
        show_ticket_detail(cfg, chat_id, tid, msg_id)
        return
    if data.startswith('adm_ticket_reply:'):
        tid = data.split(':', 1)[1]
        try: tid = int(tid)
        except: return
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
        start_ticket_reply(cfg, chat_id, user_id, tid)
        return
    if data.startswith('adm_ticket_close:'):
        tid = data.split(':', 1)[1]
        try: tid = int(tid)
        except: return
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
        show_ticket_close_confirm(cfg, chat_id, tid, msg_id)
        return
    if data.startswith('adm_ticket_closeok:'):
        tid = data.split(':', 1)[1]
        try: tid = int(tid)
        except: return
        do_close_ticket(cfg, cb, tid)
        return
    if data == 'adm_faq_stats':
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
        show_faq_stats(cfg, chat_id, msg_id)
        return
    if data == 'adm_faq_edit':
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
        show_faq_edit_list(cfg, chat_id, msg_id)
        return
    if data == 'adm_refresh':
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
        tg(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': '⚙️ Обновлено', 'parse_mode': 'HTML'})
        show_admin_menu(cfg, chat_id)
        return
    if data.startswith('faq_block:'):
        # Показать блок FAQ
        bkey = data.split(':', 1)[1]
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
        show_faq_block(cfg, chat_id, msg_id, bkey)
        return
    if data.startswith('faq_edit_go:'):
        # Редактировать блок FAQ
        bkey = data.split(':', 1)[1]
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id})
        start_faq_edit(cfg, chat_id, user_id, bkey)
        return

def show_active_tickets(cfg, chat_id, msg_id=None):
    """Список активных тикетов с кнопками"""
    token = cfg['BOT_TOKEN']
    tickets = sdb.get_active_tickets()
    NL = chr(10)

    if not tickets:
        text = NL.join([
            '📋 <b>АКТИВНЫЕ ТИКЕТЫ</b>',
            '━━━━━━━━━━━━━━━━━━━━',
            '',
            '✅ Нет открытых тикетов'
        ])
        kb = {'inline_keyboard': [[{'text': '⬅️ Назад', 'callback_data': 'adm_refresh'}]]}
    else:
        lines_txt = [
            f'📋 <b>АКТИВНЫЕ ТИКЕТЫ ({len(tickets)})</b>',
            '━━━━━━━━━━━━━━━━━━━━',
            '',
            'Выбери тикет для просмотра:'
        ]
        text = NL.join(lines_txt)

        kb_rows = []
        for t in tickets[:10]:
            user = sdb.get_user(t['user_id']) or {}
            name = user.get('first_name') or 'Клиент'
            ago = int(time.time()) - t['updated_at']
            if ago < 60:
                t_ago = 'только что'
            elif ago < 3600:
                t_ago = f'{ago // 60}мин'
            else:
                t_ago = f'{ago // 3600}ч'
            btn = f'🎫 #{t["id"]} · {name[:15]} · {t_ago}'
            kb_rows.append([{'text': btn, 'callback_data': f'adm_ticket:{t["id"]}'}])
        kb_rows.append([{'text': '⬅️ Назад', 'callback_data': 'adm_refresh'}])
        kb = {'inline_keyboard': kb_rows}

    if msg_id:
        tg(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        send(token, chat_id, text, reply_markup=kb)


def show_ticket_detail(cfg, chat_id, ticket_id, msg_id=None):
    """Детали тикета с историей"""
    token = cfg['BOT_TOKEN']
    tk = sdb.get_ticket(ticket_id)
    if not tk:
        if msg_id:
            tg(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': '❌ Тикет не найден', 'parse_mode': 'HTML'})
        return

    user = sdb.get_user(tk['user_id']) or {}
    name = user.get('first_name') or 'Клиент'
    uname = f"@{user.get('username')}" if user.get('username') else f"id{tk['user_id']}"

    # История сообщений (последние 10)
    msgs = sdb.query("SELECT * FROM messages WHERE ticket_id=? ORDER BY created_at ASC LIMIT 10", (int(ticket_id),))

    NL = chr(10)
    status = '🟢 Открыт' if tk['status'] == 'open' else '✅ Закрыт'
    created = time.strftime('%d.%m %H:%M', time.localtime(tk['created_at']))

    lines_txt = [
        f'🎫 <b>ТИКЕТ #{ticket_id}</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        f'👤 <b>{name}</b> · {uname}',
        f'🆔 <code>{tk["user_id"]}</code>',
        f'🕐 Создан: {created}',
        f'📊 Статус: {status}',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        '💬 <b>История:</b>',
        ''
    ]

    if not msgs:
        lines_txt.append('<i>Нет сообщений</i>')
    else:
        for m in msgs:
            ts = time.strftime('%H:%M', time.localtime(m['created_at']))
            if m['is_admin']:
                who = '💬 Ты'
            else:
                who = f'👤 {name}'
            # Экранируем HTML теги в тексте
            txt = (m['text'] or '').replace('<', '&lt;').replace('>', '&gt;')
            lines_txt.append(f'<b>{who}</b> · <i>{ts}</i>')
            lines_txt.append(f'{txt}')
            lines_txt.append('')

    text = NL.join(lines_txt)

    kb_rows = []
    if tk['status'] == 'open':
        kb_rows.append([{'text': '💬 Ответить клиенту', 'callback_data': f'adm_ticket_reply:{ticket_id}'}])
        kb_rows.append([{'text': '🗑 Закрыть тикет', 'callback_data': f'adm_ticket_close:{ticket_id}'}])
    else:
        kb_rows.append([{'text': '🔄 Тикет закрыт', 'callback_data': 'noop'}])
    kb_rows.append([{'text': '🔄 Обновить', 'callback_data': f'adm_ticket:{ticket_id}'}])
    kb_rows.append([{'text': '⬅️ К тикетам', 'callback_data': 'adm_tickets'}])

    kb = {'inline_keyboard': kb_rows}
    if msg_id:
        tg(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        send(token, chat_id, text, reply_markup=kb)


def show_ticket_close_confirm(cfg, chat_id, ticket_id, msg_id=None):
    """Подтверждение закрытия тикета"""
    token = cfg['BOT_TOKEN']
    tk = sdb.get_ticket(ticket_id)
    if not tk:
        return
    user = sdb.get_user(tk['user_id']) or {}
    name = user.get('first_name') or 'Клиент'
    uname = f"@{user.get('username')}" if user.get('username') else f"id{tk['user_id']}"

    NL = chr(10)
    text = NL.join([
        f'🗑 <b>ЗАКРЫТЬ ТИКЕТ #{ticket_id}?</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        f'👤 {name} · {uname}',
        '',
        'Клиент получит уведомление о закрытии.',
        'Если он напишет снова — создастся новый тикет.'
    ])
    kb = {'inline_keyboard': [
        [{'text': '✅ Да, закрыть', 'callback_data': f'adm_ticket_closeok:{ticket_id}'}],
        [{'text': '⬅️ Отмена', 'callback_data': f'adm_ticket:{ticket_id}'}]
    ]}
    if msg_id:
        tg(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        send(token, chat_id, text, reply_markup=kb)


def do_close_ticket(cfg, cb, ticket_id):
    """Закрывает тикет + уведомляет клиента"""
    token = cfg['BOT_TOKEN']
    chat_id = cb['message']['chat']['id']
    msg_id = cb['message']['message_id']
    cb_id = cb['id']

    tk = sdb.get_ticket(ticket_id)
    if not tk:
        tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': '❌ Тикет не найден', 'show_alert': True})
        return

    client_id = tk['user_id']
    sdb.close_ticket(ticket_id)

    # Уведомляем клиента
    NL = chr(10)
    out = NL.join([
        f'✅ <b>Тикет #{ticket_id} закрыт</b>',
        '',
        'Спасибо за обращение! Если возникнут',
        'вопросы — просто напиши снова.'
    ])
    try:
        send(token, client_id, out)
    except: pass

    tg(token, 'answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'✅ Тикет #{ticket_id} закрыт'})
    # Возврат к списку тикетов
    show_active_tickets(cfg, chat_id, msg_id)
    log.info(f'Ticket #{ticket_id} closed by admin')


def start_ticket_reply(cfg, chat_id, user_id, ticket_id):
    """Просит текст ответа (через reply или ForceReply)"""
    token = cfg['BOT_TOKEN']
    tk = sdb.get_ticket(ticket_id)
    if not tk:
        send(token, chat_id, '❌ Тикет не найден')
        return
    PENDING_TICKET_REPLY[user_id] = ticket_id
    NL = chr(10)
    out = NL.join([
        f'💬 <b>ОТВЕТ В ТИКЕТ #{ticket_id}</b>',
        '',
        'Напиши ответ клиенту.',
        '<i>Все следующие сообщения будут уходить ему же.</i>',
        '<i>Выход: /cancel</i>'
    ])
    send(token, chat_id, out)


# Pending: какой тикет отвечаем (user_id -> ticket_id)
PENDING_TICKET_REPLY = {}



def show_faq_stats(cfg, chat_id, msg_id=None):
    """Статистика по блокам FAQ"""
    token = cfg['BOT_TOKEN']
    rows = sdb.query("SELECT * FROM faq_stats ORDER BY hits DESC")
    NL = chr(10)
    if not rows:
        text = NL.join([
            '📊 <b>FAQ СТАТИСТИКА</b>',
            '━━━━━━━━━━━━━━━━━━━━',
            '',
            '📭 Пока нет данных',
            '',
            '<i>Данные появятся после показов FAQ клиентам</i>'
        ])
    else:
        lines_txt = [
            '📊 <b>FAQ СТАТИСТИКА</b>',
            '━━━━━━━━━━━━━━━━━━━━',
            ''
        ]
        total_hits = sum(r['hits'] for r in rows)
        total_helped = sum(r['helped'] for r in rows)
        total_not = sum(r['not_helped'] for r in rows)
        for r in rows[:15]:
            block = r['block_name'] or '—'
            # Обрезаем длинный заголовок
            if len(block) > 35:
                block = block[:32] + '...'
            pct = 0
            total_fb = r['helped'] + r['not_helped']
            if total_fb > 0:
                pct = int(r['helped'] * 100 / total_fb)
            lines_txt.append(f'<b>{block}</b>')
            lines_txt.append(f'   👁 {r["hits"]} · ✅ {r["helped"]} · ❌ {r["not_helped"]}')
            if total_fb > 0:
                lines_txt.append(f'   📈 Успех: {pct}%')
            lines_txt.append('')
        lines_txt.append('━━━━━━━━━━━━━━━━━━━━')
        lines_txt.append(f'🤖 Всего показов: <b>{total_hits}</b>')
        lines_txt.append(f'✅ Помогло: <b>{total_helped}</b>')
        lines_txt.append(f'❌ Не помогло: <b>{total_not}</b>')
        text = NL.join(lines_txt)
    kb = {'inline_keyboard': [[{'text': '⬅️ Назад', 'callback_data': 'adm_refresh'}]]}
    if msg_id:
        tg(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        send(token, chat_id, text, reply_markup=kb)


def get_faq_blocks():
    """Возвращает список блоков FAQ: [(index, title, text), ...]"""
    if not os.path.exists(FAQ_FILE):
        return []
    try:
        with open(FAQ_FILE) as f:
            content = f.read()
    except:
        return []
    parts = content.split(chr(10) + '────────────────────' + chr(10))
    result = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        lines_p = p.split(chr(10))
        title = None
        for l in lines_p:
            clean = l.replace('<b>', '').replace('</b>', '').strip()
            if clean and (clean[0] in '🔴💎📱🗑🔐❓🎁🔥' or clean.startswith('❓')):
                title = clean
                break
        if title:
            result.append((len(result), title, p))
    return result


def show_faq_edit_list(cfg, chat_id, msg_id=None):
    """Список блоков FAQ для редактирования"""
    token = cfg['BOT_TOKEN']
    blocks = get_faq_blocks()
    NL = chr(10)
    if not blocks:
        text = '📝 FAQ файл не найден или пуст'
        kb = {'inline_keyboard': [[{'text': '⬅️ Назад', 'callback_data': 'adm_refresh'}]]}
    else:
        lines_txt = [
            f'📝 <b>УПРАВЛЕНИЕ FAQ</b>',
            '━━━━━━━━━━━━━━━━━━━━',
            '',
            f'Всего блоков: <b>{len(blocks)}</b>',
            '',
            'Выбери блок для редактирования:'
        ]
        text = NL.join(lines_txt)
        kb_rows = []
        for idx, title, _ in blocks:
            # Обрезаем длинный заголовок для кнопки
            btn_text = title if len(title) <= 45 else title[:42] + '...'
            kb_rows.append([{'text': btn_text, 'callback_data': f'faq_block:{idx}'}])
        kb_rows.append([{'text': '⬅️ Назад', 'callback_data': 'adm_refresh'}])
        kb = {'inline_keyboard': kb_rows}
    if msg_id:
        tg(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})
    else:
        send(token, chat_id, text, reply_markup=kb)


def show_faq_block(cfg, chat_id, msg_id, bkey):
    """Показывает содержимое блока FAQ"""
    token = cfg['BOT_TOKEN']
    try:
        idx = int(bkey)
    except:
        return
    blocks = get_faq_blocks()
    if idx < 0 or idx >= len(blocks):
        tg(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': '❌ Блок не найден', 'parse_mode': 'HTML'})
        return
    _, title, content = blocks[idx]
    NL = chr(10)
    text = NL.join([
        '📝 <b>БЛОК FAQ</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        f'📌 <b>{title}</b>',
        '',
        '━━━━━━━━━━━━━━━━━━━━',
        '📄 <b>Текущий текст:</b>',
        '',
        content,
        '',
        '━━━━━━━━━━━━━━━━━━━━'
    ])
    kb = {'inline_keyboard': [
        [{'text': '✏️ Редактировать текст', 'callback_data': f'faq_edit_go:{idx}'}],
        [{'text': '🔄 Обновить', 'callback_data': f'faq_block:{idx}'}],
        [{'text': '⬅️ К списку', 'callback_data': 'adm_faq_edit'}]
    ]}
    tg(token, 'editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': kb})


def start_faq_edit(cfg, chat_id, user_id, bkey):
    """Начало редактирования блока FAQ"""
    token = cfg['BOT_TOKEN']
    try:
        idx = int(bkey)
    except:
        return
    blocks = get_faq_blocks()
    if idx < 0 or idx >= len(blocks):
        send(token, chat_id, '❌ Блок не найден')
        return
    _, title, content = blocks[idx]
    # Сохраняем pending — ждём текст
    PENDING_FAQ_EDIT[user_id] = idx
    NL = chr(10)
    out = NL.join([
        '✏️ <b>РЕДАКТИРОВАНИЕ БЛОКА</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        f'📌 <b>{title}</b>',
        '',
        '⚠️ Отправь <b>новый текст ответа</b> (без заголовка).',
        'Заголовок останется неизменным.',
        '',
        'Поддерживается HTML:',
        '<code>&lt;b&gt;жирный&lt;/b&gt;</code>',
        '<code>&lt;i&gt;курсив&lt;/i&gt;</code>',
        '<code>&lt;code&gt;моно&lt;/code&gt;</code>',
        '',
        '👇 Жду текст:'
    ])
    send(token, chat_id, out)


def save_faq_block(cfg, chat_id, idx, new_text):
    """Сохраняет изменения в файл FAQ"""
    token = cfg['BOT_TOKEN']
    if not os.path.exists(FAQ_FILE):
        send(token, chat_id, '❌ FAQ файл не найден')
        return
    try:
        with open(FAQ_FILE) as f:
            content = f.read()
    except Exception as e:
        send(token, chat_id, f'❌ Ошибка чтения: {e}')
        return

    # Разбиваем на блоки
    parts = content.split(chr(10) + '────────────────────' + chr(10))
    # Первая часть — заголовок FAQ ("❓ ЧАСТЫЕ ВОПРОСЫ...")
    # Далее блоки

    # Собираем блоки как (idx, title, full_block)
    block_indices = []
    for i, p in enumerate(parts):
        p_stripped = p.strip()
        if not p_stripped:
            continue
        lines_p = p_stripped.split(chr(10))
        title = None
        for l in lines_p:
            clean = l.replace('<b>', '').replace('</b>', '').strip()
            if clean and (clean[0] in '🔴💎📱🗑🔐❓🎁🔥' or clean.startswith('❓')):
                title = clean
                break
        if title:
            block_indices.append((i, title))

    if idx < 0 or idx >= len(block_indices):
        send(token, chat_id, '❌ Блок не найден')
        return

    part_idx, title = block_indices[idx]

    # Перестраиваем блок: заголовок + новый текст
    new_block = f'{title}' + chr(10) + new_text.strip()

    parts[part_idx] = new_block

    # Собираем обратно
    new_content = (chr(10) + '────────────────────' + chr(10)).join(parts)

    try:
        # Бэкап
        bak = FAQ_FILE + '.bak_' + time.strftime('%F_%H%M')
        with open(bak, 'w') as f:
            f.write(content)
        with open(FAQ_FILE, 'w') as f:
            f.write(new_content)
    except Exception as e:
        send(token, chat_id, f'❌ Ошибка записи: {e}')
        return

    NL = chr(10)
    out = NL.join([
        '✅ <b>БЛОК ОБНОВЛЁН</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        f'📌 {title}',
        f'✏️ Размер: <b>{len(new_text)}</b> символов',
        '',
        '🔄 Изменения применены — оба бота',
        '   (VPN + поддержка) увидят новый текст'
    ])
    kb = {'inline_keyboard': [
        [{'text': '⬅️ К списку FAQ', 'callback_data': 'adm_faq_edit'}],
        [{'text': '🏠 В админ-панель', 'callback_data': 'adm_refresh'}]
    ]}
    send(token, chat_id, out, reply_markup=kb)
    log.info(f'FAQ block updated: {title}')


# Pending редактирования FAQ (user_id -> block_idx)
PENDING_FAQ_EDIT = {}


def auto_close_loop(cfg):
    """Автозакрытие тикетов каждый час"""
    hours = int(cfg.get('AUTO_CLOSE_HOURS', '1') or '1')
    while True:
        try:
            time.sleep(3600)  # каждый час
            cnt = sdb.auto_close_old(hours)
            if cnt:
                log.info(f"Auto-closed {cnt} tickets")
        except Exception as e:
            log.error(f"auto_close: {e}")


def main():
    cfg = load_config()
    token = cfg.get('BOT_TOKEN', '')
    admin_id = cfg.get('ADMIN_ID', '')
    if not token:
        log.error("BOT_TOKEN не задан")
        sys.exit(1)

    log.info("━━━ Support Bot запущен ━━━")
    log.info(f"Token: ...{token[-8:]}")
    log.info(f"Admin: {admin_id}")
    tg(token, 'deleteWebhook')
    # Команды для ВСЕХ
    tg(token, 'setMyCommands', {'commands': [
        {'command': 'start', 'description': '👋 Начать'},
        {'command': 'help', 'description': '❓ Помощь'}
    ]})
    # Команды только для админа (scope: chat)
    tg(token, 'setMyCommands', {
        'commands': [
            {'command': 'start', 'description': '👋 Начать'},
            {'command': 'help', 'description': '❓ Помощь'},
            {'command': 'admin', 'description': '⚙️ Админ-панель'}
        ],
        'scope': {'type': 'chat', 'chat_id': int(admin_id)}
    })
    # Убираем старое глобальное меню (если было)
    try:
        tg(token, 'deleteMyCommands', {'scope': {'type': 'default'}})
    except: pass

    # Поток для автозакрытия
    threading.Thread(target=auto_close_loop, args=(cfg,), daemon=True).start()

    offset = 0
    while True:
        try:
            updates = tg(token, 'getUpdates', {'offset': offset, 'timeout': 30,
                                               'allowed_updates': ['message', 'callback_query']})
            if not updates or not updates.get('ok'):
                time.sleep(3); continue
            for upd in updates.get('result', []):
                offset = upd['update_id'] + 1
                try:
                    if 'callback_query' in upd:
                        handle_callback(cfg, upd['callback_query'], token, admin_id)
                    elif 'message' in upd:
                        handle_message(cfg, upd['message'], token, admin_id)
                except Exception as e:
                    log.error(f"handle error: {e}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"main loop: {e}")
            time.sleep(5)



if __name__ == '__main__':
    main()
