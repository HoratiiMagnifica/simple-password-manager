#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Password Manager Installation${NC}\n"

echo -e "${YELLOW}Enter admin credentials:${NC}"
read -p "Username (default: admin): " ADMIN_LOGIN
ADMIN_LOGIN=${ADMIN_LOGIN:-admin}

while true; do
    read -s -p "Password: " ADMIN_PASSWORD
    echo ""
    read -s -p "Confirm password: " ADMIN_PASSWORD2
    echo ""

    if [ "$ADMIN_PASSWORD" = "$ADMIN_PASSWORD2" ]; then
        if [ ${#ADMIN_PASSWORD} -ge 4 ]; then
            break
        else
            echo -e "${RED}Password must be at least 4 characters${NC}"
        fi
    else
        echo -e "${RED}Passwords do not match${NC}"
    fi
done

echo ""
echo -e "${GREEN}▶ Starting installation...${NC}"

if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: run with sudo${NC}"
   exit 1
fi

apt update
apt install -y python3-pip python3-venv ufw

cd /var/www/simple-password-manager || exit 1
rm -f passwords.db

python3 -m venv venv
source venv/bin/activate
pip install flask flask-sqlalchemy

SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
cat > .env << EOF
SECRET_KEY=$SECRET_KEY
PORT=8444
EOF

python3 << EOF
from app import app, db, User

with app.app_context():
    db.create_all()
    User.query.delete()

    user = User(
        username='$ADMIN_LOGIN',
        password='$ADMIN_PASSWORD'
    )
    db.session.add(user)
    db.session.commit()
    print('✅ User created')
EOF

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

ufw allow 8444/tcp
ufw --force enable

systemctl daemon-reload
systemctl stop password-manager 2>/dev/null
systemctl start password-manager
systemctl enable password-manager

IP=$(curl -s ifconfig.me)

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ INSTALLATION COMPLETE!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🌐 URL: http://$IP:8444${NC}"
echo -e "${GREEN}👤 Username: $ADMIN_LOGIN${NC}"
echo -e "${GREEN}🔑 Password: $ADMIN_PASSWORD${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"

cat > /root/password-manager-credentials.txt << EOF
URL: http://$IP:8444
Username: $ADMIN_LOGIN
Password: $ADMIN_PASSWORD
================================
Save these credentials in a safe place!
EOF

echo -e "${YELLOW}📄 Credentials saved to /root/password-manager-credentials.txt${NC}"
