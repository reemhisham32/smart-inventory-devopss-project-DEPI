import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from werkzeug.exceptions import HTTPException

try:
    from flask_compress import Compress
except ImportError:  # Optional dependency. The app still works without it.
    Compress = None


db = SQLAlchemy()


# ─────────────────────────────────────────────────────────────
# Application Factory
# ─────────────────────────────────────────────────────────────

def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "sqlite:///inventory.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JSON_SORT_KEYS"] = False

    # Better DB behavior when the app is deployed behind Gunicorn / Kubernetes.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }

    db.init_app(app)

    if Compress:
        Compress(app)

    register_routes(app)
    register_error_handlers(app)

    return app


# ─────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────

class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)

    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    category = db.Column(db.String(80), nullable=False, index=True)

    quantity = db.Column(db.Integer, nullable=False, default=0, index=True)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)

    description = db.Column(db.String(255), nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )

    def stock_status(self):
        if self.quantity == 0:
            return "out_of_stock"
        if self.quantity < 10:
            return "low_stock"
        return "in_stock"

    def to_dict(self):
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "category": self.category,
            "quantity": self.quantity,
            "price": float(self.price),
            "description": self.description,
            "stock_status": self.stock_status(),
            "total_value": round(float(self.price) * self.quantity, 2),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def success_response(data=None, message="success", status_code=200):
    response = {
        "status": "success",
        "message": message,
        "data": data
    }
    return jsonify(response), status_code


def error_response(message, status_code=400, details=None):
    response = {
        "status": "error",
        "message": message
    }

    if details:
        response["details"] = details

    return jsonify(response), status_code


def parse_positive_integer(value, field_name, allow_zero=True):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer")

    if allow_zero and number < 0:
        raise ValueError(f"{field_name} cannot be negative")

    if not allow_zero and number <= 0:
        raise ValueError(f"{field_name} must be greater than zero")

    return number


def parse_positive_decimal(value, field_name):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number")

    if number < 0:
        raise ValueError(f"{field_name} cannot be negative")

    return number


def validate_product_payload(data, partial=False):
    errors = {}

    required_fields = ["sku", "name", "category"]

    if not partial:
        for field in required_fields:
            if not data.get(field):
                errors[field] = f"{field} is required"

    if "sku" in data and not str(data["sku"]).strip():
        errors["sku"] = "sku cannot be empty"

    if "name" in data and not str(data["name"]).strip():
        errors["name"] = "name cannot be empty"

    if "category" in data and not str(data["category"]).strip():
        errors["category"] = "category cannot be empty"

    if "quantity" in data:
        try:
            parse_positive_integer(data["quantity"], "quantity")
        except ValueError as exc:
            errors["quantity"] = str(exc)

    if "price" in data:
        try:
            parse_positive_decimal(data["price"], "price")
        except ValueError as exc:
            errors["price"] = str(exc)

    if errors:
        return errors

    return None


def apply_product_updates(product, data):
    if "sku" in data:
        product.sku = data["sku"].strip()

    if "name" in data:
        product.name = data["name"].strip()

    if "category" in data:
        product.category = data["category"].strip()

    if "quantity" in data:
        product.quantity = parse_positive_integer(data["quantity"], "quantity")

    if "price" in data:
        product.price = parse_positive_decimal(data["price"], "price")

    if "description" in data:
        product.description = data.get("description", "").strip()


def product_query_from_request():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    stock_status = request.args.get("stock_status", "").strip()

    query = Product.query

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                Product.name.ilike(search_pattern),
                Product.sku.ilike(search_pattern),
                Product.category.ilike(search_pattern),
                Product.description.ilike(search_pattern),
            )
        )

    if category:
        query = query.filter(Product.category.ilike(category))

    if stock_status == "out_of_stock":
        query = query.filter(Product.quantity == 0)
    elif stock_status == "low_stock":
        query = query.filter(Product.quantity > 0, Product.quantity < 10)
    elif stock_status == "in_stock":
        query = query.filter(Product.quantity >= 10)
    elif stock_status:
        raise ValueError("Invalid stock_status. Use: out_of_stock, low_stock, or in_stock")

    return query


def apply_sorting(query):
    sort_by = request.args.get("sort_by", "updated_at")
    sort_order = request.args.get("sort_order", "desc")

    allowed_sort_fields = {
        "id": Product.id,
        "sku": Product.sku,
        "name": Product.name,
        "category": Product.category,
        "quantity": Product.quantity,
        "price": Product.price,
        "created_at": Product.created_at,
        "updated_at": Product.updated_at,
    }

    sort_column = allowed_sort_fields.get(sort_by)

    if not sort_column:
        raise ValueError(
            f"Invalid sort_by. Allowed values: {', '.join(allowed_sort_fields.keys())}"
        )

    if sort_order == "asc":
        return query.order_by(sort_column.asc())

    if sort_order == "desc":
        return query.order_by(sort_column.desc())

    raise ValueError("sort_order must be asc or desc")


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

