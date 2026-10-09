<div align="center">

# ⚡ VPN PANEL + Telegram Bot

**Панель управления SSH-туннелями + Telegram-бот для продажи ключей**

![Version](https://img.shields.io/badge/version-3.0.0-blue?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Ubuntu%20%7C%20Debian-orange?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.10+-yellow?style=for-the-badge)

[📢 Канал](https://t.me/ArsenVipKeys) • [💬 Поддержка](https://t.me/ArsenGuro)

</div>

---

## ✨ Возможности

**Панель (`vpn`)** — консольное управление сервером:
- 👥 Юзеры, ключи, лимиты, онлайн
- 🌐 SSH + WS-прокси для DarkTunnel / HTTP Injector / KPN
- 📊 Трафик (iptables) + авто-блокировка при превышении
- 👥 Лимит устройств (реальный сброс лишних сессий)
- 🛡️ UFW, Fail2ban, TCP BBR, баннер, автобэкап
- 🌍 **Мульти-нода** — мастер + неограниченное число нод

**Telegram-бот** — личный кабинет клиента + админка:
- 🔑 Тест/VIP ключи, баланс, история, промокоды, рефералы
- 💎 Покупка VIP, пополнение (Stars / крипта / TMCELL)
- 📲 Автогенерация `.dark` файлов со **всех онлайн-нод**
- 📊 Статистика, рассылка, автопостинг, мульти-админ

**Бот поддержки** — FAQ-автоответы + тикеты.

---

## 🆕 Что нового в v3.0.0

**🌍 Мульти-нода** — мастер + неограниченное число нод:
- Управление нодами из панели мастера (добавить / проверить / reboot / оптимизировать)
- Синхронизация юзеров, паролей, HWID, лимитов устройств
- Выдача `.dark` файлов со **всех онлайн-локаций** — клиент сам выбирает
- Единый сбор трафика со всех нод + общий лимит
- Блокировка при превышении лимита сразу на всех серверах

**⚡ Оптимизация одной кнопкой:**
- apt upgrade, IPv6 off, UFW + Fail2ban, TCP BBR, TCP Brutal (20 Mbps), буферы ядра, Swap 1 GB

**🔧 Новые скрипты:**
`install-node.sh`, `node-user.sh`, `nodes_client.py`, `vpn-traffic-check.py`, `vpn-nodes-check.py`, `vpn-limit-check.sh`, `vpn-optimize.sh`

---

## 🚀 Установка мастера

На чистом VPS (Ubuntu 20.04+ / Debian 11+):

`bash <(curl -Ls https://raw.githubusercontent.com/zotac85/vpn-panel/main/install.sh)`

Запуск панели:

`vpn`

---

## 🌍 Установка ноды

На чистом сервере (нода — SSH + WS, без панели и ботов):

`bash <(curl -Ls https://raw.githubusercontent.com/zotac85/vpn-panel/main/install-node.sh)`

Спросит: WS-порт (Enter = 2052), SSH-порт (Enter = 22).

**Подключение ноды к мастеру:**

```
vpn → 9) Управление нодами
  → 1) Добавить ноду
  → 4) Закинуть SSH-ключ на ноду
  → 2) Проверить все ноды
  → 6) Установить баннер
  → 7) Синхронизировать всех юзеров
```

Готово. Юзеры автоматически создаются на всех нодах, клиенты получают `.dark` файлы от каждой онлайн-локации.

**Автоматизация на мастере (cron):**
- Каждые 5 мин — проверка статуса нод
- Каждые 5 мин — сбор трафика со всех нод + блокировка по лимиту
- Каждую минуту — контроль лимита устройств (на каждой ноде)

---

## 🔧 Настройка ботов

Создай двух ботов через [@BotFather](https://t.me/BotFather) и заполни:

**`/etc/UDPCustom/bot.conf`:**
```ini
BOT_TOKEN="1234567890:ABC..."
ADMIN_ID="123456789"
SERVER_LOCATION="🇩🇪 Германия"
VIP_TARIFFS="10|2|100|1,30|5|300|1,90|13|900|1"
```

**`/etc/UDPCustom/support_bot.conf`:**
```ini
BOT_TOKEN="8663994758:AAFY..."
ADMIN_ID="1738878748"
MAIN_BOT="ArsenVipKeysBot"
SUPPORT_BOT="ArsenSupportBot"
```

Запуск:
`systemctl enable --now vpn-tg-bot support-bot`

---

## 📁 Структура проекта

```
vpn-panel/
├── install.sh                # Установщик мастера
├── install-node.sh           # Установщик ноды (SSH + WS)
├── vpn                       # Панель
├── core.sh
├── bot/
│   ├── vpn-tg-bot.py
│   ├── vpn-traffic-check.py  # Трафик + блокировка (мастер + ноды)
│   ├── vpn-nodes-check.py    # Статус нод
│   └── modules/              # db, cabinet, admin, nodes_client, ...
├── support/support-bot.py
├── scripts/                  # node-user.sh, vpn-limit-check.sh, ...
├── modules/                  # nodes.sh, users.sh, security.sh, ...
└── configs/                  # Шаблоны конфигов
```

**Рабочие пути на сервере:**
- `/usr/local/bin/` — скрипты
- `/usr/local/share/vpn-panel/` — панель + модули
- `/etc/UDPCustom/` — конфиги, БД, тексты, лимиты

---

## 🗄️ База данных

SQLite: `/etc/UDPCustom/vpn.db`

Таблицы: `users`, `test_keys`, `vip_keys`, `payments`, `promo_codes`, `referrals`, `broadcasts`, `nodes`.

Бэкап:
```bash
cp /etc/UDPCustom/vpn.db /root/backup_$(date +%F).db
```
Автобэкап — ночью в 4:00 + отправка в Telegram.

---

## 🔄 Обновление

Через панель: `vpn` → пункт **8) Обновить скрипт ВПН**.

Вручную:
```bash
cd /root/vpn-panel-sync && git pull origin main
```
Обновление **не трогает** `/etc/UDPCustom/*` — все юзеры, тексты и настройки сохраняются.

---

## 🐛 Troubleshooting

**Бот не отвечает:**
```bash
systemctl status vpn-tg-bot
tail -50 /var/log/vpn-tg-bot.log
```

**Ключ не подключается:**
1. Юзер есть: `grep <login> /etc/UDPCustom/users.db`
2. Пароль: `/etc/UDPCustom/passwords/<login>`
3. WS работает: `systemctl status ws-proxy`

**Нода оффлайн:**
```
vpn → 9 → 2) Проверить все ноды
ssh root@<IP> "systemctl is-active ws-proxy"
```

**Auth failed на ноде:**
- `ssh root@<IP> "node-user.sh list | grep <login>"`
- Массовый фикс: `vpn → 9 → 7) Синхронизировать всех юзеров`

---

## 📞 Поддержка

- 💬 [@ArsenGuro](https://t.me/ArsenGuro)
- 📢 [@ArsenVipKeys](https://t.me/ArsenVipKeys)
- 🐛 [Issues](https://github.com/zotac85/vpn-panel/issues)

<div align="center">

⭐ **Поставь звезду, если проект полезен!**

Made with ❤️ by [@ArsenGuro](https://t.me/ArsenGuro)

</div>
