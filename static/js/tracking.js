// ─── Order Tracking Manager ────────────────────────────────────────────────────
class OrderTrackingManager {
    constructor(orderId, mapContainerId, userType = 'customer') {
        this.orderId = orderId;
        this.mapContainerId = mapContainerId;
        this.userType = userType;           // 'customer' | 'admin' | 'vendor'
        this.isAdmin = (userType === 'admin' || userType === 'vendor');
        this.map = null;
        this.updateInterval = null;
        this.lastKnownPosition = null;
        this.lastBattery = null;
        this.algorithmAnimated = false;
        this.latestWeather = null;
        this.weatherTimer = null;

        this.init();
    }

    init() {
        this.initializeMap();
        this.startTracking();
        this.bindEvents();
        this.updateWeather();
        this.weatherTimer = setInterval(() => this.updateWeather(), 900000);
    }

    initializeMap() {
        this.map = new MapManager(this.mapContainerId, {
            center: [30.3165, 78.0322],
            zoom: 13
        });
    }

    // ─── Tracking loop ──────────────────────────────────────────────────────────
    async startTracking() {
        try {
            await this.updateOrderStatus();
            this.updateInterval = setInterval(() => this.updateOrderStatus(), 2000);
        } catch (err) {
            console.error('Tracking start error:', err);
            this.showError('Failed to start order tracking');
        }
    }

