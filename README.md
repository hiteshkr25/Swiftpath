# SwiftPath - Smart Drone Delivery System

SwiftPath is an enterprise-grade drone logistics and fleet simulation platform designed to optimize multi-hub package deliveries. Built using Flask, Leaflet, and Chart.js, the project operates a two-tier optimization workflow to dispatch and route autonomous drones across a network of regional hubs.

---

## 🗺 System Architecture Overview

The platform is designed around a modular pipeline that handles order placement, fleet dispatching, spatial routing, and live telemetry tracking:

1. **Customer Portal**: Clients configure shopping baskets, map delivery grid points, and track live status.
2. **Authentication Flow**: Gated access control separating operators (admins) and customers.
3. **Order Processing Engine**: Validates payload weights against carrying capacities of the active fleet.
4. **Greedy Drone Selection**: Resolves fleet dispatch by sorting available drones. Evaluates battery ranges and proximities to select the optimal drone.
5. **Dijkstra Route Optimization**: Computes shortest-path traversals among the 8 standardized warehouses ending at the delivery point.
6. **Warehouse Management Grid**: Coordinates 8 standardized regional hubs around Dehradun coordinates.
7. **Database Layer**: SQLite local development fallback with production PostgreSQL support via SQLAlchemy.
8. **Delivery Simulation**: Dynamic linear coordinates interpolator tracking drone status and battery decay (1% per 3km).
9. **Logistics Mission Control Dashboard**: Telemetry dashboard tracking fleet states, event logs, and Chart.js analytics graphs.

### 📊 Algorithmic Highlights (DAA Focus)

- **Fleet Dispatch Heuristic**: Greedy approach prioritizing battery limits and Euclidean distances ($O(N)$).
- **Route Path Planning**: Dijkstra's Single-Source Shortest Path algorithm on a mesh network ($O(V \log V + E)$).

---

## 🛠 Setup & Running Locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application:
   ```bash
   python main.py
   ```
3. Open in your browser: `http://localhost:5000`

---

## 📈 System Architecture Documentation Page

The application includes a built-in interactive **System Architecture & Telemetry Data Flow** page. It features an interactive SVG data flow diagram, detailed summaries of the core system modules, and placement interview talking points.

Access it directly at:
```
http://localhost:5000/architecture
```
