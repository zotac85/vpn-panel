#!/bin/bash

if [ "$EUID" -ne 0 ]; then
  echo "Ошибка: запустите скрипт от root (sudo -i)"
  exit 1
fi

PANEL_DIR="/usr/local/share/vpn-panel"
REPO_URL="https://raw.githubusercontent.com/zotac85/vpn-panel/main"

echo -e "\033[0;36m==============================================\033[0m"
echo -e "        \033[1;33m⚡ VPN PANEL INSTALLER / UPDATER ⚡\033[0m"
echo -e "\033[0;36m==============================================\033[0m"


# ──────────────────────────────────────────────────────────────
# Установка cron (нужен для автоочистки, лимитов, мониторинга)
# ──────────────────────────────────────────────────────────────
if ! command -v crontab &>/dev/null; then
    apt update -qq >/dev/null 2>&1
    apt install -y cron >/dev/null 2>&1
    echo -e "\033[0;32m✅ Cron установлен\033[0m"
fi
systemctl enable cron >/dev/null 2>&1
systemctl start cron >/dev/null 2>&1

# ──────────────────────────────────────────────────────────────
# git и curl (нужны для обновления бота)
# ──────────────────────────────────────────────────────────────
if ! command -v git >/dev/null 2>&1; then
    echo "→ Установка git..."
    apt update -qq >/dev/null 2>&1
    apt install -y git >/dev/null 2>&1
    echo -e "\033[0;32m✅  Git установлен\033[0m"
fi
if ! command -v curl >/dev/null 2>&1; then
    echo "→ Установка curl..."
    apt update -qq >/dev/null 2>&1
    apt install -y curl >/dev/null 2>&1
    echo -e "\033[0;32m✅  Curl установлен\033[0m"
fi

# ──────────────────────────────────────────────────────────────
# UTF-8 локаль (для корректной работы nano с русским текстом)
# ──────────────────────────────────────────────────────────────
if ! locale | grep -q "UTF-8"; then
    apt install -y locales >/dev/null 2>&1
    locale-gen en_US.UTF-8 >/dev/null 2>&1
    update-locale LANG=en_US.UTF-8 >/dev/null 2>&1
fi

# ──────────────────────────────────────────────────────────────
# Python-зависимости для бота (pycryptodome, msgpack)
# ──────────────────────────────────────────────────────────────
PY_DEPS_OK=1
python3 -c "import Crypto" 2>/dev/null || PY_DEPS_OK=0
python3 -c "import msgpack" 2>/dev/null || PY_DEPS_OK=0
if [ "$PY_DEPS_OK" = "0" ]; then
    echo "→ Установка Python-зависимостей (pycryptodome, msgpack)..."
    # Пробуем apt (Debian/Ubuntu)
    apt install -y python3-cryptodome python3-msgpack >/dev/null 2>&1 || true
    # Проверяем ещё раз
    python3 -c "import Crypto" 2>/dev/null || {
        # Fallback — pip (без ломания system packages)
        apt install -y python3-pip >/dev/null 2>&1 || true
        pip3 install --break-system-packages pycryptodome msgpack google-genai >/dev/null 2>&1 || \
        pip3 install pycryptodome msgpack google-genai >/dev/null 2>&1 || true
    }
    if python3 -c "import Crypto" 2>/dev/null && python3 -c "import msgpack" 2>/dev/null; then
        echo -e "\033[0;32m✅   Python-зависимости установлены\033[0m"
    else
        echo -e "\033[0;31m⚠️  Не удалось установить pycryptodome/msgpack — бот может работать некорректно\033[0m"
    # Проверка google-genai
    python3 -c "import google.genai" 2>/dev/null || {
        apt install -y python3-pip >/dev/null 2>&1 || true
        pip3 install --break-system-packages google-genai >/dev/null 2>&1 || \
        pip3 install google-genai >/dev/null 2>&1 || true
    }
    if python3 -c "import google.genai" 2>/dev/null; then
        echo -e "\033[0;32m✅    google-genai установлен (ИИ-проверка чеков)\033[0m"
    else
        echo -e "\033[0;33m⚠️  google-genai не установлен — ИИ-проверка чеков недоступна\033[0m"
    fi

    fi
fi

