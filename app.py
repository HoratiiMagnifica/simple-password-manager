import os
import base64
import hashlib
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import pyotp
import qrcode
from io import BytesIO
import base64 as b64

from config import Config

# Инициализация приложения
app = Flask(__name__)
app.config.from_object(Config)

# Инициализация БД
db = SQLAlchemy(app)

# Инициализация лимитера
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Инициализация хешера паролей
ph = PasswordHasher()

# Модели базы данных
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    totp_secret = db.Column(db.String(32))
    totp_enabled = db.Column(db.Boolean, default=False)
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    passwords = db.relationship('PasswordEntry', backref='user', lazy=True)

class PasswordEntry(db.Model):
    __tablename__ = 'passwords'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    username = db.Column(db.String(200))
    encrypted_password = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    custom_fields = db.relationship('CustomField', backref='password_entry', lazy=True, cascade='all, delete-orphan')

class CustomField(db.Model):
    __tablename__ = 'custom_fields'
    
    id = db.Column(db.Integer, primary_key=True)
    password_id = db.Column(db.Integer, db.ForeignKey('passwords.id'), nullable=False)
    field_name = db.Column(db.String(100), nullable=False)
    field_value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Класс для шифрования
class CryptoManager:
    def __init__(self, master_password, salt=None):
        if salt is None:
            self.salt = os.urandom(16)
        else:
            self.salt = salt
            
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
        self.cipher = Fernet(key)
    
    def encrypt(self, data):
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data):
        return self.cipher.decrypt(encrypted_data.encode()).decode()

# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Маршруты
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('manager'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    totp_code = data.get('totp_code')
    
    user = User.query.filter_by(username=username).first()
    
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Проверка блокировки
    if user.locked_until and user.locked_until > datetime.utcnow():
        return jsonify({'error': 'Account is locked. Try again later.'}), 403
    
    try:
        ph.verify(user.password_hash, password)
        
        # Проверка TOTP если включен
        if user.totp_enabled:
            if not totp_code:
                return jsonify({'requires_totp': True}), 200
            
            totp = pyotp.TOTP(user.totp_secret)
            if not totp.verify(totp_code):
                return jsonify({'error': 'Invalid TOTP code'}), 401
        
        # Сброс счетчика попыток
        user.failed_attempts = 0
        user.locked_until = None
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Создание сессии
        session.permanent = True
        session['user_id'] = user.id
        session['username'] = user.username
        
        # Генерация ключа шифрования из пароля
        crypto = CryptoManager(password)
        session['encryption_key'] = base64.b64encode(crypto.cipher.encrypt(password.encode())).decode()
        
        return jsonify({'success': True})
        
    except VerifyMismatchError:
        # Неудачная попытка входа
        user.failed_attempts += 1
        if user.failed_attempts >= app.config['MAX_LOGIN_ATTEMPTS']:
            user.locked_until = datetime.utcnow() + app.config['LOCKOUT_TIME']
        db.session.commit()
        
        return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/setup-2fa', methods=['POST'])
@login_required
def setup_2fa():
    user = User.query.get(session['user_id'])
    
    if not user.totp_secret:
        user.totp_secret = pyotp.random_base32()
        db.session.commit()
    
    totp = pyotp.TOTP(user.totp_secret)
    provisioning_uri = totp.provisioning_uri(
        user.username,
        issuer_name="Password Manager"
    )
    
    # Генерация QR-кода
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = b64.b64encode(buffered.getvalue()).decode()
    
    return jsonify({
        'secret': user.totp_secret,
        'qr_code': f'data:image/png;base64,{img_str}'
    })

@app.route('/verify-2fa', methods=['POST'])
@login_required
def verify_2fa():
    data = request.get_json()
    code = data.get('code')
    
    user = User.query.get(session['user_id'])
    totp = pyotp.TOTP(user.totp_secret)
    
    if totp.verify(code):
        user.totp_enabled = True
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'error': 'Invalid code'}), 400

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/manager')
@login_required
def manager():
    return render_template('manager.html', username=session['username'])

@app.route('/api/passwords', methods=['GET'])
@login_required
def get_passwords():
    user = User.query.get(session['user_id'])
    passwords = PasswordEntry.query.filter_by(user_id=user.id).all()
    
    result = []
    for p in passwords:
        result.append({
            'id': p.id,
            'title': p.title,
            'username': p.username,
            'notes': p.notes,
            'created_at': p.created_at.isoformat(),
            'custom_fields': [{'name': f.field_name, 'value': f.field_value} 
                             for f in p.custom_fields]
        })
    
    return jsonify(result)

