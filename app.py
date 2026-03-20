import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'simple-key-12345')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///passwords.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 1800

db = SQLAlchemy(app)

# Модель пользователя с правами
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Права доступа (битовые флаги)
    can_view_all = db.Column(db.Boolean, default=False)
    can_create = db.Column(db.Boolean, default=False)
    can_edit = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    can_manage_users = db.Column(db.Boolean, default=False)
    
    # Связи
    shared_items = db.relationship('ItemPermission', backref='user', lazy=True)

# Модель для базовых элементов (пароли, телефоны, карты)
class BaseItem(db.Model):
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer)  # Владелец
    title = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Права доступа к элементу
    is_public = db.Column(db.Boolean, default=False)

class Password(BaseItem):
    __tablename__ = 'passwords'
    username = db.Column(db.String(200))
    password = db.Column(db.String(200))

class Phone(BaseItem):
    __tablename__ = 'phones'
    phone_number = db.Column(db.String(50))
    operator = db.Column(db.String(100))

class Card(BaseItem):
    __tablename__ = 'cards'
    card_number = db.Column(db.String(50))
    expiry_date = db.Column(db.String(10))
    cvv = db.Column(db.String(10))

class CustomField(db.Model):
    __tablename__ = 'custom_fields'
    id = db.Column(db.Integer, primary_key=True)
    item_type = db.Column(db.String(20))
    item_id = db.Column(db.Integer)
    field_name = db.Column(db.String(100))
    field_value = db.Column(db.String(200))

# Модель для разрешений на конкретные элементы
class ItemPermission(db.Model):
    __tablename__ = 'item_permissions'
    id = db.Column(db.Integer, primary_key=True)
    item_type = db.Column(db.String(20))  # 'password', 'phone', 'card'
    item_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    can_view = db.Column(db.Boolean, default=True)
    can_edit = db.Column(db.Boolean, default=False)

