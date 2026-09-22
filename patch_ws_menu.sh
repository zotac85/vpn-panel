#!/bin/bash
# Патч: добавляет управление доменом и прокси в WebSocket Proxy

if [ "$EUID" -ne 0 ]; then
    echo "Запустите от root"
    exit 1
fi

echo "🔧 Патч: меню WebSocket Proxy (домен + прокси)"
echo ""

VPN_FILE="/usr/local/bin/vpn"
WS_FILE="/usr/local/share/vpn-panel/modules/ws.sh"
DOMAIN_MODULE="/usr/local/share/vpn-panel/modules/domain_proxy.sh"

# ─── 1. Проверка модуля ───
if [ ! -f "$DOMAIN_MODULE" ]; then
    echo "❌ Модуль не найден: $DOMAIN_MODULE"
    exit 1
fi
echo "✅ Модуль domain_proxy.sh найден"

# ─── 2. Патч vpn — добавляем source ───
if grep -q "domain_proxy" "$VPN_FILE"; then
    echo "✅ vpn: source уже есть"
else
    sed -i '/banner.sh/a source "$PANEL_DIR/modules/domain_proxy.sh"' "$VPN_FILE"
    echo "✅ vpn: source добавлен"
fi

# ─── 3. Патч ws.sh — добавляем пункты в меню ───
cp "$WS_FILE" "${WS_FILE}.bak"

# 3a. Добавляем пункты 5, 6, 7 (сдвигаем старый 5 на 7)
python3 - << 'PYEOF'
path = "/usr/local/share/vpn-panel/modules/ws.sh"
with open(path) as f: c = f.read()

# Меню
old_menu = '        echo -e " 5) 📜 Посмотреть логи работы"\n        echo -e " 6) 🗑️  Удалить с сервера"\n        echo -e " 0) ↩️  Назад в главное меню"\n        echo ""\n        read -p "Выберите действие [0-6]: " ws_choice'

new_menu = '        echo -e " 5) 🌐 Управление доменом"\n        echo -e " 6) 🔒 Управление прокси"\n        echo -e " 7) 📜 Посмотреть логи работы"\n        echo -e " 8) 🗑️  Удалить с сервера"\n        echo -e " 0) ↩️  Назад в главное меню"\n        echo ""\n        read -p "Выберите действие [0-8]: " ws_choice'

if old_menu in c:
    c = c.replace(old_menu, new_menu)
    print("✅ Меню обновлено (5-8)")
else:
    print("⚠️  Старое меню не найдено — проверь вручную")

# Case
old_case = '            4) change_ws_port ;;\n            5) header; journalctl -u ws-proxy -n 25 --no-pager; echo ""; read -p "Enter..." ;;\n            6) '

new_case = '            4) change_ws_port ;;\n            5) manage_domain ;;\n            6) manage_proxy ;;\n            7) header; journalctl -u ws-proxy -n 25 --no-pager; echo ""; read -p "Enter..." ;;\n            8) '

if old_case in c:
    c = c.replace(old_case, new_case)
    print("✅ Case обновлён (5-8)")
else:
    print("⚠️  Старый case не найден — проверь вручную")

with open(path, "w") as f: f.write(c)
PYEOF

# ─── 4. Проверка синтаксиса ───
echo ""
echo "=== Проверка синтаксиса ==="
bash -n "$VPN_FILE" && echo "✅ vpn OK"
bash -n "$WS_FILE" && echo "✅ ws.sh OK"
bash -n "$DOMAIN_MODULE" && echo "✅ domain_proxy.sh OK"

# ─── 5. Показать результат ───
echo ""
echo "=== vpn ==="
grep domain_proxy "$VPN_FILE"
echo ""
echo "=== ws.sh меню ==="
grep -E "5\) 🌐|6\) 🔒|7\) 📜|8\) 🗑" "$WS_FILE"
echo ""
echo "=== ws.sh case ==="
grep -E "5\) manage_domain|6\) manage_proxy|7\) header|8\) " "$WS_FILE"

echo ""
echo "🟢 Патч применён!"
echo ""
echo "Открывай панель: vpn → 2) WebSocket Proxy"
echo "Откат: cp ${WS_FILE}.bak ${WS_FILE}"