if [ -d "$PANEL_DIR" ] || [ -f "/usr/local/bin/vpn" ]; then
    echo -e "\033[1;33mОбнаружена ранее установленная панель.\033[0m"
    echo ""
    echo " 1) 🔄 Обновить скрипты и модули (базы и настройки сохранятся)"
    echo " 2) 🤖 Обновить только Telegram-бота (быстро, без сервисов)"
    echo " 3) 📝 Обновить только тексты (безопасно, без конфигов и баз)"
    echo " 4) ⚙️ Переустановить полностью (сброс конфигурации)"
    echo " 0) 🚪 Отмена"
    echo ""
    read -p "Выберите действие [0-4]: " choice
    case $choice in
        1) echo -e "\n🔄 Обновление компонентов панели..." ;;
        2)
            echo -e "\n🤖 Обновление Telegram-бота..."
            REPO_DIR="/root/vpn-panel-sync"
            if [ ! -d "$REPO_DIR" ]; then
                echo -e "\033[0;31m❌ Репо не найдено: $REPO_DIR\033[0m"
                exit 1
            fi
            cd "$REPO_DIR" || exit 1
            echo "→ git pull..."
            git pull origin main 2>&1 | tail -3 || true
            if [ ! -f "$REPO_DIR/bot/vpn-tg-bot.py" ]; then
                echo -e "\033[0;31m❌ Нет bot/vpn-tg-bot.py в репо\033[0m"
                exit 1
            fi
            BK_TS=$(date +%F_%H%M)
            if [ -f /usr/local/bin/vpn-tg-bot.py ]; then
                cp /usr/local/bin/vpn-tg-bot.py "/usr/local/bin/vpn-tg-bot.py.bak_${BK_TS}"
                echo "→ Бэкап: vpn-tg-bot.py.bak_${BK_TS}"
                ls -t /usr/local/bin/vpn-tg-bot.py.bak_* 2>/dev/null | tail -n +6 | xargs -r rm -f
            fi
            echo "→ Копирование..."
            cp "$REPO_DIR/bot/vpn-tg-bot.py" /usr/local/bin/vpn-tg-bot.py
            chmod +x /usr/local/bin/vpn-tg-bot.py
            mkdir -p /usr/local/bin/bot_modules
            for f in __init__.py admin.py autopost.py cabinet.py db.py dark_gen.py support_db.py; do
                if [ -f "$REPO_DIR/bot/modules/$f" ]; then
                    cp "$REPO_DIR/bot/modules/$f" "/usr/local/bin/bot_modules/$f"
                    echo "   ✓ $f"
                fi
            done
            # assets (blank.dark для dark_gen)
            mkdir -p /usr/local/bin/bot_modules/assets
            if [ -f "$REPO_DIR/bot/modules/assets/blank.dark" ]; then
                cp "$REPO_DIR/bot/modules/assets/blank.dark" /usr/local/bin/bot_modules/assets/
                echo "   ✓ assets/blank.dark"
            fi
            echo "→ Проверка синтаксиса..."
            if ! python3 -m py_compile /usr/local/bin/vpn-tg-bot.py; then
                echo -e "\033[0;31m❌ Синтаксическая ошибка!\033[0m"
                exit 1
            fi
            for f in admin.py autopost.py cabinet.py db.py; do
                if [ -f "/usr/local/bin/bot_modules/$f" ]; then
                    python3 -m py_compile "/usr/local/bin/bot_modules/$f" || exit 1
                fi
            done
            echo "   ✓ OK"
            bash "$REPO_DIR/modules/setup_ssh_banner.sh" 2>/dev/null || true
            echo "→ Перезапуск vpn-tg-bot.service..."
            systemctl restart vpn-tg-bot 2>/dev/null || true
            sleep 2
            if systemctl is-active --quiet vpn-tg-bot; then
                echo -e "\033[0;32m✅ Бот обновлён и запущен\033[0m"
            else
                echo -e "\033[0;31m⚠️  Сервис не запустился. Смотри: tail -30 /var/log/vpn-tg-bot.log\033[0m"
                exit 1
            fi
            echo ""
            chmod 600 /etc/UDPCustom/*.conf /etc/UDPCustom/*.db /etc/UDPCustom/*.txt 2>/dev/null || true
            echo -e "\033[0;32m✅  Права на конфиги: 600\033[0m"
            exit 0
            ;;
        3)
            echo -e "\n📝  Обновление универсальных текстов..."
            REPO_DIR="/root/vpn-panel-sync"
            if [ ! -d "$REPO_DIR" ]; then
                echo -e "\033[0;31m❌  Репо не найдено: $REPO_DIR\033[0m"
                exit 1
            fi
            cd "$REPO_DIR" || exit 1
            echo "→ git pull..."
            git pull origin main 2>&1 | tail -3 || true
            echo ""
            echo -e "\033[1;33m⚠️   Будут ОБНОВЛЕНЫ следующие файлы в /etc/UDPCustom/:\033[0m"
            echo "   welcome.txt, start.txt, test_ready.txt, test_issued.txt"
            echo "   help.txt, help_instruction.txt, help_faq.txt"
            echo "   vip_buy.txt, post.txt, faq_keywords.txt"
            echo ""
            echo -e "\033[0;33mℹ️   НЕ будут затронуты:\033[0m"
            echo "   bot.conf, support_bot.conf, channels.txt, support.txt,"
            echo "   ssh_banner.txt, rate.txt, vpn.db, support.db"
            echo ""
            read -p "Продолжить? [y/N]: " confirm
            if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
                echo "Отменено."
                exit 0
            fi
            BK_TS=$(date +%F_%H%M)
            TEXT_FILES="welcome.txt start.txt test_ready.txt test_issued.txt help.txt help_instruction.txt help_faq.txt help_darktunnel.txt help_httpcustom.txt help_whitedns.txt help_video.txt ad.txt vip_buy.txt post.txt faq_keywords.txt ref_post.txt"
            OK=0
            SKIP=0
            for f in $TEXT_FILES; do
                SRC="$REPO_DIR/configs/$f"
                DST="/etc/UDPCustom/$f"
                if [ ! -f "$SRC" ]; then
                    echo "   ⏭  $f (нет в репо)"
                    SKIP=$((SKIP+1))
                    continue
                fi
                if [ -f "$DST" ]; then
                    cp "$DST" "${DST}.bak_${BK_TS}"
                fi
                cp "$SRC" "$DST"
                echo "   ✓ $f"
                OK=$((OK+1))
            done
            echo ""
            echo -e "\033[0;32m✅  Обновлено: $OK, пропущено: $SKIP\033[0m"
            echo "   Бэкапы: /etc/UDPCustom/*.bak_${BK_TS}"
            echo -e "\033[0;36mℹ️   Тексты читаются ботом на лету — перезапуск не нужен\033[0m"
            # Обновляем SSH-баннер (с подстановкой локации/devices/support/channel)
            bash "$REPO_DIR/modules/setup_ssh_banner.sh" 2>/dev/null || true

            exit 0
            ;;
        4)
            echo -e "\n⚠️ Полная переустановка..."
            rm -rf "$PANEL_DIR"
            rm -f /usr/local/bin/vpn
            ;;
        *) echo -e "\n❌  Операция отменена."; exit 0 ;;
    esac
fi

mkdir -p "$PANEL_DIR/modules" /etc/UDPCustom/limits /etc/UDPCustom/traffic /etc/UDPCustom/traffic_limits
touch /etc/UDPCustom/users.db

# WhiteDNS — служебные файлы
touch /etc/UDPCustom/whitedns_servers.txt
touch /etc/UDPCustom/whitedns_resolvers_de.txt
touch /etc/UDPCustom/whitedns_resolvers_fi.txt
touch /etc/UDPCustom/whitedns_resolvers_se.txt
touch /etc/UDPCustom/whitedns_settings_3g.txt
touch /etc/UDPCustom/whitedns_settings_wifi.txt
touch /etc/UDPCustom/whitedns_settings_adsl.txt
touch /etc/UDPCustom/whitedns_issued.log
chmod 600 /etc/UDPCustom/whitedns_*.txt /etc/UDPCustom/whitedns_*.log 2>/dev/null

# rate.txt — курс USDT → манат (для ручного пополнения)
if [ ! -f /etc/UDPCustom/rate.txt ]; then
    echo "20" > /etc/UDPCustom/rate.txt
fi

# Добавляем недостающие параметры в bot.conf (не перезаписывая существующие)
if [ -f /etc/UDPCustom/bot.conf ]; then
    grep -q "^SERVER_LOCATION=" /etc/UDPCustom/bot.conf || echo 'SERVER_LOCATION="🌍 Сервер"' >> /etc/UDPCustom/bot.conf
    grep -q "^VIP_TARIFFS=" /etc/UDPCustom/bot.conf || echo 'VIP_TARIFFS="15|3|100|1,30|5|300|2,90|14|900|3"' >> /etc/UDPCustom/bot.conf
    echo -e "\033[0;32m✅   bot.conf: недостающие параметры добавлены\033[0m"
fi

# Скачивание ВСЕХ модулей
# ──────────────────────────────────────────────────────────────
echo -e "\n📥 Скачивание актуальных файлов с GitHub..."

FILES_CORE=(
    "core.sh:$PANEL_DIR/core.sh"
    "vpn:/usr/local/bin/vpn"
)

FILES_MODULES=(
    "setup_configs.sh"
    "setup_ssh_banner.sh"
    "users.sh"
    "masterdns.sh"
    "udp.sh"
    "ws.sh"
    "security.sh"
    "traffic.sh"
    "devicelimit.sh"
    "maintenance.sh"
    "torrent_block.sh"
    "domain_proxy.sh"
    "tgbot.sh"
)

# Telegram-бот: всегда обновляем (с бэкапом)
if [ -f /usr/local/bin/vpn-tg-bot.py ]; then
    BK_TS=$(date +%F_%H%M)
    cp /usr/local/bin/vpn-tg-bot.py "/usr/local/bin/vpn-tg-bot.py.bak_${BK_TS}"
    # Оставляем только последние 5 бэкапов
    ls -t /usr/local/bin/vpn-tg-bot.py.bak_* 2>/dev/null | tail -n +6 | xargs -r rm -f
fi
curl -sf -o /usr/local/bin/vpn-tg-bot.py "$REPO_URL/bot/vpn-tg-bot.py"
chmod +x /usr/local/bin/vpn-tg-bot.py

# Скачиваем модули бота
mkdir -p /usr/local/bin/bot_modules
curl -sf -o /usr/local/bin/bot_modules/__init__.py "$REPO_URL/bot/modules/__init__.py"
curl -sf -o /usr/local/bin/bot_modules/admin.py "$REPO_URL/bot/modules/admin.py"
curl -sf -o /usr/local/bin/bot_modules/autopost.py "$REPO_URL/bot/modules/autopost.py"
curl -sf -o /usr/local/bin/bot_modules/cabinet.py "$REPO_URL/bot/modules/cabinet.py"
curl -sf -o /usr/local/bin/bot_modules/db.py "$REPO_URL/bot/modules/db.py"
curl -sf -o /usr/local/bin/bot_modules/dark_gen.py "$REPO_URL/bot/modules/dark_gen.py"
mkdir -p /usr/local/bin/bot_modules/assets
curl -sf -o /usr/local/bin/bot_modules/assets/blank.dark "$REPO_URL/bot/modules/assets/blank.dark"

for item in "${FILES_CORE[@]}"; do
    src="${item%%:*}"
    dst="${item##*:}"
    curl -sf -o "$dst" "$REPO_URL/$src"
    if [ $? -ne 0 ]; then
        echo -e "\033[0;31m⚠️  Не удалось скачать: $src\033[0m"
    fi
done

for mod in "${FILES_MODULES[@]}"; do
    curl -sf -o "$PANEL_DIR/modules/$mod" "$REPO_URL/modules/$mod"
    if [ $? -ne 0 ]; then
        echo -e "\033[0;33m⚠️  Модуль не найден: $mod\033[0m"
    fi
done

# Конфиги бота (welcome, start, channels, post)
bash "$PANEL_DIR/modules/setup_configs.sh" "$REPO_URL"

chmod +x /usr/local/bin/vpn

echo -e "\033[0;32m✅ Все модули скачаны.\033[0m"

# ──────────────────────────────────────────────────────────────
# СХЕМА A: pam_limits (maxlogins для прямого SSH)
# ──────────────────────────────────────────────────────────────
if ! grep -q "pam_limits.so" /etc/pam.d/sshd 2>/dev/null; then
    echo "session required pam_limits.so" >> /etc/pam.d/sshd
    echo -e "\033[0;32m✅ pam_limits подключён к sshd.\033[0m"
else
    echo -e "\033[0;32m✅ pam_limits уже подключён.\033[0m"
fi

if [ -s /etc/UDPCustom/users.db ]; then
    while read -r u; do
        [ -z "$u" ] && continue
        id "$u" &>/dev/null || continue
        limit=3
        [ -f "/etc/UDPCustom/limits/$u" ] && limit=$(cat "/etc/UDPCustom/limits/$u")
        [[ "$limit" =~ ^[0-9]+$ ]] || limit=3
        sed -i "/^${u}[[:space:]]\+hard[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
        sed -i "/^${u}[[:space:]]\+soft[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
        echo "${u} hard maxlogins ${limit}" >> /etc/security/limits.conf
    done < /etc/UDPCustom/users.db
    echo -e "\033[0;32m✅ maxlogins синхронизирован.\033[0m"
fi

# ──────────────────────────────────────────────────────────────
# СХЕМА B: pam_exec в ACCOUNT-фазе
# ──────────────────────────────────────────────────────────────
echo -e "\n🔒 Настройка pam_exec..."

sed -i '/show-welcome/d' /etc/pam.d/sshd 2>/dev/null
sed -i '/check-device-limit-pam/d' /etc/pam.d/sshd 2>/dev/null

cat << 'PAM_EOF' > /usr/local/bin/check-device-limit-pam
#!/bin/bash
USER="$PAM_USER"
LIMITS_DIR="/etc/UDPCustom/limits"
DB_USERS="/etc/UDPCustom/users.db"

[ "$USER" == "root" ] && exit 0
[ -z "$USER" ] && exit 0
grep -q "^${USER}$" "$DB_USERS" 2>/dev/null || exit 0

LIMIT=3
[ -f "$LIMITS_DIR/$USER" ] && LIMIT=$(cat "$LIMITS_DIR/$USER")
[[ "$LIMIT" =~ ^[0-9]+$ ]] || LIMIT=3
[ "$LIMIT" -le 0 ] && exit 0

WS_P=""
[ -f /usr/local/bin/ws-proxy.py ] && \
    WS_P=$(awk -F'=' '/listen_port/ {print $2}' /usr/local/bin/ws-proxy.py | tr -dc '0-9')

FILTER="( sport = :22 or sport = :36712 or sport = :7300"
[[ "$WS_P" =~ ^[0-9]+$ ]] && FILTER="$FILTER or sport = :$WS_P"
FILTER="$FILTER )"

COUNT=0
while IFS= read -r line; do
    [ -z "$line" ] && continue
    pids=$(echo "$line" | grep -oP 'pid=\K[0-9]+' 2>/dev/null)
    [ -z "$pids" ] && continue
    for p in $pids; do
        owner=$(ps -o user= -p "$p" 2>/dev/null | tr -d ' ')
        if [ -n "$owner" ] && [ "$owner" != "root" ]; then
            [ "$owner" == "$USER" ] && COUNT=$((COUNT + 1))
            break
        fi
    done
done <<< "$(ss -H -tnp state established "$FILTER" 2>/dev/null)"

if [ "$COUNT" -ge "$LIMIT" ]; then
    echo "❌ ПРЕВЫШЕН ЛИМИТ УСТРОЙСТВ ($COUNT/$LIMIT). Отключите другое устройство."
    exit 1
fi
exit 0
PAM_EOF

chmod +x /usr/local/bin/check-device-limit-pam

# ─── PAM: точная проверка срока (timestamp) ───
mkdir -p /etc/UDPCustom/expire_ts
cat << 'EXP_EOF' > /usr/local/bin/check-expiration-pam
#!/bin/bash
USER="$PAM_USER"
TS_DIR="/etc/UDPCustom/expire_ts"
DB_USERS="/etc/UDPCustom/users.db"
[ "$USER" == "root" ] && exit 0
[ -z "$USER" ] && exit 0
grep -q "^${USER}$" "$DB_USERS" 2>/dev/null || exit 0
[ ! -f "$TS_DIR/$USER" ] && exit 0
EXP_TS=$(cat "$TS_DIR/$USER" 2>/dev/null)
[[ "$EXP_TS" =~ ^[0-9]+$ ]] || exit 0
NOW=$(date +%s)
if [ "$NOW" -gt "$EXP_TS" ]; then
    echo "❌ СРОК ДЕЙСТВИЯ ИСТЁК. Обратись в поддержку: @ArsenGuro"
    exit 1
fi
exit 0
EXP_EOF
chmod +x /usr/local/bin/check-expiration-pam

if ! PAM_USER=root /usr/local/bin/check-device-limit-pam >/dev/null 2>&1; then
    echo -e "\033[0;31m⚠️  Скрипт лимита падает — PAM НЕ трогаем.\033[0m"
else
    if grep -q "pam_nologin.so" /etc/pam.d/sshd; then
        sed -i '/pam_nologin.so/a account    required     pam_exec.so stdout /usr/local/bin/check-device-limit-pam' /etc/pam.d/sshd
        sed -i '/check-device-limit-pam/a account    required     pam_exec.so stdout /usr/local/bin/check-expiration-pam' /etc/pam.d/sshd
        echo -e "\033[0;32m✅ pam_exec добавлен.\033[0m"
    fi
fi

# ──────────────────────────────────────────────────────────────
# SSH ТАЙМАУТЫ (быстрое закрытие мёртвых сессий)
# ──────────────────────────────────────────────────────────────
if ! grep -qE '^[[:space:]]*ClientAliveInterval' /etc/ssh/sshd_config; then
    echo "ClientAliveInterval 5" >> /etc/ssh/sshd_config
fi
sed -i 's|^[[:space:]]*#\?[[:space:]]*ClientAliveInterval.*|ClientAliveInterval 5|' /etc/ssh/sshd_config
sed -i 's|^[[:space:]]*#\?[[:space:]]*ClientAliveCountMax.*|ClientAliveCountMax 2|' /etc/ssh/sshd_config
sed -i 's|^[[:space:]]*#\?[[:space:]]*TCPKeepAlive.*|TCPKeepAlive yes|' /etc/ssh/sshd_config
echo -e "\033[0;32m✅  SSH-таймауты настроены.\033[0m"
systemctl reload ssh 2>/dev/null || true
# ──────────────────────────────────────────────────────────────
# SSH-БАННЕР
# ──────────────────────────────────────────────────────────────
bash "$PANEL_DIR/modules/setup_ssh_banner.sh"

# ──────────────────────────────────────────────────────────────
# СХЕМА C: cron-страховка + трафик
# ──────────────────────────────────────────────────────────────
echo -e "\n🛡️ Настройка cron-задач..."

cat << 'CHK_EOF' > /usr/local/bin/vpn-limit-check.sh
#!/bin/bash
DB_USERS="/etc/UDPCustom/users.db"
LIMITS_DIR="/etc/UDPCustom/limits"
LOG_FILE="/var/log/vpn-limit-check.log"

get_ws_port() {
    if [ -f /usr/local/bin/ws-proxy.py ]; then
        awk -F'=' '/listen_port/ {print $2}' /usr/local/bin/ws-proxy.py | tr -dc '0-9'
    fi
}
ws_p=$(get_ws_port)
filter="( sport = :22 or sport = :36712 or sport = :7300"
[[ "$ws_p" =~ ^[0-9]+$ ]] && filter="$filter or sport = :$ws_p"
filter="$filter )"
data=$(ss -H -tnp state established "$filter" 2>/dev/null)
declare -A CONN_USER CONN_PIDS CONN_TIME
idx=0
while IFS= read -r line; do
    [ -z "$line" ] && continue
    head="${line%%users:(*}"
    peer=$(echo "$head" | awk '{print $NF}')
    [[ "$peer" == *:* ]] || continue
    pids=$(echo "$line" | grep -oP 'pid=\K[0-9]+')
    [ -z "$pids" ] && continue
    u=""
    for p in $pids; do
        owner=$(ps -o user= -p "$p" 2>/dev/null | tr -d ' ')
        if [ -n "$owner" ] && [ "$owner" != "root" ]; then u="$owner"; break; fi
    done
    [ -z "$u" ] && continue
    reftime=0
    for p in $pids; do
        t=$(stat -c %Y "/proc/$p" 2>/dev/null)
        [ -n "$t" ] && { reftime=$t; break; }
    done
    CONN_USER[$idx]="$u"; CONN_PIDS[$idx]="$pids"; CONN_TIME[$idx]="$reftime"
    ((idx++))
done <<< "$data"
declare -A USER_INDICES
for ((i=0; i<idx; i++)); do
    u="${CONN_USER[$i]}"
    USER_INDICES[$u]="${USER_INDICES[$u]} $i"
done
for u in "${!USER_INDICES[@]}"; do
    limit=3
    [ -f "$LIMITS_DIR/$u" ] && limit=$(cat "$LIMITS_DIR/$u")
    [[ "$limit" =~ ^[0-9]+$ ]] || limit=3
    [ "$limit" -le 0 ] && continue
    idxs=(${USER_INDICES[$u]}); count=${#idxs[@]}
    [ "$count" -le "$limit" ] && continue
    sorted_idxs=($(for i in "${idxs[@]}"; do echo "${CONN_TIME[$i]} $i"; done | sort -n | awk '{print $2}'))
    to_kill=$(( count - limit ))
    for ((k=count-to_kill; k<count; k++)); do
        conn_i=${sorted_idxs[$k]}
        for p in ${CONN_PIDS[$conn_i]}; do kill -9 "$p" 2>/dev/null; done
        echo "$(date '+%Y-%m-%d %H:%M:%S') Отключён: user=$u count=$count limit=$limit" >> "$LOG_FILE"
    done
done
CHK_EOF
chmod +x /usr/local/bin/vpn-limit-check.sh
echo "* * * * * root /usr/local/bin/vpn-limit-check.sh" > /etc/cron.d/vpn-device-limit
chmod 644 /etc/cron.d/vpn-device-limit

# Трафик — iptables + cron
iptables -N VPN_TRAFFIC 2>/dev/null
iptables -C OUTPUT -j VPN_TRAFFIC 2>/dev/null || iptables -I OUTPUT -j VPN_TRAFFIC

if [ -s /etc/UDPCustom/users.db ]; then
    while read -r u; do
        [ -z "$u" ] && continue
        id "$u" &>/dev/null || continue
        uid=$(id -u "$u" 2>/dev/null)
        [ -z "$uid" ] && continue
        iptables -C VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null || \
        iptables -A VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN
    done < /etc/UDPCustom/users.db
fi

cat << 'CHK_EOF' > /usr/local/bin/vpn-traffic-check.sh
#!/bin/bash
TRAFFIC_DIR="/etc/UDPCustom/traffic"
TRAFFIC_LIMITS_DIR="/etc/UDPCustom/traffic_limits"
TRAFFIC_CHAIN="VPN_TRAFFIC"
DB_USERS="/etc/UDPCustom/users.db"
mkdir -p "$TRAFFIC_DIR"
iptables -L "$TRAFFIC_CHAIN" -n &>/dev/null || exit 0
while read -r u; do
    [ -z "$u" ] && continue
    uid=$(id -u "$u" 2>/dev/null) || continue
    cur=$(iptables -L "$TRAFFIC_CHAIN" -v -x -n 2>/dev/null | awk -v pat="UID match $uid\$" '$0 ~ pat {print $2}' | head -1)
    [ -z "$cur" ] && cur=0
    total_file="$TRAFFIC_DIR/$u"
    [ -f "$total_file" ] || echo 0 > "$total_file"
    prev_total=$(cat "$total_file")
    new_total=$((prev_total + cur))
    echo "$new_total" > "$total_file"
    iptables -D "$TRAFFIC_CHAIN" -m owner --uid-owner "$uid" -j RETURN 2>/dev/null
    iptables -A "$TRAFFIC_CHAIN" -m owner --uid-owner "$uid" -j RETURN
    limit_file="$TRAFFIC_LIMITS_DIR/$u"
    if [ -f "$limit_file" ]; then
        limit_bytes=$(cat "$limit_file")
        if [[ "$limit_bytes" =~ ^[0-9]+$ ]] && [ "$limit_bytes" -gt 0 ] && [ "$new_total" -ge "$limit_bytes" ]; then
            usermod -L "$u" 2>/dev/null
        fi
    fi
done < "$DB_USERS"
CHK_EOF
chmod +x /usr/local/bin/vpn-traffic-check.sh
echo "*/5 * * * * root /usr/local/bin/vpn-traffic-check.sh" > /etc/cron.d/vpn-traffic-check
chmod 644 /etc/cron.d/vpn-traffic-check

