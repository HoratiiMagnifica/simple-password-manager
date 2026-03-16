#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}🚀 Установка менеджера паролей...${NC}"

# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка зависимостей
sudo apt install -y python3-pip python3-venv nginx ufw

# Создание структуры папок
mkdir -p ~/password-manager/{templates,ssl}

# Переход в папку проекта
cd ~/password-manager

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка Python пакетов
pip install flask flask-login flask-sqlalchemy cryptography argon2-cffi gunicorn pyotp qrcode Pillow python-dotenv

# Создание app.py (вставьте сюда полный код из предыдущего сообщения)
cat > app.py << 'EOF'
[ВСТАВЬТЕ СЮДА ПОЛНЫЙ КОД APP.PY ИЗ ПРЕДЫДУЩЕГО СООБЩЕНИЯ]
EOF

# Создание шаблонов
mkdir -p templates
cat > templates/login.html << 'EOF'
[ВСТАВЬТЕ СЮДА ПОЛНЫЙ КОД LOGIN.HTML]
EOF

cat > templates/manager.html << 'EOF'
[ВСТАВЬТЕ СЮДА ПОЛНЫЙ КОД MANAGER.HTML]
EOF

# Создание .env файла
cat > .env << EOF
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
ENCRYPTION_KEY=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
DATABASE_URL=sqlite:////home/$(whoami)/password-manager/passwords.db
EOF

# Создание сервиса systemd
sudo bash -c 'cat > /etc/systemd/system/password-manager.service << EOF
[Unit]
Description=Password Manager
After=network.target

[Service]
User='$(whoami)'
Group='$(whoami)'
WorkingDirectory=/home/$(whoami)/password-manager
Environment="PATH=/home/$(whoami)/password-manager/venv/bin"
EnvironmentFile=/home/$(whoami)/password-manager/.env
ExecStart=/home/$(whoami)/password-manager/venv/bin/python /home/$(whoami)/password-manager/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF'

# Создание самоподписанного SSL сертификата (для HTTPS)
openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes -subj "/CN=localhost"

# Настройка Nginx
sudo bash -c 'cat > /etc/nginx/sites-available/password-manager << EOF
server {
    listen 80;
    server_name _;
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /home/$(whoami)/password-manager/ssl/cert.pem;
    ssl_certificate_key /home/$(whoami)/password-manager/ssl/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF'

# Активация Nginx конфигурации
sudo ln -sf /etc/nginx/sites-available/password-manager /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# Создание первого пользователя
source venv/bin/activate
python3 << EOF
from app import app, db, User
from argon2 import PasswordHasher

ph = PasswordHasher()

with app.app_context():
    db.create_all()
    # Создание пользователя admin с паролем admin123 (ИЗМЕНИТЕ ПОТОМ!)
    if not User.query.filter_by(username='admin').first():
        user = User(
            username='admin',
            password_hash=ph.hash('admin123')
        )
        db.session.add(user)
        db.session.commit()
        print("✅ Пользователь admin создан (пароль: admin123)")
EOF

# Запуск сервиса
sudo systemctl daemon-reload
sudo systemctl enable password-manager
sudo systemctl start password-manager

# Настройка файрвола
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
echo "y" | sudo ufw enable

# Получение IP адреса
IP=$(curl -s ifconfig.me)

echo -e "${GREEN}✅ Установка завершена!${NC}"
echo -e "${GREEN}🌐 Откройте браузер и перейдите по адресу: https://$IP${NC}"
echo -e "${RED}⚠️  ВАЖНО: Смените пароль администратора после первого входа!${NC}"
echo -e "${RED}👤 Логин: admin${NC}"
echo -e "${RED}🔑 Пароль: admin123${NC}"