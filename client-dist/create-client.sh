#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Скрипт создания персонального архива для клиента
# Использование: create-client.sh <имя_клиента> <токен>
# Пример: create-client.sh ivan github_pat_11ABC...
# ═══════════════════════════════════════════════════════════════

set -e

CLIENT_NAME="$1"
CLIENT_TOKEN="$2"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_PACK="$SCRIPT_DIR/pack"
WORK_DIR="/root/clients"
[ -d "$WORK_DIR" ] || mkdir -p "$WORK_DIR"

# ─── Проверки ───
if [ -z "$CLIENT_NAME" ] || [ -z "$CLIENT_TOKEN" ]; then
    echo ""
    echo "Использование: $0 <имя_клиента> <токен>"
    echo ""
    echo "Пример:"
    echo "  $0 ivan github_pat_11ABC..."
    echo ""
    exit 1
fi

if [ ! -d "$SRC_PACK" ]; then
    echo "❌ Не найдена папка-шаблон: $SRC_PACK"
    exit 1
fi

if ! [[ "$CLIENT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "❌ Имя клиента — только буквы, цифры, _ и -"
    exit 1
fi

TARGET_DIR="$WORK_DIR/client-$CLIENT_NAME"
ZIP_FILE="$WORK_DIR/client-$CLIENT_NAME.zip"
DATE=$(date +%F_%H%M)

# ─── Удаляем старую папку если есть ───
if [ -d "$TARGET_DIR" ]; then
    echo "⚠️  Папка $TARGET_DIR уже есть — перезаписываю"
    rm -rf "$TARGET_DIR"
fi

# ─── Копируем шаблон ───
echo "📁 Копирую шаблон → $TARGET_DIR"
cp -r "$SRC_PACK" "$TARGET_DIR"

# ─── Вставляем токен ───
TOKEN_FILE="$TARGET_DIR/03_ТОКЕН.txt"
if [ -f "$TOKEN_FILE" ]; then
    sed -i "s|ВСТАВЬ_ТОКЕН_ЗДЕСЬ|$CLIENT_TOKEN|" "$TOKEN_FILE"
    echo "🔑 Токен вставлен в 03_ТОКЕН.txt"
else
    echo "❌ Не найден файл 03_ТОКЕН.txt"
    exit 1
fi

# ─── Добавляем имя клиента в прочтение ───
README_FILE="$TARGET_DIR/00_ПРОЧТИ_МЕНЯ.txt"
if [ -f "$README_FILE" ]; then
    sed -i "1i \\
КЛИЕНТ: $CLIENT_NAME\\
Дата выдачи: $DATE\\
" "$README_FILE"
fi

# ─── Упаковываем в ZIP ───
cd "$WORK_DIR"
echo "📦 Упаковываю в архив..."
zip -qr "client-$CLIENT_NAME.zip" "client-$CLIENT_NAME/"

# ─── Проверяем результат ───
if [ ! -f "$ZIP_FILE" ]; then
    echo "❌ Не удалось создать архив"
    exit 1
fi

SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ АРХИВ ГОТОВ"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Клиент:  $CLIENT_NAME"
echo "  Архив:   $ZIP_FILE"
echo "  Размер:  $SIZE"
echo "  Дата:    $DATE"
echo ""
echo "  Файлы в архиве:"
ls -la "$TARGET_DIR/" | grep -v "^total" | grep -v "^d" | awk '{print "    " $NF}'
echo ""
echo "═══════════════════════════════════════════════════"
echo ""
echo "📥 Скачай из /root/clients/client-$CLIENT_NAME.zip"
echo ""