# ── АВТООЧИСТКА ИСТЁКШИХ ──
cat << 'CLEANUP_EOF' > /usr/local/bin/vpn-auto-cleanup.sh
#!/bin/bash
DB_USERS="/etc/UDPCustom/users.db"
LIMITS_DIR="/etc/UDPCustom/limits"
TRAFFIC_LIMITS_DIR="/etc/UDPCustom/traffic_limits"
TRAFFIC_DIR="/etc/UDPCustom/traffic"
LOG_FILE="/var/log/vpn-auto-cleanup.log"
[ ! -s "$DB_USERS" ] && exit 0
TODAY=$(date +%s)
TMP_DB=$(mktemp)
: > "$TMP_DB"
while read -r u; do
    [ -z "$u" ] && continue
    id "$u" &>/dev/null || continue
    exp_raw=$(chage -l "$u" 2>/dev/null | grep "Account expires" | cut -d: -f2 | sed 's/^ *//')
    if [ "$exp_raw" == "never" ] || [ -z "$exp_raw" ]; then
        echo "$u" >> "$TMP_DB"
        continue
    fi
    exp_epoch=$(date -d "$exp_raw" +%s 2>/dev/null)
    [ -z "$exp_epoch" ] && { echo "$u" >> "$TMP_DB"; continue; }
    if [ "$exp_epoch" -ge "$TODAY" ]; then
        echo "$u" >> "$TMP_DB"
        continue
    fi
    uid=$(id -u "$u" 2>/dev/null)
    [ -n "$uid" ] && while iptables -D VPN_TRAFFIC -m owner --uid-owner "$uid" -j RETURN 2>/dev/null; do :; done
    userdel -f "$u" 2>/dev/null
    rm -f "$LIMITS_DIR/$u" "$TRAFFIC_LIMITS_DIR/$u" "$TRAFFIC_DIR/$u" 2>/dev/null
    sed -i "/^${u}[[:space:]]\+hard[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
    sed -i "/^${u}[[:space:]]\+soft[[:space:]]\+maxlogins/d" /etc/security/limits.conf 2>/dev/null
    echo "$(date '+%Y-%m-%d %H:%M:%S') Удалён истёкший: $u (истёк $exp_raw)" >> "$LOG_FILE"
