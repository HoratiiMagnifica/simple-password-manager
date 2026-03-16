import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'simple-key-12345')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///passwords.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 1800

db = SQLAlchemy(app)

# Модели
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    password = db.Column(db.String(200))

class Password(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    title = db.Column(db.String(200))
    login = db.Column(db.String(200))
    pwd = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CustomField(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    password_id = db.Column(db.Integer)
    field_name = db.Column(db.String(100))
    field_value = db.Column(db.String(200))

# Создаем таблицы
with app.app_context():
    db.create_all()

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
    
    user = User.query.filter_by(username=username, password=password).first()
    
    if user:
        session['user_id'] = user.id
        session['username'] = user.username
        return jsonify({'success': True})
    
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/manager')
def manager():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('manager.html', username=session['username'])

# ВСЕ ПАРОЛИ
@app.route('/api/passwords', methods=['GET'])
def get_passwords():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    passwords = Password.query.filter_by(user_id=session['user_id']).all()
    result = []
    for p in passwords:
        fields = CustomField.query.filter_by(password_id=p.id).all()
        custom_fields = [{'name': f.field_name, 'value': f.field_value} for f in fields]
        
        result.append({
            'id': p.id,
            'title': p.title,
            'username': p.login,
            'notes': p.notes,
            'custom_fields': custom_fields
        })
    return jsonify(result)

# КОНКРЕТНЫЙ ПАРОЛЬ (ВАЖНО - ЭТОГО НЕ ХВАТАЛО!)
@app.route('/api/passwords/<int:password_id>', methods=['GET'])
def get_password(password_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    p = Password.query.get_or_404(password_id)
    if p.user_id != session['user_id']:
        return jsonify({'error': 'No permission'}), 403
    
    fields = CustomField.query.filter_by(password_id=p.id).all()
    custom_fields = [{'name': f.field_name, 'value': f.field_value} for f in fields]
    
    return jsonify({
        'id': p.id,
        'title': p.title,
        'username': p.login,
        'password': p.pwd,
        'notes': p.notes,
        'custom_fields': custom_fields
    })

@app.route('/api/passwords', methods=['POST'])
def add_password():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    
    p = Password(
        user_id=session['user_id'],
        title=data['title'],
        login=data.get('username', ''),
        pwd=data.get('password', ''),
        notes=data.get('notes', '')
    )
    db.session.add(p)
    db.session.flush()
    
    for field in data.get('custom_fields', []):
        if field.get('name'):
            cf = CustomField(
                password_id=p.id,
                field_name=field['name'],
                field_value=field.get('value', '')
            )
            db.session.add(cf)
    
    db.session.commit()
    return jsonify({'id': p.id, 'success': True})

@app.route('/api/passwords/<int:password_id>', methods=['PUT'])
def update_password(password_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    p = Password.query.get_or_404(password_id)
    if p.user_id != session['user_id']:
        return jsonify({'error': 'No permission'}), 403
    
    data = request.get_json()
    p.title = data.get('title', p.title)
    p.login = data.get('username', p.login)
    p.pwd = data.get('password', p.pwd)
    p.notes = data.get('notes', p.notes)
    
    CustomField.query.filter_by(password_id=password_id).delete()
    
    for field in data.get('custom_fields', []):
        if field.get('name'):
            cf = CustomField(
                password_id=password_id,
                field_name=field['name'],
                field_value=field.get('value', '')
            )
            db.session.add(cf)
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/passwords/<int:password_id>', methods=['DELETE'])
def delete_password(password_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    p = Password.query.get_or_404(password_id)
    if p.user_id != session['user_id']:
        return jsonify({'error': 'No permission'}), 403
    
    CustomField.query.filter_by(password_id=password_id).delete()
    db.session.delete(p)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/search')
def search():
    if 'user_id' not in session:
        return jsonify([])
    
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify([])
    
    passwords = Password.query.filter_by(user_id=session['user_id']).all()
    results = []
    
    for p in passwords:
        if (query in p.title.lower() or 
            (p.login and query in p.login.lower()) or
            (p.notes and query in p.notes.lower())):
            
            fields = CustomField.query.filter_by(password_id=p.id).all()
            custom_fields = [{'name': f.field_name, 'value': f.field_value} for f in fields]
            
            results.append({
                'id': p.id,
                'title': p.title,
                'username': p.login,
                'password': p.pwd,
                'notes': p.notes,
                'custom_fields': custom_fields
            })
    
    return jsonify(results)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8444))
    app.run(host='0.0.0.0', port=port, debug=False)