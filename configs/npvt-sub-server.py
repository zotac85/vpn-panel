#!/usr/bin/env python3
import http.server
import socketserver
import base64
import json
import sqlite3
import sys
import ssl

sys.path.append('/usr/local/bin')
from bot_modules import db as bdb
from bot_modules import cabinet as cab

def load_cfg():
    cfg = {}
    try:
        with open('/etc/UDPCustom/bot.conf') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.strip().split('=', 1)
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    except: pass
    return cfg


PORT = 8444

def b64(s): return base64.b64encode(s.encode()).decode()

def generate_npvt(username, password, host, remark):
    port = 80
    proxy = cab.get_random_proxy() or "8.6.112.0:80"
    payload = "CONNECT / HTTP/1.1[crlf]Host: ya.ru[crlf]User-Agent: Mozilla/5.0 (Linux; Android 13) Chrome/120[crlf][crlf]POST / HTTP/1.1[crlf]Host: [host][crlf]Connection: upgrade[crlf]Upgrade: websocket[crlf][crlf]"

    data = {
        "sshConfigType": "npvs1:" + b64("SSH-Proxy-Payload"),
        "remarks": "npvs1:" + b64(remark),
        "sshHost": "npvs1:" + b64(host),
        "sshPort": port,
        "sshUsername": "npvs1:" + b64(username),
        "sshPassword": "npvs1:" + b64(password),
        "sshAuthMethod": "npvs1:" + b64("PASSWORD"),
        "sshPrivateKey": "",
        "sshPrivateKeyPassphrase": "",
        "sni": "",
        "tlsVersion": "npvs1:" + b64("DEFAULT"),
        "httpProxy": "npvs1:" + b64(proxy),
        "authenticateProxy": False,
        "proxyUsername": "",
        "proxyPassword": "",
        "payload": "npvs1:" + b64(payload),
        "dnsTTMode": "npvs1:" + b64("UDP"),
        "dnsServer": "",
        "nameserver": "",
        "publicKey": "",
        "udpgwPort": 7300,
        "udpgwTransparentDNS": False
    }
    json_str = json.dumps(data, separators=(',', ':'))
    return f"npvt-ssh://{base64.b64encode(json_str.encode()).decode()}"

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/sub_dark/'):
            key_name = self.path.split('/sub_dark/')[1].split('?')[0]
            key = bdb.get_test_key(key_name) or bdb.get_vip_key(key_name)
            if not key:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Key not found")
                return
            
            conn = sqlite3.connect('/etc/UDPCustom/vpn.db')
            nodes = conn.execute("SELECT name, host, ws_port FROM nodes WHERE is_active=1 AND (is_master=1 OR status='online') ORDER BY is_master DESC, id").fetchall()
            conn.close()
            
            links = []
            for name, host, ws_port in nodes:
                try:
                    dt_url, _cfg_name = cab._build_dark_url_for_key(
                        load_cfg(), key_name, domain=host, ws_port=ws_port, location_name=name
                    )
                    if dt_url:
                        links.append(dt_url)
                except Exception as e:
                    links.append(f"ERROR: {e}")
            
            if not links:
                links.append("ERROR: No links generated.")
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write("\n".join(links).encode('utf-8'))
            return
            
        if self.path.startswith('/sub/'):
            key_name = self.path.split('/sub/')[1].split('?')[0]
            key = bdb.get_test_key(key_name) or bdb.get_vip_key(key_name)
            if not key:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Key not found")
                return
            
            conn = sqlite3.connect('/etc/UDPCustom/vpn.db')
            nodes = conn.execute("SELECT name, host FROM nodes WHERE is_active=1 AND (is_master=1 OR status='online') ORDER BY is_master DESC, id").fetchall()
            conn.close()
            
            links = [generate_npvt(key['login'], key['password'], host, name) for name, host in nodes]
            _data = "\n".join(links).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(_data)))
            self.end_headers()
            self.wfile.write(_data)
            return
            self.end_headers()

socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
    # SSL отключен, так как Nginx берет на себя шифрование
    httpd.serve_forever()