done < "$DB_USERS"
sort -u "$TMP_DB" | grep -v '^$' > "$DB_USERS" 2>/dev/null
rm -f "$TMP_DB"
CLEANUP_EOF
chmod +x /usr/local/bin/vpn-auto-cleanup.sh
echo "0 4 * * * root /usr/local/bin/vpn-auto-cleanup.sh" > /etc/cron.d/vpn-auto-cleanup
chmod 644 /etc/cron.d/vpn-auto-cleanup


# ──────────────────────────────────────────────────────────────
# Автобэкап БД
# ──────────────────────────────────────────────────────────────
echo -e "\n💾 Установка автобэкапа БД..."
curl -sf -o /usr/local/bin/vpn-backup.sh "$REPO_URL/scripts/vpn-backup.sh" && chmod +x /usr/local/bin/vpn-backup.sh
if [ -f /usr/local/bin/vpn-backup.sh ]; then
    echo "0 4 * * * root /usr/local/bin/vpn-backup.sh >> /var/log/vpn-backup.log 2>&1" > /etc/cron.d/vpn-backup
    chmod 644 /etc/cron.d/vpn-backup
    echo -e "\033[0;32m✅   Автобэкап: ежедневно в 4:00 → /root/backups/\033[0m"
fi
systemctl restart cron 2>/dev/null || systemctl restart crond 2>/dev/null

