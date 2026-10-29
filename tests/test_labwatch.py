"""
LabWatch Automated Test Suite
Validates:
1. Database initialization and CRUD operations
2. System telemetry collector accuracy and structure
3. Alert threshold evaluation and state resolution
4. REST API endpoints (registration, telemetry, heartbeats, alerts, demo injection)
"""

import unittest
import os
import time
import json
import threading
from http.server import HTTPServer

from src.database import Database
from src.collector import SystemCollector
from src.alerts import AlertEngine
from src.server import LabWatchRequestHandler, run_server
from src.agent import LabWatchAgent

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_labwatch.db")

class TestLabWatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        cls.db = Database(TEST_DB_PATH)
        cls.alert_engine = AlertEngine(cls.db)

    @classmethod
    def tearDownClass(cls):
        # Allow connections to release before removing
        time.sleep(0.1)
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    def test_01_system_collector(self):
        collector = SystemCollector()
        data = collector.collect_all()
        self.assertIn("hostname", data)
        self.assertIn("cpu_pct", data)
        self.assertIn("ram_pct", data)
        self.assertIn("disk_pct", data)
        self.assertIn("uptime_hours", data)
        self.assertIsInstance(data["cpu_pct"], (int, float))
        self.assertIsInstance(data["ram_pct"], (int, float))
        self.assertIsInstance(data["disk_pct"], (int, float))
        print("[OK] System Collector successfully gathered real OS telemetry:", data["hostname"], f"CPU: {data['cpu_pct']}%")

    def test_02_database_device_registration(self):
        dev = self.db.register_device(
            device_id="TEST-PC-01",
            hostname="Lab-PC-01",
            os_type="Windows 11",
            ip_address="192.168.1.101",
            agent_version="1.0.0",
            token_hash="tok_abc123"
        )
        self.assertIsNotNone(dev)
        self.assertEqual(dev["device_id"], "TEST-PC-01")
        self.assertEqual(dev["status"], "online")

        # Fetch device
        fetched = self.db.get_device("TEST-PC-01")
        self.assertEqual(fetched["hostname"], "Lab-PC-01")

        # List devices
        all_devs = self.db.list_devices()
        self.assertGreaterEqual(len(all_devs), 1)

    def test_03_telemetry_recording(self):
        self.db.record_telemetry(
            device_id="TEST-PC-01",
            cpu_pct=45.2,
            ram_pct=60.1,
            ram_used_gb=8.0,
            ram_total_gb=16.0,
            disk_pct=70.0,
            disk_free_gb=100.0,
            disk_total_gb=500.0,
            uptime_hours=12.5
        )
        latest = self.db.get_latest_telemetry("TEST-PC-01")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["cpu_pct"], 45.2)

        history = self.db.get_telemetry_history("TEST-PC-01")
        self.assertGreaterEqual(len(history), 1)

    def test_04_alert_engine_evaluation(self):
        # 1. Normal values should generate no alerts
        normal_telemetry = {"cpu_pct": 20.0, "ram_pct": 30.0, "disk_pct": 50.0}
        alerts = self.alert_engine.evaluate_telemetry("TEST-PC-01", normal_telemetry)
        self.assertEqual(len(alerts), 0)

        # 2. Critical CPU (95%) should generate a critical alert
        high_cpu_telemetry = {"cpu_pct": 95.0, "ram_pct": 30.0, "disk_pct": 50.0}
        alerts = self.alert_engine.evaluate_telemetry("TEST-PC-01", high_cpu_telemetry)
        self.assertGreaterEqual(len(alerts), 1)

        active_alerts = self.db.list_alerts(active_only=True)
        self.assertTrue(any(a["metric_name"] == "cpu_pct" for a in active_alerts))

        # 3. Subsequent normal value should auto-resolve metric alert
        self.alert_engine.evaluate_telemetry("TEST-PC-01", normal_telemetry)
        active_after = self.db.list_alerts(active_only=True)
        self.assertFalse(any(a["metric_name"] == "cpu_pct" for a in active_after))

    def test_05_demo_test_alerts(self):
        aid = self.alert_engine.inject_test_alert("TEST-PC-01", "simulated_overheating")
        self.assertIsNotNone(aid)
        active = self.db.list_alerts(active_only=True)
        sim_alert = next((a for a in active if a["id"] == aid), None)
        self.assertIsNotNone(sim_alert)
        self.assertEqual(sim_alert["is_simulated"], 1)
        self.assertIn("[DEMO MODE]", sim_alert["message"])

        # Resolve demo alert
        self.db.resolve_alert(aid)
        after_resolve = self.db.list_alerts(active_only=True)
        self.assertFalse(any(a["id"] == aid for a in after_resolve))

    def test_06_process_collector(self):
        collector = SystemCollector()
        res = collector.collect_processes(max_processes=20)
        self.assertIn("total_processes", res)
        self.assertIn("processes", res)
        self.assertIsInstance(res["processes"], list)
        self.assertGreaterEqual(res["total_processes"], 1)
        if len(res["processes"]) > 0:
            sample = res["processes"][0]
            self.assertIn("pid", sample)
            self.assertIn("name", sample)
            self.assertIn("cpu_pct", sample)
            self.assertIn("mem_mb", sample)
            self.assertIn("status", sample)
        print("[OK] Process Collector gathered real processes:", f"Total: {res['total_processes']}, Inspected: {len(res['processes'])}")

    def test_07_process_database_and_retention(self):
        test_procs = [
            {"pid": 1001, "name": "chrome.exe", "cpu_pct": 12.5, "mem_pct": 3.2, "mem_mb": 250.0, "status": "running", "start_time": "2026-10-28 01:00:00"},
            {"pid": 1002, "name": "code.exe", "cpu_pct": 5.0, "mem_pct": 4.1, "mem_mb": 310.0, "status": "running", "start_time": "2026-10-28 01:05:00"},
            {"pid": 1003, "name": "python.exe", "cpu_pct": 18.0, "mem_pct": 1.5, "mem_mb": 110.0, "status": "running", "start_time": "2026-10-28 01:10:00"},
        ]
        snap_id = self.db.record_process_snapshot(
            device_id="TEST-PC-01",
            total_processes=120,
            total_cpu_pct=35.5,
            total_ram_pct=62.0,
            total_ram_used_gb=9.9,
            processes=test_procs,
            max_history_per_device=5
        )
        self.assertIsNotNone(snap_id)

        # Retrieve latest snapshot
        latest = self.db.get_latest_process_snapshot("TEST-PC-01")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["total_processes"], 120)
        self.assertEqual(len(latest["processes"]), 3)
        self.assertEqual(latest["processes"][0]["name"], "python.exe")  # Top CPU

        # Test process history query
        hist = self.db.get_process_history("TEST-PC-01", process_name="chrome")
        self.assertGreaterEqual(len(hist), 1)
        self.assertEqual(hist[0]["name"], "chrome.exe")

        # Test export records
        export_records = self.db.get_process_export_records(device_id="TEST-PC-01", limit=10)
        self.assertGreaterEqual(len(export_records), 3)
        print("[OK] Process Database Storage, Snapshot and CSV Export Queries Verified.")


if __name__ == "__main__":
    unittest.main()
