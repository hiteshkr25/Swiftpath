from flask import render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db
from models import User, Order, Drone, Warehouse, DeliveryRoute, DroneEvent
import json
import heapq
import math
import time
import requests
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.DEBUG)


class WeatherService:
    def __init__(self):
        self.cached_weather = None
        self.last_fetched = 0
        self.cache_duration = 900  # 15 minutes in seconds

    def get_weather(self):
        now = time.time()
        if self.cached_weather and (now - self.last_fetched < self.cache_duration):
            logging.info("Returning cached weather data")
            return self.cached_weather

        # Fetch from Open-Meteo
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 30.3165,
            "longitude": 78.0322,
            "current_weather": True,
            "hourly": "relativehumidity_2m,visibility",
        }
        try:
            logging.info("Fetching live weather from Open-Meteo...")
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                current = data.get("current_weather", {})
                
                # Extract temperature, weather code, wind speed
                temp = current.get("temperature")
                weather_code = current.get("weathercode")
                wind_speed = current.get("windspeed")
                
                hourly = data.get("hourly", {})
                humidities = hourly.get("relativehumidity_2m", [])
                visibilities = hourly.get("visibility", [])
                
                current_time_str = current.get("time") # format "2026-07-10T23:00"
                hourly_times = hourly.get("time", [])
                
                idx = 0
                if current_time_str in hourly_times:
                    idx = hourly_times.index(current_time_str)
                elif len(hourly_times) > 0:
                    try:
                        import datetime as dt_module
                        current_dt = dt_module.datetime.fromisoformat(current_time_str)
                        closest_diff = None
                        for i, t_str in enumerate(hourly_times):
                            t_dt = dt_module.datetime.fromisoformat(t_str)
                            diff = abs((t_dt - current_dt).total_seconds())
                            if closest_diff is None or diff < closest_diff:
                                closest_diff = diff
                                idx = i
                    except Exception:
                        idx = 0

                humidity = humidities[idx] if idx < len(humidities) else 65.0
                visibility_m = visibilities[idx] if idx < len(visibilities) else 10000.0
                visibility_km = round(visibility_m / 1000.0, 1)

                condition = self.map_weather_code(weather_code)
                delay_mins, delay_text = self.get_delay_rules(condition)
                flight_status = self.get_flight_status(condition)

                # Return a clean weather structure
                self.cached_weather = {
                    "temperature": temp,
                    "condition": condition,
                    "wind_speed": wind_speed,
                    "humidity": humidity,
                    "visibility": visibility_km,
                    "flight_status": flight_status,
                    "delay_minutes": delay_mins,
                    "delay_text": delay_text,
                    "weather_code": weather_code,
                    "last_updated": datetime.now().strftime("%I:%M %p"),
                }
                self.last_fetched = now
                return self.cached_weather
            else:
                logging.error(f"Open-Meteo response error: {response.status_code}")
        except Exception as e:
            logging.error(f"Error fetching weather from Open-Meteo: {e}")

        return None

    def map_weather_code(self, code):
        if code in (0, 1):
            return "Clear"
        elif code in (2, 3, 45, 48):
            return "Cloudy"
        elif code in (51, 53, 55, 61, 80):
            return "Light Rain"
        elif code in (63, 81):
            return "Moderate Rain"
        elif code in (65, 82):
            return "Heavy Rain"
        elif code >= 95:
            return "Thunderstorm"
        return "Clear"

    def get_delay_rules(self, condition):
        if condition == "Clear":
            return 0, "0 min"
        elif condition == "Cloudy":
            return 1, "+1 min"
        elif condition == "Light Rain":
            return 3, "+3 min"
        elif condition == "Moderate Rain":
            return 6, "+6 min"
        elif condition == "Heavy Rain":
            return 10, "+10 min"
        elif condition == "Thunderstorm":
            return -1, "Delivery Paused"
        return 0, "0 min"

    def get_flight_status(self, condition):
        if condition in ("Clear", "Cloudy"):
            return "Safe to Fly"
        elif condition in ("Light Rain", "Moderate Rain"):
            return "Fly with Caution"
        elif condition == "Heavy Rain":
            return "Slow Flight"
        elif condition == "Thunderstorm":
            return "Flight Suspended"
        return "Safe to Fly"


weather_service = WeatherService()


# ─── Constants ────────────────────────────────────────────────────────────────

