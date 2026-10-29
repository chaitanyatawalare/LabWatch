"""
LabWatch Client Monitoring Agent
Runs on monitored computers (Windows, Linux, macOS).
Gathers real CPU, RAM, Disk, Uptime, Hostname, and Network metrics,
then securely streams telemetry and heartbeats to the LabWatch server.
"""

import sys
import os
import json
import time
import socket
import urllib.request
import urllib.parse
import hashlib
import uuid
import threading

# Add parent directory to path so agent can be executed from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.collector import SystemCollector

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_config.json")

class LabWatchAgent:
    def __init__(self, server_url=None, interval=1, device_id=None):
        self.server_url = (server_url or DEFAULT_SERVER_URL).rstrip("/")
        self.interval = interval
        self.collector = SystemCollector()
        self.config = self._load_or_create_config(device_id)
        self.device_id = self.config["device_id"]
        self.token = self.config["token"]
        self._running = False
        self._process_thread = None

    def _load_or_create_config(self, forced_device_id=None):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if forced_device_id:
                        cfg["device_id"] = forced_device_id
                    return cfg
            except Exception:
                pass

        # Generate persistent unique device ID based on hostname and MAC/UUID
        hostname = self.collector.get_hostname()
        unique_seed = f"{hostname}-{uuid.getnode()}"
        device_id = forced_device_id or f"PC-{hashlib.md5(unique_seed.encode()).hexdigest()[:8].upper()}"
        token = hashlib.sha256(f"{device_id}-labwatch-secret".encode()).hexdigest()[:24]

        cfg = {
            "device_id": device_id,
            "token": token,
            "server_url": self.server_url,
            "agent_version": "1.0.0"
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
        except Exception:
            pass
        return cfg

    def _send_request(self, endpoint, data):
        url = f"{self.server_url}{endpoint}"
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Device-Token": self.token
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"error": str(e)}

    def register(self):
        print(f"[*] Registering agent [{self.device_id}] with LabWatch server ({self.server_url})...")
        payload = {
            "device_id": self.device_id,
            "hostname": self.collector.get_hostname(),
            "os_type": self.collector.get_os_info(),
            "token": self.token,
            "agent_version": "1.0.0",
            "device_type": "computer"
        }
        resp = self._send_request("/api/devices/register", payload)
        if "error" in resp:
            print(f"[!] Registration attempt warning: {resp['error']}")
            return False
        print(f"[+] Successfully registered device: {self.device_id}")
        return True

    def send_heartbeat(self):
        resp = self._send_request("/api/heartbeat", {"device_id": self.device_id})
        return resp.get("status") == "heartbeat_acknowledged"

    def send_telemetry(self):
        metrics = self.collector.collect_all()
        metrics["device_id"] = self.device_id
        metrics["token"] = self.token
        resp = self._send_request("/api/telemetry", metrics)
        return resp

    def send_processes(self, max_processes=50):
        """Collect and stream real-time process telemetry to server."""
        proc_data = self.collector.collect_processes(max_processes=max_processes)
        mem = self.collector.get_memory_info()
        payload = {
            "device_id": self.device_id,
            "token": self.token,
            "total_processes": proc_data.get("total_processes", 0),
            "total_cpu_pct": self.collector.get_cpu_utilization(),
            "total_ram_pct": mem.get("ram_pct", 0.0),
            "total_ram_used_gb": mem.get("ram_used_gb", 0.0),
            "processes": proc_data.get("processes", [])
        }
        resp = self._send_request("/api/processes", payload)
        return resp

    def _process_stream_worker(self):
        """Asynchronous worker that scans and streams processes without delaying CPU/RAM telemetry."""
        while self._running:
            try:
                proc_resp = self.send_processes(max_processes=50)
                time.sleep(2.0)
            except Exception:
                time.sleep(2.0)

    def start(self, once=False):
        self._running = True
        print("=" * 60)
        print(f"[AGENT] LabWatch Monitoring Agent Active")
        print(f"[*] Device ID: {self.device_id} | Host: {self.collector.get_hostname()}")
        print(f"[*] Target Server: {self.server_url}")
        print(f"[*] Real-time CPU/RAM Telemetry Interval: {self.interval}s")
        print("=" * 60)

        # Ensure registration
        self.register()

        # Start asynchronous process streamer in background thread
        if not once:
            self._process_thread = threading.Thread(target=self._process_stream_worker, daemon=True)
            self._process_thread.start()

        cycle_count = 0
        while self._running:
            try:
                cycle_count += 1
                resp = self.send_telemetry()
                if "error" in resp:
                    print(f"[{time.strftime('%X')}] ⚠️ Telemetry send failed: {resp['error']}")
                    if "not registered" in str(resp.get("error", "")).lower():
                        self.register()
                else:
                    latest = self.collector.collect_all()
                    print(f"[{time.strftime('%X')}] [OK] Telemetry sent - CPU: {latest['cpu_pct']}% | RAM: {latest['ram_pct']}% | Disk: {latest['disk_pct']}%")

                if once:
                    self.send_processes()
                    break

                time.sleep(self.interval)
            except KeyboardInterrupt:
                print("\n[!] Agent stopped by user.")
                break
            except Exception as e:
                print(f"[!] Agent loop exception: {e}")
                time.sleep(self.interval)

    def stop(self):
        self._running = False


if __name__ == "__main__":
    # Support CLI arguments: python agent.py [http://SERVER_IP:8000] [INTERVAL] [OPTIONAL_DEVICE_ID]
    server = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SERVER_URL
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    forced_id = sys.argv[3] if len(sys.argv) > 3 else None

    agent = LabWatchAgent(server_url=server, interval=interval, device_id=forced_id)
    agent.start()
