<div align="center">

# ⚡ VPN PANEL + Telegram Bot

**Панель управления SSH-туннелями + Telegram-бот для продажи ключей**

![Version](https://img.shields.io/badge/version-2.0.0-blue?style=for-the-badge)
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

## 🚀 Установка мастера

На чистом VPS (Ubuntu 20.04+ / Debian 11+):

```bash
bash <(curl -Ls https://raw.githubusercontent.com/zotac85/vpn-panel/main/install.sh)
