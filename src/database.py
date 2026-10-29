"""
LabWatch Database Layer
SQLite persistence for devices, telemetry, heartbeats, alerts, and system config.
"""

import sqlite3
import json
import os
import threading
from datetime import datetime, timezone

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "labwatch.db")

class Database:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_FILE
        self._local = threading.local()
        self.init_schema()

    def get_connection(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
            self._local.conn.row_factory = sqlite3.Row
            # Enable WAL mode for concurrent reads and writes
            self._local.conn.execute("PRAGMA journal_mode=WAL;")
            self._local.conn.execute("PRAGMA foreign_keys=ON;")
        return self._local.conn

    def init_schema(self):
        conn = self.get_connection()
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                os_type TEXT NOT NULL,
                ip_address TEXT,
                agent_version TEXT,
                device_type TEXT DEFAULT 'computer',
                token_hash TEXT NOT NULL,
                status TEXT DEFAULT 'offline',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                cpu_pct REAL,
                ram_pct REAL,
                ram_used_gb REAL,
                ram_total_gb REAL,
                disk_pct REAL,
                disk_free_gb REAL,
                disk_total_gb REAL,
                uptime_hours REAL,
                net_bytes_sent INTEGER,
                net_bytes_recv INTEGER,
                is_simulated INTEGER DEFAULT 0,
                sensor_notes TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices (device_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                severity TEXT NOT NULL, /* 'warning' or 'critical' */
                message TEXT NOT NULL,
                current_value REAL,
                threshold_value REAL,
                is_acknowledged INTEGER DEFAULT 0,
                is_resolved INTEGER DEFAULT 0,
                is_simulated INTEGER DEFAULT 0,
                troubleshooting TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices (device_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS alert_configs (
                metric_name TEXT PRIMARY KEY,
                warning_threshold REAL,
                critical_threshold REAL,
                is_enabled INTEGER DEFAULT 1,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS process_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                total_processes INTEGER DEFAULT 0,
                total_cpu_pct REAL DEFAULT 0.0,
                total_ram_pct REAL DEFAULT 0.0,
                total_ram_used_gb REAL DEFAULT 0.0,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices (device_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS process_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER,
                device_id TEXT NOT NULL,
                pid INTEGER NOT NULL,
                name TEXT NOT NULL,
                cpu_pct REAL DEFAULT 0.0,
                mem_pct REAL DEFAULT 0.0,
                mem_mb REAL DEFAULT 0.0,
                status TEXT DEFAULT 'running',
                start_time TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (snapshot_id) REFERENCES process_snapshots (id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices (device_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_telemetry_device_time ON telemetry (device_id, recorded_at);
            CREATE INDEX IF NOT EXISTS idx_alerts_device_status ON alerts (device_id, is_resolved);
            CREATE INDEX IF NOT EXISTS idx_process_records_device_time ON process_records (device_id, recorded_at);
            CREATE INDEX IF NOT EXISTS idx_process_records_name ON process_records (device_id, name);
            CREATE INDEX IF NOT EXISTS idx_process_snapshots_device ON process_snapshots (device_id, recorded_at);
            """)

            # Seed default threshold configurations if not present
            defaults = [
                ('cpu_pct', 75.0, 90.0, 1, 'CPU utilization percentage threshold'),
                ('ram_pct', 80.0, 92.0, 1, 'Memory utilization percentage threshold'),
                ('disk_pct', 85.0, 95.0, 1, 'Disk space utilization percentage threshold'),
                ('heartbeat_timeout_sec', 30.0, 60.0, 1, 'Heartbeat staleness detection timeout')
            ]
            for metric, warn, crit, en, desc in defaults:
                conn.execute("""
                    INSERT OR IGNORE INTO alert_configs (metric_name, warning_threshold, critical_threshold, is_enabled, description)
                    VALUES (?, ?, ?, ?, ?)
                """, (metric, warn, crit, en, desc))

    # --- Device Operations ---
    def register_device(self, device_id, hostname, os_type, ip_address, agent_version, token_hash, device_type="computer", metadata=None):
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute("""
                INSERT INTO devices (device_id, hostname, os_type, ip_address, agent_version, token_hash, device_type, status, registered_at, last_seen_at, is_active, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'online', ?, ?, 1, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    hostname=excluded.hostname,
                    os_type=excluded.os_type,
                    ip_address=excluded.ip_address,
                    agent_version=excluded.agent_version,
                    token_hash=excluded.token_hash,
                    device_type=excluded.device_type,
                    status='online',
                    last_seen_at=excluded.last_seen_at,
                    is_active=1,
                    metadata=excluded.metadata
            """, (device_id, hostname, os_type, ip_address, agent_version, token_hash, device_type, now, now, json.dumps(metadata or {})))
        return self.get_device(device_id)

    def get_device(self, device_id):
        conn = self.get_connection()
        cursor = conn.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_devices(self, include_inactive=False):
        conn = self.get_connection()
        query = "SELECT * FROM devices" if include_inactive else "SELECT * FROM devices WHERE is_active = 1"
        query += " ORDER BY status DESC, hostname ASC"
        cursor = conn.execute(query)
        return [dict(r) for r in cursor.fetchall()]

    def update_heartbeat(self, device_id, ip_address=None):
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            if ip_address:
                conn.execute("UPDATE devices SET last_seen_at = ?, status = 'online', ip_address = ? WHERE device_id = ?", (now, ip_address, device_id))
            else:
                conn.execute("UPDATE devices SET last_seen_at = ?, status = 'online' WHERE device_id = ?", (now, device_id))

    def update_device_status(self, device_id, status):
        conn = self.get_connection()
        with conn:
            conn.execute("UPDATE devices SET status = ? WHERE device_id = ?", (status, device_id))

    def delete_device(self, device_id):
        conn = self.get_connection()
        with conn:
            conn.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))

    # --- Telemetry Operations ---
    def record_telemetry(self, device_id, cpu_pct, ram_pct, ram_used_gb, ram_total_gb,
                         disk_pct, disk_free_gb, disk_total_gb, uptime_hours,
                         net_bytes_sent=0, net_bytes_recv=0, is_simulated=0, sensor_notes=None):
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute("""
                INSERT INTO telemetry (
                    device_id, cpu_pct, ram_pct, ram_used_gb, ram_total_gb,
                    disk_pct, disk_free_gb, disk_total_gb, uptime_hours,
                    net_bytes_sent, net_bytes_recv, is_simulated, sensor_notes, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, cpu_pct, ram_pct, ram_used_gb, ram_total_gb,
                disk_pct, disk_free_gb, disk_total_gb, uptime_hours,
                net_bytes_sent, net_bytes_recv, is_simulated, sensor_notes, now
            ))
            # Also update last seen
            conn.execute("UPDATE devices SET last_seen_at = ?, status = 'online' WHERE device_id = ?", (now, device_id))

    def get_latest_telemetry(self, device_id):
        conn = self.get_connection()
        cursor = conn.execute("""
            SELECT * FROM telemetry WHERE device_id = ? ORDER BY id DESC LIMIT 1
        """, (device_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_telemetry_history(self, device_id, limit=60):
        conn = self.get_connection()
        cursor = conn.execute("""
            SELECT * FROM telemetry WHERE device_id = ? ORDER BY id DESC LIMIT ?
        """, (device_id, limit))
        rows = cursor.fetchall()
        # Return in chronological order
        return [dict(r) for r in reversed(rows)]

    # --- Alert Operations ---
    def create_alert(self, device_id, metric_name, severity, message, current_value, threshold_value, is_simulated=0, troubleshooting=None):
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            # Check if active unacknowledged alert already exists for device + metric to avoid spamming
            cursor = conn.execute("""
                SELECT id FROM alerts
                WHERE device_id = ? AND metric_name = ? AND is_resolved = 0
            """, (device_id, metric_name))
            existing = cursor.fetchone()
            if existing:
                # Update current value
                conn.execute("""
                    UPDATE alerts SET current_value = ?, message = ?, severity = ?
                    WHERE id = ?
                """, (current_value, message, severity, existing["id"]))
                return existing["id"]

            cursor = conn.execute("""
                INSERT INTO alerts (
                    device_id, metric_name, severity, message, current_value,
                    threshold_value, is_acknowledged, is_resolved, is_simulated,
                    troubleshooting, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
            """, (
                device_id, metric_name, severity, message, current_value,
                threshold_value, is_simulated, troubleshooting, now
            ))
            return cursor.lastrowid

    def acknowledge_alert(self, alert_id):
        conn = self.get_connection()
        with conn:
            conn.execute("UPDATE alerts SET is_acknowledged = 1 WHERE id = ?", (alert_id,))

    def resolve_alert(self, alert_id):
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute("UPDATE alerts SET is_resolved = 1, resolved_at = ? WHERE id = ?", (now, alert_id))

    def resolve_metric_alerts(self, device_id, metric_name):
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute("""
                UPDATE alerts SET is_resolved = 1, resolved_at = ?
                WHERE device_id = ? AND metric_name = ? AND is_resolved = 0
            """, (now, device_id, metric_name))

    def list_alerts(self, active_only=False, limit=50):
        conn = self.get_connection()
        query = "SELECT a.*, d.hostname FROM alerts a JOIN devices d ON a.device_id = d.device_id"
        if active_only:
            query += " WHERE a.is_resolved = 0"
        query += " ORDER BY a.id DESC LIMIT ?"
        cursor = conn.execute(query, (limit,))
        return [dict(r) for r in cursor.fetchall()]

    def get_alert_configs(self):
        conn = self.get_connection()
        cursor = conn.execute("SELECT * FROM alert_configs")
        return {r["metric_name"]: dict(r) for r in cursor.fetchall()}

    def update_alert_config(self, metric_name, warning_threshold, critical_threshold, is_enabled):
        conn = self.get_connection()
        with conn:
            conn.execute("""
                UPDATE alert_configs SET warning_threshold = ?, critical_threshold = ?, is_enabled = ?
                WHERE metric_name = ?
            """, (warning_threshold, critical_threshold, is_enabled, metric_name))

    # --- Process Telemetry & Analytics Operations ---
    def record_process_snapshot(self, device_id, total_processes, total_cpu_pct, total_ram_pct, total_ram_used_gb, processes, max_history_per_device=500):
        """
        Record a process snapshot and its process records.
        Applies a retention policy to purge old snapshots and prevent excessive database growth.
        """
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            cursor = conn.execute("""
                INSERT INTO process_snapshots (device_id, total_processes, total_cpu_pct, total_ram_pct, total_ram_used_gb, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (device_id, total_processes, total_cpu_pct, total_ram_pct, total_ram_used_gb, now))
            snapshot_id = cursor.lastrowid

            if processes:
                # Insert top processes associated with this snapshot
                rows = []
                for p in processes:
                    rows.append((
                        snapshot_id,
                        device_id,
                        int(p.get("pid", 0)),
                        str(p.get("name", "Unknown")),
                        float(p.get("cpu_pct", 0.0)),
                        float(p.get("mem_pct", 0.0)),
                        float(p.get("mem_mb", 0.0)),
                        str(p.get("status", "running")),
                        str(p.get("start_time", "N/A")),
                        now
                    ))
                conn.executemany("""
                    INSERT INTO process_records (
                        snapshot_id, device_id, pid, name, cpu_pct, mem_pct, mem_mb, status, start_time, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)

            # Retention policy: keep latest N snapshots per device
            conn.execute("""
                DELETE FROM process_snapshots
                WHERE device_id = ? AND id NOT IN (
                    SELECT id FROM process_snapshots WHERE device_id = ? ORDER BY id DESC LIMIT ?
                )
            """, (device_id, device_id, max_history_per_device))

            # Prune orphan process records if cascading didn't catch them
            conn.execute("""
                DELETE FROM process_records
                WHERE snapshot_id NOT IN (SELECT id FROM process_snapshots)
            """)

        return snapshot_id

    def get_latest_process_snapshot(self, device_id):
        """Get the latest process snapshot and its associated process list for a device."""
        conn = self.get_connection()
        cursor = conn.execute("""
            SELECT * FROM process_snapshots WHERE device_id = ? ORDER BY id DESC LIMIT 1
        """, (device_id,))
        snapshot = cursor.fetchone()
        if not snapshot:
            return None

        snap_dict = dict(snapshot)
        proc_cursor = conn.execute("""
            SELECT pid, name, cpu_pct, mem_pct, mem_mb, status, start_time
            FROM process_records
            WHERE snapshot_id = ?
            ORDER BY cpu_pct DESC, mem_mb DESC
        """, (snap_dict["id"],))
        snap_dict["processes"] = [dict(r) for r in proc_cursor.fetchall()]
        return snap_dict

    def get_process_history(self, device_id, process_name=None, limit=100):
        """Retrieve historical telemetry records for trend charts and resource analytics."""
        conn = self.get_connection()
        if process_name:
            cursor = conn.execute("""
                SELECT pid, name, cpu_pct, mem_pct, mem_mb, status, start_time, recorded_at
                FROM process_records
                WHERE device_id = ? AND name LIKE ?
                ORDER BY id DESC LIMIT ?
            """, (device_id, f"%{process_name}%", limit))
        else:
            cursor = conn.execute("""
                SELECT pid, name, cpu_pct, mem_pct, mem_mb, status, start_time, recorded_at
                FROM process_records
                WHERE device_id = ?
                ORDER BY id DESC LIMIT ?
            """, (device_id, limit))
        rows = cursor.fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_process_export_records(self, device_id=None, process_name=None, limit=1000):
        """Export process records for CSV generation."""
        conn = self.get_connection()
        query = "SELECT p.device_id, d.hostname, p.pid, p.name, p.cpu_pct, p.mem_pct, p.mem_mb, p.status, p.start_time, p.recorded_at FROM process_records p JOIN devices d ON p.device_id = d.device_id WHERE 1=1"
        params = []
        if device_id:
            query += " AND p.device_id = ?"
            params.append(device_id)
        if process_name:
            query += " AND p.name LIKE ?"
            params.append(f"%{process_name}%")
        query += " ORDER BY p.id DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, tuple(params))
        return [dict(r) for r in cursor.fetchall()]
