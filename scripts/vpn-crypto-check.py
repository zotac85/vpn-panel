#!/usr/bin/env python3
# vpn-crypto-check.py - проверяет pending-платежи Plisio
import sys, time, logging
sys.path.insert(0, '/usr/local/bin')
from bot_modules import plisio, db

logging.basicConfig(
    filename='/var/log/vpn-crypto-check.log',
    level=logging.INFO,
    format='%(asctime)s [CRYPTO] %(message)s'
)

def main():
    rows = db.query("SELECT id, tg_id, amount, external_id FROM payments WHERE method='crypto' AND status='pending'")
    if not rows:
        return
    for r in rows:
        op = plisio.get_operation(r['external_id'])
        if not op:
            continue
        status = op.get('status', '')
        if status not in ('completed', 'mismatch'):
            continue
        amt = float(r['amount'])
        tg = int(r['tg_id'])
        bonus = db.get_topup_bonus(tg)
        add = 0.0
        if bonus:
            try:
                add = amt * float(bonus['percent']) / 100.0
            except Exception:
                pass
        total = amt + add
        db.add_balance(tg, total, method='crypto', meta={'op': r['external_id'], 'bonus': add})
        if bonus:
            try:
                db.mark_bonus_used(tg)
            except Exception:
                pass
        db.execute("UPDATE payments SET status='paid', paid_at=? WHERE id=?", (int(time.time()), r['id']))
        logging.info('paid: tg=%s amount=%s bonus=%s', tg, amt, add)

if __name__ == '__main__':
    main()