# ──────────────────────────────────────────────────────────────
# Синхронизация трафика и уведомления (новые скрипты)
# ──────────────────────────────────────────────────────────────
echo -e "\n📊 Установка скриптов трафика и уведомлений..."

# vpn-traffic-sync.py — синхронизация файлов трафика в БД
curl -sf -o /usr/local/bin/vpn-traffic-sync.py "$REPO_URL/bot/vpn-traffic-sync.py"
if [ $? -eq 0 ]; then
    chmod +x /usr/local/bin/vpn-traffic-sync.py
    python3 -m py_compile /usr/local/bin/vpn-traffic-sync.py 2>/dev/null
    echo "*/5 * * * * root sleep 30 && /usr/local/bin/vpn-traffic-sync.py" > /etc/cron.d/vpn-traffic-sync
    chmod 644 /etc/cron.d/vpn-traffic-sync
    echo -e "\033[0;32m✅  vpn-traffic-sync установлен\033[0m"
else
    echo -e "\033[0;33m⚠️  Не удалось скачать vpn-traffic-sync.py\033[0m"
fi

# vpn-notify-expiring.py — уведомления VIP за 24ч
curl -sf -o /usr/local/bin/vpn-notify-expiring.py "$REPO_URL/bot/vpn-notify-expiring.py"
if [ $? -eq 0 ]; then
    chmod +x /usr/local/bin/vpn-notify-expiring.py
    python3 -m py_compile /usr/local/bin/vpn-notify-expiring.py 2>/dev/null
    echo "0 * * * * root /usr/local/bin/vpn-notify-expiring.py" > /etc/cron.d/vpn-notify-expiring
    chmod 644 /etc/cron.d/vpn-notify-expiring
    echo -e "\033[0;32m✅  vpn-notify-expiring установлен\033[0m"