def register_routes(app):

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/products", methods=["GET"])
    def get_products():
        page = request.args.get("page", 1)
        per_page = request.args.get("per_page", 10)

        try:
            page = parse_positive_integer(page, "page", allow_zero=False)
            per_page = parse_positive_integer(per_page, "per_page", allow_zero=False)
            per_page = min(per_page, 100)
            query = product_query_from_request()
            query = apply_sorting(query)
        except ValueError as exc:
            return error_response(str(exc), 400)

        paginated = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )

        result = {
            "items": [product.to_dict() for product in paginated.items],
            "pagination": {
                "page": paginated.page,
                "per_page": paginated.per_page,
                "total_items": paginated.total,
                "total_pages": paginated.pages,
                "has_next": paginated.has_next,
                "has_prev": paginated.has_prev,
            }
        }

        return success_response(result)

    @app.route("/api/products/<int:product_id>", methods=["GET"])
    def get_product(product_id):
        product = db.session.get(Product, product_id)

        if not product:
            return error_response("Product not found", 404)

        return success_response(product.to_dict())

    @app.route("/api/products", methods=["POST"])
    def create_product():
        data = request.get_json(silent=True)

        if not data:
            return error_response("Request body must be valid JSON", 400)

        errors = validate_product_payload(data)

        if errors:
            return error_response("Validation failed", 400, errors)

        existing_product = Product.query.filter_by(
            sku=data["sku"].strip()
        ).first()

        if existing_product:
            return error_response("Product SKU already exists", 409)

        product = Product(
            sku=data["sku"].strip(),
            name=data["name"].strip(),
            category=data["category"].strip(),
            quantity=parse_positive_integer(data.get("quantity", 0), "quantity"),
            price=parse_positive_decimal(data.get("price", 0), "price"),
            description=data.get("description", "").strip()
        )

        db.session.add(product)
        db.session.commit()

        return success_response(product.to_dict(), "Product created successfully", 201)

    @app.route("/api/products/<int:product_id>", methods=["PUT"])
    def update_product(product_id):
        product = db.session.get(Product, product_id)

        if not product:
            return error_response("Product not found", 404)

        data = request.get_json(silent=True)

        if not data:
            return error_response("Request body must be valid JSON", 400)

        errors = validate_product_payload(data, partial=True)

        if errors:
            return error_response("Validation failed", 400, errors)

        if "sku" in data:
            duplicate_product = Product.query.filter(
                Product.sku == data["sku"].strip(),
                Product.id != product_id
            ).first()

            if duplicate_product:
                return error_response("Product SKU already exists", 409)

        apply_product_updates(product, data)

        db.session.commit()

        return success_response(product.to_dict(), "Product updated successfully")

    @app.route("/api/products/<int:product_id>", methods=["DELETE"])
    def delete_product(product_id):
        product = db.session.get(Product, product_id)

        if not product:
            return error_response("Product not found", 404)

        db.session.delete(product)
        db.session.commit()

        return success_response(
            {"id": product_id},
            "Product deleted successfully"
        )

    @app.route("/api/products/<int:product_id>/stock", methods=["PATCH"])
    def update_stock(product_id):
        product = db.session.get(Product, product_id)

        if not product:
            return error_response("Product not found", 404)

        data = request.get_json(silent=True)

        if not data or "quantity" not in data:
            return error_response("quantity is required", 400)

        try:
            product.quantity = parse_positive_integer(data["quantity"], "quantity")
        except ValueError as exc:
            return error_response(str(exc), 400)

        db.session.commit()

        return success_response(product.to_dict(), "Stock updated successfully")

    @app.route("/api/categories", methods=["GET"])
    def get_categories():
        categories = (
            db.session.query(Product.category)
            .distinct()
            .order_by(Product.category.asc())
            .all()
        )

        return success_response([category[0] for category in categories])

    @app.route("/api/categories/summary", methods=["GET"])
    def get_category_summary():
        category_stats = (
            db.session.query(
                Product.category,
                db.func.count(Product.id),
                db.func.coalesce(db.func.sum(Product.quantity), 0),
                db.func.coalesce(db.func.sum(Product.quantity * Product.price), 0),
                db.func.coalesce(db.func.avg(Product.price), 0)
            )
            .group_by(Product.category)
            .order_by(Product.category.asc())
            .all()
        )

        result = [
            {
                "name": category,
                "product_count": product_count,
                "total_quantity": int(total_quantity),
                "total_value": round(float(total_value), 2),
                "average_price": round(float(average_price), 2),
            }
            for category, product_count, total_quantity, total_value, average_price in category_stats
        ]

        return success_response(result)

    @app.route("/api/stats", methods=["GET"])
    def get_stats():
        total_products = Product.query.count()

        total_stock = db.session.query(
            db.func.coalesce(db.func.sum(Product.quantity), 0)
        ).scalar()

        low_stock = Product.query.filter(
            Product.quantity > 0,
            Product.quantity < 10
        ).count()

        out_of_stock = Product.query.filter(
            Product.quantity == 0
        ).count()

        inventory_value = db.session.query(
            db.func.coalesce(db.func.sum(Product.quantity * Product.price), 0)
        ).scalar()

        average_price = db.session.query(
            db.func.coalesce(db.func.avg(Product.price), 0)
        ).scalar()

        category_stats = (
            db.session.query(
                Product.category,
                db.func.count(Product.id),
                db.func.coalesce(db.func.sum(Product.quantity), 0),
                db.func.coalesce(db.func.sum(Product.quantity * Product.price), 0)
            )
            .group_by(Product.category)
            .order_by(Product.category.asc())
            .all()
        )

        result = {
            "total_products": total_products,
            "total_stock": int(total_stock),
            "low_stock_items": low_stock,
            "out_of_stock_items": out_of_stock,
            "inventory_value": round(float(inventory_value), 2),
            "average_price": round(float(average_price), 2),
            "categories": [
                {
                    "name": category,
                    "product_count": product_count,
                    "total_quantity": int(total_quantity),
                    "total_value": round(float(total_value), 2),
                }
                for category, product_count, total_quantity, total_value in category_stats
            ]
        }

        return success_response(result)

    @app.route("/api/reports", methods=["GET"])
    def get_reports():
        low_stock_products = (
            Product.query
            .filter(Product.quantity > 0, Product.quantity < 10)
            .order_by(Product.quantity.asc(), Product.name.asc())
            .limit(10)
            .all()
        )

        out_of_stock_products = (
            Product.query
            .filter(Product.quantity == 0)
            .order_by(Product.name.asc())
            .limit(10)
            .all()
        )

        top_value_products = (
            Product.query
            .order_by((Product.quantity * Product.price).desc())
            .limit(10)
            .all()
        )

        category_summary = (
            db.session.query(
                Product.category,
                db.func.count(Product.id),
                db.func.coalesce(db.func.sum(Product.quantity), 0),
                db.func.coalesce(db.func.sum(Product.quantity * Product.price), 0)
            )
            .group_by(Product.category)
            .order_by(db.func.coalesce(db.func.sum(Product.quantity * Product.price), 0).desc())
            .all()
        )

        result = {
            "low_stock_products": [product.to_dict() for product in low_stock_products],
            "out_of_stock_products": [product.to_dict() for product in out_of_stock_products],
            "top_value_products": [product.to_dict() for product in top_value_products],
            "category_summary": [
                {
                    "name": category,
                    "product_count": product_count,
                    "total_quantity": int(total_quantity),
                    "total_value": round(float(total_value), 2),
                }
                for category, product_count, total_quantity, total_value in category_summary
            ]
        }

        return success_response(result)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "service": "smart-inventory-api",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })


