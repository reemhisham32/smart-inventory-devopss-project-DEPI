from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ─── Model ────────────────────────────────────────────────────────────────────

class Product(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(120), nullable=False)
    category    = db.Column(db.String(80), nullable=False)
    quantity    = db.Column(db.Integer, nullable=False, default=0)
    price       = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.String(255), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':          self.id,
            'name':        self.name,
            'category':    self.category,
            'quantity':    self.quantity,
            'price':       self.price,
            'description': self.description,
            'created_at':  self.created_at.strftime('%Y-%m-%d %H:%M'),
            'updated_at':  self.updated_at.strftime('%Y-%m-%d %H:%M'),
        }

# ─── UI Route ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

# ─── API Routes ───────────────────────────────────────────────────────────────

@app.route('/api/products', methods=['GET'])
def get_products():
    search   = request.args.get('search', '')
    category = request.args.get('category', '')
    query    = Product.query
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    if category:
        query = query.filter_by(category=category)
    products = query.order_by(Product.updated_at.desc()).all()
    return jsonify([p.to_dict() for p in products])

@app.route('/api/products/<int:pid>', methods=['GET'])
def get_product(pid):
    p = Product.query.get_or_404(pid)
    return jsonify(p.to_dict())

@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.get_json()
    if not data or not data.get('name') or not data.get('category'):
        return jsonify({'error': 'name and category are required'}), 400
    p = Product(
        name        = data['name'],
        category    = data['category'],
        quantity    = data.get('quantity', 0),
        price       = data.get('price', 0.0),
        description = data.get('description', ''),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201

@app.route('/api/products/<int:pid>', methods=['PUT'])
def update_product(pid):
    p    = Product.query.get_or_404(pid)
    data = request.get_json()
    if 'name'        in data: p.name        = data['name']
    if 'category'    in data: p.category    = data['category']
    if 'quantity'    in data: p.quantity    = data['quantity']
    if 'price'       in data: p.price       = data['price']
    if 'description' in data: p.description = data['description']
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(p.to_dict())

@app.route('/api/products/<int:pid>', methods=['DELETE'])
def delete_product(pid):
    p = Product.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return jsonify({'message': f'Product {pid} deleted'})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    total_products  = Product.query.count()
    total_stock     = db.session.query(db.func.sum(Product.quantity)).scalar() or 0
    low_stock       = Product.query.filter(Product.quantity < 10).count()
    categories      = db.session.query(Product.category, db.func.count()).group_by(Product.category).all()
    inventory_value = db.session.query(
        db.func.sum(Product.quantity * Product.price)
    ).scalar() or 0
    return jsonify({
        'total_products':  total_products,
        'total_stock':     total_stock,
        'low_stock_items': low_stock,
        'inventory_value': round(inventory_value, 2),
        'categories':      [{'name': c, 'count': n} for c, n in categories],
    })

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

# ─── Bootstrap ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # seed some demo data if empty
        if Product.query.count() == 0:
            seeds = [
                Product(name='Laptop Pro X',    category='Electronics', quantity=45,  price=1299.99, description='High-performance laptop'),
                Product(name='Wireless Mouse',  category='Electronics', quantity=120, price=29.99,  description='Ergonomic wireless mouse'),
                Product(name='Office Chair',    category='Furniture',   quantity=8,   price=349.00, description='Adjustable ergonomic chair'),
                Product(name='Desk Lamp',       category='Furniture',   quantity=3,   price=49.99,  description='LED desk lamp'),
                Product(name='Notebook A4',     category='Stationery',  quantity=500, price=2.99,   description='Ruled notebook'),
                Product(name='Ballpoint Pens',  category='Stationery',  quantity=7,   price=1.49,   description='Box of 12 pens'),
            ]
            db.session.add_all(seeds)
            db.session.commit()
    app.run(host='0.0.0.0', port=5000, debug=True)
