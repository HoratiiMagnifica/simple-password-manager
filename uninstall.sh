#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${RED}🗑️  Удаление менеджера паролей...${NC}"

# Остановка и удаление сервиса
systemctl stop password-manager
systemctl disable password-manager
rm -f /etc/systemd/system/password-manager.service
systemctl daemon-reload

# Удаление файлов
rm -rf /var/www/simple-password-manager/venv
rm -f /var/www/simple-password-manager/passwords.db
rm -f /var/www/simple-password-manager/.env

# Закрыть порт
ufw delete allow 8444/tcp

# Удаление credentials
rm -f /root/password_manager_credentials.txt

echo -e "${GREEN}✅ Менеджер паролей удален${NC}"
echo -e "${YELLOW}📁 Файлы проекта сохранены в /var/www/simple-password-manager${NC}"
echo -e "${YELLOW}📁 Чтобы удалить полностью: rm -rf /var/www/simple-password-manager${NC}"