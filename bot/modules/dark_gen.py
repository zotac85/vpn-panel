#!/usr/bin/env python3
"""
Генератор darktunnel:// конфига с HWID-привязкой.
Сервер: de.cdnstore.shop (Германия)

Использование:
    python3 gen_dark.py <HWID>
    python3 gen_dark.py CF72F6289D5AD93C52205D3251B7330CD25618B6

Опционально можно переопределить (позиционные аргументы):
    [host] [port] [user] [pass] [proxyHost] [proxyPort] [name]
"""
import sys, base64, json, msgpack, hashlib
from Crypto.Cipher import AES

KEY256   = b"$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd"
KEY192   = b"F)J@NcRfUjXn2r4u7x!A%D*G"
IV       = bytes.fromhex("232e39185523184a5723586242200e05")
HW_CONST = "dc55427ad9af7cd342eb60c17393d1c2936521bae81e39147e9e974bf44dff80"
import os
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'assets', 'blank.dark')

# Данные немецкого сервера
DEF_HOST      = 'de.cdnstore.shop'
DEF_PORT      = '2052'
DEF_USER      = 'vip_rrrttrrrr'
DEF_PASS      = 'G4PY1McMVote'
DEF_PROXYHOST = '162.159.228.0'
DEF_PROXYPORT = '2052'
DEF_PAYLOAD   = ('CONNECT http://co.nr HTTP/1.1[crlf]Host: www.icloud.com[crlf]'
                 'User-Agent: microsoft.com[crlf][crlf]AN / HTTP/1.1[lf]Host: [host][lf]'
                 'Connection: Upgrade[lf]Upgrade: websocket[crlf][crlf]')

def b64u(d): return base64.urlsafe_b64encode(d).decode().rstrip('=')
def b64d(s): return base64.urlsafe_b64decode(s + "="*(-len(s)%4))
def E(k,d):
    if isinstance(d,str): d=d.encode()
    return AES.new(k, AES.MODE_CFB, iv=IV, segment_size=128).encrypt(d)
def D(k,d): return AES.new(k, AES.MODE_CFB, iv=IV, segment_size=128).decrypt(d)

def build_hwid(h):
    h = h.strip().upper().replace('-','').replace(' ','')
    return HW_CONST.encode().hex() + h.encode().hex() + hashlib.sha256(b'').hexdigest()

def generate(hwid, host=DEF_HOST, port=DEF_PORT, user=DEF_USER, pw=DEF_PASS,
             proxyhost=DEF_PROXYHOST, proxyport=DEF_PROXYPORT, name=None):
    if name is None:
        name = f'VIP-\u0413\u0435\u0440\u043c\u0430\u043d\u0438\u044f-{hwid[:6]}'

    link = open(TEMPLATE).read().strip().replace("darktunnel://","")
    outer  = json.loads(b64d(link).decode())
    inner  = msgpack.unpackb(D(KEY256, b64d(outer['encryptedLockedConfig'])), raw=False, strict_map_key=False)
    locked = msgpack.unpackb(D(KEY192, inner['EncryptedLockedConfig']), raw=False, strict_map_key=False)

    # LockedAppConfig: HWID + обязательный непустой ConnectedMessage
    lac = inner['LockedAppConfig']
    lac['ConnectedMessage'] = '\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043e !'.encode()
    lac['Message'] = b'<b>ArsenVipKeys</b><br>t.me/ArsenVipKeys'
    lac['HardwareIdList']   = [build_hwid(hwid)]
    lac['IsSshLocked']      = True

    # ===== ПРАВИЛА DarkTunnel (НЕ УДАЛЯТЬ!) =====
    # 1) ConnectedMessage обязательно непустое
    # 2) SSH host/port/user/pw — обязательно непустые
    # 3) Proxy proxyhost/proxyport/payload — обязательно непустые
    # 4) HardwareIdList обязательно заполнен
    if not lac.get('ConnectedMessage'):
        raise ValueError('DarkTunnel: ConnectedMessage НЕ МОЖЕТ быть пустым!')
    for _fn, _fv in (('host',host),('port',port),('user',user),('pw',pw)):
        if not _fv:
            raise ValueError(f'DarkTunnel: SSH-поле {_fn!r} не может быть пустым')
    for _fn, _fv in (('proxyhost',proxyhost),('proxyport',proxyport)):
        if not _fv:
            raise ValueError(f'DarkTunnel: proxy-поле {_fn!r} не может быть пустым')
    if not DEF_PAYLOAD:
        raise ValueError('DarkTunnel: payload не может быть пустым')
    if not lac.get('HardwareIdList'):
        raise ValueError('DarkTunnel: HardwareIdList не может быть пустым')

    # SshConfig
    ssh = locked['SshConfig']
    ssh['IsEncrypted']       = True
    ssh['IsLocked']          = True
    ssh['EncryptedHost']     = E(KEY192, host)
    ssh['EncryptedPort']     = E(KEY192, port)
    ssh['EncryptedUsername'] = E(KEY192, user)
    ssh['EncryptedPassword'] = E(KEY192, pw)

    # InjectConfig
    inj = locked['InjectConfig']
    inj['IsEncrypted']                   = True
    inj['EncryptedMode']                 = E(KEY192, 'PROXY')
    inj['EncryptedProxyHost']            = E(KEY192, proxyhost)
    inj['EncryptedProxyPort']            = E(KEY192, proxyport)
    inj['EncryptedServerNameIndication'] = E(KEY192, '')
    inj['EncryptedPayload']              = E(KEY192, DEF_PAYLOAD)
    inj['EncryptedDnsttDnsHost']         = E(KEY192, '1.1.1.1')
    inj['EncryptedDnsttDnsPort']         = E(KEY192, '53')
    inj['EncryptedDnsttServerName']      = E(KEY192, '')
    inj['EncryptedDnsttPubkey']          = E(KEY192, '')

    # V2RayConfig
    v2 = locked['V2RayConfig']
    v2['IsEncrypted']         = True
    v2['IsInjectModeEnabled'] = False
    v2['EncryptedConfig']     = E(KEY192, '')

    inner['EncryptedLockedConfig'] = E(KEY192, msgpack.packb(locked, use_bin_type=True))
    enc = E(KEY256, msgpack.packb(inner, use_bin_type=True))
    o2 = dict(outer)
    o2['encryptedLockedConfig'] = b64u(enc)
    o2['name'] = name
    return 'darktunnel://' + b64u(json.dumps(o2, ensure_ascii=False, separators=(',',':')).encode())

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    hwid = sys.argv[1]
    args = sys.argv[2:]
    host      = args[0] if len(args) > 0 else DEF_HOST
    port      = args[1] if len(args) > 1 else DEF_PORT
    user      = args[2] if len(args) > 2 else DEF_USER
    pw        = args[3] if len(args) > 3 else DEF_PASS
    proxyhost = args[4] if len(args) > 4 else DEF_PROXYHOST
    proxyport = args[5] if len(args) > 5 else DEF_PROXYPORT
    name      = args[6] if len(args) > 6 else None

    link = generate(hwid, host, port, user, pw, proxyhost, proxyport, name)
    out = f'/tmp/dark_{hwid[:8]}.txt'
    open(out, 'w').write(link)
    print(f"OK -> {out}  ({len(link)} \u0431\u0430\u0439\u0442)\n")
    print(link)

if __name__ == '__main__':
    main()