BATTERY_DRAIN_PER_KM = 1.0 / 3.0   # 1% per 3 km of flight
BATTERY_CHARGE_PER_MIN = 5.0        # 5% per minute when charging
LOW_BATTERY_THRESHOLD = 10.0        # trigger mid-flight handoff below this
CHARGE_TARGET = 100.0               # always charge to 100% before going idle
DELIVERY_SIMULATION_MINUTES = 20    # simulated delivery window

# 10-drone fleet data for seeding
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
# to choose between when building a delivery route. Keep in sync with app.py.
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


# ─── Database Seeding ─────────────────────────────────────────────────────────

def seed_database():
    """Seed warehouses and drones if not present."""
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
        logging.info('Seeded default users (admin/admin123, customer/customer123)')

    # Warehouses - seed only if the table is empty, never touch existing data
    if Warehouse.query.count() == 0:
        for w in WAREHOUSE_SEED_DATA:
            warehouse = Warehouse(
                name=w['name'], location=w['location'],
                lat=w['lat'], lng=w['lng'], products=w['products']
            )
            db.session.add(warehouse)
        logging.info('Seeded warehouses - created 8 initial warehouses')

    # Drones - seed only if the table is empty, never touch existing data
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
            logging.info('Seeded drone fleet - created 10 initial drones')

    db.session.commit()


# ─── Battery & Charging Helpers ───────────────────────────────────────────────

