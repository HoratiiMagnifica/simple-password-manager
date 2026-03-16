#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${RED}▶ Удаление менеджера паролей...${NC}"

# Останавливаем и удаляем сервис
systemctl stop password-manager
systemctl disable password-manager
rm -f /etc/systemd/system/password-manager.service
systemctl daemon-reload

# Закрываем порт
ufw delete allow 8444/tcp

# Удаляем базу данных
rm -f /var/www/simple-password-manager/passwords.db

# Удаляем файл с credentials
rm -f /root/password-manager-credentials.txt

echo -e "${GREEN}✅ Удаление завершено${NC}"
echo -e "${YELLOW}📁 Папка проекта: /var/www/simple-password-manager${NC}"
echo -e "${YELLOW}📁 Чтобы удалить полностью: rm -rf /var/www/simple-password-manager${NC}"