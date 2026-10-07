# DarkTunnel HWID Generator — заметки

## Ключи
KEY256 = b"$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd"   # AES-256-CFB outer
KEY192 = b"F)J@NcRfUjXn2r4u7x!A%D*G"           # AES-192-CFB inner
IV     = bytes.fromhex("232e39185523184a5723586242200e05")

## Формула HWID (272 hex)
HW_CONST = "dc55427ad9af7cd342eb60c17393d1c2936521bae81e39147e9e974bf44dff80"
hwid_string = hex(HW_CONST) + hex(HWID) + sha256("")

## Структура darktunnel://
1. base64url -> outer JSON
2. AES-256-CFB decrypt(encryptedLockedConfig) -> msgpack -> inner
3. inner['EncryptedLockedConfig'] -> AES-192-CFB decrypt -> msgpack -> lockedConfig
4. Поля Encrypted* -> AES-192-CFB decrypt

## Правила (иначе "config upgrade required")
- ConnectedMessage — непустое
- host/port/user/pw (SshConfig) — непустые
- proxyHost/proxyPort/payload (InjectConfig) — непустые
- HardwareIdList заполнен
- Message — можно пустое
- Mode=PROXY (Direct не работает)

## Ошибки
- config upgrade required -> битый конфиг / неверный SSH-пароль
- config locked to specific device -> HWID != устройства
- Unexpected EOF at $.encryptedLockedConfig -> ссылка обрезана

## Ссылки
- https://github.com/anujeditsbyanuj-bit/darktunnel-decrypt
- https://github.com/Bujairkc/DarkTunnel-Decrypt
