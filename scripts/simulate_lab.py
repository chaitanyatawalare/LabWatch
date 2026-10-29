"""
LabWatch Lab Computer Simulator (Multi-Device Scale Demonstration)
Simulates multiple additional lab computers on the network for demonstrating
large-scale monitoring (e.g. 5, 10, or 50 lab workstations).
Each virtual lab node runs in its own lightweight thread with realistic load profiles,
registers with the server, and sends continuous heartbeats and telemetry.
"""

import sys
import os
import json
import time
import random
import threading
import urllib.request

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"

class SimulatedLabPC(threading.Thread):
    def __init__(self, pc_num, server_url=DEFAULT_SERVER_URL, interval=4):
        super().__init__(daemon=True)
        self.device_id = f"LAB-PC-{pc_num:02d}"
        self.hostname = f"LAB-DESKTOP-{pc_num:02d}"
        self.ip_address = f"192.168.1.{100 + pc_num}"
        self.server_url = server_url.rstrip("/")
        self.interval = interval
        self.token = f"sim_token_{pc_num}"
        self.running = True

        # Base specs
        self.ram_total = 16.0
        self.disk_total = 512.0
        self.disk_used = random.uniform(120.0, 240.0)

    def _post(self, endpoint, data):
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
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def register(self):
        payload = {
            "device_id": self.device_id,
            "hostname": self.hostname,
            "os_type": "Windows 11 Education (64bit)",
            "token": self.token,
            "agent_version": "1.0.0",
            "device_type": "computer"
        }
        self._post("/api/devices/register", payload)

    def run(self):
        self.register()
        while self.running:
            try:
                # Generate realistic fluctuating lab utilization
                cpu = round(random.uniform(5.0, 65.0), 1)
                # Occasional spike
                if random.random() < 0.05:
                    cpu = round(random.uniform(78.0, 94.0), 1)

                ram_pct = round(random.uniform(40.0, 75.0), 1)
                ram_used = round(self.ram_total * (ram_pct / 100.0), 2)
                disk_pct = round((self.disk_used / self.disk_total) * 100.0, 1)
                disk_free = round(self.disk_total - self.disk_used, 2)

                payload = {
                    "device_id": self.device_id,
                    "token": self.token,
                    "cpu_pct": cpu,
                    "ram_pct": ram_pct,
                    "ram_used_gb": ram_used,
                    "ram_total_gb": self.ram_total,
                    "disk_pct": disk_pct,
                    "disk_free_gb": disk_free,
                    "disk_total_gb": self.disk_total,
                    "uptime_hours": round(random.uniform(1.0, 120.0), 2),
                    "is_simulated": 0,
                    "sensor_notes": "Standard Lab Workstation Telemetry"
                }
                self._post("/api/telemetry", payload)

                # Send simulated process list periodically (every cycle)
                sim_processes = [
                    {"pid": 1042 + self.pc_num, "name": "chrome.exe", "cpu_pct": round(random.uniform(2.0, 15.0), 1), "mem_pct": 5.2, "mem_mb": 420.5, "status": "running", "start_time": "2026-10-28 08:30:00"},
                    {"pid": 2084 + self.pc_num, "name": "code.exe", "cpu_pct": round(random.uniform(1.0, 12.0), 1), "mem_pct": 4.1, "mem_mb": 350.2, "status": "running", "start_time": "2026-10-28 08:32:00"},
                    {"pid": 3120 + self.pc_num, "name": "python.exe", "cpu_pct": round(random.uniform(5.0, 35.0), 1), "mem_pct": 2.8, "mem_mb": 210.8, "status": "running", "start_time": "2026-10-28 08:35:00"},
                    {"pid": 4150 + self.pc_num, "name": "explorer.exe", "cpu_pct": round(random.uniform(0.5, 3.0), 1), "mem_pct": 1.5, "mem_mb": 115.4, "status": "running", "start_time": "2026-10-28 08:00:00"},
                    {"pid": 5200 + self.pc_num, "name": "discord.exe", "cpu_pct": round(random.uniform(0.2, 2.5), 1), "mem_pct": 2.2, "mem_mb": 180.0, "status": "running", "start_time": "2026-10-28 08:15:00"},
                ]
                proc_payload = {
                    "device_id": self.device_id,
                    "token": self.token,
                    "total_processes": 85 + self.pc_num,
                    "total_cpu_pct": cpu,
                    "total_ram_pct": ram_pct,
                    "total_ram_used_gb": ram_used,
                    "processes": sim_processes
                }
                self._post("/api/processes", proc_payload)

                time.sleep(self.interval + random.uniform(-0.5, 0.5))
            except Exception:
                time.sleep(self.interval)

    def stop(self):
        self.running = False
        # Send instant graceful offline status to server
        try:
            self._post("/api/devices/status", {"device_id": self.device_id, "status": "offline"})
        except Exception:
            pass


def launch_simulated_lab(count=5, server_url=DEFAULT_SERVER_URL):
    print("=" * 65)
    print(f"🏭 Launching {count} Simulated Lab Computers...")
    print(f"🎯 Target Server: {server_url}")
    print("=" * 65)

    nodes = []
    for i in range(1, count + 1):
        node = SimulatedLabPC(i, server_url=server_url)
        node.start()
        nodes.append(node)
        print(f" [+] Initialized {node.hostname} ({node.device_id})")

    print(f"\n[OK] All {count} nodes active and reporting to server.")
    print("Press Ctrl+C to terminate simulated lab computers.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping simulated lab computers...")
        # Batch notify server to instantly mark all simulated PCs offline
        try:
            device_ids = [n.device_id for n in nodes]
            req = urllib.request.Request(
                f"{server_url.rstrip('/')}/api/devices/batch-status",
                data=json.dumps({"device_ids": device_ids, "status": "offline"}).encode('utf-8'),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                pass
        except Exception:
            pass

        for n in nodes:
            n.stop()
        print("Done. All simulated lab nodes marked offline.")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    server = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SERVER_URL
    launch_simulated_lab(count, server)
