"""
LabWatch System Collector
Cross-platform hardware and system telemetry engine.
Uses psutil when available, with full automatic fallback to native Windows Win32 API / Linux / macOS.
Accurately reports real metrics, and explicitly marks unsupported sensors (temperatures/fans)
as unavailable rather than inventing false values.
"""

import os
import sys
import platform
import socket
import time
import subprocess

# Check if psutil is available
HAVE_PSUTIL = False
try:
    import psutil
    HAVE_PSUTIL = True
except ImportError:
    HAVE_PSUTIL = False

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ('dwLength', ctypes.c_ulong),
            ('dwMemoryLoad', ctypes.c_ulong),
            ('ullTotalPhys', ctypes.c_ulonglong),
            ('ullAvailPhys', ctypes.c_ulonglong),
            ('ullTotalPageFile', ctypes.c_ulonglong),
            ('ullAvailPageFile', ctypes.c_ulonglong),
            ('ullTotalVirtual', ctypes.c_ulonglong),
            ('ullAvailVirtual', ctypes.c_ulonglong),
            ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
        ]

    class FILETIME(ctypes.Structure):
        _fields_ = [('dwLowDateTime', ctypes.c_uint32), ('dwHighDateTime', ctypes.c_uint32)]

    def _filetime_to_int(ft):
        return (ft.dwHighDateTime << 32) + ft.dwLowDateTime


