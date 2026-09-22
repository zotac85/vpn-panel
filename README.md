

```markdown
<div align="center">

# ⚡ ULTIMATE VPN CONTROL PANEL

**Интерактивная консольная панель для администрирования Linux VPN-серверов**

![Version](https://img.shields.io/badge/version-2.0-blue?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Ubuntu%20%7C%20Debian-orange?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)
![Language](https://img.shields.io/badge/lang-Русский-red?style=for-the-badge)

[📢 Канал](https://t.me/ArsenVipKeys) • [💬 Поддержка](https://t.me/ArsenGuro) • [🚀 Установка](#-установка)

</div>

---

## ✨ Возможности

<div align="center">

| 🎨 Баннер | 👥 Пользователи | 🛡️ Безопасность |
|:---------:|:---------------:|:---------------:|
| HTML-баннер | Лимит устройств | UFW Firewall |
| ANSI-цвета | Лимит трафика | Fail2ban |
| 4 шаблона | Срок действия | TCP BBR |
| Управление из панели | Онлайн-мониторинг | Оптимизация ядра |

</div>

### 🔥 Ключевые фишки

- **🚦 Лимит устройств для SSH over WS** — реальная блокировка через PAM `pam_exec` (не kill-loop)
- **📶 Лимит трафика** — подсчёт через iptables `owner-match`, авто-блокировка
- **🎨 HTML-баннер** — красивый, работает в DarkTunnel / HTTP Injector / KPN
- **🧹 Автоочистка** — ежедневное удаление истёкших аккаунтов
- **💾 Бэкап / восстановление** — в одну кнопку
- **🕸️ WebSocket Proxy** — обход DPI-блокировок
- **🌐 MasterDnsVPN + UDP Custom** — поддержка нескольких протоколов

---

## 🚀 Установка

**Одной командой на чистом VPS (Ubuntu / Debian):**

```bash
bash <(curl -Ls https://raw.githubusercontent.com/zotac85/vpn-panel/main/install.sh)
```

После установки — запуск панели в любой момент:

```bash
vpn
```

---

🎯 Что внутри

📋 Главное меню

```
1) 👥 Управление пользователями
2) 🕸️  WebSocket Proxy (Кастомный)
3) ⚡ UDP Custom (Управление)
4) 🌐 MasterDnsVPN
5) 🛡️  Безопасность, IPv6 и Оптимизация
6) 🎨 Баннер при подключении
7) 🔄 Обновить скрипт ВПН
0) 🚪 Выход
```

👥 Управление пользователями

```
1) ➕ Добавить пользователя
   ├─ 🧪 Тестовый аккаунт (одной кнопкой)
   └─ 👑 VIP аккаунт (ручной ввод)
2) ✏️  Редактировать пользователя
3) 🔒 Блокировать / Разблокировать
4) 🗑️  Удалить пользователя
5) 📋 Список пользователей и онлайн
6) 📊 Общая статистика
7) 🚦 Контроль лимита устройств
8) 📶 Мониторинг трафика
9) 🧹 Обслуживание (бэкап, истёкшие)
```

---

📁 Структура проекта

```
vpn-panel/
├── install.sh              # Установщик / обновлятор
├── vpn                     # Главная точка входа
├── core.sh                 # Общие функции (header, session stats)
├── README.md
└── modules/
    ├── users.sh            # Пользователи, лимиты, add/edit/delete
    ├── banner.sh           # HTML-баннер (Banner в sshd_config)
    ├── devicelimit.sh      # Cron-страховка для лимита устройств
    ├── traffic.sh          # Мониторинг трафика (iptables)
    ├── maintenance.sh      # Бэкап, автоочистка, истёкшие
    ├── masterdns.sh        # MasterDnsVPN
    ├── udp.sh              # UDP Custom + UDPGW
    ├── ws.sh               # WebSocket Proxy
    └── security.sh         # UFW, Fail2ban, BBR, sysctl
```

---

🛠️ Технические детали

Лимит устройств для SSH over WS

Панель использует тройную защиту:

1. pam_exec в account-фазе — блокирует новый вход, если лимит превышен
2. maxlogins в limits.conf — для прямого SSH
3. Cron-страховка — kill лишних сессий раз в минуту

Это решает проблему цикла переподключений, которую не могут решить обычные kill-скрипты.

Лимит трафика

· iptables-цепочка VPN_TRAFFIC с правилом -m owner --uid-owner <UID> -j RETURN
· Cron раз в 5 минут снимает счётчики, суммирует в файл
· При превышении — usermod -L (блокировка)

Баннер

· Файл /etc/bannerssh с HTML
· Подключён через Banner в /etc/ssh/sshd_config
· Работает в DarkTunnel, HTTP Injector, KPN Tunnel

---

🧪 Проверка после установки

```bash
# PAM — проверка лимита устройств
grep "check-device-limit-pam" /etc/pam.d/sshd

# Баннер
grep "^Banner" /etc/ssh/sshd_config
cat /etc/bannerssh

# Cron-задачи
ls -la /etc/cron.d/vpn-*

# iptables
iptables -L VPN_TRAFFIC -v -n
```

---

🐛 Troubleshooting

<details>
<summary><b>SSH не пускает root после установки</b></summary>

Через VNC-консоль хостера:

```bash
sed -i '/check-device-limit-pam/d' /etc/pam.d/sshd
systemctl restart ssh
```

</details>

<details>
<summary><b>Баннер не показывается</b></summary>

Проверь:

```bash
cat /etc/bannerssh
grep "^Banner" /etc/ssh/sshd_config
systemctl restart ssh
```

</details>

<details>
<summary><b>WS Proxy не работает</b></summary>

```bash
systemctl status ws-proxy
journalctl -u ws-proxy -n 50
```

</details>

---

📞 Поддержка

· 💬 Telegram: @ArsenGuro
· 📢 Канал: @ArsenVipKeys

---

<div align="center">

⭐ Если панель полезна — поставь звезду!

Made with ❤️ by @ArsenGuro

</div>
```
