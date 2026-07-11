import os
import logging
from datetime import datetime, timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

load_dotenv()

# IST = UTC + 5:30
IST_OFFSET = timedelta(hours=5, minutes=30)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

db = SQLAlchemy()

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
# - Falls back to local SQLite when DATABASE_URL is not set (local dev).
# - Uses PostgreSQL automatically when DATABASE_URL is present (e.g. Render deployment).
# - Some providers hand out URLs with the legacy "postgres://" scheme, which
#   SQLAlchemy's psycopg2 dialect no longer accepts; normalize to "postgresql://".
_database_url = os.environ.get("DATABASE_URL", "sqlite:///swiftpath.db")
if _database_url.startswith("postgres://"):
    _database_url = _database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

@app.template_filter('as_ist')
def as_ist(dt):
    """Convert a naive UTC datetime to IST (UTC+5:30) for template display."""
    if dt is None:
        return dt
    return dt + IST_OFFSET

with app.app_context():
    # Import models and routes
    import models
    import routes
    
    # Create all database tables
    db.create_all()

    # Ensure schema has required columns for Drone (handles existing DB from prior schema)
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    if 'drone' in inspector.get_table_names():
        drone_columns = {c['name'] for c in inspector.get_columns('drone')}
        required_columns = {
            'warehouse_id': 'INTEGER',
            'last_battery_update': 'DATETIME',
            'max_weight': 'FLOAT',
        }
        for col_name, col_type in required_columns.items():
            if col_name not in drone_columns:
                logging.info(f"Adding missing column drone.{col_name}")
                db.session.execute(text(f'ALTER TABLE drone ADD COLUMN {col_name} {col_type}'))
        db.session.commit()

    if 'order' in inspector.get_table_names():
        order_columns = {c['name'] for c in inspector.get_columns('order')}
        order_required_columns = {
            'pickup_locations': 'TEXT',
            'optimized_route': 'TEXT',
            'route_total_distance': 'FLOAT',
            'current_location_lat': 'FLOAT',
            'current_location_lng': 'FLOAT',
            'estimated_delivery_time': 'DATETIME',
        }
        for col_name, col_type in order_required_columns.items():
            if col_name not in order_columns:
                logging.info(f"Adding missing column order.{col_name}")
                db.session.execute(text(f'ALTER TABLE "order" ADD COLUMN {col_name} {col_type}'))
        db.session.commit()

    # Create sample warehouses and drones if they don't exist
    from models import Warehouse, Drone, User
    from werkzeug.security import generate_password_hash
    
    # Seed default users
    if User.query.count() == 0:
        admin = User(
            username='admin',
            email='admin@swiftpath.com',
            password_hash=generate_password_hash('admin123'),
            user_type='admin',
            full_name='System Admin',
            phone='1234567890'
        )
        customer = User(
            username='customer',
            email='customer@swiftpath.com',
            password_hash=generate_password_hash('customer123'),
            user_type='customer',
            full_name='Demo Customer',
            phone='0987654321'
        )
        db.session.add(admin)
        db.session.add(customer)
        db.session.flush()
        logging.info("Seeded default users (admin/admin123, customer/customer123)")
    
    # Seed data constants (matching routes.py)
    DRONE_FLEET_DATA = [
        {'name': 'Swift-Alpha',   'warehouse_idx': 0},
        {'name': 'Swift-Beta',    'warehouse_idx': 0},
        {'name': 'Swift-Gamma',   'warehouse_idx': 1},
        {'name': 'Swift-Delta',   'warehouse_idx': 1},
        {'name': 'Swift-Echo',    'warehouse_idx': 2},
        {'name': 'Swift-Foxtrot', 'warehouse_idx': 3},
        {'name': 'Swift-Golf',    'warehouse_idx': 4},
        {'name': 'Swift-Hotel',   'warehouse_idx': 5},
        {'name': 'Swift-India',   'warehouse_idx': 6},
        {'name': 'Swift-Juliet',  'warehouse_idx': 7},
    ]

    # 8 warehouses spread evenly across Dehradun (~2.5-4.7km apart, ~12km max span)
    # so the routing engine always has multiple comparable-distance alternatives
    # to choose between when building a delivery route.
    WAREHOUSE_SEED_DATA = [
        {'name': 'ISBT Hub',                 'location': 'ISBT Dehradun',        'lat': 30.3035, 'lng': 78.0450, 'products': 'Electronics,Mobile Accessories,Chargers'},
        {'name': 'Clock Tower Hub',          'location': 'Clock Tower',          'lat': 30.3223, 'lng': 78.0598, 'products': 'Groceries,Snacks,Daily Essentials'},
        {'name': 'Ballupur Hub',             'location': 'Ballupur Chowk',       'lat': 30.3605, 'lng': 78.0155, 'products': 'Medicines,First Aid,Health Supplements'},
        {'name': 'Rajpur Road Hub',          'location': 'Rajpur Road',          'lat': 30.3350, 'lng': 78.1024, 'products': 'Books,Notebooks,Stationery,Gifts'},
        {'name': 'Prem Nagar Hub',           'location': 'Prem Nagar',           'lat': 30.3350, 'lng': 77.9980, 'products': 'Clothing,Accessories,Shoes'},
        {'name': 'Clement Town Hub',         'location': 'Clement Town',         'lat': 30.3000, 'lng': 78.0044, 'products': 'Sports Equipment,Fitness Gear'},
        {'name': 'Sahastradhara Hub',        'location': 'Sahastradhara Road',   'lat': 30.3764, 'lng': 78.0930, 'products': 'Furniture,Garden Tools,Home Decor'},
        {'name': 'Mussoorie Diversion Hub',  'location': 'Mussoorie Diversion',  'lat': 30.3891, 'lng': 78.0450, 'products': 'Pharmacy,Cosmetics,Wellness Products'},
    ]
    
    # Seed warehouses only if the table is empty - never touch existing data
    if Warehouse.query.count() == 0:
        for w in WAREHOUSE_SEED_DATA:
            warehouse = Warehouse(
                name=w['name'], location=w['location'],
                lat=w['lat'], lng=w['lng'], products=w['products']
            )
            db.session.add(warehouse)
        db.session.flush()
        logging.info("Seeded warehouses - created 8 initial warehouses")

    # Seed drones only if the table is empty - never touch existing data
    if Drone.query.count() == 0:
        warehouses = Warehouse.query.order_by(Warehouse.id).all()
        if warehouses:
            for d in DRONE_FLEET_DATA:
                warehouse = warehouses[d['warehouse_idx']]
                drone = Drone(
                    name=d['name'],
                    status='idle',
                    battery_level=100.0,
                    current_lat=warehouse.lat,
                    current_lng=warehouse.lng,
                    warehouse_id=warehouse.id,
                    last_battery_update=datetime.utcnow()
                )
                db.session.add(drone)
            logging.info("Seeded drone fleet - created 10 initial drones")

    db.session.commit()
    logging.info("Startup seeding complete")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
