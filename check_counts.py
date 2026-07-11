from app import app, db
from models import Warehouse, Drone
with app.app_context():
    print('Warehouses:', Warehouse.query.count())
    print('Drones:', Drone.query.count())