# actions/system_health_agent.py
# Cristine — System Health Agent
#
# Orchestrates system health scanning and safe optimization recommendations.
# All actions require explicit user confirmation.

import json
import threading
from pathlib import Path
import sys

# Import scanner and cleanup modules
from system.system_scanner import get_health_report
from system.cleanup_tasks import (
    clean_temp_files,
    empty_recycle_bin,
    disable_startup_app,
    clear_browser_cache
)


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()


# ============================================================================
# Main Entry Points for Executor
# ============================================================================

def system_health_check() -> dict:
    """
    Main entry point: Perform comprehensive system health scan.
    
    Returns formatted health report with recommendations.
    Runs synchronously but can be called from async context.
    
    Returns:
        Dict with health report, recommendations, and action options
    """
    try:
        print("[Health Agent] Starting system health check...")
        
        # Get comprehensive health report
        report = get_health_report()
        
        if report.get("status") == "error":
            return {
                "status": "error",
                "error": report.get("error"),
                "message": "Failed to perform system health check."
            }
        
        # Format report for display
        formatted_report = _format_health_report(report)
        
        return {
            "status": "success",
            "report": formatted_report,
            "raw_data": report,
            "can_perform_actions": True,
            "available_actions": _get_available_actions(report)
        }
    
    except Exception as e:
        print(f"[Health Agent] Error during health check: {e}")
        return {
            "status": "error",
            "error": str(e),
            "message": "System health check failed."
        }


def system_health_action(action: str, target: str = None, confirm: bool = True) -> dict:
    """
    Execute a system health action (cleanup, etc).
    
    Args:
        action: "clean_temp" | "empty_recycle" | "clear_cache" | "disable_startup" | "run_security_scan"
        target: Target app name or browser (for specific actions)
        confirm: Whether to require confirmation (should be True for safety)
    
    Returns:
        Dict with action result
    """
    try:
        print(f"[Health Agent] Executing action: {action}, target: {target}")
        
        if action == "clean_temp":
            return clean_temp_files(confirm=confirm)
        
        elif action == "empty_recycle":
            return empty_recycle_bin(confirm=confirm)
        
        elif action == "clear_cache":
            browser = target or "all"
            return clear_browser_cache(browser=browser, confirm=confirm)
        
        elif action == "disable_startup":
            if not target:
                return {
                    "status": "error",
                    "error": "Target application name required for disable_startup action"
                }
            return disable_startup_app(target, confirm=confirm)
        
        elif action == "run_security_scan":
            return _run_security_scan()
        
        elif action == "open_windows_update":
            return _open_windows_update_settings()
        
        else:
            return {
                "status": "error",
                "error": f"Unknown action: {action}"
            }
    
    except Exception as e:
        print(f"[Health Agent] Error during action execution: {e}")
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to execute action: {action}"
        }


# ============================================================================
# Support Functions
# ============================================================================

def _format_health_report(raw_report: dict) -> str:
    """
    Format the raw health report into a human-readable string.
    """
    try:
        report_lines = [
            "=" * 70,
            "SYSTEM HEALTH REPORT",
            "=" * 70,
            ""
        ]
        
        # Summary section
        summary = raw_report.get("summary", {})
        report_lines.append(f"Status: {summary.get('status', 'unknown').upper()}")
        report_lines.append(f"Message: {summary.get('message', 'N/A')}")
        report_lines.append("")
        
        # Temp files
        temp_data = raw_report.get("temp_files", {})
        if temp_data.get("status") == "success":
            report_lines.append("TEMPORARY FILES")
            report_lines.append(f"  Size: {temp_data.get('temp_size_formatted', 'N/A')}")
            report_lines.append(f"  Count: {temp_data.get('file_count', 0)} files")
            if temp_data.get("largest_files"):
                largest = temp_data["largest_files"][0]
                report_lines.append(f"  Largest: {largest[0]} ({largest[1]})")
            report_lines.append("")
        
        # Recycle Bin
        rb_data = raw_report.get("recycle_bin", {})
        if rb_data.get("status") == "success":
            report_lines.append("RECYCLE BIN")
            report_lines.append(f"  Size: {rb_data.get('recycle_bin_size_formatted', 'N/A')}")
            report_lines.append(f"  Items: {rb_data.get('item_count', 0)}")
            report_lines.append("")
        
        # Startup Programs
        startup_data = raw_report.get("startup_programs", {})
        if startup_data.get("status") == "success":
            report_lines.append("STARTUP PROGRAMS")
            counts = startup_data.get("impact_counts", {})
            report_lines.append(f"  High Impact: {counts.get('High', 0)}")
            report_lines.append(f"  Medium Impact: {counts.get('Medium', 0)}")
            report_lines.append(f"  Low Impact: {counts.get('Low', 0)}")
            report_lines.append("")
        
        # Browser Cache
        browser_data = raw_report.get("browser_cache", {})
        if browser_data.get("status") == "success":
            report_lines.append("BROWSER CACHE")
            report_lines.append(f"  Total: {browser_data.get('total_cache_formatted', 'N/A')}")
            browsers = browser_data.get("browsers", {})
            for browser_name, data in browsers.items():
                report_lines.append(f"  {browser_name}: {data.get('cache_size_formatted', 'N/A')}")
            report_lines.append("")
        
        # Windows Updates
        updates_data = raw_report.get("windows_updates", {})
        if updates_data.get("status") == "success":
            report_lines.append("WINDOWS UPDATES")
            if updates_data.get("updates_available"):
                report_lines.append("  Status: Updates Available")
            else:
                report_lines.append("  Status: System Up to Date")
            report_lines.append("")
        
        # Recommendations
        if summary.get("recommendations"):
            report_lines.append("RECOMMENDATIONS")
            for i, rec in enumerate(summary["recommendations"], 1):
                report_lines.append(f"  {i}. {rec}")
            report_lines.append("")
        
        report_lines.append("=" * 70)
        
        return "\n".join(report_lines)
    
    except Exception as e:
        return f"Error formatting report: {str(e)}"