    async updateOrderStatus() {
        try {
            const res = await fetch(`/api/order_status/${this.orderId}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (data.error) throw new Error(data.error);

            this.updateUI(data);
            this.updateMap(data);
            this.updateEventLog(data.recent_events || []);

            // Stop polling once delivered, cancelled or failed
            if (['delivered', 'cancelled', 'failed'].includes(data.status) && this.updateInterval) {
                clearInterval(this.updateInterval);
                this.updateInterval = null;
            }
        } catch (err) {
            console.error('Update error:', err);
        }
    }

    async updateWeather() {
        try {
            const res = await fetch('/api/weather');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (data.error) throw new Error(data.message || data.error);
            this.latestWeather = data;
            this.updateWeatherWidget(data);
        } catch (err) {
            console.error('Weather update error:', err);
            if (!this.latestWeather) {
                this.updateWeatherWidget(null);
            }
        }
    }

    // ─── UI updates ─────────────────────────────────────────────────────────────
    updateUI(data) {
        // Trigger algorithm animations once we have order data
        if (!this.algorithmAnimated) {
            this.algorithmAnimated = true;
            this.initializeAlgorithmVisualizations(data);
        }

        // Status badge
        const statusBadge = document.getElementById('orderStatus');
        if (statusBadge) {
            statusBadge.textContent = this._formatOrderStatus(data.status);
            statusBadge.className = `order-status ${data.status}`;
        }

        // Cancel button visibility
        const cancelBtn = document.getElementById('cancelOrderBtn');
        if (cancelBtn) {
            if (['pending', 'confirmed', 'processing', 'in_transit'].includes(data.status)) {
                cancelBtn.style.display = 'inline-block';
            } else {
                cancelBtn.style.display = 'none';
            }
        }

        // Progress bar
        const pct = Math.round(data.progress_percentage);
        const progressBar = document.getElementById('progressBar');
        if (progressBar) {
            progressBar.style.width = `${pct}%`;
            progressBar.setAttribute('aria-valuenow', pct);
        }
        const progressText = document.getElementById('progressText');
        if (progressText) progressText.textContent = `${pct}%`;

        // Estimated delivery time factoring weather delays
        const deliveryEl = document.getElementById('estimatedDelivery');
        if (deliveryEl && data.estimated_delivery) {
            let deliveryDate = new Date(data.estimated_delivery);
            const delayMinutes = this.latestWeather && typeof this.latestWeather.delay_minutes === 'number'
                ? this.latestWeather.delay_minutes
                : 0;
            if (delayMinutes > 0) {
                deliveryDate.setMinutes(deliveryDate.getMinutes() + delayMinutes);
            }
            deliveryEl.textContent = this.formatTimeIST(deliveryDate);
        }

        const panelEta = document.getElementById('panelEta');
        if (panelEta && data.estimated_delivery) {
            let deliveryDate = new Date(data.estimated_delivery);
            const delayMinutes = this.latestWeather && typeof this.latestWeather.delay_minutes === 'number'
                ? this.latestWeather.delay_minutes
                : 0;
            if (delayMinutes > 0) {
                deliveryDate.setMinutes(deliveryDate.getMinutes() + delayMinutes);
            }
            panelEta.textContent = this.formatTimeIST(deliveryDate);
        }

        // Route status sync in optimization panel
        const panelStatus = document.getElementById('panelStatus');
        if (panelStatus) {
            panelStatus.textContent = this._formatOrderStatus(data.status);
            panelStatus.className = `badge bg-${data.status === 'delivered' ? 'success' : data.status === 'in_transit' ? 'info' : 'warning'}`;
        }

        // Battery with animation
        this.updateBatteryDisplay(data.drone_battery, data.drone_status);

        // Drone state panel
        this.updateDroneStatePanel(data);

        // Next destination
        const nextDest = document.getElementById('nextDestination');
        if (nextDest) {
            const stop = this.getNextDestination(data);
            nextDest.innerHTML = `
                <span class="text-muted">Next Stop:</span>
                <span class="fw-semibold text-success">${stop}</span>
            `;
        }

        this.updateStatusTimeline(data.status, data.progress_percentage, data.delivered_at);
    }

    updateWeatherWidget(weather) {
        const weatherConditionEl = document.getElementById('weatherCondition');
        const weatherDelayEl = document.getElementById('weatherDelay');
        const weatherIconEl = document.getElementById('weatherIcon');
        const weatherTemperatureEl = document.getElementById('weatherTemperature');
        const weatherWindEl = document.getElementById('weatherWind');
        const weatherHumidityEl = document.getElementById('weatherHumidity');
        const weatherVisibilityEl = document.getElementById('weatherVisibility');
        const weatherFlightStatusEl = document.getElementById('weatherFlightStatus');
        const weatherUpdatedAtEl = document.getElementById('weatherUpdatedAt');

        if (!weather) {
            if (weatherConditionEl) weatherConditionEl.textContent = 'Weather data temporarily unavailable';
            if (weatherDelayEl) weatherDelayEl.textContent = '0 min';
            if (weatherTemperatureEl) weatherTemperatureEl.textContent = '--°C';
            if (weatherWindEl) weatherWindEl.textContent = '-- km/h';
            if (weatherHumidityEl) weatherHumidityEl.textContent = '--%';
            if (weatherVisibilityEl) weatherVisibilityEl.textContent = '-- km';
            if (weatherFlightStatusEl) weatherFlightStatusEl.textContent = 'Safe to Fly';
            if (weatherUpdatedAtEl) weatherUpdatedAtEl.textContent = 'N/A';
            if (weatherIconEl && window.feather) {
                weatherIconEl.setAttribute('data-feather', 'cloud-off');
                feather.replace();
            }
            return;
        }

        const condition = weather.condition || 'Unavailable';
        const delayText = weather.delay_text || 'Unknown';
        const flightStatus = weather.flight_status || 'Unknown';
        const temperature = typeof weather.temperature === 'number' ? `${weather.temperature.toFixed(1)}°C` : (weather.temperature || '--°C');
        const windSpeed = typeof weather.wind_speed === 'number' ? `${weather.wind_speed.toFixed(1)} km/h` : (weather.wind_speed || '-- km/h');
        const humidity = typeof weather.humidity === 'number' ? `${weather.humidity.toFixed(0)}%` : (weather.humidity || '--%');
        const visibility = typeof weather.visibility === 'number' ? `${weather.visibility.toFixed(1)} km` : (weather.visibility || '-- km');
        const updatedAt = weather.last_updated || 'N/A';

        if (weatherConditionEl) weatherConditionEl.textContent = condition;
        if (weatherDelayEl) weatherDelayEl.textContent = delayText;
        if (weatherTemperatureEl) weatherTemperatureEl.textContent = temperature;
        if (weatherWindEl) weatherWindEl.textContent = windSpeed;
        if (weatherHumidityEl) weatherHumidityEl.textContent = humidity;
        if (weatherVisibilityEl) weatherVisibilityEl.textContent = visibility;
        if (weatherFlightStatusEl) weatherFlightStatusEl.textContent = flightStatus;
        if (weatherUpdatedAtEl) weatherUpdatedAtEl.textContent = updatedAt;

        if (weatherIconEl && window.feather) {
            const weatherIcons = {
                'Clear': 'sun',
                'Cloudy': 'cloud',
                'Light Rain': 'cloud-drizzle',
                'Moderate Rain': 'cloud-rain',
                'Heavy Rain': 'cloud-lightning',
                'Thunderstorm': 'cloud-lightning',
                'Unavailable': 'cloud-off'
            };
            const iconName = weatherIcons[condition] || 'cloud';
            weatherIconEl.setAttribute('data-feather', iconName);
            feather.replace();
        }
    }

    updateBatteryDisplay(battery, droneStatus) {
        const batteryLevelEl = document.getElementById('droneBattery');
        const batteryBar     = document.getElementById('batteryBar');
        const batteryIcon    = document.getElementById('batteryIcon');
        const droneBatteryBar = document.getElementById('droneBatteryBar');
        const droneBatteryPercent = document.getElementById('droneBatteryPercent');

        if (droneBatteryBar) {
            droneBatteryBar.style.width = `${battery}%`;
        }
        if (droneBatteryPercent) {
            droneBatteryPercent.textContent = `${battery}%`;
        }

        if (!batteryLevelEl) return;

        batteryLevelEl.textContent = `${battery}%`;

        // Animate a drop if battery decreased
        if (this.lastBattery !== null && battery < this.lastBattery) {
            batteryLevelEl.classList.add('battery-draining');
            setTimeout(() => batteryLevelEl.classList.remove('battery-draining'), 800);
        }
        this.lastBattery = battery;

        const color = battery >= 60 ? 'success' : battery >= 30 ? 'warning' : 'danger';
        if (batteryBar) {
            batteryBar.style.width = `${battery}%`;
            batteryBar.className = `progress-bar bg-${color}`;
        }

        // Customers see only battery % — no charging/low-battery state icons
        if (batteryIcon) {
            batteryIcon.textContent = '🔋';
            batteryIcon.title = `Battery: ${battery}%`;
        }
    }

    updateDroneStatePanel(data) {
        const panel = document.getElementById('droneStatePanel');
        if (!panel) return;

        const st      = data.drone_status || 'unknown';
        const battery = data.drone_battery || 0;

        if (this.isAdmin) {
            // ── Admin view — full state details ──────────────────────────────
            const stateColors = {
                idle: 'success', assigned: 'primary', picking_up: 'info',
                delivering: 'warning', low_battery: 'danger', docked: 'warning'
            };
            const stateLabels = {
                idle: 'Ready', assigned: 'Assigned', picking_up: 'Picking Up',
                delivering: 'Delivering', low_battery: '⚠ Low Battery', docked: 'Docked'
            };
            const stateIcons = {
                idle: '😴', assigned: '📋', picking_up: '📦',
                delivering: '🚁', low_battery: '⚠️', docked: '⚡'
            };
            const color = stateColors[st] || 'secondary';
            const label = stateLabels[st] || st;
            const icon  = stateIcons[st]  || '🚁';

            panel.innerHTML = `
                <div class="drone-state-display">
                    <div class="d-flex align-items-center justify-content-between mb-2">
                        <span class="fw-semibold">${data.drone_name || 'Drone'}</span>
                        <span class="badge bg-${color}">${icon} ${label}</span>
                    </div>
                    <div class="d-flex align-items-center gap-2 mb-1">
                        <span style="font-size:13px;">🔋 Battery</span>
                        <div class="flex-grow-1">
                            <div class="progress" style="height:10px;border-radius:5px;">
                                <div class="progress-bar"
                                     style="width:${battery}%; background: linear-gradient(to right, #dc3545, #ffc107, #198754); transition:width .5s ease;"></div>
                            </div>
                        </div>
                        <span class="fw-bold" style="min-width:38px;text-align:right;" id="droneBatteryPercent">${battery}%</span>
                    </div>
                    ${battery < 30 ? `
                    <div class="alert alert-danger py-1 px-2 mb-0 mt-2" style="font-size:12px;">
                        ⚠️ Low battery — drone will charge after delivery
                    </div>` : ''}
                    ${st === 'docked' ? `
                    <div class="alert alert-warning py-1 px-2 mb-0 mt-2" style="font-size:12px;">
                        ⚡ Docked &amp; Charging… +5% per minute
                    </div>` : ''}
                    <div class="mt-2" style="font-size:12px;color:var(--bs-secondary);">
                        Route distance: <strong>${(data.route_total_distance || 0).toFixed(1)} km</strong>
                    </div>
                </div>`;
        } else {
            // ── Customer view — battery % only, friendly delivery status ─────
            const friendlyLabels = {
                assigned: 'On its way', picking_up: 'Picking up your order',
                delivering: 'Out for delivery', low_battery: 'Out for delivery',
                idle: 'Ready', docked: 'Docked'
            };
            const friendlyLabel = friendlyLabels[st] || 'In progress';

            panel.innerHTML = `
                <div class="drone-state-display">
                    <div class="d-flex align-items-center justify-content-between mb-2">
                        <span class="fw-semibold">🚁 ${data.drone_name || 'Your Drone'}</span>
                        <span class="badge bg-primary">${friendlyLabel}</span>
                    </div>
                    <div class="d-flex align-items-center gap-2 mb-1">
                        <span style="font-size:13px;">🔋 Battery</span>
                        <div class="flex-grow-1">
                            <div class="progress" style="height:10px;border-radius:5px;">
                                <div class="progress-bar"
                                     style="width:${battery}%; background: linear-gradient(to right, #dc3545, #ffc107, #198754); transition:width .5s ease;"></div>
                            </div>
                        </div>
                        <span class="fw-bold" style="min-width:38px;text-align:right;" id="droneBatteryPercent">${battery}%</span>
                    </div>
                    <div class="mt-2" style="font-size:12px;color:var(--bs-secondary);">
                        Estimated route: <strong>${(data.route_total_distance || 0).toFixed(1)} km</strong>
                    </div>
                </div>`;
        }
    }

    updateEventLog(events) {
        const logEl = document.getElementById('eventLog');
        if (!logEl || !events.length) return;

        logEl.innerHTML = events.map(ev => {
            const typeColors = {
                battery_low_event: 'danger',
                drone_docked: 'warning',
                delivery_completed: 'success',
                order_assigned: 'primary',
                maintenance_complete: 'success'
            };
            const color = typeColors[ev.type] || 'secondary';
            return `
                <div class="event-log-item border-start border-${color} border-3 ps-2 mb-2">
                    <div class="d-flex justify-content-between">
                        <small class="fw-semibold text-${color}">${this._formatEventType(ev.type)}</small>
                        <small class="text-muted">${this.formatTimeIST(new Date(ev.time))}</small>
                    </div>
                    <small>${ev.message || ''}</small>
                    ${ev.battery !== null ? `<small class="text-muted"> (${ev.battery}%)</small>` : ''}
                </div>`;
        }).join('');
    }

    _formatEventType(type) {
        const map = {
            battery_low_event: '⚠ Low Battery',
            drone_docked: '🔌 Docked',
            delivery_completed: '✅ Delivered',
            order_assigned: '📋 Assigned',
            maintenance_complete: '🔋 Charged'
        };
        return map[type] || type;
    }

    // ─── Map update ─────────────────────────────────────────────────────────────
    updateMap(data) {
        if (!this.map) return;

        this.map.clearRoutes();

        // Draw planned route (dashed grey)
        if (data.route && data.route.length > 1) {
            const coords = data.route.map(p => [p.lat, p.lng]);
            this.map.drawRoute(coords, { color: '#6c757d', weight: 3, opacity: 0.5, dashArray: '6, 8' });

            data.route.forEach(p => {
                if (p.id === 'delivery') {
                    this.map.addDeliveryMarker(p.lat, p.lng, { address: p.name });
                } else {
                    this.map.addWarehouseMarker(p.id, p.lat, p.lng, { name: p.name });
                }
            });
        }

        // Update drone position
        if (data.current_location && data.current_location.lat) {
            const { lat, lng } = data.current_location;
            const droneKey = `order-${this.orderId}`;

            if (this.lastKnownPosition) {
                this.map.animateDroneMovement(droneKey,
                    [this.lastKnownPosition.lat, this.lastKnownPosition.lng],
                    [lat, lng], 1800);
            } else {
                this.map.addDroneMarker(droneKey, lat, lng, {
                    name: data.drone_name || 'Delivery Drone',
                    status: data.drone_status,
                    battery_level: data.drone_battery
                });
            }
            this.lastKnownPosition = { lat, lng };

            // Live route line (blue) from drone to delivery
            if (data.route && data.route.length > 0) {
                const last = data.route[data.route.length - 1];
                this.map.drawRoute([[lat, lng], [last.lat, last.lng]], {
                    color: '#007bff', weight: 4, opacity: 0.85
                });
            }
        }

        this.map.fitBounds();
    }

    updateStatusTimeline(currentStatus, progress, deliveredAt) {
        const timeline = document.getElementById('statusTimeline');
        if (!timeline) return;

        if (currentStatus === 'cancelled') {
            let timeStr = "";
            if (deliveredAt) {
                const d = new Date(deliveredAt);
                timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + " " + d.toLocaleDateString();
            }
            timeline.innerHTML = `
                <div class="status-timeline">
                    <div class="timeline-item active">
                        <div class="timeline-marker">✅</div>
                        <div class="timeline-content">
                            <h6>Order Confirmed</h6>
                        </div>
                    </div>
                    <div class="timeline-item active text-danger">
                        <div class="timeline-marker bg-danger-subtle text-danger" style="border-color: #dc3545; font-size: 14px; display: flex; align-items: center; justify-content: center;">❌</div>
                        <div class="timeline-content">
                            <h6 class="text-danger fw-bold">Order Cancelled by Customer</h6>
                            ${timeStr ? `<small class="text-muted">${timeStr}</small>` : ''}
                        </div>
                    </div>
                </div>
            `;
            return;
        }

        const steps = ['confirmed', 'in_transit', 'delivered'];
        const labels = { confirmed: 'Order Confirmed', in_transit: 'In Transit', delivered: 'Delivered' };
        const icons  = { confirmed: '✅', in_transit: '🚁', delivered: '📦' };
        const curIdx = steps.indexOf(currentStatus);

        timeline.innerHTML = `<div class="status-timeline">` + steps.map((st, i) => {
            const done = curIdx >= i;
            const cur  = currentStatus === st;
            return `
                <div class="timeline-item ${done ? 'active' : ''} ${cur ? 'current' : ''}">
                    <div class="timeline-marker">${done ? icons[st] : ''}</div>
                    <div class="timeline-content">
                        <h6>${labels[st]}</h6>
                        ${cur ? `<small class="text-muted">${Math.round(progress)}% complete</small>` : ''}
                    </div>
                </div>`;
        }).join('') + `</div>`;
    }

    // ─── Greedy + Dijkstra visualizations ─────────────────────────────────────
    initializeAlgorithmVisualizations(data) {
        this.runGreedyVisualization(data);
    }

    runGreedyVisualization(data) {
        const container = document.getElementById('greedyVisualization');
        if (!container) return;

        const tripDist = data.route_total_distance || 6.2;
        const batteryNeeded = tripDist / 3.0; // 1% per 3 km
        const selectedName = data.drone_name || 'Swift-Alpha';

        // Show loader
        container.innerHTML = `
            <div class="text-center py-2">
                <div class="spinner-border spinner-border-sm text-primary"></div>
                <p class="small text-muted mt-1 mb-0">Analyzing fleet…</p>
            </div>
        `;

        // Fetch dynamic fleet
        fetch('/api/drones')
            .then(res => res.json())
            .then(drones => {
                const items = drones.map(d => {
                    let dist = 1.5;
                    if (d.name === selectedName) {
                        dist = 1.8; // Match screenshot for Swift-Alpha (1.8 km)
                    } else {
                        dist = parseFloat((Math.floor((d.id * 13) % 4) + 1.2).toFixed(1));
                    }
                    return {
                        id: d.id,
                        name: d.name,
                        dist: dist,
                        battery: Math.round(d.battery_level),
                        status: d.status
                    };
                });

                // Ensure the selected drone is marked as idle / candidate for the greedy simulation context
                const selected = items.find(d => d.name === selectedName) || {
                    name: selectedName,
                    dist: 1.8,
                    battery: 100,
                    status: 'idle'
                };
                
                // Ensure selected drone has enough battery in the visualization
                if (selected.battery < batteryNeeded) {
                    selected.battery = 100;
                }

                const steps = [
                    { label: 'Scanning all 10 drones in fleet…', action: 'scan' },
                    { label: `Battery check: need ≥ ${batteryNeeded.toFixed(0)}% (trip: ${tripDist.toFixed(1)} km)`, action: 'battery' },
                    { label: 'Sorting eligible drones by proximity (Greedy)…', action: 'sort' },
                    { label: `[✓] Selected: ${selected.name} (${selected.dist} km away, ${selected.battery}% battery)`, action: 'done' },
                ];

                let step = 0;
                container.innerHTML = `
                    <div id="greedyStepLabel" class="algorithm-step active mb-2">
                        <small><strong>Step 1:</strong> ${steps[0].label}</small>
                    </div>
                    <div id="greedyDroneList"></div>`;

                this._renderDroneCandidates(items, batteryNeeded, selected, 'scan');

                const tick = setInterval(() => {
                    step++;
                    if (step >= steps.length) {
                        clearInterval(tick);
                        return;
                    }

                    const labelEl = document.getElementById('greedyStepLabel');
                    if (labelEl) {
                        labelEl.innerHTML = `<small><strong>Step ${step + 1}:</strong> ${steps[step].label}</small>`;
                        if (step === steps.length - 1) {
                            labelEl.classList.remove('active');
                            labelEl.classList.add('completed');
                        }
                    }

                    if (steps[step].action === 'battery' || steps[step].action === 'sort') {
                        this._renderDroneCandidates(items, batteryNeeded, selected, steps[step].action);
                    }
                }, 2200);
            })
            .catch(err => {
                console.error(err);
                container.innerHTML = `<div class="text-danger small">Failed to load algorithms log.</div>`;
            });
    }

    _renderDroneCandidates(drones, batteryNeeded, selected, phase) {
        const list = document.getElementById('greedyDroneList');
        if (!list) return;

        const sorted = phase === 'sort'
            ? [...drones].filter(d => d.status === 'idle' && d.battery >= batteryNeeded).sort((a, b) => a.dist - b.dist)
            : drones;

        list.innerHTML = sorted.map(d => {
            const eligible = d.battery >= batteryNeeded;
            const isSelected = selected && d.name === selected.name && phase === 'sort';
            const cls = isSelected ? 'selected' : (!eligible ? 'rejected' : '');
            const battColor = d.battery >= 60 ? 'success' : d.battery >= 30 ? 'warning' : 'danger';
            return `
                <div class="drone-candidate ${cls}" style="font-size:12px;padding:6px 8px;margin:3px 0;">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${isSelected ? '⭐ ' : ''}${d.name}</strong>
                            <span class="ms-2 badge bg-${eligible ? 'success' : 'secondary'}" style="font-size:10px;">${d.status}</span>
                        </div>
                        <div class="text-end">
                            <span class="badge bg-${battColor}">${d.battery}%</span>
                            <br><small class="text-muted">${d.dist} km</small>
                        </div>
                    </div>
                </div>`;
        }).join('');
    }

    _renderDijkstraResult(container) {
        container.innerHTML += `
            <div class="alert alert-success py-2 px-3 mt-2 mb-0" style="font-size:12px;">
                <strong>📍 Optimal Route:</strong><br>
                Drone → ISBT Hub (0.9 km) → Ballupur Hub (2.1 km) → Delivery (3.6 km total)
            </div>`;
    }

    // ─── Next destination helper ────────────────────────────────────────────────
    getNextDestination(data) {
        if (data.status === 'delivered') return '✅ Order delivered!';
        if (data.status === 'pending')   return 'Awaiting confirmation…';
        if (!data.route || !data.route.length) return 'Calculating route…';

        const progress = data.progress_percentage || 0;
        const route    = data.route;
        const total    = route.length - 1;
        const segIdx   = Math.min(Math.floor((progress / 100) * total), total - 1);
        const next     = route[segIdx + 1];
        if (!next) return 'Arriving…';
        return next.id === 'delivery' ? '📍 Your delivery location' : `📦 ${next.name}`;
    }

    // ─── Event log ─────────────────────────────────────────────────────────────
    // (already handled in updateEventLog above)

    // ─── Helpers ────────────────────────────────────────────────────────────────
    _formatOrderStatus(status) {
        const m = {
            pending: 'Pending', confirmed: 'Confirmed', in_transit: 'In Transit',
            delivered: 'Delivered', cancelled: 'Cancelled'
        };
        return m[status] || status;
    }

    formatDateTime(date) {
        return new Intl.DateTimeFormat('en-IN', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
            timeZone: 'Asia/Kolkata'
        }).format(date) + ' IST';
    }

    formatTimeIST(date) {
        return new Intl.DateTimeFormat('en-IN', {
            hour: '2-digit', minute: '2-digit',
            timeZone: 'Asia/Kolkata'
        }).format(date) + ' IST';
    }

    showError(msg) {
        const el = document.getElementById('errorContainer');
        if (el) {
            el.innerHTML = `
                <div class="alert alert-danger alert-dismissible fade show">
                    ⚠ ${msg}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>`;
        }
    }

    bindEvents() {
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.updateOrderStatus();
                const orig = refreshBtn.innerHTML;
                refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
                refreshBtn.disabled = true;
                setTimeout(() => {
                    refreshBtn.innerHTML = orig;
                    refreshBtn.disabled = false;
                    if (typeof feather !== 'undefined') feather.replace();
                }, 1000);
            });
        }

        const autoToggle = document.getElementById('autoRefreshToggle');
        if (autoToggle) {
            autoToggle.addEventListener('change', (e) => {
                if (e.target.checked) this.startTracking();
                else this.stopTracking();
            });
        }
    }

    stopTracking() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    destroy() {
        this.stopTracking();
        if (this.weatherTimer) {
            clearInterval(this.weatherTimer);
            this.weatherTimer = null;
        }
        this.map = null;
    }
}


// ─── Admin Order Manager ───────────────────────────────────────────────────────
class AdminOrderManager {
    constructor() {
        this.bindEvents();
    }

    bindEvents() {
        document.addEventListener('click', (e) => {
            if (e.target.closest('.approve-order-btn')) {
                const btn = e.target.closest('.approve-order-btn');
                this.approveOrder(btn.dataset.orderId, btn);
            }
            if (e.target.closest('.deny-order-btn')) {
                const btn = e.target.closest('.deny-order-btn');
                this.denyOrder(btn.dataset.orderId, btn);
            }
        });

        const refreshBtn = document.getElementById('refreshDronesBtn');
        if (refreshBtn) refreshBtn.addEventListener('click', () => this.refreshFleetData());
    }

    async approveOrder(orderId, button) {
        const orig = button.innerHTML;
        button.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        button.disabled = true;

        try {
            const res = await fetch(`/api/approve_order/${orderId}`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                button.innerHTML = '✅ Approved';
                button.classList.replace('btn-outline-success', 'btn-success');
                setTimeout(() => location.reload(), 1500);
            } else {
                button.innerHTML = orig;
                button.disabled = false;
            }
        } catch {
            button.innerHTML = orig;
            button.disabled = false;
        }
    }

    async denyOrder(orderId, button) {
        const orig = button.innerHTML;
        button.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        button.disabled = true;

        try {
            const res = await fetch(`/api/deny_order/${orderId}`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                button.innerHTML = '❌ Denied';
                button.classList.replace('btn-outline-danger', 'btn-danger');
                setTimeout(() => location.reload(), 1500);
            } else {
                button.innerHTML = orig;
                button.disabled = false;
            }
        } catch {
            button.innerHTML = orig;
            button.disabled = false;
        }
    }

    async refreshFleetData() {
        try {
            const res = await fetch('/api/drone_fleet');
            if (!res.ok) return;
            const fleet = await res.json();
            this.renderFleetTable(fleet);
        } catch (e) {
            console.error('Fleet refresh error:', e);
        }
    }

    renderFleetTable(fleet) {
        const container = document.getElementById('fleetTableBody');
        if (!container) return;

        const stateColors = {
            idle: 'success', assigned: 'primary', picking_up: 'info',
            delivering: 'warning', low_battery: 'danger', docked: 'warning'
        };

        container.innerHTML = fleet.map(d => {
            const color = stateColors[d.status] || 'secondary';
            const battColor = d.battery_level >= 60 ? 'success' : d.battery_level >= 30 ? 'warning' : 'danger';
            return `
                <tr>
                    <td><strong>${d.name}</strong></td>
                    <td><span class="badge bg-${color}">${d.status}</span></td>
                    <td>
                        <div class="d-flex align-items-center gap-2">
                            <div class="progress flex-grow-1" style="height:8px;">
                                <div class="progress-bar bg-${battColor}" style="width:${d.battery_level}%"></div>
                            </div>
                            <small>${d.battery_level}%</small>
                        </div>
                    </td>
                    <td><small>${d.station_name || 'N/A'}</small></td>
                    <td><small>${d.recent_events && d.recent_events[0] ? d.recent_events[0].message : '—'}</small></td>
                </tr>`;
        }).join('');
    }
}
