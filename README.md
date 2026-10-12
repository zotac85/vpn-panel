<div align="center">

# ⚡ VPN PANEL + Telegram Bot

**Панель управления SSH-туннелями + Telegram-бот для продажи ключей**

![Version](https://img.shields.io/badge/version-3.1.0-blue?style=for-the-badge)
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

## 🆕 Что нового в v3.1.0

**🌐 Управление доменами:**
- Список всех доменов (мастер + ноды) в `/admin → ⚙️ SSH WS`
- Редактор домена (FSM как WhiteDNS) — тапнул кнопку, отправил новое значение
- Кнопка **📨 Уведомить клиентов** после смены — рассылка с превью и редактированием
- В панели: `vpn → 9 → 10) Изменить домен ноды`

**🔒 Прокси и Payload через бота:**
- Редактор в стиле WhiteDNS (ввод через сообщение, замена целиком)
- Список прокси + ✏️ Редактировать список
- Payload + ✏️ Редактировать

**⏰ Блокировка по сроку и трафику:**
- Красивые баннеры в DarkTunnel:
  - `❌ СРОК ДЕЙСТВИЯ КЛЮЧА ИСТЁК`
  - `⚠️ ПРЕВЫШЕН ЛИМИТ ТРАФИКА`
- Кликабельные ссылки на поддержку и канал (из `support.txt` / `channels.txt`)
- `vpn-nologin.sh` — кастомный shell для заблокированных
- `Match User` + `AllowTcpForwarding no` — реальный запрет SSH-туннеля
- Автоблокировка/разблокировка через cron каждую минуту

**🌐 WhiteDNS (MasterDnsVPN):**
- Единый модуль управления — мастер и все ноды
- Порт 53 (TCP+UDP) открывается автоматически
- Ключ клиента показывается после установки

**📡 UDP Custom / UDPGW разделены:**
- `vpn → 3) UDP Custom` — только UDP Custom
- `vpn → 2) WebSocket Proxy → 7) UDPGW` — управление UDPGW (порт 7300)
- Установка UDPGW на ноды: `vpn → 9 → 11) Установить UDPGW на ноду`
- Статус UDPGW в шапках главного меню и меню WS

**🧹 Автоочистка (cron каждый час):**
- Удаление истёкших и висячих юзеров (Linux + БД + ноды)
- Синхронизация удалений на все ноды

**🛡️ Самовосстановление `VPN_TRAFFIC`:**
- `vpn-traffic-check.py` создаёт цепочку iptables если её снесло `ufw reset`
- Автодобавление правил `--uid-owner` для всех юзеров

**🔧 Исправлено:**
- `auth failed` при пересоздании ключа (унификация reset с create)
- `PerSourcePenalties` банил WS-прокси → отключён на всех серверах
- Android кешировал `.dark` → timestamp в имени файла
- Ускорена синхронизация (пропуск offline-нод)
- `Include` в `sshd_config` — в конце (Match User переопределяет Banner)
- `cmd_list` в `node-user.sh` — теперь видит `test*` без подчёркивания

**🧹 Оптимизация:**
- Журнал journald ограничен 200 МБ (было 3.7 ГБ)
- Чистка временных файлов и бэкапов

**🌍 Мульти-нода (v3.0.0):**
- Мастер + неограниченное число нод
- Синхронизация юзеров, HWID, лимитов устройств
- Выдача .dark файлов со всех онлайн-локаций
- Единый сбор трафика + блокировка по лимиту

**⚡ Оптимизация одной кнопкой (v3.0.0):**
- apt upgrade, IPv6 off, UFW + Fail2ban, TCP BBR, TCP Brutal, буферы ядра, Swap 1 GB

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

## 🌐 WhiteDNS (MasterDnsVPN)

DNS-туннель для обхода блокировок через порт 53. Работает параллельно с SSH.

### Установка

Скрипт сам откроет порт 53 (TCP+UDP) и покажет ключ клиента.

### DNS в Cloudflare

Для каждой ноды нужно 2 записи:

| Тип | Имя | Значение |
|---|---|---|
| `A` | `ns1.домен` | IP ноды |
| `NS` | `домен` | `ns1.домен` |

Proxy Status — **DNS only** (серое облако).

### Управление

Всё через `vpn → 4`: перезапуск / стоп / редактирование / удаление.

--

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
├── scripts/
│   ├── node-user.sh          # CLI юзеров на ноде
│   ├── vpn-limit-check.sh    # Devicelimit
│   ├── vpn-nologin.sh        # Кастомный shell
│   ├── vpn-expiry-check.sh   # Блокировка по сроку
│   ├── vpn-auto-cleanup.sh   # Автоочистка
│   ├── install-udpgw-node.sh # Установка UDPGW
│   └── vpn-optimize.sh       # Оптимизация
├── modules/
│   ├── nodes.sh              # Управление нодами
│   ├── udp.sh                # UDP Custom + UDPGW
│   ├── ws.sh                 # WebSocket + UDPGW
│   ├── security.sh           # Безопасность + TCP Brutal
│   ├── masterdns.sh          # WhiteDNS
│   └── ...
└── configs/                  # Шаблоны конфигов
```

**Рабочие пути на сервере:**
- `/usr/local/bin/` — скрипты
- `/usr/local/share/vpn-panel/` — панель + модули
- `/etc/UDPCustom/` — конфиги, БД, тексты, лимиты
- `/etc/ssh/sshd_config.d/` — `blocked-users.conf`, `overlimit-users.conf` (автогенерация)

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
