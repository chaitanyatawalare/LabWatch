"""
LabWatch Central Monitoring Server
Zero-dependency, high-performance HTTP REST API and Live Web Dashboard.
Includes Server-Sent Events (SSE) for real-time telemetry streaming,
device authentication, alert evaluation, and multi-threaded background workers.
"""

import sys
import os
import json
import time
import socket
import threading
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server so persistent SSE streams do not block incoming HTTP page loads."""
    daemon_threads = True

# Import LabWatch modules
from src.database import Database
from src.alerts import AlertEngine
from src.collector import SystemCollector

PORT = 8000
HOST = "0.0.0.0"

# Connected SSE client queues
sse_clients = []
sse_lock = threading.Lock()

def broadcast_event(event_type, data):
    """Broadcast real-time updates to all connected browser dashboards."""
    payload = f"data: {json.dumps({'type': event_type, **data})}\n\n"
    with sse_lock:
        dead_clients = []
        for client in sse_clients:
            try:
                client.wfile.write(payload.encode("utf-8"))
                client.wfile.flush()
            except Exception:
                dead_clients.append(client)
        for dead in dead_clients:
            if dead in sse_clients:
                sse_clients.remove(dead)


class LabWatchRequestHandler(BaseHTTPRequestHandler):
    # Disable default chatty logging
    def log_message(self, format, *args):
        pass

    def send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Device-Token")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Device-Token")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Serve Dashboard HTML or Process Monitor HTML
        if path == "/" or path == "/index.html":
            template_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                data = html_content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(500, f"Error loading dashboard: {e}")
            return

        if path == "/processes" or path == "/processes.html":
            template_path = os.path.join(os.path.dirname(__file__), "templates", "processes.html")
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                data = html_content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(500, f"Error loading process monitor: {e}")
            return

        # Server-Sent Events (SSE) Stream
        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with sse_lock:
                sse_clients.append(self)
            try:
                # Keep socket alive
                while True:
                    time.sleep(15)
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
            except Exception:
                with sse_lock:
                    if self in sse_clients:
                        sse_clients.remove(self)
            return

        # API: List Registered Devices
        if path == "/api/devices":
            db = Database()
            devices = db.list_devices()
            # Attach latest telemetry summary to each device
            for d in devices:
                latest = db.get_latest_telemetry(d["device_id"])
                d["latest_telemetry"] = latest
            self.send_json(200, devices)
            return

        # API: Get Specific Device Telemetry History
        if path == "/api/telemetry":
            device_id = query.get("device_id", [None])[0]
            limit = int(query.get("limit", [60])[0])
            if not device_id:
                self.send_json(400, {"error": "Missing device_id"})
                return
            db = Database()
            history = db.get_telemetry_history(device_id, limit=limit)
            self.send_json(200, history)
            return

        # API: List Alerts
        if path == "/api/alerts":
            active_only = query.get("active_only", ["0"])[0] == "1"
            db = Database()
            alerts = db.list_alerts(active_only=active_only)
            self.send_json(200, alerts)
            return

        # API: Threshold Configs
        if path == "/api/config/thresholds":
            db = Database()
            configs = db.get_alert_configs()
            self.send_json(200, configs)
            return

        # API: Mobile Client Self-Registration / Info Ping
        if path == "/api/client/ping":
            self.send_json(200, {
                "server": "LabWatch Core v1.0",
                "client_ip": self.client_address[0],
                "status": "ready"
            })
            return

        # API: Get Latest Process Snapshot for Device
        if path == "/api/processes/latest":
            device_id = query.get("device_id", [None])[0]
            if not device_id:
                self.send_json(400, {"error": "Missing device_id query param"})
                return
            db = Database()
            snap = db.get_latest_process_snapshot(device_id)
            if not snap:
                self.send_json(200, {
                    "device_id": device_id,
                    "total_processes": 0,
                    "total_cpu_pct": 0.0,
                    "total_ram_pct": 0.0,
                    "total_ram_used_gb": 0.0,
                    "processes": [],
                    "recorded_at": None,
                    "is_stale": True
                })
                return
            # Check staleness (if snapshot > 45s old)
            recorded_at = snap.get("recorded_at")
            is_stale = False
            if recorded_at:
                try:
                    from datetime import datetime, timezone
                    now_utc = datetime.now(timezone.utc)
                    rec_utc = datetime.fromisoformat(recorded_at)
                    if rec_utc.tzinfo is None:
                        rec_utc = rec_utc.replace(tzinfo=timezone.utc)
                    if (now_utc - rec_utc).total_seconds() > 45:
                        is_stale = True
                except Exception:
                    pass
            snap["is_stale"] = is_stale
            self.send_json(200, snap)
            return

        # API: Get Historical Process Telemetry (trends for selected process or overall)
        if path == "/api/processes/history":
            device_id = query.get("device_id", [None])[0]
            process_name = query.get("name", [None])[0]
            limit = int(query.get("limit", [60])[0])
            if not device_id:
                self.send_json(400, {"error": "Missing device_id query param"})
                return
            db = Database()
            hist = db.get_process_history(device_id, process_name=process_name, limit=limit)
            self.send_json(200, hist)
            return

        # API: Export Process Records to CSV
        if path == "/api/processes/export":
            device_id = query.get("device_id", [None])[0]
            process_name = query.get("name", [None])[0]
            limit = int(query.get("limit", [1000])[0])
            db = Database()
            records = db.get_process_export_records(device_id=device_id, process_name=process_name, limit=limit)

            import io
            import csv
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["device_id", "hostname", "pid", "process_name", "cpu_pct", "mem_pct", "mem_mb", "status", "start_time", "recorded_at"])
            for r in records:
                writer.writerow([
                    r.get("device_id", ""),
                    r.get("hostname", ""),
                    r.get("pid", 0),
                    r.get("name", ""),
                    r.get("cpu_pct", 0.0),
                    r.get("mem_pct", 0.0),
                    r.get("mem_mb", 0.0),
                    r.get("status", ""),
                    r.get("start_time", ""),
                    r.get("recorded_at", "")
                ])
            csv_bytes = out.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f"attachment; filename=labwatch_processes_{device_id or 'all'}.csv")
            self.send_header("Content-Length", str(len(csv_bytes)))
            self.end_headers()
            self.wfile.write(csv_bytes)
            return

        # 7. Device Status Update (Graceful Shutdown / Immediate Offline)
        if path == "/api/devices/status":
            device_id = body.get("device_id")
            new_status = body.get("status", "offline")
            if not device_id:
                self.send_json(400, {"error": "device_id required"})
                return
            db.update_device_status(device_id, new_status)
            broadcast_event("device_status_change", {"device_id": device_id, "status": new_status})
            self.send_json(200, {"status": "updated", "device_id": device_id, "new_status": new_status})
            return

        # 8. Batch Deactivate / Disconnect Simulated Devices
        if path == "/api/devices/batch-status":
            device_ids = body.get("device_ids", [])
            new_status = body.get("status", "offline")
            for did in device_ids:
                db.update_device_status(did, new_status)
            broadcast_event("device_status_change", {"device_ids": device_ids, "status": new_status})
            self.send_json(200, {"status": "batch_updated", "count": len(device_ids)})
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)

        try:
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            self.send_json(400, {"error": "Invalid JSON body"})
            return

        db = Database()
        alert_engine = AlertEngine(db)

        # 1. Device Registration API
        if path == "/api/devices/register":
            device_id = body.get("device_id")
            hostname = body.get("hostname")
            os_type = body.get("os_type", "Unknown")
            token_hash = body.get("token", "default_token")
            agent_version = body.get("agent_version", "1.0.0")
            device_type = body.get("device_type", "computer")

            if not device_id or not hostname:
                self.send_json(400, {"error": "device_id and hostname are required"})
                return

            client_ip = self.client_address[0]
            dev = db.register_device(
                device_id=device_id,
                hostname=hostname,
                os_type=os_type,
                ip_address=client_ip,
                agent_version=agent_version,
                token_hash=token_hash,
                device_type=device_type
            )
            broadcast_event("device_registered", {"device_id": device_id, "hostname": hostname})
            self.send_json(200, {"status": "registered", "device": dev})
            return

        # 2. Telemetry Ingestion API
        if path == "/api/telemetry":
            device_id = body.get("device_id")
            token = self.headers.get("X-Device-Token") or body.get("token")

            if not device_id:
                self.send_json(400, {"error": "device_id required"})
                return

            # Verify device exists and token matches
            dev = db.get_device(device_id)
            if not dev:
                self.send_json(404, {"error": "Device not registered"})
                return
            if dev["token_hash"] and token and dev["token_hash"] != token:
                self.send_json(403, {"error": "Unauthorized device token"})
                return

            cpu_pct = float(body.get("cpu_pct", 0.0))
            ram_pct = float(body.get("ram_pct", 0.0))
            ram_used_gb = float(body.get("ram_used_gb", 0.0))
            ram_total_gb = float(body.get("ram_total_gb", 0.0))
            disk_pct = float(body.get("disk_pct", 0.0))
            disk_free_gb = float(body.get("disk_free_gb", 0.0))
            disk_total_gb = float(body.get("disk_total_gb", 0.0))
            uptime_hours = float(body.get("uptime_hours", 0.0))
            is_simulated = int(body.get("is_simulated", 0))
            sensor_notes = body.get("sensor_notes", "")

            db.record_telemetry(
                device_id=device_id,
                cpu_pct=cpu_pct,
                ram_pct=ram_pct,
                ram_used_gb=ram_used_gb,
                ram_total_gb=ram_total_gb,
                disk_pct=disk_pct,
                disk_free_gb=disk_free_gb,
                disk_total_gb=disk_total_gb,
                uptime_hours=uptime_hours,
                is_simulated=is_simulated,
                sensor_notes=sensor_notes
            )

            # Evaluate thresholds and create alerts if violated
            new_alerts = alert_engine.evaluate_telemetry(device_id, body, is_simulated=is_simulated)

            broadcast_event("telemetry", {"device_id": device_id, "cpu_pct": cpu_pct, "ram_pct": ram_pct})
            if new_alerts:
                broadcast_event("alert", {"device_id": device_id, "alerts": new_alerts})

            self.send_json(200, {"status": "ok", "alerts_triggered": len(new_alerts)})
            return

        # 2b. Process Telemetry Ingestion API
        if path == "/api/processes":
            device_id = body.get("device_id")
            token = self.headers.get("X-Device-Token") or body.get("token")

            if not device_id:
                self.send_json(400, {"error": "device_id required"})
                return

            dev = db.get_device(device_id)
            if not dev:
                self.send_json(404, {"error": "Device not registered"})
                return
            if dev["token_hash"] and token and dev["token_hash"] != token:
                self.send_json(403, {"error": "Unauthorized device token"})
                return

            total_processes = int(body.get("total_processes", 0))
            total_cpu_pct = float(body.get("total_cpu_pct", 0.0))
            total_ram_pct = float(body.get("total_ram_pct", 0.0))
            total_ram_used_gb = float(body.get("total_ram_used_gb", 0.0))
            processes = body.get("processes", [])

            snapshot_id = db.record_process_snapshot(
                device_id=device_id,
                total_processes=total_processes,
                total_cpu_pct=total_cpu_pct,
                total_ram_pct=total_ram_pct,
                total_ram_used_gb=total_ram_used_gb,
                processes=processes
            )

            broadcast_event("processes_updated", {
                "device_id": device_id,
                "snapshot_id": snapshot_id,
                "total_processes": total_processes,
                "total_cpu_pct": total_cpu_pct,
                "total_ram_pct": total_ram_pct
            })

            self.send_json(200, {"status": "ok", "snapshot_id": snapshot_id, "processes_recorded": len(processes)})
            return

        # 3. Heartbeat Ingestion API
        if path == "/api/heartbeat":
            device_id = body.get("device_id")
            if not device_id:
                self.send_json(400, {"error": "device_id required"})
                return
            db.update_heartbeat(device_id, ip_address=self.client_address[0])
            self.send_json(200, {"status": "heartbeat_acknowledged"})
            return

        # 4. Inject Safe Demo Alert API
        if path == "/api/alerts/test":
            device_id = body.get("device_id")
            test_type = body.get("test_type", "simulated_overheating")
            if not device_id:
                self.send_json(400, {"error": "device_id required"})
                return
            aid = alert_engine.inject_test_alert(device_id, test_type=test_type)
            broadcast_event("alert", {"device_id": device_id, "test_alert_id": aid})
            self.send_json(200, {"status": "test_alert_injected", "alert_id": aid})
            return

        # 5. Resolve Alert API
        if path.startswith("/api/alerts/") and path.endswith("/resolve"):
            parts = path.strip("/").split("/")
            try:
                alert_id = int(parts[2])
                db.resolve_alert(alert_id)
                broadcast_event("alert", {"resolved_id": alert_id})
                self.send_json(200, {"status": "resolved"})
                return
            except Exception as e:
                self.send_json(400, {"error": str(e)})
                return

        # 5b. Clear/Resolve ALL Alerts API
        if path == "/api/alerts/clear-all":
            try:
                conn = db.get_connection()
                with conn:
                    conn.execute("UPDATE alerts SET is_resolved = 1 WHERE is_resolved = 0")
                broadcast_event("alert", {"action": "cleared_all"})
                self.send_json(200, {"status": "all_alerts_cleared"})
                return
            except Exception as e:
                self.send_json(500, {"error": str(e)})
                return

        # 6. Update Thresholds API
        if path == "/api/config/thresholds":
            metric = body.get("metric_name")
            warn = float(body.get("warning_threshold", 80.0))
            crit = float(body.get("critical_threshold", 90.0))
            en = int(body.get("is_enabled", 1))
            if not metric:
                self.send_json(400, {"error": "metric_name required"})
                return
            # Safety check: critical must be >= warning
            if crit < warn:
                crit, warn = warn, crit
            db.update_alert_config(metric, warn, crit, en)
            self.send_json(200, {"status": "threshold_updated"})
            return

        # 7. Device Status Update (Graceful Shutdown / Immediate Offline)
        if path == "/api/devices/status":
            device_id = body.get("device_id")
            new_status = body.get("status", "offline")
            if not device_id:
                self.send_json(400, {"error": "device_id required"})
                return
            db.update_device_status(device_id, new_status)
            broadcast_event("device_status_change", {"device_id": device_id, "status": new_status})
            self.send_json(200, {"status": "updated", "device_id": device_id, "new_status": new_status})
            return

        # 8. Batch Deactivate / Disconnect Simulated Devices
        if path == "/api/devices/batch-status":
            device_ids = body.get("device_ids", [])
            new_status = body.get("status", "offline")
            for did in device_ids:
                db.update_device_status(did, new_status)
            broadcast_event("device_status_change", {"device_ids": device_ids, "status": new_status})
            self.send_json(200, {"status": "batch_updated", "count": len(device_ids)})
            return

        self.send_error(404, "Not Found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/devices/"):
            device_id = path.replace("/api/devices/", "").strip()
            if device_id:
                db = Database()
                db.delete_device(device_id)
                broadcast_event("device_removed", {"device_id": device_id})
                self.send_json(200, {"status": "deleted", "device_id": device_id})
                return
        self.send_error(404, "Not Found")


def heartbeat_checker_worker():
    """Background worker that continuously inspects device heartbeats and flags offline nodes."""
    db = Database()
    alert_engine = AlertEngine(db)
    while True:
        try:
            offline = alert_engine.check_heartbeats()
            if offline:
                broadcast_event("device_status_change", {"offline_devices": offline})
        except Exception as e:
            pass
        time.sleep(5)


def run_server(port=PORT):
    # Initialize DB
    db = Database()
    collector = SystemCollector()
    local_ip = collector.get_local_ip()

    # Start background heartbeat daemon
    hb_thread = threading.Thread(target=heartbeat_checker_worker, daemon=True)
    hb_thread.start()

    server = ThreadedHTTPServer((HOST, port), LabWatchRequestHandler)
    print("=" * 65)
    print(f"[START] LabWatch Central Server Active")
    print(f"[*] Local Access:   http://localhost:{port}")
    print(f"[*] Network/Mobile: http://{local_ip}:{port}")
    print("=" * 65)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down LabWatch Server...")
        server.server_close()


if __name__ == "__main__":
    run_server()
