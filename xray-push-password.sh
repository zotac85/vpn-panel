#!/bin/bash
# xray-push-password.sh <login> <target>
#   target: "all" | N (порядковый номер из меню) | IP | host | часть имени
# Синхронизирует trojan_password VIP-ключа на ноду (или все ноды).

set -u
LOGIN="$1"
TARGET="${2:-all}"
[ -z "$LOGIN" ] && { echo "Usage: $0 <login> <all|N|host|ip>"; exit 1; }

DB=/etc/UDPCustom/vpn.db
PASS=$(python3 -c "import sqlite3; r=sqlite3.connect('$DB').execute('SELECT trojan_password FROM vip_keys WHERE login=?', ('$LOGIN',)).fetchone(); print(r[0] if r and r[0] else '')")
if [ -z "$PASS" ]; then
    echo "[xray-push] ERROR: нет trojan_password у '$LOGIN' (сначала запроси ключ Трояна)"
    exit 2
fi
echo "[xray-push] login=$LOGIN pass=${PASS:0:8}..."

# Собираем список нод (без мастера)
NODES=$(python3 - "$TARGET" << 'PYEOF'
import sqlite3, sys
DB = '/etc/UDPCustom/vpn.db'
TARGET = sys.argv[1]
db = sqlite3.connect(DB)

if TARGET == 'all':
    for r in db.execute('SELECT id,name,ip,ssh_port FROM nodes WHERE is_master=0 ORDER BY id'):
        print('|'.join(str(x) for x in r))
    sys.exit(0)

# Сортируем как в меню: master first, потом по id
rows = db.execute('SELECT id,name,ip,ssh_port,is_master FROM nodes ORDER BY is_master DESC, id').fetchall()

def emit(r):
    if r[4] == 1:
        print("MASTER|0|0|0")
    else:
        print('|'.join(str(x) for x in r[:4]))

if TARGET.isdigit():
    # 1. Порядковый номер (как в меню)
    idx = int(TARGET) - 1
    if 0 <= idx < len(rows):
        emit(rows[idx]); sys.exit(0)
    # 2. Fallback: реальный DB id
    r = db.execute('SELECT id,name,ip,ssh_port,is_master FROM nodes WHERE id=?', (TARGET,)).fetchone()
    if r:
        emit(r); sys.exit(0)

# 3. IP или host
r = db.execute('SELECT id,name,ip,ssh_port,is_master FROM nodes WHERE ip=? OR host=?', (TARGET, TARGET)).fetchone()
if r:
    emit(r); sys.exit(0)

# 4. Подстрока в имени
for r in rows:
    if TARGET.lower() in str(r[1]).lower():
        emit(r); sys.exit(0)

print("NOTFOUND")
PYEOF
)

if [ -z "$NODES" ] || [ "$NODES" = "NOTFOUND" ]; then
    echo "[xray-push] WARN: нода не найдена (target=$TARGET)"
    exit 1
fi

if echo "$NODES" | grep -q '^MASTER'; then
    echo "[xray-push] WARN: '$TARGET' — это мастер. На мастере пароль уже есть, пропускаю."
    exit 0
fi

FAIL=0; TOTAL=0
while IFS='|' read -r id name ip sport; do
    [ -z "$id" ] && continue
    TOTAL=$((TOTAL+1))
    echo -n "[xray-push] → $name ($ip: $sport): "
    RESULT=$(ssh -q -o StrictHostKeyChecking=no -o BatchMode=yes -o LogLevel=QUIET -o ConnectTimeout=10 -p "$sport" root@"$ip" "python3 - '$PASS'" 2>&1 << 'NODE_PY'
import json, sys
PASS = sys.argv[1]
p = '/usr/local/etc/xray/config.json'
try:
    with open(p) as f: c = json.load(f)
    clients = c['inbounds'][0]['settings']['clients']
    if any(cl.get('password') == PASS for cl in clients):
        print('already'); sys.exit(0)
    clients.append({'password': PASS})
    with open(p, 'w') as f: json.dump(c, f, indent=2)
    print('added')
except Exception as e:
    print(f'ERROR: {e}'); sys.exit(1)
NODE_PY
)
    case "$RESULT" in
        already) echo "уже есть" ;;
        added)
            if ssh -q -o StrictHostKeyChecking=no -o BatchMode=yes -o LogLevel=QUIET -p "$sport" root@"$ip" "systemctl restart xray" >/dev/null 2>&1; then
                echo "✅ добавлен + Xray перезапущен"
            else
                echo "⚠️  добавлен, но рестарт Xray упал"; FAIL=$((FAIL+1))
            fi ;;
        *) echo "❌ $RESULT"; FAIL=$((FAIL+1)) ;;
    esac
done <<< "$NODES"

echo
if [ "$FAIL" -eq 0 ]; then
    echo "[xray-push] OK (нод: $TOTAL)"; exit 0
else
    echo "[xray-push] WARN: ошибок $FAIL из $TOTAL"; exit 1
fi