def _get_available_actions(report: dict) -> list:
    """
    Determine what actions are available based on report findings.
    """
    actions = []
    
    # Temp files cleanup
    temp_data = report.get("temp_files", {})
    if temp_data.get("status") == "success" and temp_data.get("file_count", 0) > 0:
        actions.append({
            "action": "clean_temp",
            "name": "Clean Temporary Files",
            "description": f"Delete {temp_data.get('file_count')} temporary files ({temp_data.get('temp_size_formatted')})",
            "requires_confirmation": True
        })
    
    # Recycle bin
    rb_data = report.get("recycle_bin", {})
    if rb_data.get("status") == "success" and rb_data.get("can_empty"):
        actions.append({
            "action": "empty_recycle",
            "name": "Empty Recycle Bin",
            "description": f"Remove {rb_data.get('item_count')} items ({rb_data.get('recycle_bin_size_formatted')})",
            "requires_confirmation": True
        })
    
    # Browser cache
    browser_data = report.get("browser_cache", {})
    if browser_data.get("status") == "success" and browser_data.get("can_clear"):
        actions.append({
            "action": "clear_cache",
            "name": "Clear Browser Cache",
            "description": f"Clear cache from {len(browser_data.get('browsers', {}))} browser(s) ({browser_data.get('total_cache_formatted')})",
            "requires_confirmation": True,
            "target_options": list(browser_data.get("browsers", {}).keys()) + ["all"]
        })
    
    # Disable startup apps
    startup_data = report.get("startup_programs", {})
    if startup_data.get("status") == "success":
        high_impact = startup_data.get("high_impact_programs", {})
        if high_impact:
            actions.append({
                "action": "disable_startup",
                "name": "Disable Startup Program",
                "description": f"Disable selected from {len(high_impact)} high-impact startup programs",
                "requires_confirmation": True,
                "target_options": list(high_impact.keys())
            })
    
    # Windows Update
    updates_data = report.get("windows_updates", {})
    if updates_data.get("status") == "success" and updates_data.get("updates_available"):
        actions.append({
            "action": "open_windows_update",
            "name": "Open Windows Update Settings",
            "description": "Install available Windows updates",
            "requires_confirmation": False
        })
    
    # Security Scan
    security_data = report.get("security_scan", {})
    if security_data.get("status") == "success" and security_data.get("defender_available"):
        actions.append({
            "action": "run_security_scan",
            "name": "Run Security Scan",
            "description": "Run Windows Defender quick scan",
            "requires_confirmation": True
        })
    
    return actions


def _run_security_scan() -> dict:
    """
    Launch Windows Defender quick scan.
    """
    try:
        import subprocess
        
        # Run Windows Defender quick scan
        # This opens the app but doesn't wait for completion
        subprocess.Popen(
            ["pwsh", "-Command", "Start-Process 'windowsdefender://' -WindowStyle Maximized"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        return {
            "status": "success",
            "action": "security_scan_initiated",
            "message": "Windows Defender security scan initiated. This may take several minutes."
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Could not launch security scan"
        }


def _open_windows_update_settings() -> dict:
    """
    Open Windows Update settings page.
    """
    try:
        import subprocess
        
        subprocess.Popen(
            ["start", "ms-settings:windowsupdate"],
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        return {
            "status": "success",
            "action": "windows_update_opened",
            "message": "Windows Update settings opened."
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Could not open Windows Update settings"
        }


if __name__ == "__main__":
    # Test the health agent
    print("[Health Agent] Running test...")
    result = system_health_check()
    print(result.get("report"))
    print()
    print(json.dumps(result.get("available_actions"), indent=2))
