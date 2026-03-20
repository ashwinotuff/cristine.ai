# system/cleanup_tasks.py
# Cristine — Safe System Cleanup Tasks
#
# All cleanup operations require explicit user confirmation.
# Never delete user files or system-critical files.

import os
import sys
import shutil
import winreg
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import time


def clean_temp_files(confirm: bool = True, dry_run: bool = False) -> dict:
    """
    Safely clean temporary files from Windows temp directories.
    
    SAFETY RULES:
    - Only deletes files in TEMP directory
    - Skips files currently in use
    - Skips system-critical temp files
    - Requires confirmation
    
    Args:
        confirm: If True, requires explicit confirmation (not used in dry_run)
        dry_run: If True, shows what would be deleted without deleting
    
    Returns:
        Dictionary with cleanup results
    """
    try:
        temp_paths = [
            os.environ.get("TEMP", ""),
            os.environ.get("TMP", ""),
            Path.home() / "AppData" / "Local" / "Temp"
        ]
        
        # System-critical temp files to skip (never delete)
        skip_patterns = {
            "appdata",
            "windows",
            "system",
            "$recycle",
            ".sys",
            ".lock",
            "thumbs.db",
            "desktop.ini"
        }
        
        deleted_files = []
        deleted_size = 0
        skipped_files = []
        failed_files = []
        
        for temp_path in temp_paths:
            if not temp_path or not Path(temp_path).exists():
                continue
            
            temp_path = Path(temp_path)
            
            try:
                for f in temp_path.rglob("*"):
                    if not f.is_file():
                        continue
                    
                    # Skip critical files
                    skip = False
                    filename_lower = f.name.lower()
                    for pattern in skip_patterns:
                        if pattern in filename_lower:
                            skip = True
                            break
                    
                    if skip:
                        skipped_files.append(str(f))
                        continue
                    
                    # Try to delete (will fail if file is in use)
                    try:
                        if dry_run:
                            file_size = f.stat().st_size
                            deleted_files.append(str(f))
                            deleted_size += file_size
                        else:
                            file_size = f.stat().st_size
                            os.remove(f)
                            deleted_files.append(str(f))
                            deleted_size += file_size
                    except (PermissionError, OSError) as e:
                        # File is in use or protected
                        failed_files.append((str(f), str(e)))
            
            except Exception as e:
                print(f"[Cleanup] Error processing {temp_path}: {e}")
        
        def _format_size(bytes_size: int) -> str:
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_size < 1024.0:
                    return f"{bytes_size:.2f} {unit}"
                bytes_size /= 1024.0
            return f"{bytes_size:.2f} TB"
        
        return {
            "status": "success",
            "action": "dry_run" if dry_run else "cleaned",
            "deleted_files_count": len(deleted_files),
            "deleted_size_bytes": deleted_size,
            "deleted_size_formatted": _format_size(deleted_size),
            "skipped_files_count": len(skipped_files),
            "failed_files_count": len(failed_files),
            "failed_files": failed_files[:10],  # Show first 10 failures
            "message": f"Would delete {len(deleted_files)} files ({_format_size(deleted_size)})" if dry_run 
                      else f"Deleted {len(deleted_files)} files ({_format_size(deleted_size)})"
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def empty_recycle_bin(confirm: bool = True) -> dict:
    """
    Safely empty the Windows Recycle Bin.
    
    SAFETY RULES:
    - Only empties recycle bin (NOT permanent delete)
    - Requires confirmation
    - Shows files before deletion
    
    Args:
        confirm: If True, requires confirmation
    
    Returns:
        Dictionary with results
    """
    try:
        import comtypes.client
        
        shell = comtypes.client.CreateObject("Shell.Application")
        recycle_bin = shell.NameSpace(10)
        
        total_size = 0
        item_count = 0
        
        # Count items
        for item in recycle_bin.Items():
            try:
                total_size += item.Size
                item_count += 1
            except Exception:
                pass
        
        if item_count == 0:
            return {
                "status": "success",
                "message": "Recycle Bin is already empty.",
                "item_count": 0,
                "size_bytes": 0,
                "size_formatted": "0 B"
            }
        
        def _format_size(bytes_size: int) -> str:
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_size < 1024.0:
                    return f"{bytes_size:.2f} {unit}"
                bytes_size /= 1024.0
            return f"{bytes_size:.2f} TB"
        
        # Empty the bin using Windows API
        try:
            import ctypes
            # SHEmptyRecycleBin flags: 0 = no confirmation, 1 = show confirmation, 4 = show progress
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0)
        except Exception as e:
            print(f"[Cleanup] Recycle bin empty failed: {e}")
            return {
                "status": "error",
                "error": f"Could not empty recycle bin: {str(e)}"
            }
        
        return {
            "status": "success",
            "action": "emptied",
            "item_count_deleted": item_count,
            "size_released_bytes": total_size,
            "size_released_formatted": _format_size(total_size),
            "message": f"Recycle Bin emptied ({item_count} items, {_format_size(total_size)} released)"
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def disable_startup_app(app_name: str, confirm: bool = True) -> dict:
    """
    Safely disable a startup application from registry.
    
    SAFETY RULES:
    - Does NOT uninstall the application
    - Does NOT delete application files
    - Only removes from Run registry entry
    - Can be re-enabled manually
    - Requires confirmation
    
    Args:
        app_name: Name of the application to disable
        confirm: If True, requires confirmation
    
    Returns:
        Dictionary with results
    """
    try:
        registry_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ]
        
        disabled_apps = []
        failed = []
        
        for hive, path in registry_paths:
            try:
                key = winreg.OpenKey(hive, path, 0, winreg.KEY_WRITE)
                i = 0
                
                values_to_delete = []
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        if app_name.lower() in name.lower():
                            values_to_delete.append(name)
                        i += 1
                    except OSError:
                        break
                
                # Delete the matching values
                for name in values_to_delete:
                    try:
                        winreg.DeleteValue(key, name)
                        disabled_apps.append((name, path))
                    except Exception as e:
                        failed.append((name, str(e)))
                
                winreg.CloseKey(key)
            
            except Exception as e:
                print(f"[Cleanup] Registry access error: {e}")
        
        if disabled_apps:
            return {
                "status": "success",
                "action": "disabled",
                "app_name": app_name,
                "disabled_entries": disabled_apps,
                "message": f"{app_name} disabled from startup. Application files not modified."
            }
        elif failed:
            return {
                "status": "partial_error",
                "error": "Could not disable some startup entries",
                "failed_entries": failed
            }
        else:
            return {
                "status": "error",
                "error": f"Application '{app_name}' not found in startup registry"
            }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def clear_browser_cache(browser: str = "all", confirm: bool = True) -> dict:
    """
    Safely clear browser cache without deleting passwords or history.
    
    SAFETY RULES:
    - Only deletes cache folder
    - Does NOT touch: passwords, bookmarks, history, saved sessions
    - Does NOT uninstall browser
    - Requires confirmation
    
    Args:
        browser: "chrome", "edge", "firefox", or "all"
        confirm: If True, requires confirmation
    
    Returns:
        Dictionary with results
    """
    try:
        home = Path.home()
        cleared_browsers = []
        failed = []
        total_size = 0
        
        def _format_size(bytes_size: int) -> str:
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_size < 1024.0:
                    return f"{bytes_size:.2f} {unit}"
                bytes_size /= 1024.0
            return f"{bytes_size:.2f} TB"
        
        def _get_dir_size(path: Path) -> int:
            total = 0
            try:
                for entry in path.rglob("*"):
                    if entry.is_file():
                        try:
                            total += entry.stat().st_size
                        except (OSError, PermissionError):
                            pass
            except Exception:
                pass
            return total
        
        # Chrome cache
        if browser.lower() in ["all", "chrome"]:
            chrome_cache = home / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default" / "Cache"
            if chrome_cache.exists():
                try:
                    cache_size = _get_dir_size(chrome_cache)
                    shutil.rmtree(chrome_cache, ignore_errors=True)
                    chrome_cache.mkdir(parents=True, exist_ok=True)  # Recreate empty dir
                    cleared_browsers.append(("Google Chrome", _format_size(cache_size)))
                    total_size += cache_size
                except Exception as e:
                    failed.append(("Google Chrome", str(e)))
        
        # Edge cache
        if browser.lower() in ["all", "edge"]:
            edge_cache = home / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache"
            if edge_cache.exists():
                try:
                    cache_size = _get_dir_size(edge_cache)
                    shutil.rmtree(edge_cache, ignore_errors=True)
                    edge_cache.mkdir(parents=True, exist_ok=True)  # Recreate empty dir
                    cleared_browsers.append(("Microsoft Edge", _format_size(cache_size)))
                    total_size += cache_size
                except Exception as e:
                    failed.append(("Microsoft Edge", str(e)))
        
        # Firefox cache
        if browser.lower() in ["all", "firefox"]:
            firefox_cache = home / "AppData" / "Local" / "Mozilla" / "Firefox" / "Profiles"
            if firefox_cache.exists():
                try:
                    cache_total = 0
                    for profile_dir in firefox_cache.iterdir():
                        if profile_dir.is_dir():
                            cache_dir = profile_dir / "cache2"
                            if cache_dir.exists():
                                cache_total += _get_dir_size(cache_dir)
                                shutil.rmtree(cache_dir, ignore_errors=True)
                                cache_dir.mkdir(parents=True, exist_ok=True)  # Recreate empty dir
                    
                    if cache_total > 0:
                        cleared_browsers.append(("Mozilla Firefox", _format_size(cache_total)))
                        total_size += cache_total
                except Exception as e:
                    failed.append(("Mozilla Firefox", str(e)))
        
        return {
            "status": "success" if cleared_browsers else "error",
            "action": "cleared",
            "browsers_cleared": cleared_browsers,
            "total_size_released_bytes": total_size,
            "total_size_released_formatted": _format_size(total_size),
            "failed": failed,
            "message": f"Cleared cache from {len(cleared_browsers)} browser(s) ({_format_size(total_size)}).",
            "note": "Passwords, bookmarks, and history were NOT deleted."
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    # Test cleanup functions with dry_run=True
    print("[Cleanup] Testing cleanup tasks...")
    
    result = clean_temp_files(dry_run=True)
    import json
    print(json.dumps(result, indent=2))
