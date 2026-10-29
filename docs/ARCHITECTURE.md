# LabWatch Architecture & Technical Specification

## 1. System Overview
**LabWatch** is a production-grade, distributed client-server computer lab monitoring system built using Python, SQLite, Win32/psutil telemetry collectors, and an event-driven web dashboard.

It is specifically engineered to solve the practical challenge of monitoring 50+ computers in educational or enterprise computer laboratories while providing immediate, non-simulated real-world demonstration using just **one Windows laptop and one Android smartphone**.

```
                ┌────────────────────────────────────────┐
                │        LabWatch Central Server         │
                │        (Running on Host Laptop)        │
                │  - REST API & SSE Broadcast (Port 8000)│
                │  - SQLite Multi-Threaded WAL Database  │
                │  - Alert & Diagnostic Engine           │
                │  - Background Heartbeat Daemon         │
                └───────┬────────────────────────┬───────┘
                        │                        │
         HTTP Telemetry │                        │ HTTP / SSE Dashboard
         & Heartbeats   │                        │ (Responsive UI)
                        ▼                        ▼
       ┌────────────────────────┐      ┌────────────────────────┐
       │   LabWatch Agent       │      │  Android Mobile Client │
       │ (Win32 / psutil Real)  │      │  (Chrome/Firefox View  │
       │ - CPU, RAM, Disk, Time │      │   or Termux Agent)     │
       └────────────────────────┘      └────────────────────────┘
                        │
                        ▼
       ┌─────────────────────────────────────────────────────────┐
       │ Future / Simulated Lab Clients (Node 01 to 50+)        │
       │ Multi-device scaled monitoring on local Wi-Fi / LAN     │
       └─────────────────────────────────────────────────────────┘
```

## 2. Component Specifications

### 2.1 Database Architecture (`src/database.py`)
- **Engine**: SQLite with Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and foreign key constraints enabled.
- **Tables**:
  - `devices`: Tracks `device_id`, `hostname`, `os_type`, `ip_address`, `agent_version`, `token_hash`, `status` (`online`/`offline`), `registered_at`, `last_seen_at`.
  - `telemetry`: High-frequency metrics including `cpu_pct`, `ram_pct`, `ram_used_gb`, `ram_total_gb`, `disk_pct`, `disk_free_gb`, `uptime_hours`, `net_bytes`, `sensor_notes`. Indexed by `(device_id, recorded_at)`.
  - `alerts`: Tracks severity (`warning`, `critical`), trigger metrics, thresholds, values, acknowledgment, resolution, and actionable diagnostic recommendations.
  - `alert_configs`: Configurable threshold limits for CPU, RAM, Disk, and Heartbeat timeouts.

### 2.2 Telemetry Collector Engine (`src/collector.py`)
- **Zero-Falsehood Guarantee**: Never fabricates unsupported temperature or fan readings. Explicitly annotates thermal availability based on OS permissions and kernel access.
- **Hybrid Architecture**:
  - Prefers `psutil` if installed in the host Python environment.
  - Features a complete native Windows Win32 API engine using `ctypes` (`GlobalMemoryStatusEx`, `GetDiskFreeSpaceExW`, `GetSystemTimes`, `GetTickCount64`).
  - Supports cross-platform POSIX fallbacks.

### 2.3 Alert & Diagnostic Engine (`src/alerts.py`)
- Continuously assesses metrics against configured thresholds.
- Contains built-in heuristic troubleshooting knowledge for computer lab administrators (e.g. runaway process detection, swap/RAM optimization, temp directory clearing).
- Includes **Safe Demonstration Mode** to inject labeled test alerts (`simulated_overheating`, `simulated_cpu_spike`) during viva evaluations without stressing physical hardware.

### 2.4 Server & Real-time Broadcast (`src/server.py`)
- **Transport**: Standard HTTP REST for commands and **Server-Sent Events (SSE)** on `/api/events` for real-time live streaming to web dashboards without excessive client polling.
- **Background Workers**: Heartbeat reaper daemon checks node staleness every 5 seconds and flags disconnected PCs.

### 2.5 Monitoring Agent (`src/agent.py`)
- Generates persistent unique device tokens and IDs based on hardware signatures.
- Automatically handles server discovery, registration, heartbeat delivery, and resilient error recovery.
