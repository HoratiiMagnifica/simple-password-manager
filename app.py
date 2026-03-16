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

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    password = db.Column(db.String(200))

class BaseItem(db.Model):
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    title = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    item_type = db.Column(db.String(20))   # Вот это поле обязательно!
    item_id = db.Column(db.Integer)
    field_name = db.Column(db.String(100))
    field_value = db.Column(db.String(200))

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


# Get all items
@app.route('/api/items/<item_type>', methods=['GET'])
def get_items(item_type):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    if not model:
        return jsonify({'error': 'Invalid type'}), 400
    
    items = model.query.filter_by(user_id=session['user_id']).all()
    result = []
    for item in items:
        fields = CustomField.query.filter_by(item_type=item_type, item_id=item.id).all()
        custom_fields = [{'name': f.field_name, 'value': f.field_value} for f in fields]
        
        item_dict = {
            'id': item.id,
            'title': item.title,
            'notes': item.notes,
            'created_at': item.created_at.isoformat() if item.created_at else None,
            'updated_at': item.updated_at.isoformat() if item.updated_at else None,
            'custom_fields': custom_fields
        }
        
        if item_type == 'passwords':
            item_dict['username'] = item.username
            item_dict['password'] = item.password
        elif item_type == 'phones':
            item_dict['phone_number'] = item.phone_number
            item_dict['operator'] = item.operator
        elif item_type == 'cards':
            item_dict['card_number'] = item.card_number
            item_dict['expiry_date'] = item.expiry_date
            item_dict['cvv'] = item.cvv
        
        result.append(item_dict)
    
    return jsonify(result)

# Get single item
@app.route('/api/items/<item_type>/<int:item_id>', methods=['GET'])
def get_item(item_type, item_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    if not model:
        return jsonify({'error': 'Invalid type'}), 400
    
    item = model.query.get_or_404(item_id)
    if item.user_id != session['user_id']:
        return jsonify({'error': 'No permission'}), 403
    
    
    fields = CustomField.query.filter_by(item_type=item_type, item_id=item.id).all()
    custom_fields = [{'name': f.field_name, 'value': f.field_value} for f in fields]
    
    result = {
        'id': item.id,
        'title': item.title,
        'notes': item.notes,
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
        'custom_fields': custom_fields
    }
    
    if item_type == 'passwords':
        result['username'] = item.username
        result['password'] = item.password
    elif item_type == 'phones':
        result['phone_number'] = item.phone_number
        result['operator'] = item.operator
    elif item_type == 'cards':
        result['card_number'] = item.card_number
        result['expiry_date'] = item.expiry_date
        result['cvv'] = item.cvv
    
    return jsonify(result)

# Add item
@app.route('/api/items/<item_type>', methods=['POST'])
def add_item(item_type):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    if not model:
        return jsonify({'error': 'Invalid type'}), 400
    
    item_data = {
        'user_id': session['user_id'],
        'title': data['title'],
        'notes': data.get('notes', '')
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
    
    db.session.commit()
    return jsonify({'id': item.id, 'success': True})

# Update item
@app.route('/api/items/<item_type>/<int:item_id>', methods=['PUT'])
def update_item(item_type, item_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    if not model:
        return jsonify({'error': 'Invalid type'}), 400
    
    item = model.query.get_or_404(item_id)
    if item.user_id != session['user_id']:
        return jsonify({'error': 'No permission'}), 403
    
    data = request.get_json()
    
    item.title = data.get('title', item.title)
    item.notes = data.get('notes', item.notes)
    
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
    
    db.session.commit()
    return jsonify({'success': True})

# Delete item
@app.route('/api/items/<item_type>/<int:item_id>', methods=['DELETE'])
def delete_item(item_type, item_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    model_map = {'passwords': Password, 'phones': Phone, 'cards': Card}
    model = model_map.get(item_type)
    if not model:
        return jsonify({'error': 'Invalid type'}), 400
    
    item = model.query.get_or_404(item_id)
    if item.user_id != session['user_id']:
        return jsonify({'error': 'No permission'}), 403
    
    CustomField.query.filter_by(item_type=item_type, item_id=item_id).delete()
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True})

# Search across all items
@app.route('/api/search')
def search():
    if 'user_id' not in session:
        return jsonify([])
    
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify([])
    
    results = []
    
    # Search passwords
    passwords = Password.query.filter_by(user_id=session['user_id']).all()
    for p in passwords:
        if (query in p.title.lower() or 
            (p.username and query in p.username.lower()) or
            (p.notes and query in p.notes.lower())):
            results.append({
                'type': 'password',
                'id': p.id,
                'title': p.title,
                'subtitle': p.username
            })
    
    # Search phones
    phones = Phone.query.filter_by(user_id=session['user_id']).all()
    for p in phones:
        if (query in p.title.lower() or 
            (p.phone_number and query in p.phone_number) or
            (p.operator and query in p.operator.lower())):
            results.append({
                'type': 'phone',
                'id': p.id,
                'title': p.title,
                'subtitle': p.phone_number
            })
    
    # Search cards
    cards = Card.query.filter_by(user_id=session['user_id']).all()
    for c in cards:
        if (query in c.title.lower() or 
            (c.card_number and query in c.card_number) or
            (c.notes and query in c.notes.lower())):
            results.append({
                'type': 'card',
                'id': c.id,
                'title': c.title,
                'subtitle': f"**** {c.card_number[-4:]}" if c.card_number else ''
            })
    
    return jsonify(results)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8444))
    app.run(host='0.0.0.0', port=port, debug=False)