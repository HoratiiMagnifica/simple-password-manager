#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Установка менеджера паролей${NC}"
echo ""

# Запрашиваем данные администратора
echo -e "${YELLOW}Введите данные для входа:${NC}"
read -p "Логин (по умолчанию admin): " ADMIN_LOGIN
ADMIN_LOGIN=${ADMIN_LOGIN:-admin}

while true; do
    read -s -p "Пароль: " ADMIN_PASSWORD
    echo ""
    read -s -p "Повторите пароль: " ADMIN_PASSWORD2
    echo ""
    
    if [ "$ADMIN_PASSWORD" = "$ADMIN_PASSWORD2" ]; then
        if [ ${#ADMIN_PASSWORD} -ge 4 ]; then
            break
        else
            echo -e "${RED}Пароль должен быть минимум 4 символа${NC}"
        fi
    else
        echo -e "${RED}Пароли не совпадают${NC}"
    fi
done

echo ""
echo -e "${GREEN}▶ Начинаю установку...${NC}"

# Проверка root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Ошибка: запустите с sudo${NC}"
   exit 1
fi

# Установка зависимостей
apt update
apt install -y python3-pip python3-venv ufw

# Переходим в папку проекта
cd /var/www/simple-password-manager

# Удаляем старую базу
rm -f passwords.db

# Создаем виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Устанавливаем пакеты
pip install flask flask-sqlalchemy

# Создаем .env файл
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
cat > .env << EOF
SECRET_KEY=$SECRET_KEY
PORT=8444
EOF

# Создаем нового пользователя в базе через Python
python3 << EOF
from app import app, db, User

with app.app_context():
    db.create_all()
    
    # Удаляем старого admin если есть
    User.query.delete()
    
    # Создаем нового пользователя
    user = User(
        username='$ADMIN_LOGIN',
        password='$ADMIN_PASSWORD'
    )
    db.session.add(user)
    db.session.commit()
    print('✅ Пользователь создан')
EOF

# Создаем systemd сервис
cat > /etc/systemd/system/password-manager.service << EOF
[Unit]
Description=Password Manager
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/var/www/simple-password-manager
Environment="PATH=/var/www/simple-password-manager/venv/bin"
EnvironmentFile=/var/www/simple-password-manager/.env
ExecStart=/var/www/simple-password-manager/venv/bin/python /var/www/simple-password-manager/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Открываем порт
ufw allow 8444/tcp
ufw --force enable

# Запускаем
systemctl daemon-reload
systemctl stop password-manager 2>/dev/null
systemctl start password-manager
systemctl enable password-manager

IP=$(curl -s ifconfig.me)

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ УСТАНОВКА ЗАВЕРШЕНА!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🌐 Адрес: http://$IP:8444${NC}"
echo -e "${GREEN}👤 Логин: $ADMIN_LOGIN${NC}"
echo -e "${GREEN}🔑 Пароль: $ADMIN_PASSWORD${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"

# Сохраняем данные в файл
cat > /root/password-manager-credentials.txt << EOF
URL: http://$IP:8444
Login: $ADMIN_LOGIN
Password: $ADMIN_PASSWORD
================================
Сохраните эти данные в надежном месте!
EOF

echo -e "${YELLOW}📄 Данные сохранены в /root/password-manager-credentials.txt${NC}"