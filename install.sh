#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Установка менеджера паролей...${NC}"

# Проверка root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Запустите с sudo: sudo ./install.sh${NC}"
   exit 1
fi

# Установка зависимостей
apt update
apt install -y python3-pip python3-venv ufw

# Создание виртуального окружения
cd /var/www/simple-password-manager
python3 -m venv venv
source venv/bin/activate

# Установка пакетов
pip install --upgrade pip
pip install flask flask-login flask-sqlalchemy cryptography argon2-cffi

# Создание .env
cat > .env << EOF
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
DATABASE_URL=sqlite:////var/www/simple-password-manager/passwords.db
PORT=8444
EOF

# Создание systemd сервиса
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
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Создание пользователя admin
source venv/bin/activate
python3 << EOF
from app import app, db, User
from argon2 import PasswordHasher
import secrets
import string

ph = PasswordHasher()

with app.app_context():
    db.create_all()
    
    # Удаляем старого admin если есть
    User.query.filter_by(username='admin').delete()
    
    # Генерируем пароль
    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    
    user = User(
        username='admin',
        password_hash=ph.hash(password)
    )
    db.session.add(user)
    db.session.commit()
    
    with open('/root/password_manager_credentials.txt', 'w') as f:
        f.write(f"URL: http://$(curl -s ifconfig.me):8444\n")
        f.write(f"Login: admin\n")
        f.write(f"Password: {password}\n")
    
    print(f"\n✅ Пользователь admin создан")
EOF

# Открыть порт
ufw allow 8444/tcp
ufw --force enable

# Запуск сервиса
systemctl daemon-reload
systemctl enable password-manager
systemctl start password-manager
sleep 3

# Проверка
if systemctl is-active --quiet password-manager; then
    echo -e "${GREEN}✅ Сервис запущен${NC}"
else
    echo -e "${RED}❌ Ошибка запуска сервиса${NC}"
    systemctl status password-manager --no-pager
fi

IP=$(curl -s ifconfig.me)
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Установка завершена!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🌐 Откройте браузер: http://$IP:8444${NC}"
echo -e "${RED}══════════════════════════════════════════════════${NC}"
cat /root/password_manager_credentials.txt 2>/dev/null || echo -e "${RED}❌ Файл с паролем не найден${NC}"
echo -e "${RED}══════════════════════════════════════════════════${NC}"