def calculate_distance(lat1, lng1, lat2, lng2):
    """Haversine distance in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_battery_usage(distance_km):
    """Battery % consumed for a given distance."""
    return distance_km * BATTERY_DRAIN_PER_KM


def log_drone_event(drone, event_type, message, order=None):
    """Persist a drone event to the database."""
    ev = DroneEvent(
        drone_id=drone.id,
        order_id=order.id if order else None,
        event_type=event_type,
        message=message,
        battery_at_event=round(drone.battery_level, 1)
    )
    db.session.add(ev)


def update_docked_drones():
    """Increase battery for all drones currently in 'docked' state.
    Charges at BATTERY_CHARGE_PER_MIN until 100%, then sets idle."""
    now = datetime.utcnow()
    docked_drones = Drone.query.filter_by(status='docked').all()
    for drone in docked_drones:
        if drone.last_battery_update:
            elapsed_minutes = (now - drone.last_battery_update).total_seconds() / 60.0
            charge_gain = elapsed_minutes * BATTERY_CHARGE_PER_MIN
            drone.battery_level = min(100.0, drone.battery_level + charge_gain)
            drone.last_battery_update = now

            if drone.battery_level >= CHARGE_TARGET:
                drone.battery_level = 100.0
                drone.status = 'idle'
                log_drone_event(drone, 'maintenance_complete',
                                f'{drone.name} fully charged to 100%')
    if docked_drones:
        db.session.commit()


def drain_drone_battery(drone, distance_km, order=None):
    """Drain battery for actual distance flown (1% per 3 km).
    Clamps to 0 — drone physically cannot move below 0%."""
    drain = calculate_battery_usage(distance_km)
    drone.battery_level = max(0.0, drone.battery_level - drain)
    drone.last_battery_update = datetime.utcnow()

    if drone.battery_level <= LOW_BATTERY_THRESHOLD and drone.status == 'delivering':
        drone.status = 'low_battery'
        log_drone_event(drone, 'battery_low_event',
                        f'{drone.name} battery critically low ({drone.battery_level:.1f}%) — handoff needed', order)


def send_drone_to_warehouse(drone):
    """Send drone back to its assigned warehouse. Always called after delivery or handoff."""
    if drone.warehouse:
        drone.status = 'docked'
        drone.current_lat = drone.warehouse.lat
        drone.current_lng = drone.warehouse.lng
        drone.last_battery_update = datetime.utcnow()
        log_drone_event(drone, 'drone_docked',
                        f'{drone.name} returned to {drone.warehouse.name} ({drone.battery_level:.1f}%)')


def find_handoff_drone(cur_lat, cur_lng, order, progress_pct):
    """Find an idle drone that can complete the remaining delivery route.
    Prioritises: highest battery → nearest to current position."""
    remaining_dist_to_delivery = (order.route_total_distance or 0) * (1.0 - progress_pct / 100.0)

    candidates = Drone.query.filter(
        Drone.status == 'idle',
        Drone.id != order.drone_id
    ).all()

    if not candidates:
        return None

    valid = []
    for d in candidates:
        return_dist = 0.0
        if d.warehouse:
            return_dist = calculate_distance(order.delivery_lat, order.delivery_lng, d.warehouse.lat, d.warehouse.lng)
        total_dist = remaining_dist_to_delivery + return_dist
        battery_needed = calculate_battery_usage(total_dist)
        if d.battery_level >= battery_needed:
            valid.append(d)

    if not valid:
        return None

    valid.sort(key=lambda d: (
        -d.battery_level,
        calculate_distance(d.current_lat or cur_lat, d.current_lng or cur_lng, cur_lat, cur_lng)
    ))
    return valid[0]


# ─── Drone Assignment (Greedy + Battery-Aware) ────────────────────────────────

def assign_drone_based_on_battery(delivery_lat, delivery_lng, warehouses):
    """
    Greedy drone assignment with full round-trip battery check.
    Priority order:
      1. Maximum battery percentage (highest battery first)
      2. Nearest to the first warehouse
      3. Must be idle and have enough battery for full round trip:
         drone → warehouses → delivery → drone's home warehouse
    Returns the selected Drone or None.
    """
    update_docked_drones()

    candidates = Drone.query.filter_by(status='idle').all()
    if not candidates:
        return None

    first_wh = warehouses[0] if warehouses else {'lat': delivery_lat, 'lng': delivery_lng}
    valid = []

    for drone in candidates:
        drone_lat = drone.current_lat or 30.3165
        drone_lng = drone.current_lng or 78.0322

        # Full round trip: drone → warehouses → delivery → drone's home warehouse
        trip_points = [(drone_lat, drone_lng)]
        for wh in warehouses:
            trip_points.append((wh['lat'], wh['lng']))
        trip_points.append((delivery_lat, delivery_lng))

        # Add return leg to the drone's assigned warehouse
        if drone.warehouse:
            trip_points.append((drone.warehouse.lat, drone.warehouse.lng))

        total_dist = sum(
            calculate_distance(trip_points[i][0], trip_points[i][1],
                               trip_points[i + 1][0], trip_points[i + 1][1])
            for i in range(len(trip_points) - 1)
        )
        battery_needed = calculate_battery_usage(total_dist)

        # Only accept drone if it can complete the full round trip
        if drone.battery_level >= battery_needed:
            dist_to_first_wh = calculate_distance(drone_lat, drone_lng,
                                                  first_wh['lat'], first_wh['lng'])
            valid.append((dist_to_first_wh, drone))

    if not valid:
        return None

    # Priority: maximum battery percentage first, nearest to first warehouse second
    valid.sort(key=lambda x: (-x[1].battery_level, x[0]))
    return valid[0][1]


# ─── Route Optimisation (Dijkstra / Nearest-Neighbour) ────────────────────────

def get_warehouse_graph():
    """
    Constructs and returns the sparse warehouse network graph.
    Warehouse names are keys; values are lists of (neighbor_name, dist_weight).
    """
    warehouses = Warehouse.query.all()
    wh_by_name = {w.name: w for w in warehouses}
    
    graph = {name: [] for name in wh_by_name}
    
    # Adjacency list definition representing valid flight corridors (sparse graph)
    connections = [
        ('ISBT Hub', 'Clock Tower Hub'),
        ('ISBT Hub', 'Clement Town Hub'),
        ('Clock Tower Hub', 'Ballupur Hub'),
        ('Clock Tower Hub', 'Rajpur Road Hub'),
        ('Ballupur Hub', 'Prem Nagar Hub'),
        ('Ballupur Hub', 'Mussoorie Diversion Hub'),
        ('Rajpur Road Hub', 'Sahastradhara Hub'),
        ('Sahastradhara Hub', 'Mussoorie Diversion Hub')
    ]
    
    for u, v in connections:
        if u in wh_by_name and v in wh_by_name:
            wu = wh_by_name[u]
            wv = wh_by_name[v]
            dist = calculate_distance(wu.lat, wu.lng, wv.lat, wv.lng)
            graph[wu.name].append((wv.name, dist))
            graph[wv.name].append((wu.name, dist))
            
    return graph


def dijkstra_shortest_path(graph, start, end):
    """
    Genuine Dijkstra implementation to compute the shortest path between
    start and end warehouses using heapq priority queue.
    """
    distances = {node: float('inf') for node in graph}
    previous = {node: None for node in graph}
    visited = set()
    
    distances[start] = 0.0
    pq = [(0.0, start)]
    
    while pq:
        curr_dist, u = heapq.heappop(pq)
        
        if u == end:
            break
            
        if u in visited:
            continue
        visited.add(u)
        
        for v, weight in graph.get(u, []):
            if v not in visited:
                alt = curr_dist + weight
                if alt < distances[v]:
                    distances[v] = alt
                    previous[v] = u
                    heapq.heappush(pq, (alt, v))
                    
    # Reconstruct path
    path = []
    curr = end
    if distances[end] != float('inf'):
        while curr is not None:
            path.append(curr)
            curr = previous[curr]
        path.reverse()
        
    return path, distances[end]


def find_optimal_warehouse_order(graph, warehouses):
    """
    Finds the permutation of warehouses that minimizes the total Dijkstra path distance.
    Returns the ordered list of warehouses.
    """
    if len(warehouses) <= 1:
        return warehouses
        
    import itertools
    best_order = None
    min_total_dist = float('inf')
    
    # Try all permutations of the warehouses to visit them in the optimal order
    for perm in itertools.permutations(warehouses):
        total_dist = 0.0
        possible = True
        for i in range(len(perm) - 1):
            _, dist = dijkstra_shortest_path(graph, perm[i]['name'], perm[i + 1]['name'])
            if dist == float('inf'):
                possible = False
                break
            total_dist += dist
        if possible and total_dist < min_total_dist:
            min_total_dist = total_dist
            best_order = perm
            
    return list(best_order) if best_order else warehouses


def calculate_optimized_route(warehouses, delivery_location):
    """
    Calculates the shortest route visiting all required warehouses using Dijkstra,
    optimizing the visitation sequence, and ending at the delivery location.
    """
    if not warehouses:
        return [delivery_location], 0.0

    # Get the sparse warehouse graph
    graph = get_warehouse_graph()
    
    # 1. Find the optimal sequence to visit the required warehouses
    ordered_warehouses = find_optimal_warehouse_order(graph, warehouses)
    warehouse_names = [w['name'] for w in ordered_warehouses]
    
    # 2. Chain the Dijkstra paths between the ordered warehouses, skipping already visited ones
    full_path_names = []
    total_dist = 0.0
    
    visited_required = set()
    
    # Start with the first warehouse in the optimized order
    if warehouse_names:
        current_node = warehouse_names[0]
        full_path_names.append(current_node)
        visited_required.add(current_node)
        
        i = 1
        while i < len(warehouse_names):
            next_target = warehouse_names[i]
            
            # If this target was already visited as an intermediate node, skip explicit routing to it
            if next_target in visited_required:
                i += 1
                continue
                
            path, dist = dijkstra_shortest_path(graph, current_node, next_target)
            
            if not path:
                # Fallback if no path exists
                full_path_names.append(next_target)
                curr_lat_lng = next(w for w in warehouses if w['name'] == current_node)
                next_lat_lng = next(w for w in warehouses if w['name'] == next_target)
                total_dist += calculate_distance(
                    curr_lat_lng['lat'], curr_lat_lng['lng'],
                    next_lat_lng['lat'], next_lat_lng['lng']
                )
                current_node = next_target
                visited_required.add(next_target)
            else:
                # Append path elements (excluding the first node to prevent duplicate consecutive nodes)
                for node in path[1:]:
                    full_path_names.append(node)
                    if node in warehouse_names:
                        visited_required.add(node)
                total_dist += dist
                current_node = next_target
            i += 1

    # 3. Clean up any accidental consecutive duplicate nodes
    cleaned_path_names = []
    for name in full_path_names:
        if not cleaned_path_names or cleaned_path_names[-1] != name:
            cleaned_path_names.append(name)
            
    # 4. Map the list of names back to coordinate dicts
    all_whs = Warehouse.query.all()
    wh_dict = {w.name: {'id': w.id, 'lat': w.lat, 'lng': w.lng, 'name': w.name} for w in all_whs}
    
    route = []
    for name in cleaned_path_names:
        if name in wh_dict:
            route.append(wh_dict[name])
            
    # 5. Append the customer destination and add the distance from the last warehouse to the destination
    if route:
        last = route[-1]
        total_dist += calculate_distance(
            last['lat'], last['lng'],
            delivery_location['lat'], delivery_location['lng']
        )
    route.append(delivery_location)
    
    return route, round(total_dist, 2)



# ─── Delivery Simulation ──────────────────────────────────────────────────────

def simulate_drone_progress(order):
    """Simulate drone movement and battery drain based on elapsed time.

    Battery logic:
    - Drained based on actual distance covered since last known position (1% / 3km).
    - If battery hits 0%: drone stops physically. Handoff is attempted.
    - A handoff drone continues from the current position, preserving route progress.

    Post-delivery:
    - Drone always returns to its assigned warehouse and docks to charge to 100%.
    """
    if not order.confirmed_at:
        return {'lat': 0, 'lng': 0, 'progress': 0}

    total_time = DELIVERY_SIMULATION_MINUTES * 60
    elapsed = (datetime.utcnow() - order.confirmed_at).total_seconds()
    progress_pct = min((elapsed / total_time) * 100, 100)

    route = order.get_optimized_route_list()
    if not route:
        return {'lat': 0, 'lng': 0, 'progress': 0}

    total_segs = len(route) - 1
    if total_segs == 0:
        return {'lat': route[0]['lat'], 'lng': route[0]['lng'], 'progress': progress_pct}

    seg_prog = (progress_pct / 100) * total_segs
    cur_seg  = min(int(seg_prog), total_segs - 1)
    seg_frac = seg_prog - cur_seg

    start_pt = route[cur_seg]
    end_pt   = route[cur_seg + 1]
    cur_lat  = start_pt['lat'] + (end_pt['lat'] - start_pt['lat']) * seg_frac
    cur_lng  = start_pt['lng'] + (end_pt['lng'] - start_pt['lng']) * seg_frac

    # ── Delivery completed ────────────────────────────────────────────────────
    if progress_pct >= 100 and order.status != 'delivered':
        order.status = 'delivered'
        order.delivered_at = datetime.utcnow()

        drone = order.assigned_drone
        if drone:
            drone.current_lat = order.delivery_lat
            drone.current_lng = order.delivery_lng
            log_drone_event(drone, 'delivery_completed',
                            f'{drone.name} completed delivery for order #{order.id}', order)
            # Always return to warehouse and charge/dock
            send_drone_to_warehouse(drone)

        db.session.commit()

    # ── Order just left the warehouse (confirmed → in_transit) ────────────────
    elif progress_pct > 0 and order.status == 'confirmed':
        order.status = 'in_transit'
        if order.assigned_drone:
            order.assigned_drone.status = 'delivering'
            order.current_location_lat = cur_lat
            order.current_location_lng = cur_lng
        db.session.commit()

    # ── En route: drain battery based on distance actually covered ────────────
    elif order.status == 'in_transit' and order.assigned_drone:
        drone = order.assigned_drone

        # Battery at 0% — drone physically cannot move → attempt handoff
        if drone.battery_level <= 0:
            rescue = find_handoff_drone(cur_lat, cur_lng, order, progress_pct)
            if rescue:
                original = drone
                # Adjust confirmed_at so simulation continues from current progress
                order.drone_id = rescue.id
                elapsed_so_far = total_time * (progress_pct / 100.0)
                order.confirmed_at = datetime.utcnow() - timedelta(seconds=elapsed_so_far)
                rescue.status = 'delivering'
                rescue.current_lat = cur_lat
                rescue.current_lng = cur_lng
                log_drone_event(rescue, 'handoff_received',
                                f'{rescue.name} took over order #{order.id} at {progress_pct:.0f}% '
                                f'(battery: {rescue.battery_level:.1f}%)', order)
                log_drone_event(original, 'handoff_sent',
                                f'{original.name} handed off order #{order.id} — battery depleted', order)
                send_drone_to_warehouse(original)
            else:
                # No rescue available — log once, keep order paused
                if drone.status != 'low_battery':
                    drone.status = 'low_battery'
                    log_drone_event(drone, 'delivery_stalled',
                                    f'Order #{order.id} stalled — no rescue drone available', order)
            db.session.commit()
        else:
            # Normal flight: drain battery proportional to actual distance traveled
            prev_lat = order.current_location_lat or cur_lat
            prev_lng = order.current_location_lng or cur_lng
            dist_this_tick = calculate_distance(prev_lat, prev_lng, cur_lat, cur_lng)

            if dist_this_tick > 0:
                drain_drone_battery(drone, dist_this_tick, order)

                # Low battery during flight → try handoff immediately
                if drone.battery_level <= LOW_BATTERY_THRESHOLD:
                    rescue = find_handoff_drone(cur_lat, cur_lng, order, progress_pct)
                    if rescue:
                        original = drone
                        order.drone_id = rescue.id
                        elapsed_so_far = total_time * (progress_pct / 100.0)
                        order.confirmed_at = datetime.utcnow() - timedelta(seconds=elapsed_so_far)
                        rescue.status = 'delivering'
                        rescue.current_lat = cur_lat
                        rescue.current_lng = cur_lng
                        log_drone_event(rescue, 'handoff_received',
                                        f'{rescue.name} took over order #{order.id} at {progress_pct:.0f}% '
                                        f'(battery: {rescue.battery_level:.1f}%)', order)
                        log_drone_event(original, 'handoff_sent',
                                        f'{original.name} handed off — battery {original.battery_level:.1f}%', order)
                        send_drone_to_warehouse(original)

            order.current_location_lat = cur_lat
            order.current_location_lng = cur_lng
            db.session.commit()

    return {'lat': cur_lat, 'lng': cur_lng, 'progress': round(progress_pct, 1)}


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        user_type = request.form.get('user_type', 'customer')

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('register.html')
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return render_template('register.html')

        user = User(
            username=username, email=email,
            password_hash=generate_password_hash(password),
            full_name=full_name, phone=phone, user_type=user_type
        )
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Login successful!', 'success')
            if user.user_type in ('admin', 'vendor'):
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('customer_dashboard'))

        flash('Invalid username or password', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/customer_dashboard')
@login_required
def customer_dashboard():
    if current_user.user_type != 'customer':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    recent_orders = Order.query.filter_by(customer_id=current_user.id)\
        .order_by(Order.created_at.desc()).limit(5).all()
    
    # Update order statuses by running simulation
    for order in recent_orders:
        if order.status in ['confirmed', 'in_transit', 'assigned']:
            simulate_drone_progress(order)
    
    all_drones = Drone.query.all()
    return render_template('customer_dashboard.html', orders=recent_orders, drones=all_drones)


@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.user_type not in ('admin', 'vendor'):
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    update_docked_drones()

    all_orders = Order.query.order_by(Order.created_at.desc()).all()
    all_drones = Drone.query.all()

    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    idle_drones = Drone.query.filter_by(status='idle').count()
    docked_drones = Drone.query.filter_by(status='docked').count()
    delivering_drones = Drone.query.filter(
        Drone.status.in_(['delivering', 'picking_up', 'assigned'])
    ).count()
    low_battery_drones = Drone.query.filter_by(status='low_battery').count()

    stats = {
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'active_drones': idle_drones,
        'total_drones': len(all_drones),
        'docked_drones': docked_drones,
        'delivering_drones': delivering_drones,
        'low_battery_drones': low_battery_drones,
    }

    return render_template('admin_dashboard.html',
                           orders=all_orders, drones=all_drones,
                           stats=stats)


@app.route('/place_order', methods=['GET', 'POST'])
@login_required
def place_order():
    if current_user.user_type != 'customer':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        selected_items = request.form.getlist('items')
        # total_weight = float(request.form.get('total_weight', 0))
        # order_type = request.form.get('order_type', 'normal')
        total_weight = 0.0  # Default weight
        order_type = 'normal'  # Default type
        delivery_lat = float(request.form.get('delivery_lat'))
        delivery_lng = float(request.form.get('delivery_lng'))
        delivery_address = request.form.get('delivery_address', '')

        items_data = []
        required_warehouses = set()
        for item in selected_items:
            warehouse_id, product_name = item.split(':')
            items_data.append({'warehouse_id': int(warehouse_id), 'product': product_name, 'quantity': 1})
            required_warehouses.add(int(warehouse_id))

        warehouse_locations = []
        for wid in required_warehouses:
            wh = Warehouse.query.get(wid)
            warehouse_locations.append({'id': wh.id, 'lat': wh.lat, 'lng': wh.lng, 'name': wh.name})

        delivery_location = {'id': 'delivery', 'lat': delivery_lat, 'lng': delivery_lng, 'name': 'Delivery Location'}

        # Optimise route
        optimized_route, total_dist = calculate_optimized_route(warehouse_locations, delivery_location)

        # Battery-aware greedy drone assignment
        selected_drone = assign_drone_based_on_battery(delivery_lat, delivery_lng, warehouse_locations)
        if not selected_drone:
            flash('No drones available with sufficient battery right now. Please try again shortly.', 'error')
            return redirect(url_for('place_order'))

        order = Order(
            customer_id=current_user.id,
            drone_id=selected_drone.id,
            items=json.dumps(items_data),
            total_weight=total_weight,
            order_type=order_type,
            pickup_locations=json.dumps(warehouse_locations),
            delivery_lat=delivery_lat,
            delivery_lng=delivery_lng,
            delivery_address=delivery_address,
            optimized_route=json.dumps(optimized_route),
            route_total_distance=total_dist,
            status='confirmed',
            confirmed_at=datetime.utcnow(),
            estimated_delivery_time=datetime.utcnow() + timedelta(minutes=20)
        )

        selected_drone.status = 'assigned'
        log_drone_event(selected_drone, 'order_assigned',
                        f'{selected_drone.name} assigned to new order (battery: {selected_drone.battery_level:.1f}%, trip: {total_dist:.1f} km)', order)

        db.session.add(order)
        db.session.commit()

        flash('Order placed successfully! Your drone is on the way.', 'success')
        return redirect(url_for('track_order', order_id=order.id))

    warehouses = Warehouse.query.all()
    return render_template('place_order.html', warehouses=warehouses)


@app.route('/track_order/<int:order_id>')
@login_required
def track_order(order_id):
    order = Order.query.get_or_404(order_id)
    if current_user.user_type == 'customer' and order.customer_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('customer_dashboard'))
    return render_template('track_order.html', order=order)


# ─── APIs ─────────────────────────────────────────────────────────────────────

@app.route('/api/order_status/<int:order_id>')
@login_required
def api_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    if current_user.user_type == 'customer' and order.customer_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    route = order.get_optimized_route_list()
    current_progress = simulate_drone_progress(order)

    drone = order.assigned_drone
    recent_events = []
    if drone:
        evts = DroneEvent.query.filter_by(drone_id=drone.id)\
            .order_by(DroneEvent.created_at.desc()).limit(5).all()
        recent_events = [{
            'type': e.event_type,
            'message': e.message,
            'battery': e.battery_at_event,
            'time': e.created_at.isoformat() + 'Z'
        } for e in evts]

    # Dehradun standard warehouses
    DEHRADUN_WAREHOUSES = [
        { 'id': 1, 'name': 'ISBT Hub', 'lat': 30.2878, 'lng': 77.9972 },
        { 'id': 2, 'name': 'Clock Tower Hub', 'lat': 30.3244, 'lng': 78.0411 },
        { 'id': 3, 'name': 'Ballupur Hub', 'lat': 30.3340, 'lng': 78.0080 },
        { 'id': 4, 'name': 'Rajpur Road Hub', 'lat': 30.3650, 'lng': 78.0620 },
        { 'id': 5, 'name': 'Prem Nagar Hub', 'lat': 30.3360, 'lng': 77.9580 },
        { 'id': 6, 'name': 'Clement Town Hub', 'lat': 30.2670, 'lng': 78.0210 },
        { 'id': 7, 'name': 'Sahastradhara Hub', 'lat': 30.3630, 'lng': 78.0790 },
        { 'id': 8, 'name': 'Mussoorie Diversion Hub', 'lat': 30.3891, 'lng': 78.0450 },
    ]

    unique_nodes = list(DEHRADUN_WAREHOUSES)
    unique_nodes.append({
        'id': 'delivery',
        'name': 'Customer Destination',
        'lat': order.delivery_lat or 30.3165,
        'lng': order.delivery_lng or 78.0322
    })
    
    # Pre-calculate pairwise distances using routing engine's formula
    distance_matrix = {}
    n_nodes = len(unique_nodes)
    for i in range(n_nodes):
        for j in range(i, n_nodes):
            n1 = unique_nodes[i]
            n2 = unique_nodes[j]
            d = calculate_distance(n1['lat'], n1['lng'], n2['lat'], n2['lng'])
            key1 = f"{n1['name']}-{n2['name']}"
            key2 = f"{n2['name']}-{n1['name']}"
            distance_matrix[key1] = d
            distance_matrix[key2] = d

    return jsonify({
        'order_id': order.id,
        'status': order.status,
        'current_location': {'lat': current_progress['lat'], 'lng': current_progress['lng']},
        'route': route,
        'progress_percentage': current_progress['progress'],
        'estimated_delivery': (order.estimated_delivery_time.isoformat() + 'Z') if order.estimated_delivery_time else None,
        'drone_battery': round(drone.battery_level, 1) if drone else 0,
        'drone_status': drone.status if drone else 'unknown',
        'drone_name': drone.name if drone else 'N/A',
        'route_total_distance': order.route_total_distance or 0,
        'recent_events': recent_events,
        'distance_matrix': distance_matrix,
    })


@app.route('/api/weather')
@login_required
def api_weather():
    w = weather_service.get_weather()
    if not w:
        return jsonify({
            'error': True,
            'message': 'Weather data temporarily unavailable',
            'condition': 'Unavailable',
            'weather_code': None,
            'temperature': 'N/A',
            'humidity': 'N/A',
            'wind_speed': 'N/A',
            'visibility': 'N/A',
            'delay_minutes': 0,
            'last_updated': 'N/A'
        })
    return jsonify({
        'condition': w.get('condition'),
        'weather_code': w.get('weather_code'),
        'temperature': w.get('temperature'),
        'humidity': w.get('humidity'),
        'wind_speed': w.get('wind_speed'),
        'visibility': w.get('visibility'),
        'delay_minutes': w.get('delay_minutes'),
        'last_updated': w.get('last_updated')
    })


@app.route('/api/drones')
@login_required
def api_drones():
    update_docked_drones()
    drones = Drone.query.all()
    return jsonify([d.to_dict() for d in drones])


@app.route('/api/drone_fleet')
@login_required
def api_drone_fleet():
    if current_user.user_type not in ('admin', 'vendor'):
        return jsonify({'error': 'Access denied'}), 403
    update_docked_drones()
    drones = Drone.query.all()
    fleet = []
    for d in drones:
        last_events = DroneEvent.query.filter_by(drone_id=d.id)\
            .order_by(DroneEvent.created_at.desc()).limit(3).all()
        fleet.append({
            **d.to_dict(),
            'station_name': d.warehouse.name if d.warehouse else 'N/A',
            'recent_events': [{'type': e.event_type, 'message': e.message,
                                'battery': e.battery_at_event,
                                'time': e.created_at.isoformat() + 'Z'} for e in last_events]
        })
    return jsonify(fleet)


@app.route('/api/approve_order/<int:order_id>', methods=['POST'])
@login_required
def api_approve_order(order_id):
    if current_user.user_type not in ('admin', 'vendor'):
        return jsonify({'error': 'Access denied'}), 403
    order = Order.query.get_or_404(order_id)
    order.status = 'confirmed'
    order.confirmed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Order approved successfully'})


def cancel_order_shared(order, initiator_name):
    """Core order cancellation logic, releasing the assigned drone if any."""
    order.status = 'cancelled'
    if order.assigned_drone:
        drone = order.assigned_drone
        send_drone_to_warehouse(drone)
        # Log event with ❌ prefix as requested
        log_drone_event(
            drone, 
            'delivery_cancelled', 
            f'❌ Order #{order.id} Cancelled by {initiator_name}', 
            order
        )
    db.session.commit()


@app.route('/api/deny_order/<int:order_id>', methods=['POST'])
@login_required
def api_deny_order(order_id):
    if current_user.user_type not in ('admin', 'vendor'):
        return jsonify({'error': 'Access denied'}), 403
    order = Order.query.get_or_404(order_id)
    cancel_order_shared(order, f"admin {current_user.username}")
    return jsonify({'success': True, 'message': 'Order denied successfully'})


@app.route('/api/cancel_order/<int:order_id>', methods=['POST'])
@login_required
def api_cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    # Customer can cancel their own order; admin/vendor can also cancel
    if current_user.user_type not in ('admin', 'vendor') and order.customer_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    if order.status in ('delivered', 'cancelled', 'failed', 'returned'):
        return jsonify({'error': f'Order cannot be cancelled in state: {order.status}'}), 400

    cancel_order_shared(order, f"customer {current_user.username}")
    return jsonify({'success': True, 'message': 'Order cancelled successfully'})


@app.route('/architecture')
def system_architecture():
    return render_template('system_architecture.html')


# Register seed to run on first request
@app.before_request
def ensure_seeded():
    if not hasattr(app, '_seeded'):
        seed_database()
        app._seeded = True
