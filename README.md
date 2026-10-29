# LabWatch — Real-Time Multi-Device Computer Lab Monitoring System

[![Python Version](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20Android-green.svg)]()
[![License](https://img.shields.io/badge/Project-Final%20Year%20Engineering-orange.svg)]()

**LabWatch** is a production-grade, distributed client-server computer lab monitoring solution designed for academic laboratories and university IT departments. 

It provides real-time telemetry, automated threshold alerts, administrative diagnostics, and responsive mobile surveillance using **only one Windows laptop and one Android smartphone** immediately, while architecturally ready for **50+ lab computers**.

---

## 🌟 Key Features

- **Real System Telemetry**: Collects actual CPU utilization, RAM usage, storage space, uptime, and network metrics using `psutil` or native Win32 `ctypes` fallback.
- **Real-Time Process & Application Monitoring**:
  - Live discovery of all active running processes and applications on each monitored PC.
  - Per-process PID, process name, CPU utilization percentage, Memory MB (working set / RSS), and Memory percentage.
  - Side-by-side **Top 10 CPU-consuming** and **Top 10 Memory-consuming** application rankings.
  - Interactive searchable and sortable process inventory with quick PID/name filtering.
  - Individual process historical workload trend charts (CPU & RAM trends over time).
  - One-click **CSV Export** for lab audit logs and college engineering reports.
- **Truthful Metric Reporting**: Never fabricates unsupported temperature or fan data. Accurately reports hardware sensor status.
- **Mobile-Responsive Dashboard**: Accessible from any mobile browser (Android/iOS) over local Wi-Fi or hotspot.
- **Server-Sent Events (SSE)**: Sub-second live updates without dashboard page refreshes.
- **Threshold-Based Alerts & Diagnostics**: Automatic warning and critical alerts with actionable troubleshooting advice for lab administrators.
- **Safe Viva Demo Mode**: Non-destructive test alert injection for college evaluations.
- **Scale Simulator**: Includes `simulate_lab.py` to demonstrate monitoring 5 to 50+ concurrent workstations.
- **Lightweight & Zero Paid Cloud Dependencies**: Self-contained SQLite database with Write-Ahead Logging (WAL).

---

## 🚀 Quick Start Guide (Windows)

### 1. Prerequisites
- Python 3.8 or higher installed on Windows.
- Make sure Python is added to your Windows PATH.

### 2. Setup (Run in PowerShell or Command Prompt)
```powershell
# Navigate to the project directory
cd "d:\Programming\Multi-Device Computer Lab Monitoring System"

# (Optional) Install dependencies for advanced psutil support
pip install -r requirements.txt
```
*(Note: LabWatch contains an integrated native Win32 collector and works even in zero-dependency environments!)*

---

## 💻 Running the System (One Laptop + One Mobile Phone)

### Step 1: Start the Central Monitoring Server
In Terminal 1:
```powershell
python -m src.server
```
Output will show:
```
=================================================================
🚀 LabWatch Central Server Active
👉 Local Access:   http://localhost:8000
👉 Network/Mobile: http://10.108.205.138:8000
=================================================================
```

### Step 2: Start the Laptop Monitoring Agent
In Terminal 2:
```powershell
python -m src.agent
```
The agent automatically registers your laptop, collects real metrics, and streams updates every 3 seconds!

### Step 3: Open Dashboard on Laptop
Open your browser and navigate to:
```
http://localhost:8000
```
You will immediately see your laptop listed with live CPU, RAM, and Disk graphs!

### Step 4: Open Dashboard on Android Mobile Phone
1. Connect your Android phone to the **same Wi-Fi** network or to your laptop's **Mobile Hotspot**.
2. Open Google Chrome on your phone.
3. Enter the URL displayed in the server terminal (e.g. `http://10.108.205.138:8000`).
4. You now have a real-time lab supervisor monitor in the palm of your hand!

### Step 5: Real-Time Process & Application Monitor
Open the **Process Monitor** page:
> **`http://localhost:8000/processes`** *(or tap "⚡ Process Monitor" on the header)*

- View running processes on your laptop or any selected lab computer.
- Inspect Top 10 CPU and RAM applications in real-time.
- Click any process to isolate its workload history.
- Click **"📥 Export CSV"** to download raw records.

---

## 🎓 5-Minute College Demonstration Procedure

Follow this script during your final-year project demonstration or viva:

1. **Architecture Explanation (1 min)**:
   - Explain the client-server architecture: Host server running SQLite + SSE event streaming, communicating with lightweight agents.
2. **Real Laptop Telemetry (1.5 min)**:
   - Show the laptop's live CPU and RAM meters moving as you launch an application. Point out the truthful sensor status note.
3. **Mobile Phone Supervision (1 min)**:
   - Show the examiners the live dashboard running on your Android phone browser, updating simultaneously via Server-Sent Events.
4. **Safe Alert Triggering (1 min)**:
   - Click **"⚡ Inject Demo Alert"** on the dashboard.
   - Choose *Simulated High Temperature (92.4°C)* or *Simulated CPU Spike*.
   - Point out the purple `[DEMO MODE]` badge, real-time alert card, and the step-by-step diagnostic advice generated for lab technicians.
   - Click **"✓ Acknowledge & Resolve"** to clear the alert.
5. **Multi-Device Scalability Demo (30 sec)**:
   - In a 3rd terminal, run:
     ```powershell
     python scripts/simulate_lab.py 10
     ```
   - Watch the dashboard instantly populate with 10 lab computers, showing search, status filters, and individual telemetry!

---

## 🔧 Windows Firewall & Network Troubleshooting

If your Android phone cannot connect to `http://<LAPTOP_IP>:8000`:

1. **Verify Same Network**: Ensure both devices are connected to the same router or turn on Windows Mobile Hotspot and connect your phone to it.
2. **Find Your Laptop IP**:
   Run `ipconfig` in Command Prompt and check `IPv4 Address` under your active Wi-Fi adapter.
3. **Allow Port 8000 in Windows Firewall**:
   Run PowerShell as Administrator and execute:
   ```powershell
   New-NetFirewallRule -DisplayName "LabWatch Port 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
   ```

---

## 📁 Repository Structure

```
├── src/
│   ├── server.py              # Central HTTP REST & SSE streaming server
│   ├── agent.py               # Background telemetry monitoring agent
│   ├── collector.py           # Win32 & psutil hardware telemetry harvester
│   ├── database.py            # SQLite database schema, WAL mode, CRUD ops
│   ├── alerts.py              # Threshold rules, diagnostics, and test alerts
│   └── templates/
│       └── dashboard.html     # High-tech dark-theme responsive dashboard
├── tests/
│   └── test_labwatch.py       # Automated unit tests
├── scripts/
│   ├── simulate_lab.py        # Multi-computer simulator for 50+ nodes
│   └── android_agent.py       # Optional mobile agent for Termux/Pydroid
├── docs/
│   ├── ARCHITECTURE.md        # Technical architecture design
│   ├── API.md                 # Complete REST API reference
│   └── VIVA_AND_REPORT.md     # Final-year project report & viva Q&A
├── requirements.txt           # Python package requirements
└── README.md                  # Comprehensive documentation
```

---

## 🧪 Automated Testing

To run the automated test suite:
```powershell
python -m unittest tests/test_labwatch.py
```
All tests validate database consistency, telemetry integrity, and alert lifecycles.
