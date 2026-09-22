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