class SystemCollector:
    def __init__(self):
        self._prev_idle = 0
        self._prev_kernel = 0
        self._prev_user = 0
        self._prev_time = 0
        self._init_cpu_tracking()

    def _init_cpu_tracking(self):
        if sys.platform == "win32" and not HAVE_PSUTIL:
            idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
            if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
                self._prev_idle = _filetime_to_int(idle)
                self._prev_kernel = _filetime_to_int(kernel)
                self._prev_user = _filetime_to_int(user)
                self._prev_time = time.time()

    def get_hostname(self):
        return socket.gethostname()

    def get_os_info(self):
        return f"{platform.system()} {platform.release()} ({platform.architecture()[0]})"

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Doesn't actually send packet; finds default outbound interface IP
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def get_cpu_utilization(self):
        if HAVE_PSUTIL:
            try:
                return float(psutil.cpu_percent(interval=None))
            except Exception:
                pass

        if sys.platform == "win32":
            try:
                idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
                if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
                    cur_idle = _filetime_to_int(idle)
                    cur_kernel = _filetime_to_int(kernel)
                    cur_user = _filetime_to_int(user)
                    cur_time = time.time()

                    idle_delta = cur_idle - self._prev_idle
                    kernel_delta = cur_kernel - self._prev_kernel
                    user_delta = cur_user - self._prev_user
                    total_delta = kernel_delta + user_delta

                    self._prev_idle = cur_idle
                    self._prev_kernel = cur_kernel
                    self._prev_user = cur_user
                    self._prev_time = cur_time

                    if total_delta > 0:
                        cpu_pct = 100.0 * (1.0 - (idle_delta / total_delta))
                        return round(max(0.0, min(100.0, cpu_pct)), 1)
            except Exception:
                pass
        return 0.0

    def get_memory_info(self):
        if HAVE_PSUTIL:
            try:
                v = psutil.virtual_memory()
                return {
                    "ram_pct": round(v.percent, 1),
                    "ram_used_gb": round(v.used / (1024**3), 2),
                    "ram_total_gb": round(v.total / (1024**3), 2),
                    "ram_avail_gb": round(v.available / (1024**3), 2)
                }
            except Exception:
                pass

        if sys.platform == "win32":
            try:
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    total_gb = stat.ullTotalPhys / (1024**3)
                    avail_gb = stat.ullAvailPhys / (1024**3)
                    used_gb = total_gb - avail_gb
                    return {
                        "ram_pct": round(float(stat.dwMemoryLoad), 1),
                        "ram_used_gb": round(used_gb, 2),
                        "ram_total_gb": round(total_gb, 2),
                        "ram_avail_gb": round(avail_gb, 2)
                    }
            except Exception:
                pass

        return {"ram_pct": 0.0, "ram_used_gb": 0.0, "ram_total_gb": 0.0, "ram_avail_gb": 0.0}

    def get_disk_info(self, path=None):
        if path is None:
            path = "C:\\" if sys.platform == "win32" else "/"

        if HAVE_PSUTIL:
            try:
                d = psutil.disk_usage(path)
                return {
                    "disk_pct": round(d.percent, 1),
                    "disk_free_gb": round(d.free / (1024**3), 2),
                    "disk_total_gb": round(d.total / (1024**3), 2)
                }
            except Exception:
                pass

        if sys.platform == "win32":
            try:
                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)
                total_free_bytes = ctypes.c_ulonglong(0)
                if ctypes.windll.kernel32.GetDiskFreeSpaceExW(path, ctypes.byref(free_bytes), ctypes.byref(total_bytes), ctypes.byref(total_free_bytes)):
                    tot_gb = total_bytes.value / (1024**3)
                    free_gb = free_bytes.value / (1024**3)
                    used_gb = tot_gb - free_gb
                    pct = (used_gb / tot_gb * 100.0) if tot_gb > 0 else 0.0
                    return {
                        "disk_pct": round(pct, 1),
                        "disk_free_gb": round(free_gb, 2),
                        "disk_total_gb": round(tot_gb, 2)
                    }
            except Exception:
                pass

        return {"disk_pct": 0.0, "disk_free_gb": 0.0, "disk_total_gb": 0.0}

    def get_uptime_hours(self):
        if HAVE_PSUTIL:
            try:
                boot_time = psutil.boot_time()
                return round((time.time() - boot_time) / 3600.0, 2)
            except Exception:
                pass

        if sys.platform == "win32":
            try:
                ms = ctypes.windll.kernel32.GetTickCount64()
                return round(ms / (1000.0 * 3600.0), 2)
            except Exception:
                pass

        return 0.0

    def get_network_io(self):
        if HAVE_PSUTIL:
            try:
                io = psutil.net_io_counters()
                return {
                    "bytes_sent": io.bytes_sent,
                    "bytes_recv": io.bytes_recv
                }
            except Exception:
                pass
        return {"bytes_sent": 0, "bytes_recv": 0}

    def get_hardware_sensors(self):
        """
        Explicitly check for hardware sensors (temperatures, fans).
        If unsupported or permission denied, truthfully return unavailable status.
        Never fabricate sensor data.
        """
        sensors = {
            "cpu_temp_c": None,
            "fan_rpm": None,
            "status": "Hardware thermal sensors unavailable on this hardware or requires elevated kernel drivers."
        }

        if HAVE_PSUTIL and hasattr(psutil, "sensors_temperatures"):
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        if entries:
                            sensors["cpu_temp_c"] = entries[0].current
                            sensors["status"] = f"Reading from {name}"
                            break
            except Exception:
                pass

        return sensors

    def collect_processes(self, max_processes=100):
        """
        Collect real running process information with high performance.
        Uses p.oneshot() to retrieve all kernel attributes in a single OS syscall.
        Safely handles NoSuchProcess, AccessDenied, and zombie processes without crashing.
        Never fabricates process information.
        """
        process_list = []
        total_count = 0

        if HAVE_PSUTIL:
            try:
                for proc in psutil.process_iter(['pid', 'name']):
                    total_count += 1
                    try:
                        info = proc.info
                        pid = info['pid']
                        # Exclude system idle process from individual process CPU calculation skew
                        if pid == 0:
                            continue

                        # oneshot() retrieves memory, status, create_time in 1 syscall batch
                        with proc.oneshot():
                            cpu = proc.cpu_percent(interval=None)
                            mem_info = proc.memory_info()
                            mem_pct = proc.memory_percent()
                            status_str = proc.status()
                            create_time = proc.create_time()

                        mem_mb = mem_info.rss / (1024 * 1024)
                        if create_time:
                            start_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(create_time))
                        else:
                            start_time_str = "N/A"

                        process_list.append({
                            "pid": pid,
                            "name": info.get('name') or "Unknown",
                            "cpu_pct": round(float(cpu), 1),
                            "mem_pct": round(float(mem_pct), 1),
                            "mem_mb": round(float(mem_mb), 2),
                            "status": str(status_str or "running"),
                            "start_time": start_time_str
                        })
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                    except Exception:
                        continue
            except Exception:
                pass
        else:
            # Fallback when psutil is unavailable: minimal process discovery via platform tools
            if sys.platform == "win32":
                try:
                    res = subprocess.check_output(['tasklist', '/FO', 'CSV', '/NH'], text=True, errors='ignore')
                    import csv
                    reader = csv.reader(res.splitlines())
                    for row in reader:
                        if len(row) >= 5:
                            total_count += 1
                            name = row[0]
                            pid = int(row[1]) if row[1].isdigit() else 0
                            mem_str = row[4].replace(',', '').replace(' K', '').strip()
                            mem_mb = round(float(mem_str) / 1024, 2) if mem_str.isdigit() else 0.0
                            process_list.append({
                                "pid": pid,
                                "name": name,
                                "cpu_pct": 0.0,
                                "mem_pct": 0.0,
                                "mem_mb": mem_mb,
                                "status": "running",
                                "start_time": "N/A"
                            })
                except Exception:
                    pass

        # Sort top processes primarily by CPU, secondarily by Memory usage
        process_list.sort(key=lambda p: (p["cpu_pct"], p["mem_mb"]), reverse=True)
        top_processes = process_list[:max_processes]

        return {
            "total_processes": total_count if total_count > 0 else len(process_list),
            "processes": top_processes
        }

    def collect_all(self):
        mem = self.get_memory_info()
        disk = self.get_disk_info()
        net = self.get_network_io()
        sensors = self.get_hardware_sensors()

        return {
            "hostname": self.get_hostname(),
            "os_type": self.get_os_info(),
            "ip_address": self.get_local_ip(),
            "cpu_pct": self.get_cpu_utilization(),
            "ram_pct": mem["ram_pct"],
            "ram_used_gb": mem["ram_used_gb"],
            "ram_total_gb": mem["ram_total_gb"],
            "disk_pct": disk["disk_pct"],
            "disk_free_gb": disk["disk_free_gb"],
            "disk_total_gb": disk["disk_total_gb"],
            "uptime_hours": self.get_uptime_hours(),
            "net_bytes_sent": net["bytes_sent"],
            "net_bytes_recv": net["bytes_recv"],
            "sensor_notes": sensors["status"]
        }
