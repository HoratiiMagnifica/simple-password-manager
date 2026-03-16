import os
import base64
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from cryptography.fernet import Fernet
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32).hex())
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///passwords.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 1800
app.config['SESSION_COOKIE_SECURE'] = False  # False для HTTP
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db = SQLAlchemy(app)
ph = PasswordHasher()

# Модели
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    passwords = db.relationship('PasswordEntry', backref='owner', lazy=True)

class PasswordEntry(db.Model):
    __tablename__ = 'passwords'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    username = db.Column(db.String(200))
    encrypted_password = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    custom_fields = db.relationship('CustomField', backref='password_entry', lazy=True, cascade='all, delete-orphan')

class CustomField(db.Model):
    __tablename__ = 'custom_fields'
    id = db.Column(db.Integer, primary_key=True)
    password_id = db.Column(db.Integer, db.ForeignKey('passwords.id'), nullable=False)
    field_name = db.Column(db.String(100), nullable=False)
    field_value = db.Column(db.Text)

# Декоратор авторизации
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
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    try:
        ph.verify(user.password_hash, password)
        session.permanent = True
        session['user_id'] = user.id
        session['username'] = user.username
        return jsonify({'success': True})
    except VerifyMismatchError:
        return jsonify({'error': 'Invalid credentials'}), 401

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
    passwords = PasswordEntry.query.filter_by(user_id=session['user_id']).all()
    result = []
    for p in passwords:
        result.append({
            'id': p.id,
            'title': p.title,
            'username': p.username,
            'notes': p.notes,
            'created_at': p.created_at.isoformat() if p.created_at else None,
            'custom_fields': [{'name': f.field_name, 'value': f.field_value} for f in p.custom_fields]
        })
    return jsonify(result)

@app.route('/api/passwords/<int:password_id>', methods=['GET'])
@login_required
def get_password(password_id):
    p = PasswordEntry.query.get_or_404(password_id)
    if p.user_id != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Для простоты используем фиктивный ключ (в реальном проекте нужно хранить ключ в сессии)
    cipher = Fernet(base64.urlsafe_b64encode(b'0' * 32))
    try:
        decrypted = cipher.decrypt(p.encrypted_password.encode()).decode()
    except:
        decrypted = "********"
    
    return jsonify({
        'id': p.id,
        'title': p.title,
        'username': p.username,
        'password': decrypted,
        'notes': p.notes,
        'custom_fields': [{'name': f.field_name, 'value': f.field_value} for f in p.custom_fields]
    })

@app.route('/api/passwords', methods=['POST'])
@login_required
def add_password():
    data = request.get_json()
    
    cipher = Fernet(base64.urlsafe_b64encode(b'0' * 32))
    encrypted = cipher.encrypt(data.get('password', '').encode())
    
    p = PasswordEntry(
        user_id=session['user_id'],
        title=data['title'],
        username=data.get('username', ''),
        encrypted_password=encrypted.decode(),
        notes=data.get('notes', '')
    )
    
    db.session.add(p)
    db.session.flush()
    
    for field in data.get('custom_fields', []):
        if field.get('name') and field.get('value'):
            cf = CustomField(
                password_id=p.id,
                field_name=field['name'],
                field_value=field['value']
            )
            db.session.add(cf)
    
    db.session.commit()
    return jsonify({'id': p.id, 'success': True})

@app.route('/api/passwords/<int:password_id>', methods=['PUT'])
@login_required
def update_password(password_id):
    p = PasswordEntry.query.get_or_404(password_id)
    if p.user_id != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    p.title = data.get('title', p.title)
    p.username = data.get('username', p.username)
    p.notes = data.get('notes', p.notes)
    
    if data.get('password'):
        cipher = Fernet(base64.urlsafe_b64encode(b'0' * 32))
        p.encrypted_password = cipher.encrypt(data['password'].encode()).decode()
    
    CustomField.query.filter_by(password_id=p.id).delete()
    
    for field in data.get('custom_fields', []):
        if field.get('name') and field.get('value'):
            cf = CustomField(
                password_id=p.id,
                field_name=field['name'],
                field_value=field['value']
            )
            db.session.add(cf)
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/passwords/<int:password_id>', methods=['DELETE'])
@login_required
def delete_password(password_id):
    p = PasswordEntry.query.get_or_404(password_id)
    if p.user_id != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(p)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/search')
@login_required
def search():
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify([])
    
    passwords = PasswordEntry.query.filter_by(user_id=session['user_id']).all()
    results = []
    
    for p in passwords:
        if (query in p.title.lower() or 
            (p.username and query in p.username.lower()) or
            (p.notes and query in p.notes.lower())):
            results.append({
                'id': p.id,
                'title': p.title,
                'username': p.username,
                'notes': p.notes
            })
    
    return jsonify(results)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 8444))
    app.run(host='0.0.0.0', port=port, debug=False)