else
    echo -e "\033[0;33m⚠️  Не удалось скачать vpn-notify-expiring.py\033[0m"
fi

systemctl restart cron 2>/dev/null || systemctl restart crond 2>/dev/null

# ──────────────────────────────────────────────────────────────
# Конфиг бота и сервис systemd
# ──────────────────────────────────────────────────────────────

# bot.conf — создаём только если нет (не перезаписываем!)
if [ ! -f /etc/UDPCustom/bot.conf ]; then
    echo "→ Создание /etc/UDPCustom/bot.conf из шаблона..."
    if curl -sf -o /etc/UDPCustom/bot.conf "$REPO_URL/configs/bot.conf.template"; then
        echo -e "\033[0;33m⚠️  ЗАПОЛНИ BOT_TOKEN и ADMIN_ID в /etc/UDPCustom/bot.conf!\033[0m"
    else
        # Fallback — минимальный конфиг
        cat > /etc/UDPCustom/bot.conf << BOTCONF_EOF
BOT_TOKEN=""
ADMIN_ID=""
CHANNEL_ID=""
REQUIRE_SUBSCRIPTION="0"
COOLDOWN_HOURS="8"
TEST_HOURS="8"
VERIFIED_MINUTES="60"
TEST_DEVICES="1"
TEST_TRAFFIC_GB="50"
CONFIG_NAME="VPN"
SERVER_LOCATION="🌍 Сервер"
CONNECTED_MSG="Подключено!"
VIP_TARIFFS="15|3|100|1,30|5|300|2,90|14|900|3"
BOTCONF_EOF
        echo -e "\033[0;33m⚠️  Создан минимальный bot.conf. Заполни BOT_TOKEN!\033[0m"
    fi
