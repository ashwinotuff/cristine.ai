# system/__init__.py
# Cristine — System Health & Maintenance Module
#
# Provides non-destructive system diagnostics and safe cleanup operations.

from system.system_scanner import (
    get_health_report,
    scan_temp_files,
    scan_recycle_bin,
    scan_startup_programs,
    scan_browser_cache,
    check_windows_updates,
    check_security_scan
)

from system.cleanup_tasks import (
    clean_temp_files,
    empty_recycle_bin,
    disable_startup_app,
    clear_browser_cache
)

__all__ = [
    # Scanner functions
    'get_health_report',
    'scan_temp_files',
    'scan_recycle_bin',
    'scan_startup_programs',
    'scan_browser_cache',
    'check_windows_updates',
    'check_security_scan',
    
    # Cleanup functions
    'clean_temp_files',
    'empty_recycle_bin',
    'disable_startup_app',
    'clear_browser_cache'
]
