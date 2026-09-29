"""DarkTunnel .dark config encryptor (формат 1.0.26)."""
import base64
import hashlib
import json
import os
import msgpack
from Crypto.Cipher import AES

KEY256 = b"$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd"
KEY192 = b"F)J@NcRfUjXn2r4u7x!A%D*G"
IV = bytes.fromhex("232e39185523184a5723586242200e05")

# Секретная константа, извлечена из libgojni.so (aztecrabbit/libdarktunnel)
HW_CONST = "dc55427ad9af7cd342eb60c17393d1c2936521bae81e39147e9e974bf44dff80"


def _build_hwid(hwid):
    """Строит строку HWID для HardwareIdList (272 символа).
    Формула: hex(HW_CONST) + hex(HWID_upper) + sha256(b"").hexdigest()
    """
    if not hwid:
        return None
    h = str(hwid).strip().upper().replace("-", "").replace(" ", "")
    sha_empty = hashlib.sha256(b"").hexdigest()
    return HW_CONST.encode().hex() + h.encode().hex() + sha_empty


def _enc(key, data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return AES.new(key, AES.MODE_CFB, iv=IV, segment_size=128).encrypt(data)


def _b64url(data):
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _enc_field(name, value):
    if value is None:
        value = ''
    if isinstance(value, (int, float)):
        value = str(value)
    return 'Encrypted' + name[0].upper() + name[1:], _enc(KEY192, value)


def build_darktunnel_link(name, ssh_config, inject_config, hardware_list=None,
                          message=None, connected_message=None):
    """Собирает darktunnel:// ссылку. HWID-привязка отключена (Lock SSH Account),
    конфиг зашифрован, но без проверки устройства."""

    # ===== InjectConfig =====
    inj = inject_config or {}
    inject_locked = {'IsEncrypted': True}
    for key, src in (
        ('Mode', 'mode'),
        ('ProxyHost', 'proxyHost'),
        ('ProxyPort', 'proxyPort'),
        ('ServerNameIndication', 'serverNameIndication'),
        ('Payload', 'payload'),
        ('DnsttDnsHost', 'dnsttDnsHost'),
        ('DnsttDnsPort', 'dnsttDnsPort'),
        ('DnsttServerName', 'dnsttServerName'),
        ('DnsttPubkey', 'dnsttPubkey'),
    ):
        val = inj.get(src, '')
        if src == 'mode' and not val:
            val = 'PROXY'
        if src == 'dnsttDnsHost' and not val:
            val = '1.1.1.1'
        if src == 'dnsttDnsPort' and not val:
            val = '53'
        k, v = _enc_field(key, val)
        inject_locked[k] = v

    # ===== SshConfig =====
    ssh = ssh_config or {}
    has_hwid = bool(hardware_list)
    ssh_locked = {
        'IsEncrypted': True,
        'IsLocked': has_hwid,
    }
    for key, src in (
        ('Host', 'host'),
        ('Port', 'port'),
        ('Username', 'username'),
        ('Password', 'password'),
    ):
        k, v = _enc_field(key, ssh.get(src, ''))
        ssh_locked[k] = v

    # ===== V2RayConfig =====
    v2ray_locked = {
        'IsEncrypted': True,
        'IsInjectModeEnabled': False,
        'EncryptedConfig': _enc(KEY192, ''),
    }

    locked_inner = {
        'InjectConfig': inject_locked,
        'SshConfig': ssh_locked,
        'V2RayConfig': v2ray_locked,
    }
    inner_locked_bytes = _enc(KEY192, msgpack.packb(locked_inner, use_bin_type=True))

    # ===== LockedAppConfig =====
    # HWID-привязка: Password оставляем пустым (DarkTunnel принимает),
    # HardwareIdList заполняем строками из формулы _build_hwid().
    hw_list = []
    for h in (hardware_list or []):
        s_hw = _build_hwid(h)
        if s_hw:
            hw_list.append(s_hw)
    locked_app = {
        'VersionCode': 32,
        'VersionName': b'1.0.26',
        'Message': (message or '').encode('utf-8'),
        'ConnectedMessage': (connected_message or '').encode('utf-8'),
        'Password': b'',
        'ExpiredAtTimestamp': 0,
        'HardwareIdList': hw_list,
        'TunnelType': 'SSH',
        'IsSshLocked': bool(hw_list),
    }

    inner = {
        'LockedAppConfig': locked_app,
        'EncryptedLockedConfig': inner_locked_bytes,
    }
    outer_locked_bytes = _enc(KEY256, msgpack.packb(inner, use_bin_type=True))

    outer = {
        'type': 'SSH',
        'name': name,
        'sshTunnelConfig': {
            'injectConfig': {
                'enabled': True,
                'mode': 'PROXY',
            },
        },
        'encryptedLockedConfig': _b64url(outer_locked_bytes),
    }
    outer_json = json.dumps(outer, ensure_ascii=False, separators=(',', ':'))
    return 'darktunnel://' + _b64url(outer_json.encode('utf-8'))
