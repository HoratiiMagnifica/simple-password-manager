#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}▶ Uninstalling Password Manager...${NC}"

systemctl stop password-manager
systemctl disable password-manager
rm -f /etc/systemd/system/password-manager.service
systemctl daemon-reload

ufw delete allow 8444/tcp

rm -f /var/www/simple-password-manager/passwords.db
rm -f /root/password-manager-credentials.txt

echo -e "${GREEN}✅ Uninstall complete${NC}"
echo -e "${YELLOW}📁 Project folder: /var/www/simple-password-manager${NC}"
echo -e "${YELLOW}📁 To remove completely: rm -rf /var/www/simple-password-manager${NC}"
