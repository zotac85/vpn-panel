# Plisio payment gateway module
import json
import urllib.request
import urllib.parse
import logging

log = logging.getLogger('plisio')

API_BASE = 'https://api.plisio.net/api/v1'
UA = 'Mozilla/5.0 VPNPanel/1.0'


def _get_key():
    try:
        with open('/etc/UDPCustom/plisio.env') as f:
            for line in f:
                if line.startswith('PLISIO_KEY='):
                    return line.split('=', 1)[1].strip()
    except Exception as e:
        log.error('read key: %s', e)
    return ''


def _get(url):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UA)
    
    # Пытаемся взять прокси из файла, чтобы обойти блокировку провайдера
    proxy_url = None
    try:
        with open('/etc/UDPCustom/proxies.txt') as f:
            for line in f:
                p = line.strip()
                if p:
                    if ':' not in p: p += ':80'
                    proxy_url = f'http://{p}'
                    break
    except: pass

    if proxy_url:
        log.info(f'Plisio using proxy: {proxy_url}')
        proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
        opener = urllib.request.build_opener(proxy_handler)
        with opener.open(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    else:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())


def create_invoice(amount_usd, order_id, currency='USDT_BSC',
                   description='VPN balance topup',
                   callback_url=''):
    key = _get_key()
    if not key:
        return None
    params = {
        'api_key': key,
        'currency': currency,
        'order_name': order_id,
        'order_number': order_id,
        'source_currency': 'USD',
        'source_amount': str(amount_usd),
        'description': description,
    }
    if callback_url:
        params['callback_url'] = callback_url
    url = API_BASE + '/invoices/new?' + urllib.parse.urlencode(params)
    try:
        data = _get(url)
    except Exception as e:
        log.error('create_invoice: %s', e)
        return None
    if data.get('status') != 'success':
        log.error('plisio error: %s', data)
        return None
    return data.get('data')


def get_operation(operation_id):
    key = _get_key()
    if not key:
        return None
    url = API_BASE + '/operations/' + str(operation_id) + '?api_key=' + key
    try:
        data = _get(url)
    except Exception as e:
        log.error('get_operation: %s', e)
        return None
    if data.get('status') != 'success':
        return None
    return data.get('data')
