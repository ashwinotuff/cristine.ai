# actions/system_monitor.py
# Cristine — System Awareness & Health
#
# Provides real-time monitoring for CPU, RAM, Battery, Disk, and Network.
# Also handles network diagnostics and audio profiles.

import psutil
import socket
import subprocess
import platform
import time
from pathlib import Path

_OS = platform.system()

def get_system_stats():
    """Returns a dictionary of current system performance metrics."""
    try:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        
        battery = psutil.sensors_battery()
        bat_percent = battery.percent if battery else "N/A"
        bat_plugged = battery.power_plugged if battery else "N/A"
        
        net_io = psutil.net_io_counters()
        sent = net_io.bytes_sent
        recv = net_io.bytes_recv
        
        return {
            "cpu": cpu,
            "ram": ram,
            "disk": disk,
            "battery": bat_percent,
            "battery_plugged": bat_plugged,
            "net_sent": sent,
            "net_recv": recv,
            "status": "Healthy" if cpu < 80 and ram < 85 else "High Load"
        }
    except Exception as e:
        return {"error": str(e)}

def network_diagnostics():
    """Performs a quick network health check."""
    results = {}
    
    # Local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        results["local_ip"] = s.getsockname()[0]
        s.close()
    except Exception:
        results["local_ip"] = "Disconnected"
        
    # Ping/Latency
    try:
        param = "-n" if _OS == "Windows" else "-c"
        command = ["ping", param, "1", "8.8.8.8"]
        output = subprocess.check_output(command, stderr=subprocess.STDOUT, universal_newlines=True)
        if "time=" in output:
            results["latency"] = output.split("time=")[1].split("ms")[0].strip() + "ms"
        elif "time<" in output:
            results["latency"] = "<1ms"
        else:
            results["latency"] = "High"
    except Exception:
        results["latency"] = "Request Timed Out"
        
    return results

def set_audio_profile(profile_name: str):
    """Sets volume based on predefined profiles."""
    profiles = {
        "silent": 0,
        "meeting": 15,
        "work": 30,
        "normal": 50,
        "entertainment": 80,
        "max": 100
    }
    
    target = profiles.get(profile_name.lower())
    if target is None:
        return f"Unknown profile: {profile_name}. Available: {list(profiles.keys())}"
    
    # We leverage the existing volume_set logic if possible, 
    # but to keep this file standalone, we'll implement a quick version for Windows
    if _OS == "Windows":
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            import math
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            vol_db = -65.25 if target == 0 else max(-65.25, 20 * math.log10(target / 100))
            vol.SetMasterVolumeLevel(vol_db, None)
            return f"Audio profile set to '{profile_name}' ({target}%)"
        except Exception as e:
            return f"Failed to set audio profile: {e}"
    else:
        # Simple fallback for other OS using subprocess
        try:
            if _OS == "Darwin":
                subprocess.run(["osascript", "-e", f"set volume output volume {target}"])
            else:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{target}%"])
            return f"Audio profile set to '{profile_name}' ({target}%)"
        except Exception as e:
            return f"Failed to set audio profile: {e}"

def system_monitor_action(parameters: dict):
    """Dispatcher for the agent."""
    action = parameters.get("action", "stats").lower()
    
    if action == "stats":
        stats = get_system_stats()
        diag = network_diagnostics()
        return f"System Stats: CPU {stats['cpu']}%, RAM {stats['ram']}%, Disk {stats['disk']}%, Battery {stats['battery']}%. Network: IP {diag['local_ip']}, Latency {diag.get('latency', 'N/A')}."
    
    elif action == "network":
        diag = network_diagnostics()
        return f"Network Diagnostics: Local IP {diag['local_ip']}, Latency {diag.get('latency', 'N/A')}."
    
    elif action == "audio_profile":
        profile = parameters.get("value", "normal")
        return set_audio_profile(profile)
    
    return "Invalid system monitor action."
