A lightweight, self-hosted password manager with web interface. Passwords are stored locally on your server.

Quick start

```bash
git clone https://github.com/HoratiiMagnifica/simple-password-manager.git
cd simple-password-manager
chmod +x install.sh uninstall.sh
./install.sh
# During installation you'll be prompted to set admin username and password.
# Ur credentials will be saved to /root/password-manager-credentials.txt
# goto http://URIP:8444/
# u will be redirected to http://URIP:8444/login
# auth
# profit!!!
```

The installer automatically creates a systemd service (password-manager.service) and a .env configuration file.

```bash
# logs
journalctl -u password-manager -f
# stop
systemctl stop password-manager
# restart 
systemctl restart password-manager
```

if u want to change port go to .env

```bash
# do not forget to check ur firewall
ufw status
ufw allow 8444/tcp
# ufw allow URPORT/tcp
```

Uninstall

```bash
# Make sure uninstall.sh is executable (if not done yet)
chmod +x uninstall.sh
# run it
./uninstall.sh
# For complete removal of all files
cd ..
rm -rf simple-password-manager
```