# Декораторы для проверки прав
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def can_manage_items(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        user = User.query.get(session['user_id'])
        if not user or (not user.can_create and not user.is_admin):
            return jsonify({'error': 'Permission denied'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Проверка доступа к конкретному элементу
# Проверка доступа к конкретному элементу
def can_access_item(item_type, item_id, user_id, action='view'):
    user = User.query.get(user_id)
    
    # Админ имеет полный доступ
    if user.is_admin:
        return True
    
    # Владелец имеет полный доступ
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    if not model:
        return False
    
    item = model.query.get(item_id)
    if not item:
        return False
    
    if item.owner_id == user_id:
        return True
    
    # Проверка глобальных прав (can_view_all)
    if action == 'view' and user.can_view_all:
        return True
    
    # Проверка публичного доступа
    if action == 'view' and item.is_public:
        return True
    
    # Проверка индивидуальных разрешений
    perm = ItemPermission.query.filter_by(
        item_type=item_type,
        item_id=item_id,
        user_id=user_id
    ).first()
    
    if action == 'view':
        return perm and perm.can_view
    elif action == 'edit':
        return perm and perm.can_edit
    elif action == 'delete':
        return False  # Удалять может только владелец или админ
    
    return False

with app.app_context():
    db.create_all()
    
    # Создание админа по умолчанию если нет пользователей
    if User.query.count() == 0:
        admin = User(
            username='admin',
            password='admin123',
            is_admin=True,
            can_view_all=True,
            can_create=True,
            can_edit=True,
            can_delete=True,
            can_manage_users=True
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin user created: admin / admin123")

# ============ Аутентификация ============
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
        session['is_admin'] = user.is_admin
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
    user = User.query.get(session['user_id'])
    return render_template('manager.html', username=session['username'], is_admin=user.is_admin)

# ============ Управление пользователями ============
@app.route('/api/users', methods=['GET'])
@login_required
@admin_required
def get_users():
    users = User.query.all()
    result = []
    for u in users:
        result.append({
            'id': u.id,
            'username': u.username,
            'is_admin': u.is_admin,
            'can_view_all': u.can_view_all,
            'can_create': u.can_create,
            'can_edit': u.can_edit,
            'can_delete': u.can_delete,
            'can_manage_users': u.can_manage_users,
            'created_at': u.created_at.isoformat() if u.created_at else None
        })
    return jsonify(result)

@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    data = request.get_json()
    
    # Проверка существования
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    user = User(
        username=data['username'],
        password=data.get('password', 'changeme123'),
        is_admin=data.get('is_admin', False),
        can_view_all=data.get('can_view_all', False),
        can_create=data.get('can_create', False),
        can_edit=data.get('can_edit', False),
        can_delete=data.get('can_delete', False),
        can_manage_users=data.get('can_manage_users', False)
    )
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'id': user.id, 'success': True})

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    # Нельзя менять последнего админа
    if user.is_admin and User.query.filter_by(is_admin=True).count() == 1 and not data.get('is_admin', True):
        return jsonify({'error': 'Cannot remove last admin'}), 400
    
    user.username = data.get('username', user.username)
    if data.get('password'):
        user.password = data['password']
    user.is_admin = data.get('is_admin', user.is_admin)
    user.can_view_all = data.get('can_view_all', user.can_view_all)
    user.can_create = data.get('can_create', user.can_create)
    user.can_edit = data.get('can_edit', user.can_edit)
    user.can_delete = data.get('can_delete', user.can_delete)
    user.can_manage_users = data.get('can_manage_users', user.can_manage_users)
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Нельзя удалить себя
    if user.id == session['user_id']:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    
    # Нельзя удалить последнего админа
    if user.is_admin and User.query.filter_by(is_admin=True).count() == 1:
        return jsonify({'error': 'Cannot delete last admin'}), 400
    
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/users')
@login_required
def users_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user.is_admin:
        return redirect(url_for('manager'))
    return render_template('users.html', username=session['username'])

@app.route('/api/current-user', methods=['GET'])
@login_required
def get_current_user():
    user = User.query.get(session['user_id'])
    return jsonify({
        'id': user.id,
        'username': user.username,
        'is_admin': user.is_admin
    })

# ============ Получение элементов (с учетом прав) ============
@app.route('/api/items/<item_type>', methods=['GET'])
@login_required
def get_items(item_type):
    user = User.query.get(session['user_id'])
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    
    if not model:
        return jsonify({'error': 'Invalid type'}), 400
    
    if user.can_view_all or user.is_admin:
        items = model.query.all()
    else:
        # Свои + публичные + с разрешением
        items = model.query.filter(
            (model.owner_id == user.id) | 
            (model.is_public == True)
        ).all()
        
        # Добавляем элементы с индивидуальными разрешениями
        perms = ItemPermission.query.filter_by(user_id=user.id, can_view=True).all()
        for perm in perms:
            if perm.item_type == item_type:
                item = model.query.get(perm.item_id)
                if item and item not in items:
                    items.append(item)
    
    result = []
    for item in items:
        fields = CustomField.query.filter_by(item_type=item_type, item_id=item.id).all()
        custom_fields = [{'name': f.field_name, 'value': f.field_value} for f in fields]
        
        item_dict = {
            'id': item.id,
            'title': item.title,
            'notes': item.notes,
            'owner_id': item.owner_id,
            'is_public': item.is_public,
            'created_at': item.created_at.isoformat() if item.created_at else None,
            'updated_at': item.updated_at.isoformat() if item.updated_at else None,
            'custom_fields': custom_fields
        }
        
        if item_type == 'passwords':
            item_dict['username'] = item.username
            item_dict['password'] = item.password if item.owner_id == user.id or user.is_admin else '********'
        elif item_type == 'phones':
            item_dict['phone_number'] = item.phone_number
            item_dict['operator'] = item.operator
        elif item_type == 'cards':
            item_dict['card_number'] = item.card_number if item.owner_id == user.id or user.is_admin else '****' + item.card_number[-4:] if item.card_number else ''
            item_dict['expiry_date'] = item.expiry_date
            item_dict['cvv'] = item.cvv if item.owner_id == user.id or user.is_admin else '***'
        
        result.append(item_dict)
    
    return jsonify(result)

# ============ Получение одного элемента ============
@app.route('/api/items/<item_type>/<int:item_id>', methods=['GET'])
@login_required
def get_item(item_type, item_id):
    user = User.query.get(session['user_id'])
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    
    if not model:
        return jsonify({'error': 'Invalid type'}), 400
    
    item = model.query.get_or_404(item_id)
    
    # Проверка прав доступа
    if not can_access_item(item_type, item_id, user.id, 'view'):
        return jsonify({'error': 'No permission'}), 403
    
    fields = CustomField.query.filter_by(item_type=item_type, item_id=item.id).all()
    custom_fields = [{'name': f.field_name, 'value': f.field_value} for f in fields]
    
    # Определяем, показывать ли полные данные или скрытые
    show_full = (item.owner_id == user.id or user.is_admin or user.can_view_all)
    
    result = {
        'id': item.id,
        'title': item.title,
        'notes': item.notes,
        'owner_id': item.owner_id,
        'is_public': item.is_public,
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
        'custom_fields': custom_fields,
        'shared_with': []
    }
    
    # Получаем список пользователей с доступом (только для владельца или админа)
    if item.owner_id == user.id or user.is_admin:
        perms = ItemPermission.query.filter_by(item_type=item_type, item_id=item_id).all()
        for perm in perms:
            shared_user = User.query.get(perm.user_id)
            if shared_user:
                result['shared_with'].append({
                    'id': shared_user.id,
                    'username': shared_user.username,
                    'can_edit': perm.can_edit
                })
    
    # Заполняем поля в зависимости от типа
    if item_type == 'passwords':
        result['username'] = item.username if show_full else ''
        result['password'] = item.password if show_full else '********'
    elif item_type == 'phones':
        result['phone_number'] = item.phone_number if show_full else ''
        result['operator'] = item.operator if show_full else ''
    elif item_type == 'cards':
        result['card_number'] = item.card_number if show_full else '****' + item.card_number[-4:] if item.card_number else ''
        result['expiry_date'] = item.expiry_date if show_full else '**/**'
        result['cvv'] = item.cvv if show_full else '***'
    
    return jsonify(result)

# ============ Добавление элемента ============
@app.route('/api/items/<item_type>', methods=['POST'])
@login_required
def add_item(item_type):
    user = User.query.get(session['user_id'])
    
    if not (user.can_create or user.is_admin):
        return jsonify({'error': 'No permission to create'}), 403
    
    data = request.get_json()
    
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    if not model:
        return jsonify({'error': 'Invalid type'}), 400
    
    item_data = {
        'owner_id': session['user_id'],
        'title': data['title'],
        'notes': data.get('notes', ''),
        'is_public': data.get('is_public', False)
    }
    
    if item_type == 'passwords':
        item_data['username'] = data.get('username', '')
        item_data['password'] = data.get('password', '')
    elif item_type == 'phones':
        item_data['phone_number'] = data.get('phone_number', '')
        item_data['operator'] = data.get('operator', '')
    elif item_type == 'cards':
        item_data['card_number'] = data.get('card_number', '')
        item_data['expiry_date'] = data.get('expiry_date', '')
        item_data['cvv'] = data.get('cvv', '')
    
    item = model(**item_data)
    db.session.add(item)
    db.session.flush()
    
    for field in data.get('custom_fields', []):
        if field.get('name'):
            cf = CustomField(
                item_type=item_type,
                item_id=item.id,
                field_name=field['name'],
                field_value=field.get('value', '')
            )
            db.session.add(cf)
    
    # Добавляем разрешения для указанных пользователей
    for share in data.get('shared_with', []):
        if share.get('user_id'):
            perm = ItemPermission(
                item_type=item_type,
                item_id=item.id,
                user_id=share['user_id'],
                can_view=True,
                can_edit=share.get('can_edit', False)
            )
            db.session.add(perm)
    
    db.session.commit()
    return jsonify({'id': item.id, 'success': True})

# ============ Обновление элемента ============
@app.route('/api/items/<item_type>/<int:item_id>', methods=['PUT'])
@login_required
def update_item(item_type, item_id):
    user = User.query.get(session['user_id'])
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    
    if not model:
        return jsonify({'error': 'Invalid type'}), 400
    
    item = model.query.get_or_404(item_id)
    
    # Проверка прав на редактирование
    if item.owner_id != user.id and not (user.is_admin or user.can_edit):
        perm = ItemPermission.query.filter_by(
            item_type=item_type, item_id=item_id, user_id=user.id, can_edit=True
        ).first()
        if not perm:
            return jsonify({'error': 'No permission to edit'}), 403
    
    data = request.get_json()
    
    item.title = data.get('title', item.title)
    item.notes = data.get('notes', item.notes)
    item.is_public = data.get('is_public', item.is_public)
    
    if item_type == 'passwords':
        item.username = data.get('username', item.username)
        item.password = data.get('password', item.password)
    elif item_type == 'phones':
        item.phone_number = data.get('phone_number', item.phone_number)
        item.operator = data.get('operator', item.operator)
    elif item_type == 'cards':
        item.card_number = data.get('card_number', item.card_number)
        item.expiry_date = data.get('expiry_date', item.expiry_date)
        item.cvv = data.get('cvv', item.cvv)
    
    CustomField.query.filter_by(item_type=item_type, item_id=item_id).delete()
    
    for field in data.get('custom_fields', []):
        if field.get('name'):
            cf = CustomField(
                item_type=item_type,
                item_id=item_id,
                field_name=field['name'],
                field_value=field.get('value', '')
            )
            db.session.add(cf)
    
    # Обновляем разрешения
    ItemPermission.query.filter_by(item_type=item_type, item_id=item_id).delete()
    for share in data.get('shared_with', []):
        if share.get('user_id'):
            perm = ItemPermission(
                item_type=item_type,
                item_id=item_id,
                user_id=share['user_id'],
                can_view=True,
                can_edit=share.get('can_edit', False)
            )
            db.session.add(perm)
    
    db.session.commit()
    return jsonify({'success': True})

# ============ Удаление элемента ============
@app.route('/api/items/<item_type>/<int:item_id>', methods=['DELETE'])
@login_required
def delete_item(item_type, item_id):
    user = User.query.get(session['user_id'])
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    
    if not model:
        return jsonify({'error': 'Invalid type'}), 400
    
    item = model.query.get_or_404(item_id)
    
    if item.owner_id != user.id and not (user.is_admin or user.can_delete):
        return jsonify({'error': 'No permission to delete'}), 403
    
    CustomField.query.filter_by(item_type=item_type, item_id=item_id).delete()
    ItemPermission.query.filter_by(item_type=item_type, item_id=item_id).delete()
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True})

# ============ Поиск ============
@app.route('/api/search')
@login_required
def search():
    user = User.query.get(session['user_id'])
    query = request.args.get('q', '').lower()
    
    if not query:
        return jsonify([])
    
    results = []
    
    # Функция для поиска в конкретном типе
    def search_in_model(model, item_type, type_name):
        if user.can_view_all or user.is_admin:
            items = model.query.all()
        else:
            items = model.query.filter(
                (model.owner_id == user.id) | (model.is_public == True)
            ).all()
        
        for item in items:
            if (query in item.title.lower() or 
                (item.notes and query in item.notes.lower())):
                results.append({
                    'type': type_name,
                    'id': item.id,
                    'title': item.title,
                    'subtitle': ''
                })
    
    search_in_model(Password, 'passwords', 'password')
    search_in_model(Phone, 'phones', 'phone')
    search_in_model(Card, 'cards', 'card')
    
    return jsonify(results)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8444))
    app.run(host='0.0.0.0', port=port, debug=False)