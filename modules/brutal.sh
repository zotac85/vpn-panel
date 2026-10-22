#!/bin/bash
BRUTAL_CONF="/etc/UDPCustom/brutal_rules.conf"
BRUTAL_SERVICE="/etc/systemd/system/tcp-brutal.service"

_update_systemd_service() {
    # Создаем или обновляем сервис автозагрузки (с игнорированием ошибок дубликатов)
    cat << SERVICE > "$BRUTAL_SERVICE"
[Unit]
Description=TCP Brutal Autoload Rules
After=network.target

[Service]
Type=oneshot
ExecStart=-/sbin/modprobe brutal
ExecStart=-/bin/bash -c 'if [ -f $BRUTAL_CONF ]; then while read -r ip spd; do [[ -z "\$ip" || "\$ip" == \#* ]] || /usr/local/bin/brutalctl add "\$ip" "\$spd"; done < $BRUTAL_CONF; fi'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICE
    systemctl daemon-reload
    systemctl enable tcp-brutal.service &>/dev/null
}

_apply_rules_now() {
    # Очищаем текущие правила и применяем из конфига
    if command -v brutalctl &>/dev/null; then
        for ip in $(brutalctl list | awk '{print $1}'); do
            brutalctl del "$ip" &>/dev/null
        done
    fi
    modprobe brutal 2>/dev/null
    if [ -f "$BRUTAL_CONF" ]; then
        while read -r ip spd; do
            [[ -z "$ip" || "$ip" == \#* ]] && continue
            brutalctl add "$ip" "$spd" &>/dev/null
        done < "$BRUTAL_CONF"
    fi
}

install_tcp_brutal() {
    clear
    echo "=================================================="
    echo "        УСТАНОВКА / ОБНОВЛЕНИЕ TCP BRUTAL         "
    echo "=================================================="
    
    echo "→ Обновление списка пакетов..."
    apt update -y &>/dev/null
    
    echo "→ Установка зависимостей (linux-headers, build-essential, dkms)..."
    apt install -y linux-headers-$(uname -r) build-essential dkms &>/dev/null
    
    echo "→ Запуск официального установщика TCP Brutal..."
    bash <(curl -fsSL https://tcp.hy2.sh/)
    
    if [ $? -eq 0 ]; then
        echo "✅ Установка завершена успешно!"
        modprobe brutal 2>/dev/null
        
        # Проверка загрузки модуля
        if lsmod | grep -q "brutal"; then
            echo -e "[0;32m✅ Модуль 'brutal' успешно загружен в ядро.[0m"
        else
            echo -e "[0;31m❌ ВНИМАНИЕ: Модуль установлен, но не загрузился.[0m"
            echo -e "[0;33mВозможно, включен Secure Boot или требуется перезагрузка сервера.[0m"
        fi
        
        _update_systemd_service
        _apply_rules_now
        echo "✅ Автозагрузка настроена."
    else
        echo "❌ Ошибка установки TCP Brutal."
    fi
    read -p "Нажмите Enter..."
}

manage_tcp_brutal() {
    touch "$BRUTAL_CONF"
    _update_systemd_service

    while true; do
        clear
        echo "=================================================="
        echo "        УПРАВЛЕНИЕ TCP BRUTAL                     "
        echo "=================================================="
        
        if ! command -v brutalctl &> /dev/null; then
            echo "TCP Brutal не установлен."
            read -p "Установить сейчас? (y/n): " inst
            if [[ "$inst" == "y" || "$inst" == "Y" ]]; then install_tcp_brutal; fi
            return
        fi

        if lsmod | grep -q "brutal"; then
            echo -e "Статус: \033[0;32mМодуль загружен\033[0m"
        else
            echo -e "Статус: \033[0;31mМодуль не загружен\033[0m"
        fi

        echo ""
        echo "1) Показать активные правила"
        echo "2) Добавить/Изменить правило (в автозагрузку)"
        echo "3) Удалить правило (из автозагрузки)"
        echo "4) Обновить TCP Brutal (переустановить)"
        echo "0) Назад"
        echo "--------------------------------------------------"
        read -p "Выберите пункт [0-4]: " b_choice
        
        case $b_choice in
            1)
                echo ""
                brutalctl list
                read -p "Нажмите Enter..."
                ;;
            2)
                read -p "Введите IP (или 0.0.0.0/0): " cip
                read -p "Введите скорость (Мбит/с): " spd
                if [[ -n "$cip" && -n "$spd" ]]; then
                    if [[ "$cip" != */* ]]; then cip="${cip}/32"; fi
                    
                    # Сохраняем в конфиг
                    sed -i "\|^$cip|d" "$BRUTAL_CONF"
                    echo "$cip $spd" >> "$BRUTAL_CONF"
                    
                    # Применяем
                    _apply_rules_now
                    systemctl restart tcp-brutal.service
                    
                    # Честная проверка
                    if systemctl is-active --quiet tcp-brutal.service; then
                        echo -e "\033[0;32m✅ Правило $cip со скоростью $spd Мбит/с успешно сохранено и применено!\033[0m"
                    else
                        echo -e "\033[0;31m❌ ОШИБКА: Не удалось применить правило.\033[0m"
                        echo -e "\033[0;33mПроверьте: journalctl -u tcp-brutal.service\033[0m"
                    fi
                fi
                read -p "Нажмите Enter..."
                ;;
            3)
                read -p "Введите IP для удаления: " cip
                if [[ -n "$cip" ]]; then
                    if [[ "$cip" != */* ]]; then cip="${cip}/32"; fi
                    sed -i "\|^$cip|d" "$BRUTAL_CONF"
                    _apply_rules_now
                    systemctl restart tcp-brutal.service
                    echo -e "\033[0;32m✅ Правило удалено.\033[0m"
                fi
                read -p "Нажмите Enter..."
                ;;
            4)
                install_tcp_brutal
                ;;
            0) return ;;
        esac
    done
}
