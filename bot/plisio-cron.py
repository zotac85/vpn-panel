#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, json, time, logging, urllib.request, urllib.parse
sys.path.insert(0, '/usr/local/bin')

logging.basicConfig(
    filename='/var/log/plisio-cron.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger('plisio-cron')

CONF = '/etc/UDPCustom/bot.conf'

def load_cfg():
    cfg = {}
    try:
        with open(CONF) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip().strip('"')
    except Exception as e:
        log.error('load_cfg: %s', e)
    return cfg

def tg_send(token, chat_id, text):
    if not token or not chat_id:
        return
    try:
        data = urllib.parse.urlencode({
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }).encode()
        req = urllib.request.Request(
            'https://api.telegram.org/bot' + token + '/sendMessage',
            data=data
        )
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        log.error('tg_send: %s', e)


def check_payments():
    from bot_modules import db
    from bot_modules import plisio

    rows = db.query(
        "SELECT id, tg_id, amount, external_id, meta FROM payments "
        "WHERE method='crypto' AND status='pending' "
        "AND created_at < ? ORDER BY id ASC LIMIT 20",
        (int(time.time()) - 30,)
    )
    if not rows:
        return 0

    cfg = load_cfg()
    token = cfg.get('BOT_TOKEN', '')
    admin_id = cfg.get('ADMIN_ID', '')
    done = 0

    for row in rows:
        pid = row['id']
        tg_id = row['tg_id']
        amt = float(row['amount'])
        txn = row['external_id']
        if not txn:
            continue
        op = plisio.get_operation(txn)
        if not op:
            continue
        status = (op.get('status') or '').lower()
        log.info('payment #%s txn=%s status=%s', pid, txn, status)

        if status in ('completed', 'mismatch'):
            _credit_paid(db, cfg, token, admin_id, pid, tg_id, amt, op)
            done += 1
        elif status in ('expired', 'cancelled', 'error'):
            db.execute(
                "UPDATE payments SET status='failed' WHERE id=?",
                (pid,)
            )
            tg_send(token, tg_id,
                '❌ <b>Счёт истёк</b>\n\n'
                'Заказ <code>' + str(txn) + '</code> не оплачен.\n'
                'Создай новый счёт в кабинете.')
    return done


def _credit_paid(db, cfg, token, admin_id, pid, tg_id, amt, op):
    real = op.get('amount') or op.get('invoice_total_sum') or amt
    try:
        real_amt = float(real)
    except:
        real_amt = amt
    if real_amt <= 0:
        real_amt = amt

    user = db.get_user(tg_id) or {}
    u_name = user.get('first_name') or '—'
    u_uname = user.get('username') or ''
    if u_uname:
        u_link = '@' + u_uname
    else:
        u_link = 'ID ' + str(tg_id)

    cur = (op.get('psys_cid') or '').upper()
    if not cur:
        meta = {}
        try:
            meta = json.loads(op.get('meta') or '{}')
        except:
            pass
        cur = (meta.get('currency') or 'USDT').upper()

    meta_json = json.dumps({
        'txn': op.get('txn_id'),
        'status': op.get('status'),
        'currency': cur,
    })

    db.execute(
        "UPDATE payments SET status='paid', paid_at=?, meta=? WHERE id=?",
        (int(time.time()), meta_json, pid)
    )
    db.execute(
        "UPDATE users SET balance = balance + ? WHERE tg_id=?",
        (round(real_amt, 4), int(tg_id))
    )

    NL = chr(10)
    user_msg = NL.join([
        '✅ <b>ОПЛАТА ПОЛУЧЕНА</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '💵 Зачислено: <b>' + ('%.2f' % real_amt) + ' USD</b>',
        '💎 Сеть: <b>' + cur + '</b>',
        '🆔 Заказ: <code>' + str(op.get('txn_id')) + '</code>',
        '',
        'Баланс обновлён в кабинете 👤',
    ])
    tg_send(token, tg_id, user_msg)

    admin_msg = NL.join([
        '💰 <b>CRYPTO ОПЛАТА</b>',
        '━━━━━━━━━━━━━━━━━━━━',
        '',
        '👤 Юзер: ' + u_name + ' (' + u_link + ')',
        '🆔 TG ID: <code>' + str(tg_id) + '</code>',
        '💵 Сумма: <b>' + ('%.2f' % real_amt) + ' USD</b>',
        '💎 Сеть: <b>' + cur + '</b>',
        '📦 Заказ: <code>' + str(op.get('txn_id')) + '</code>',
    ])
    tg_send(token, admin_id, admin_msg)
    log.info('credited #%s tg=%s amt=%s', pid, tg_id, real_amt)


def main():
    try:
        n = check_payments()
        if n:
            log.info('credited %s payment(s)', n)
    except Exception as e:
        log.exception('main: %s', e)


if __name__ == '__main__':
    main()
