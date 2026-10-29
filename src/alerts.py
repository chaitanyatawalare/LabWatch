"""
LabWatch Alert & Diagnostic Engine
Evaluates telemetry against configurable thresholds, detects heartbeat timeouts,
generates actionable diagnostic advice, and supports safe demonstration test alerts.
"""

from datetime import datetime, timezone

TROUBLESHOOTING_GUIDE = {
    "cpu_pct": (
        "High CPU utilization detected (> {thresh}%). "
        "Diagnostic steps: 1. Open Task Manager to inspect processes consuming CPU cycles. "
        "2. Check for runaway computational tasks, malware, or infinite loops. "
        "3. Consider process throttling or optimizing background agent threads."
    ),
    "ram_pct": (
        "High RAM consumption detected (> {thresh}%). "
        "Diagnostic steps: 1. Identify memory-leaking applications in Task Manager/Resource Monitor. "
        "2. Close unneeded heavy browser tabs or IDE instances. "
        "3. Ensure the host has adequate virtual pagefile allocated."
    ),
    "disk_pct": (
        "Critically low disk storage remaining (> {thresh}% full). "
        "Diagnostic steps: 1. Clear %TEMP% and temporary cache folders. "
        "2. Empty Recycle Bin and remove old lab student build artifacts. "
        "3. Run Windows Disk Cleanup (`cleanmgr.exe`)."
    ),
    "heartbeat": (
        "Agent heartbeat missing for more than {thresh} seconds. "
        "Diagnostic steps: 1. Verify if the client PC is powered on or in sleep mode. "
        "2. Check local network connectivity (Wi-Fi/Ethernet) and ping IP {ip}. "
        "3. Verify that the LabWatch agent process is running on the client."
    ),
    "simulated_overheating": (
        "[DEMO / SIMULATION] Simulated Thermal Threshold Alert. "
        "Diagnostic steps: This is a safe software demonstration alert. "
        "No actual hardware heating occurred. In real scenarios: check fan vents, airflow, and thermal paste."
    ),
    "simulated_cpu_spike": (
        "[DEMO / SIMULATION] Simulated High CPU Workload Spike. "
        "Diagnostic steps: Safe software test alert. Allows testing real-time notification popups without stressing hardware."
    )
}

class AlertEngine:
    def __init__(self, db):
        self.db = db

    def evaluate_telemetry(self, device_id, telemetry_data, is_simulated=0):
        """
        Evaluate real or test telemetry against active database thresholds.
        """
        configs = self.db.get_alert_configs()
        alerts_generated = []

        metrics_to_check = [
            ("cpu_pct", "CPU Utilization"),
            ("ram_pct", "Memory Utilization"),
            ("disk_pct", "Disk Utilization")
        ]

        for metric_key, label in metrics_to_check:
            val = telemetry_data.get(metric_key)
            if val is None:
                continue

            cfg = configs.get(metric_key)
            if not cfg or not cfg["is_enabled"]:
                continue

            warn_th = cfg["warning_threshold"]
            crit_th = cfg["critical_threshold"]

            if val >= crit_th:
                msg = f"CRITICAL: {label} reached {val}% (Limit: {crit_th}%)"
                guide = TROUBLESHOOTING_GUIDE.get(metric_key, "").format(thresh=crit_th)
                aid = self.db.create_alert(
                    device_id=device_id,
                    metric_name=metric_key,
                    severity="critical",
                    message=msg,
                    current_value=val,
                    threshold_value=crit_th,
                    is_simulated=is_simulated,
                    troubleshooting=guide
                )
                alerts_generated.append(aid)
            elif val >= warn_th:
                msg = f"WARNING: {label} elevated at {val}% (Limit: {warn_th}%)"
                guide = TROUBLESHOOTING_GUIDE.get(metric_key, "").format(thresh=warn_th)
                aid = self.db.create_alert(
                    device_id=device_id,
                    metric_name=metric_key,
                    severity="warning",
                    message=msg,
                    current_value=val,
                    threshold_value=warn_th,
                    is_simulated=is_simulated,
                    troubleshooting=guide
                )
                alerts_generated.append(aid)
            else:
                # Value is within normal range; auto-resolve previous active alerts for this metric
                if not is_simulated:
                    self.db.resolve_metric_alerts(device_id, metric_key)

        return alerts_generated

    def check_heartbeats(self):
        """
        Scan all registered devices. If last_seen exceeds threshold, mark device offline and trigger alert.
        """
        configs = self.db.get_alert_configs()
        hb_cfg = configs.get("heartbeat_timeout_sec")
        timeout_sec = hb_cfg["warning_threshold"] if hb_cfg else 30.0

        now = datetime.now(timezone.utc)
        devices = self.db.list_devices()
        offline_devices = []

        for d in devices:
            last_seen_str = d.get("last_seen_at")
            if not last_seen_str:
                continue

            try:
                # Support ISO format
                last_seen = datetime.fromisoformat(last_seen_str)
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                diff_sec = (now - last_seen).total_seconds()
            except Exception:
                diff_sec = 0

            if diff_sec > timeout_sec:
                if d["status"] != "offline":
                    self.db.update_device_status(d["device_id"], "offline")
                    guide = TROUBLESHOOTING_GUIDE.get("heartbeat", "").format(thresh=int(timeout_sec), ip=d.get("ip_address", "Unknown"))
                    self.db.create_alert(
                        device_id=d["device_id"],
                        metric_name="heartbeat",
                        severity="warning",
                        message=f"Device {d['hostname']} ({d['device_id']}) is offline. No heartbeat for {int(diff_sec)}s.",
                        current_value=round(diff_sec, 1),
                        threshold_value=timeout_sec,
                        is_simulated=0,
                        troubleshooting=guide
                    )
                offline_devices.append(d["device_id"])
            else:
                if d["status"] == "offline":
                    self.db.update_device_status(d["device_id"], "online")
                    self.db.resolve_metric_alerts(d["device_id"], "heartbeat")

        return offline_devices

    def inject_test_alert(self, device_id, test_type="simulated_overheating"):
        """
        Safe, non-destructive test alerts for college viva and project demonstrations.
        Clearly visually tagged as [DEMO/SIMULATION].
        """
        if test_type == "simulated_overheating":
            msg = "[DEMO MODE] Simulated High Temperature Warning: 92.4°C on Thermal Zone 0"
            guide = TROUBLESHOOTING_GUIDE["simulated_overheating"]
            return self.db.create_alert(
                device_id=device_id,
                metric_name="test_thermal",
                severity="critical",
                message=msg,
                current_value=92.4,
                threshold_value=85.0,
                is_simulated=1,
                troubleshooting=guide
            )
        elif test_type == "simulated_cpu_spike":
            msg = "[DEMO MODE] Simulated Workload Spike: 98.7% CPU load across 16 threads"
            guide = TROUBLESHOOTING_GUIDE["simulated_cpu_spike"]
            return self.db.create_alert(
                device_id=device_id,
                metric_name="test_cpu",
                severity="critical",
                message=msg,
                current_value=98.7,
                threshold_value=90.0,
                is_simulated=1,
                troubleshooting=guide
            )
        return None
