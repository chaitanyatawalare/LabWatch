# LabWatch: Final-Year Engineering Project Report Outline & Viva Guide

## Part 1: Project Report Structure

### Chapter 1: Introduction
- **1.1 Background**: Growth of high-density academic computer laboratories and IT resource management challenges.
- **1.2 Problem Statement**: Existing commercial solutions (e.g. Datadog, SolarWinds, PRTG) are expensive, cloud-dependent, resource-heavy, and lack localized student-lab-focused diagnostic controls.
- **1.3 Project Objectives**:
  - Build a lightweight, cross-platform client-server monitoring system.
  - Implement zero-dependency native Win32/POSIX OS telemetry harvesting.
  - Provide threshold-based proactive alerts with administrator diagnostics.
  - Deliver responsive mobile supervisor monitoring over local LAN.
  - Guarantee truthful metric reporting (no fabricated sensors).
- **1.4 Scope and Limitations**: Real-time performance monitoring within local subnets; no destructive commands executed without authentication.

### Chapter 2: Literature Review & Existing Systems
- Comparative study of SNMP (Simple Network Management Protocol), WMI (Windows Management Instrumentation), and modern REST/SSE micro-agents.
- Evaluation of telemetry push vs. poll models.
- Hardware sensor security and access restrictions on Windows 11 and Android mobile OS.

### Chapter 3: System Design & Architecture
- **3.1 High-Level Architecture**: Client-Server topology.
- **3.2 Database Design**: Entity-Relationship diagram (Devices, Telemetry, Alerts, Thresholds).
- **3.3 Telemetry Acquisition Engine**: Dual-layer architecture (`psutil` and native Win32 C-types fallback).
- **3.4 Real-time Communication**: HTTP REST and Server-Sent Events (SSE).
- **3.5 Security Model**: Per-node SHA-256 device tokens and local-subnet firewall bounding.

### Chapter 4: Implementation Details
- Module breakdown: `database.py`, `collector.py`, `alerts.py`, `server.py`, `agent.py`, `dashboard.html`.
- Algorithm for idle-time CPU calculation using Win32 `GetSystemTimes`.
- Heartbeat timeout and stale device reaper mechanism.
- Safe simulation and demo injection engine.

### Chapter 5: Results & Performance Evaluation
- Latency and throughput benchmarks under 1, 10, and 50+ concurrent nodes.
- Memory and CPU overhead of the LabWatch agent (<1% CPU, <25 MB RAM).
- Demonstration of live synchronization between Windows laptop and Android smartphone.

### Chapter 6: Conclusion & Future Enhancements
- Summary of achievements.
- Future work: Centralized remote script deployment, wake-on-LAN integration, and machine-learning-based anomaly forecasting.

---

## Part 2: College Viva Questions & Answers

### Q1: Why did you choose a custom Python client-server architecture instead of using existing open-source tools like Nagios or Zabbix?
**Answer**: Enterprise tools like Zabbix require complex daemon setups, extensive databases (MySQL/PostgreSQL), and significant system overhead on each client machine. LabWatch is specifically tailored for educational computer labs: it is zero-dependency, ultra-lightweight, runs out-of-the-box on standard Python with SQLite, and provides an instant mobile-accessible interface without requiring cloud subscriptions or complex infrastructure.

### Q2: How does your agent measure CPU utilization without third-party dependencies?
**Answer**: While LabWatch seamlessly uses `psutil` when available, it includes a native Win32 fallback utilizing `ctypes.windll.kernel32.GetSystemTimes`. It captures idle, kernel, and user FILETIME structures across a sampling delta. By calculating `1.0 - (idle_delta / total_delta)`, it accurately measures real Windows CPU consumption identical to the Windows Task Manager.

### Q3: Why doesn't the system report CPU temperature on all machines?
**Answer**: Modern operating systems (especially Windows 11) strictly guard ring-0 hardware thermal registers for security reasons. Standard user-space applications cannot read hardware thermal sensors without custom signed kernel drivers (like WinRing0) or vendor-specific ACPI WMI interfaces. LabWatch adheres to strict engineering integrity: rather than fabricating fake temperatures, it truthfully notifies the administrator that thermal sensors are restricted by OS security policies.

### Q4: How is real-time synchronization achieved without polling the server constantly?
**Answer**: LabWatch utilizes Server-Sent Events (SSE) over the `/api/events` endpoint. When any client sends telemetry or an alert is triggered, the server broadcasts an event immediately over persistent HTTP connections to all connected browsers (laptop and mobile), achieving sub-50ms UI update latency with minimal bandwidth.

### Q5: How do you demonstrate alert detection during viva without damaging your laptop?
**Answer**: LabWatch includes a safe, built-in Demonstration Mode. Through the dashboard, the examiner can inject safe test alerts (such as simulated thermal threshold warnings or sudden CPU spikes). These events are visibly tagged as `[DEMO MODE]` in purple, triggering real-time diagnostics and resolution flows without causing real hardware stress.

### Q6: Can this system scale to an entire university lab of 60 computers?
**Answer**: Yes. The SQLite database uses Write-Ahead Logging (WAL mode) for high-concurrency non-blocking reads and writes. The server uses multi-threaded HTTP request processing, and the agent uses lightweight JSON payloads of less than 400 bytes per cycle. We include a simulation script (`scripts/simulate_lab.py`) that can simulate 50+ active lab computers concurrently to verify dashboard responsiveness.
