# system/system_scanner.py
# Cristine — System Health Scanner
#
# Non-destructive system diagnostics:
# - Temporary files size
# - Recycle bin size
# - Startup programs analysis
# - Browser cache size
# - Windows updates status
# - Security scan status

import os
import sys
import shutil
import subprocess
import winreg
from pathlib import Path
from datetime import datetime, timedelta
import psutil

def _format_size(bytes_size: int) -> str:
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def _get_dir_size(path: str | Path) -> int:
    """Recursively calculate directory size in bytes."""
    total = 0
    try:
        path = Path(path)
        if not path.exists():
            return 0
        
        for entry in path.rglob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except (OSError, PermissionError):
                pass
    except Exception as e:
        print(f"[Scanner] Error calculating dir size: {e}")
    
    return total


def scan_temp_files() -> dict:
    """
    Scan Windows temp directory for temporary files.
    Returns size and file count without deleting anything.
    """
    try:
        temp_paths = [
            os.environ.get("TEMP", ""),
            os.environ.get("TMP", ""),
            Path.home() / "AppData" / "Local" / "Temp"
        ]
        
        total_size = 0
        file_count = 0
        largest_files = []
        
        for temp_path in temp_paths:
            if not temp_path or not Path(temp_path).exists():
                continue
            
            temp_path = Path(temp_path)
            
            try:
                for f in temp_path.rglob("*"):
                    if f.is_file():
                        try:
                            file_size = f.stat().st_size
                            total_size += file_size
                            file_count += 1
                            
                            # Track largest files
                            if len(largest_files) < 10:
                                largest_files.append((str(f), file_size))
                            else:
                                largest_files.sort(key=lambda x: x[1], reverse=True)
                                if file_size > largest_files[-1][1]:
                                    largest_files[-1] = (str(f), file_size)
                        except (OSError, PermissionError):
                            pass
            except Exception as e:
                print(f"[Scanner] Error scanning {temp_path}: {e}")
        
        # Sort largest files
        largest_files.sort(key=lambda x: x[1], reverse=True)
        
        return {
            "status": "success",
            "temp_size_bytes": total_size,
            "temp_size_formatted": _format_size(total_size),
            "file_count": file_count,
            "largest_files": [(f, _format_size(s)) for f, s in largest_files[:5]]
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def scan_recycle_bin() -> dict:
    """
    Get Windows Recycle Bin size.
    Uses Windows Shell API via COM.
    """
    try:
        import comtypes.client
        
        shell = comtypes.client.CreateObject("Shell.Application")
        recycle_bin = shell.NameSpace(10)  # 10 = Recycle Bin
        
        total_size = 0
        item_count = 0
        
        # Iterate through items in recycle bin
        for item in recycle_bin.Items():
            try:
                total_size += item.Size
                item_count += 1
            except Exception:
                pass
        
        return {
            "status": "success",
            "recycle_bin_size_bytes": total_size,
            "recycle_bin_size_formatted": _format_size(total_size),
            "item_count": item_count,
            "can_empty": item_count > 0
        }
    
    except Exception as e:
        print(f"[Scanner] Recycle bin access error: {e}")
        return {
            "status": "error",
            "error": f"Could not access recycle bin: {str(e)}"
        }


def scan_startup_programs() -> dict:
    """
    Analyze Windows startup programs from registry.
    Classifies by likely startup impact.
    """
    try:
        startup_programs = {}
        
        # Common startup registry locations
        registry_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ]
        
        # Known high-impact apps
        high_impact = {"Discord", "Spotify", "Teams", "Slack", "Zoom", "Steam"}
        medium_impact = {"OneDrive", "GoogleDrive", "Dropbox", "1Password", "Bitwarden"}
        
        for hive, path in registry_paths:
            try:
                key = winreg.OpenKey(hive, path)
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        
                        # Classify by impact
                        impact = "Low"
                        for app in high_impact:
                            if app.lower() in name.lower() or app.lower() in value.lower():
                                impact = "High"
                                break
                        
                        if impact != "High":
                            for app in medium_impact:
                                if app.lower() in name.lower() or app.lower() in value.lower():
                                    impact = "Medium"
                                    break
                        
                        if name not in startup_programs:
                            startup_programs[name] = {
                                "path": value,
                                "impact": impact,
                                "registry_location": hive
                            }
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except Exception as e:
                print(f"[Scanner] Registry access error for {path}: {e}")
        
        # Count by impact
        impact_counts = {"High": 0, "Medium": 0, "Low": 0}
        for prog in startup_programs.values():
            impact_counts[prog["impact"]] += 1
        
        return {
            "status": "success",
            "programs": startup_programs,
            "total_startup_programs": len(startup_programs),
            "impact_counts": impact_counts,
            "high_impact_programs": {k: v for k, v in startup_programs.items() if v["impact"] == "High"}
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def scan_browser_cache() -> dict:
    """
    Analyze browser cache sizes for Chrome, Edge, Firefox.
    Does NOT access saved passwords, history, or sessions.
    """
    try:
        browsers = {}
        home = Path.home()
        
        # Chrome cache
        chrome_cache = home / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default" / "Cache"
        if chrome_cache.exists():
            cache_size = _get_dir_size(chrome_cache)
            browsers["Google Chrome"] = {
                "path": str(chrome_cache),
                "cache_size_bytes": cache_size,
                "cache_size_formatted": _format_size(cache_size)
            }
        
        # Edge cache
        edge_cache = home / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache"
        if edge_cache.exists():
            cache_size = _get_dir_size(edge_cache)
            browsers["Microsoft Edge"] = {
                "path": str(edge_cache),
                "cache_size_bytes": cache_size,
                "cache_size_formatted": _format_size(cache_size)
            }
        
        # Firefox cache
        firefox_cache = home / "AppData" / "Local" / "Mozilla" / "Firefox" / "Profiles"
        if firefox_cache.exists():
            total_cache = 0
            for profile_dir in firefox_cache.iterdir():
                if profile_dir.is_dir():
                    cache_dir = profile_dir / "cache2"
                    if cache_dir.exists():
                        total_cache += _get_dir_size(cache_dir)
            
            if total_cache > 0:
                browsers["Mozilla Firefox"] = {
                    "path": str(firefox_cache),
                    "cache_size_bytes": total_cache,
                    "cache_size_formatted": _format_size(total_cache)
                }
        
        total_browser_cache = sum(b["cache_size_bytes"] for b in browsers.values())
        
        return {
            "status": "success",
            "browsers": browsers,
            "total_cache_bytes": total_browser_cache,
            "total_cache_formatted": _format_size(total_browser_cache),
            "can_clear": len(browsers) > 0
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def check_windows_updates() -> dict:
    """
    Check Windows Update status.
    Uses WMI and Registry to detect pending updates.
    """
    try:
        updates_available = False
        update_count = 0
        
        # Try WMI approach
        try:
            import wmi
            w = wmi.WMI()
            updates = w.query("select * from Win32_QuickFixEngineering")
            update_count = len(list(updates))
        except Exception:
            pass
        
        # Check Windows Update registry for pending updates
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\Restarts"
            )
            updates_available = True
            winreg.CloseKey(key)
        except OSError:
            pass
        
        # Try checking via Windows Update COM object
        try:
            import comtypes.client
            au = comtypes.client.CreateObject("Microsoft.Update.AutoUpdate")
            result = au.DetectNow()
            updates_available = True
        except Exception:
            pass
        
        return {
            "status": "success",
            "updates_available": updates_available,
            "installed_patches": update_count,
            "can_open_settings": True
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def check_security_scan() -> dict:
    """
    Check Windows Defender status and capability to run scans.
    """
    try:
        defender_available = False
        
        # Check if Windows Defender is available
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Windows Defender"
            )
            defender_available = True
            winreg.CloseKey(key)
        except OSError:
            pass
        
        # Alternative: Check via Registry for MpEngine (Defender service)
        if not defender_available:
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Services\WinDefend"
                )
                defender_available = True
                winreg.CloseKey(key)
            except OSError:
                pass
        
        return {
            "status": "success",
            "defender_available": defender_available,
            "can_run_scan": defender_available
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def get_health_report() -> dict:
    """
    Generate comprehensive system health report.
    Combines all scanner outputs into a single report.
    """
    try:
        report = {
            "timestamp": datetime.now().isoformat(),
            "system_name": "System Health Report",
            
            "temp_files": scan_temp_files(),
            "recycle_bin": scan_recycle_bin(),
            "startup_programs": scan_startup_programs(),
            "browser_cache": scan_browser_cache(),
            "windows_updates": check_windows_updates(),
            "security_scan": check_security_scan(),
        }
        
        # Summary section
        summary = {
            "status": "healthy",
            "issues_detected": 0,
            "recommendations": []
        }
        
        # Check for large temp files
        if report["temp_files"]["status"] == "success":
            temp_size = report["temp_files"]["temp_size_bytes"]
            if temp_size > 500 * 1024 * 1024:  # > 500 MB
                summary["issues_detected"] += 1
                summary["recommendations"].append("Clean temporary files")
        
        # Check recycle bin
        if report["recycle_bin"]["status"] == "success":
            rb_size = report["recycle_bin"]["recycle_bin_size_bytes"]
            if rb_size > 500 * 1024 * 1024:  # > 500 MB
                summary["issues_detected"] += 1
                summary["recommendations"].append("Empty Recycle Bin")
        
        # Check browser cache
        if report["browser_cache"]["status"] == "success":
            browser_cache_size = report["browser_cache"]["total_cache_bytes"]
            if browser_cache_size > 500 * 1024 * 1024:  # > 500 MB
                summary["issues_detected"] += 1
                summary["recommendations"].append("Clear browser cache")
        
        # Check startup programs
        if report["startup_programs"]["status"] == "success":
            high_impact = len(report["startup_programs"]["high_impact_programs"])
            if high_impact > 5:
                summary["issues_detected"] += 1
                summary["recommendations"].append("Consider disabling non-essential startup programs")
        
        # Check Windows updates
        if report["windows_updates"]["status"] == "success":
            if report["windows_updates"]["updates_available"]:
                summary["issues_detected"] += 1
                summary["recommendations"].append("Install Windows updates")
        
        if summary["issues_detected"] == 0:
            summary["status"] = "excellent"
            summary["message"] = "Your system is running optimally."
        elif summary["issues_detected"] <= 2:
            summary["status"] = "good"
            summary["message"] = "Minor optimizations recommended."
        else:
            summary["status"] = "fair"
            summary["message"] = "Several optimizations recommended."
        
        report["summary"] = summary
        
        return report
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    # Test the scanner functions
    print("[Scanner] Running system health check...")
    report = get_health_report()
    
    import json
    print(json.dumps(report, indent=2, default=str))