@app.route('/api/passwords/<int:password_id>', methods=['GET'])
@login_required
def get_password(password_id):
    password_entry = PasswordEntry.query.get_or_404(password_id)
    
    if password_entry.user_id != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Дешифровка пароля
    encryption_key = base64.b64decode(session['encryption_key'])
    cipher = Fernet(encryption_key)
    decrypted_password = cipher.decrypt(password_entry.encrypted_password.encode()).decode()
    
    return jsonify({
        'id': password_entry.id,
        'title': password_entry.title,
        'username': password_entry.username,
        'password': decrypted_password,
        'notes': password_entry.notes,
        'custom_fields': [{'name': f.field_name, 'value': f.field_value} 
                         for f in password_entry.custom_fields]
    })

@app.route('/api/passwords', methods=['POST'])
@login_required
def add_password():
    data = request.get_json()
    
    # Шифрование пароля
    encryption_key = base64.b64decode(session['encryption_key'])
    cipher = Fernet(encryption_key)
    encrypted_password = cipher.encrypt(data['password'].encode())
    
    password_entry = PasswordEntry(
        user_id=session['user_id'],
        title=data['title'],
        username=data.get('username', ''),
        encrypted_password=encrypted_password.decode(),
        notes=data.get('notes', '')
    )
    
    db.session.add(password_entry)
    db.session.flush()
    
    # Добавление кастомных полей
    if 'custom_fields' in data:
        for field in data['custom_fields']:
            if field['name'] and field['value']:
                custom_field = CustomField(
                    password_id=password_entry.id,
                    field_name=field['name'],
                    field_value=field['value']
                )
                db.session.add(custom_field)
    
    db.session.commit()
    
    return jsonify({'id': password_entry.id, 'success': True})

@app.route('/api/passwords/<int:password_id>', methods=['PUT'])
@login_required
def update_password(password_id):
    password_entry = PasswordEntry.query.get_or_404(password_id)
    
    if password_entry.user_id != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    
    # Обновление основных полей
    password_entry.title = data.get('title', password_entry.title)
    password_entry.username = data.get('username', password_entry.username)
    password_entry.notes = data.get('notes', password_entry.notes)
    
    # Обновление пароля если предоставлен
    if 'password' in data:
        encryption_key = base64.b64decode(session['encryption_key'])
        cipher = Fernet(encryption_key)
        encrypted_password = cipher.encrypt(data['password'].encode())
        password_entry.encrypted_password = encrypted_password.decode()
    
    # Обновление кастомных полей
    if 'custom_fields' in data:
        # Удаление старых полей
        CustomField.query.filter_by(password_id=password_entry.id).delete()
        
        # Добавление новых
        for field in data['custom_fields']:
            if field['name'] and field['value']:
                custom_field = CustomField(
                    password_id=password_entry.id,
                    field_name=field['name'],
                    field_value=field['value']
                )
                db.session.add(custom_field)
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/passwords/<int:password_id>', methods=['DELETE'])
@login_required
def delete_password(password_id):
    password_entry = PasswordEntry.query.get_or_404(password_id)
    
    if password_entry.user_id != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(password_entry)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/search')
@login_required
def search_passwords():
    query = request.args.get('q', '').lower()
    
    if not query:
        return jsonify([])
    
    passwords = PasswordEntry.query.filter_by(user_id=session['user_id']).all()
    
    results = []
    for p in passwords:
        if (query in p.title.lower() or 
            (p.username and query in p.username.lower()) or
            (p.notes and query in p.notes.lower())):
            
            # Дешифровка пароля для поиска в кастомных полях
            encryption_key = base64.b64decode(session['encryption_key'])
            cipher = Fernet(encryption_key)
            
            try:
                decrypted_password = cipher.decrypt(p.encrypted_password.encode()).decode()
                
                # Поиск в кастомных полях
                for field in p.custom_fields:
                    if query in field.field_name.lower() or query in field.field_value.lower():
                        results.append({
                            'id': p.id,
                            'title': p.title,
                            'username': p.username,
                            'password': decrypted_password,
                            'notes': p.notes,
                            'custom_fields': [{'name': f.field_name, 'value': f.field_value} 
                                             for f in p.custom_fields]
                        })
                        break
                else:
                    results.append({
                        'id': p.id,
                        'title': p.title,
                        'username': p.username,
                        'password': decrypted_password,
                        'notes': p.notes,
                        'custom_fields': [{'name': f.field_name, 'value': f.field_value} 
                                         for f in p.custom_fields]
                    })
            except:
                continue
    
    return jsonify(results)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False, host='0.0.0.0', port=5000)