# LabWatch REST API Documentation

The LabWatch Central Server exposes a lightweight, authenticated REST API on port `8000`.

## Base URL
```
http://<SERVER_IP>:8000/api
```

---

## 1. Device Endpoints

### `POST /api/devices/register`
Registers a new computer or updates an existing device registration.
- **Headers**: `Content-Type: application/json`
- **Request Body**:
```json
{
  "device_id": "PC-A1B2C3D4",
  "hostname": "LAB-DESKTOP-01",
  "os_type": "Windows 11 (64bit)",
  "token": "secret_device_token",
  "agent_version": "1.0.0",
  "device_type": "computer"
}
```
- **Response** `200 OK`:
```json
{
  "status": "registered",
  "device": {
    "device_id": "PC-A1B2C3D4",
    "hostname": "LAB-DESKTOP-01",
    "status": "online"
  }
}
```

### `GET /api/devices`
Returns all registered devices along with their latest telemetry snapshot.
- **Response** `200 OK`: Array of device records.

### `DELETE /api/devices/<device_id>`
Unregisters/removes a device from the lab inventory.
- **Response** `200 OK`: `{"status": "deleted", "device_id": "..."}`

---

## 2. Telemetry & Heartbeat Endpoints

### `POST /api/telemetry`
Submits real-time performance metrics from an agent.
- **Headers**:
  - `Content-Type: application/json`
  - `X-Device-Token: <token>`
- **Request Body**:
```json
{
  "device_id": "PC-A1B2C3D4",
  "cpu_pct": 24.5,
  "ram_pct": 68.2,
  "ram_used_gb": 10.9,
  "ram_total_gb": 16.0,
  "disk_pct": 74.1,
  "disk_free_gb": 78.5,
  "disk_total_gb": 301.0,
  "uptime_hours": 3.42,
  "net_bytes_sent": 1048576,
  "net_bytes_recv": 2097152,
  "is_simulated": 0,
  "sensor_notes": "Hardware thermal sensors unavailable on this hardware or requires elevated kernel drivers."
}
```
- **Response** `200 OK`: `{"status": "ok", "alerts_triggered": 0}`

### `GET /api/telemetry?device_id=<device_id>&limit=60`
Fetches chronological historical metric records for SVG charts.

### `POST /api/heartbeat`
Lightweight keep-alive ping for agents when full telemetry is paused.
- **Request Body**: `{"device_id": "PC-A1B2C3D4"}`

---

## 3. Alerts & Diagnostics Endpoints

### `GET /api/alerts?active_only=1`
Returns active system warnings and critical alerts.

### `POST /api/alerts/<alert_id>/resolve`
Marks an alert as acknowledged and resolved.

### `POST /api/alerts/test`
Injects safe, clearly labeled demo alerts for viva evaluations without hardware impact.
- **Request Body**:
```json
{
  "device_id": "PC-A1B2C3D4",
  "test_type": "simulated_overheating"
}
```
*(Options: `simulated_overheating`, `simulated_cpu_spike`)*

---

## 4. Real-Time Streaming

### `GET /api/events`
Server-Sent Events (SSE) connection stream broadcasting instant updates for:
- `telemetry` (live CPU/RAM)
- `alert` (new warning/critical alerts)
- `device_registered`
- `device_status_change` (offline timeout trigger)
