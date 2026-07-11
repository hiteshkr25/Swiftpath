import logging
from app import app, db
from models import Warehouse, Drone, DroneEvent, Order, DeliveryRoute

logging.basicConfig(level=logging.INFO)

with app.app_context():
    logging.info("Clearing legacy database tables...")
    
    # Delete dependent tables first to avoid foreign key constraint errors
    db.session.query(DeliveryRoute).delete()
    db.session.query(DroneEvent).delete()
    db.session.query(Order).delete()
    db.session.query(Drone).delete()
    db.session.query(Warehouse).delete()
    db.session.commit()
    logging.info("Deleted all rows from DeliveryRoute, DroneEvent, Order, Drone, Warehouse.")
    
    # Import routes to run seeding
    from routes import seed_database
    seed_database()
    logging.info("Database successfully seeded with standardized 8 warehouses and 10 drones.")
