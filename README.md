# 🚁 SwiftPath - Smart Drone Delivery System

> A full-stack intelligent drone delivery platform that simulates real-world autonomous logistics using **Greedy Algorithm for drone selection** and **Dijkstra's Algorithm for shortest path routing**, featuring live order tracking, fleet management, weather-aware delivery estimation, and an interactive Mission Control Dashboard.

---

## 📌 Overview

SwiftPath is a web-based drone delivery management system designed to simulate modern logistics operations. The platform enables customers to place orders from multiple warehouses while automatically selecting the most suitable drone and computing the optimal delivery route.

The project demonstrates practical applications of **Data Structures & Algorithms (DAA)**, **Flask Web Development**, **PostgreSQL**, **Leaflet Maps**, and **real-time tracking** in a production-like logistics environment.

---

# ✨ Features

## 👤 Customer Module

- User Registration & Login
- Place Orders
- Multi-Warehouse Product Selection
- Real-Time Order Tracking
- Interactive Delivery Map
- Live Drone Status
- Weather-aware ETA
- Order Timeline
- Customer Order Cancellation
- Order History

---

## 🚁 Drone Management

- Fleet of Autonomous Delivery Drones
- Battery Monitoring
- Warehouse Docking System
- Automatic Drone Assignment
- Drone Status Tracking
- Delivery Progress Simulation
- Live Telemetry Updates

---

## 📍 Route Optimization

### Greedy Algorithm

Used exclusively for **Drone Selection**

The system evaluates:

- Distance from warehouse
- Battery level
- Delivery feasibility
- Return trip feasibility

The best available drone is selected using a greedy optimization strategy.

---

### Dijkstra Algorithm

Used exclusively for **Shortest Route Optimization**

Features:

- Weighted Graph Representation
- Sparse Flight Corridor Graph
- Priority Queue (`heapq`)
- Shortest Path Computation
- Distance Matrix
- Route Distance Calculation

The optimized route is stored in the database and visualized during live tracking.

---

## 🛰 Live Tracking

- Real-Time Drone Position
- Warehouse Markers
- Animated Drone Movement
- Live Delivery Progress
- Route Visualization
- Delivery Timeline
- Live Weather Status
- ETA Updates

---

## 🌦 Live Weather Integration

Powered by **Open-Meteo API**

Displays

- Current Temperature
- Weather Condition
- Wind Speed
- Humidity
- Visibility
- Drone Flight Status
- Weather Delay Estimation

Weather updates are cached for **15 minutes** to reduce unnecessary API requests.

---

## 📊 Logistics Mission Control Dashboard

Professional Admin Dashboard including:

### KPI Cards

- Total Deliveries
- Active Deliveries
- Completed Deliveries
- Cancelled Deliveries
- Fleet Utilization
- Available Drones
- Average Battery Level
- Average Delivery Time

---

### Fleet Management

- Drone Status
- Assigned Warehouse
- Current Destination
- Docked Drones
- Low Battery Monitoring

---

### Operations Map

- Live Fleet Locations
- Warehouse Locations
- Active Delivery Routes
- Drone Tracking

---

### Mission Event Log

Real-time operational events:

- Drone Assigned
- Delivery Started
- Delivery Completed
- Order Cancelled
- Drone Docked
- Battery Alerts

---

### Analytics Dashboard

Interactive charts including:

- Deliveries Per Hour
- Fleet Status Distribution
- Warehouse Workload
- Battery Distribution
- Delivery Success Rate

---

# 🏗 System Architecture

The project includes a dedicated **System Architecture** page documenting:

- Customer Module
- Authentication
- Warehouse Management
- Drone Fleet
- Greedy Drone Selection
- Dijkstra Route Optimization
- Delivery Tracking
- Database Layer
- Admin Mission Control

---

# 🧠 Algorithms Used

## Greedy Algorithm

Purpose:

Drone Selection

Optimization Factors

- Distance
- Battery
- Delivery Capability
- Return Capability

Time Complexity

```
O(n)
```

---

## Dijkstra Algorithm

Purpose

Shortest Route Optimization

Data Structures

- Weighted Graph
- Priority Queue
- Adjacency List

Time Complexity

```
O((V + E) log V)
```

---

# 🗺 Technology Stack

## Backend

- Python
- Flask
- Flask SQLAlchemy
- Flask Login
- PostgreSQL
- SQLAlchemy ORM

---

## Frontend

- HTML5
- CSS3
- Bootstrap 5
- JavaScript
- Leaflet.js
- Chart.js

---

## Database

- PostgreSQL
- Neon Cloud Database

---

## Deployment

- Render
- Neon PostgreSQL

---

## APIs

- Open-Meteo Weather API

---

# 📂 Project Structure

```
SwiftPath/
│
├── static/
│   ├── css/
│   ├── js/
│   └── images/
│
├── templates/
│
├── models.py
├── routes.py
├── app.py
├── main.py
├── requirements.txt
└── README.md
```

---

# 🚀 Installation

Clone the repository

```bash
git clone https://github.com/hiteshkr25/Swiftpath---Smart-Drone-Delivery.git
```

Go to project

```bash
cd Swiftpath---Smart-Drone-Delivery
```

Install dependencies

```bash
pip install -r requirements.txt
```

Create a `.env`

```env
DATABASE_URL=your_postgresql_connection_string
SESSION_SECRET=your_secret_key
```

Run

```bash
python main.py
```

---

# 🗄 Database

The project supports:

- SQLite (Local Development)
- PostgreSQL (Production)
- Neon Cloud PostgreSQL

Database selection is automatic using the `DATABASE_URL` environment variable.

---

# 📈 Future Enhancements

- AI-based Delivery Prediction
- Multi-Drone Route Optimization
- Traffic-aware Routing
- Battery Consumption Prediction
- Weather Forecast-based Dispatch Planning
- Drone Maintenance Scheduling
- Mobile Application
- Push Notifications

---

# 🎓 Academic Concepts Demonstrated

- Greedy Algorithms
- Dijkstra's Algorithm
- Graph Theory
- Priority Queues
- Haversine Distance
- Shortest Path Problems
- Fleet Optimization
- Database Design
- REST APIs
- Real-Time Systems

---

# 👨‍💻 Developed By

- **Hitesh Kumar**
- **Anjali Sinha**
- **Vasu Singh**
- **Rahul Raj**

---

# 📄 License

This project is licensed under the **MIT License**.

---

# ⭐ If you found this project useful, consider giving it a star!