else
    echo -e "\033[0;32m✅  bot.conf уже существует (не перезаписываем)\033[0m"
fi

# Сервис systemd — создаём только если нет
if [ ! -f /etc/systemd/system/vpn-tg-bot.service ]; then
    echo "→ Создание systemd-сервиса vpn-tg-bot..."
    curl -sf -o /etc/systemd/system/vpn-tg-bot.service "$REPO_URL/configs/vpn-tg-bot.service"
    if [ $? -ne 0 ]; then
        # Fallback
        cat > /etc/systemd/system/vpn-tg-bot.service << SERVICE_EOF
[Unit]
Description=VPN Panel Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /usr/local/bin/vpn-tg-bot.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/vpn-tg-bot.log
StandardError=append:/var/log/vpn-tg-bot.log

[Install]
WantedBy=multi-user.target
SERVICE_EOF
    fi
    systemctl daemon-reload
    echo -e "\033[0;32m✅  Сервис создан\033[0m"
fi

# Активируем автозапуск (если есть BOT_TOKEN)
if [ -f /etc/UDPCustom/bot.conf ] && grep -q "^BOT_TOKEN=\"[^\"]" /etc/UDPCustom/bot.conf 2>/dev/null; then
    systemctl enable vpn-tg-bot 2>/dev/null
    echo -e "\033[0;32m✅  Автозапуск бота включён\033[0m"
else
    echo -e "\033[0;33m⚠️  BOT_TOKEN не задан — бот не запущен\033[0m"
    echo -e "\033[0;33m   Заполни /etc/UDPCustom/bot.conf и запусти:\033[0m"
    echo -e "\033[0;33m   systemctl enable --now vpn-tg-bot\033[0m"