# ─────────────────────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────────────────────

def register_error_handlers(app):

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        return error_response(error.description, error.code)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        db.session.rollback()
        app.logger.exception(error)
        return error_response("Internal server error", 500)


# ─────────────────────────────────────────────────────────────
# Database Initialization
# ─────────────────────────────────────────────────────────────

def seed_database():
    if Product.query.count() > 0:
        return

    demo_products = [
        Product(
            sku="ELEC-LAP-001",
            name="Laptop Pro X",
            category="Electronics",
            quantity=45,
            price=1299.99,
            description="High-performance laptop"
        ),
        Product(
            sku="ELEC-MOU-001",
            name="Wireless Mouse",
            category="Electronics",
            quantity=120,
            price=29.99,
            description="Ergonomic wireless mouse"
        ),
        Product(
            sku="FURN-CHR-001",
            name="Office Chair",
            category="Furniture",
            quantity=8,
            price=349.00,
            description="Adjustable ergonomic chair"
        ),
        Product(
            sku="FURN-LMP-001",
            name="Desk Lamp",
            category="Furniture",
            quantity=3,
            price=49.99,
            description="LED desk lamp"
        ),
        Product(
            sku="STAT-NBK-001",
            name="Notebook A4",
            category="Stationery",
            quantity=500,
            price=2.99,
            description="Ruled notebook"
        ),
        Product(
            sku="STAT-PEN-001",
            name="Ballpoint Pens",
            category="Stationery",
            quantity=7,
            price=1.49,
            description="Box of 12 pens"
        ),
    ]

    db.session.add_all(demo_products)
    db.session.commit()


def initialize_database():
    with app.app_context():
        db.create_all()
        seed_database()


# ─────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────

app = create_app()
initialize_database()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    app.run(host="0.0.0.0", port=port, debug=debug)