fi

# ──────────────────────────────────────────────────────────────
# Support Bot (отдельный бот поддержки)
# ──────────────────────────────────────────────────────────────
echo -e "\n🤖 Установка бота поддержки..."

# Код бота поддержки
curl -sf -o /usr/local/bin/support-bot.py "$REPO_URL/support/support-bot.py" && chmod +x /usr/local/bin/support-bot.py
curl -sf -o /usr/local/bin/bot_modules/support_db.py "$REPO_URL/bot/modules/support_db.py"

# Конфиг бота поддержки (если нет)
if [ ! -f /etc/UDPCustom/support_bot.conf ]; then
    if [ -f "$PANEL_DIR/configs/support_bot.conf.template" ]; then
        cp "$PANEL_DIR/configs/support_bot.conf.template" /etc/UDPCustom/support_bot.conf
    else
        curl -sf -o /etc/UDPCustom/support_bot.conf "$REPO_URL/configs/support_bot.conf.template"
    fi
    echo -e "\033[0;33m⚠️  ЗАПОЛНИ BOT_TOKEN в /etc/UDPCustom/support_bot.conf!\033[0m"
fi

# Ключевые слова для FAQ
if [ ! -f /etc/UDPCustom/faq_keywords.txt ]; then
    curl -sf -o /etc/UDPCustom/faq_keywords.txt "$REPO_URL/configs/faq_keywords.txt"
fi

# Systemd-сервис
if [ ! -f /etc/systemd/system/support-bot.service ]; then
    curl -sf -o /etc/systemd/system/support-bot.service "$REPO_URL/configs/support-bot.service"
    if [ $? -ne 0 ]; then
        cat > /etc/systemd/system/support-bot.service << 'SUPSERVICE_EOF'
[Unit]
Description=VPN Support Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /usr/local/bin/support-bot.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/vpn-support-bot.log
StandardError=append:/var/log/vpn-support-bot.log

[Install]
WantedBy=multi-user.target
SUPSERVICE_EOF
    fi
    systemctl daemon-reload
fi

# Инициализация БД
python3 -c "import sys; sys.path.insert(0, '/usr/local/bin'); from bot_modules import support_db; support_db.init_schema()" 2>/dev/null

# Автозапуск (если токен задан)
if [ -f /etc/UDPCustom/support_bot.conf ] && grep -q "^BOT_TOKEN=\"[^\"]" /etc/UDPCustom/support_bot.conf 2>/dev/null; then
    systemctl enable support-bot 2>/dev/null
    systemctl restart support-bot 2>/dev/null
    echo -e "\033[0;32m✅  Support Bot запущен\033[0m"
else
    echo -e "\033[0;33m⚠️  Support Bot: BOT_TOKEN не задан\033[0m"
    echo -e "\033[0;33m   Заполни /etc/UDPCustom/support_bot.conf\033[0m"
    echo -e "\033[0;33m   и запусти: systemctl enable --now support-bot\033[0m"
fi


# ──────────────────────────────────────────────────────────────
# ПРАВА НА КОНФИГИ (защита от чтения не-root пользователями)
# ──────────────────────────────────────────────────────────────
chmod 600 /etc/UDPCustom/*.conf /etc/UDPCustom/*.db /etc/UDPCustom/*.txt 2>/dev/null
echo -e "\033[0;32m✅   Права на конфиги: 600 (только root)\033[0m"
# ──────────────────────────────────────────────────────────────
# ФИНАЛЬНАЯ ПРОВЕРКА PAM  (ИСПРАВЛЕНО)
# ──────────────────────────────────────────────────────────────
echo -e "\n🔍 Финальная проверка..."
PAM_OK=1
grep -q "@include common-auth" /etc/pam.d/sshd || { echo -e "\033[0;31m⚠️  common-auth нет!\033[0m"; PAM_OK=0; }
grep -q "@include common-account" /etc/pam.d/sshd || { echo -e "\033[0;31m⚠️  common-account нет!\033[0m"; PAM_OK=0; }

for pat in "check-device-limit-pam" "show-welcome"; do
    cnt=$(grep -c "$pat" /etc/pam.d/sshd 2>/dev/null)
    [ -z "$cnt" ] && cnt=0
    if [ "$cnt" -gt 1 ] 2>/dev/null; then
        first=1; : > /tmp/sshd.clean
        while IFS= read -r line; do
            if echo "$line" | grep -q "$pat"; then
                [ "$first" -eq 1 ] && { first=0; echo "$line" >> /tmp/sshd.clean; }
            else
                echo "$line" >> /tmp/sshd.clean
            fi
        done < /etc/pam.d/sshd
        mv /tmp/sshd.clean /etc/pam.d/sshd
    fi
done

if [ "$PAM_OK" -eq 1 ]; then
    echo -e "\033[0;32m✅ PAM в порядке. Перезапускаем sshd...\033[0m"
    sleep 2
    systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null
    systemctl restart vpn-tg-bot 2>/dev/null
    [ -f /etc/default/dropbear ] && systemctl restart dropbear 2>/dev/null
else
    echo -e "\033[0;31m⚠️  PAM повреждён! Откат...\033[0m"
    sed -i '/check-device-limit-pam/d' /etc/pam.d/sshd
fi

echo -e "\n\033[0;32m🟢 Операция успешно завершена, Хозяин!\033[0m"
echo -e "Запуск панели: \033[1;33mvpn\033[0m"
