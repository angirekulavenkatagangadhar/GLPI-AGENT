#!/usr/bin/env python3
"""
GLPI Agent Tools - Python Implementation

This module provides OS-independent generic functions for the GLPI Agent,
converted from the original Perl implementation.
"""

import os
import sys
import re
import time
import glob
import stat
import shutil
import signal
import subprocess
import platform
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union, Iterator, IO
from functools import wraps
import importlib
import pkgutil

# Third-party imports that would be needed
try:
    import pwd
except ImportError:
    pwd = None  # Windows doesn't have pwd module

# Keep a copy of sys.argv for compatibility
ARGV = sys.argv.copy()

# Global remote object for remote operations
_remote = None


def set_remote_for_tools(remote_obj):
    """Set remote object for tools operations."""
    global _remote
    _remote = remote_obj


def reset_remote_for_tools():
    """Reset remote object for tools operations."""
    global _remote
    _remote = None


def get_os_name() -> str:
    """Get the operating system name."""
    if _remote:
        return _remote.os_name()
    return platform.system()


def uname(*args) -> Optional[str]:
    """Execute uname command with given arguments."""
    cmd = ["uname"] + list(args)
    return get_first_line(command=cmd)


def glob_files(pattern: str, test: Optional[str] = None) -> List[str]:
    """
    Glob files matching pattern with optional test.
    
    Args:
        pattern: Glob pattern to match
        test: Optional test ('-s' for size, '-h' for symlink)
        
    Returns:
        List of matching files
    """
    if _remote:
        return _remote.remote_glob(pattern, test)
    
    files = glob.glob(pattern)
    
    if test == '-s':
        return [f for f in files if os.path.getsize(f) > 0]
    elif test == '-h':
        return [f for f in files if os.path.islink(f)]
    
    return files


def has_folder(path: str) -> bool:
    """Check if folder exists."""
    if _remote:
        return _remote.remote_test_folder(path)
    return os.path.isdir(path)


def has_file(path: str) -> bool:
    """Check if file exists."""
    if _remote:
        return _remote.remote_test_file(path)
    return os.path.exists(path)


def can_read(path: str) -> bool:
    """Check if file can be read."""
    if _remote:
        return _remote.remote_test_file(path, 'r')
    return os.access(path, os.R_OK)


def has_link(path: str) -> bool:
    """Check if path is a symbolic link."""
    if _remote:
        return _remote.remote_test_link(path)
    return os.path.islink(path)


def file_stat(path: str) -> Optional[os.stat_result]:
    """Get file statistics."""
    if _remote:
        return _remote.remote_file_stat(path)
    
    try:
        return os.stat(path)
    except (OSError, IOError):
        return None


def read_link(path: str) -> Optional[str]:
    """Read symbolic link target."""
    if _remote:
        return _remote.remote_read_link(path)
    
    try:
        return os.readlink(path)
    except (OSError, IOError):
        return None


def get_next_user() -> Optional[Dict[str, Any]]:
    """Get next user from system user database."""
    if _remote:
        return _remote.remote_get_next_user()
    
    if not pwd:
        return None
    
    try:
        entry = pwd.getpwall()
        if entry:
            user = entry[0]  # Get first user for simplicity
            return {
                'name': user.pw_name,
                'uid': user.pw_uid,
                'dir': user.pw_dir
            }
    except Exception:
        pass
    
    return None


def empty(value: Any) -> bool:
    """Check if value is empty (None or empty string)."""
    return value is None or (isinstance(value, str) and len(value) == 0)


def first(predicate: Callable, iterable) -> Any:
    """Return first item matching predicate or None."""
    for item in iterable:
        if predicate(item):
            return item
    return None


def get_formatted_local_time(timestamp: Optional[float] = None) -> str:
    """
    Get formatted local time from timestamp.
    
    Args:
        timestamp: Unix timestamp, defaults to current time
        
    Returns:
        Formatted date string in format: YY-MM-DD HH:MM:SS
    """
    if timestamp is None:
        timestamp = time.time()
    
    dt = datetime.fromtimestamp(timestamp)
    return get_formatted_date(
        dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second
    )


def get_formatted_gmt_time(timestamp: float) -> str:
    """
    Get formatted GMT time from timestamp.
    
    Args:
        timestamp: Unix timestamp
        
    Returns:
        Formatted date string in format: YY-MM-DD HH:MM:SS
    """
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    # Note: Original Perl code has some odd year calculation (year - 70)
    # This appears to be a bug in the original, keeping standard format
    return get_formatted_date(
        dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second
    )


def get_formatted_date(year: int, month: int, day: int, 
                      hour: int = 0, minute: int = 0, second: int = 0) -> str:
    """
    Format date components into string.
    
    Returns:
        Formatted date string in format: YYYY-MM-DD HH:MM:SS
    """
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"


def get_canonical_manufacturer(manufacturer: str) -> Optional[str]:
    """
    Normalize manufacturer name.
    
    Args:
        manufacturer: Raw manufacturer string
        
    Returns:
        Normalized manufacturer name
    """
    if not manufacturer:
        return None
    
    # Direct mappings
    manufacturers = {
        'GenuineIntel': 'Intel',
        'AuthenticAMD': 'AMD',
        'TMx86': 'Transmeta',
        'TransmetaCPU': 'Transmeta',
        'CyrixInstead': 'Cyrix',
        'CentaurHauls': 'VIA',
        'HygonGenuine': 'Hygon'
    }
    
    if manufacturer in manufacturers:
        return manufacturers[manufacturer]
    
    # Pattern-based mappings
    patterns = {
        "Apple": r'^APPLE',
        "Hewlett-Packard": r'^(hp|HPE?|hewlett[ -]packard|MM)',
        "Hitachi": r'^(HD|IC|HU|HGST)',
        "Seagate": r'^(ST|seagate)',
        "Sony": r'^OPTIARC',
        "Western Digital": r'^(WDC?|western)',
        "Crucial": r'^CT',
        "PNY": r'^PNY',
    }
    
    for name, pattern in patterns.items():
        if re.match(pattern, manufacturer, re.IGNORECASE):
            return name
    
    # Common manufacturer names
    common_names = [
        'lg', 'broadcom', 'compaq', 'dell', 'epson', 'fujitsu',
        'hitachi', 'ibm', 'intel', 'kingston', 'matshita', 'maxtor',
        'nvidia', 'nec', 'pioneer', 'samsung', 'sony', 'supermicro',
        'toshiba', 'transcend'
    ]
    
    for name in common_names:
        if re.search(rf'\b{name}\b', manufacturer, re.IGNORECASE):
            return name.capitalize()
    
    return manufacturer


def get_canonical_speed(speed: str) -> Optional[float]:
    """
    Normalize speed value to MHz.
    
    Args:
        speed: Speed string with optional unit
        
    Returns:
        Speed in MHz or None if invalid
    """
    if not speed:
        return None
    
    # Already numeric
    if re.match(r'^[,.\d]+$', speed):
        return float(speed.replace(',', '.'))
    
    # Special case
    if speed == 'PC3200U':
        return 400.0
    
    # Parse value and unit
    match = re.match(r'^([,.\d]+)\s?(\S+)', speed)
    if not match:
        return None
    
    value = float(match.group(1).replace(',', '.'))
    unit = match.group(2).lower()
    
    # Convert to MHz
    if unit == 'ghz':
        return value * 1000
    elif unit in ('mhz', 'mt/s'):
        return value
    
    return None


def get_canonical_interface_speed(speed: str) -> Optional[float]:
    """
    Normalize network interface speed to Mb/s.
    
    Args:
        speed: Speed string with unit
        
    Returns:
        Speed in Mb/s or None if invalid
    """
    if not speed:
        return None
    
    match = re.match(r'^([,.\d]+)\s?(\S\S)\S*$', speed)
    if not match:
        return None
    
    value = float(match.group(1).replace(',', '.'))
    unit = match.group(2).lower()
    
    if unit == 'gb':
        return value * 1000
    elif unit == 'mb':
        return value
    elif unit == 'kb':
        return int(value / 1000)
    
    return None


def get_canonical_size(size: str, base: int = 1000) -> Optional[float]:
    """
    Normalize size value to MB.
    
    Args:
        size: Size string with unit
        base: Base for calculation (1000 or 1024)
        
    Returns:
        Size in MB or None if invalid
    """
    if not size:
        return None
    
    # Already numeric
    if re.match(r'^\d+$', size):
        return float(size)
    
    # Remove spaces
    size = size.replace(' ', '')
    
    match = re.match(r'^([,.\d]+)\s*(\S+)$', size)
    if not match:
        return None
    
    value_str = match.group(1)
    unit = match.group(2).lower()
    
    # Handle different number formats
    if re.match(r'^(0|[1-9](\d*|\d{0,2}([, ]\d{3})+))(\.\d+)?$', value_str):
        value_str = value_str.replace(',', '').replace(' ', '')
    else:
        value_str = value_str.replace(',', '.')
    
    value = float(value_str)
    
    # Check for binary units (with 'i')
    if re.match(r'^[eptgmk]ib$', unit):
        unit = unit[0] + 'b'
        base = 1024
    
    # Convert to MB
    multipliers = {
        'eb': base ** 4,
        'pb': base ** 3,
        'tb': base ** 2,
        'gb': base,
        'mb': 1,
        'kb': 1 / base,
        'bytes': 1 / (base ** 2)
    }
    
    if unit in multipliers:
        return value * multipliers[unit]
    
    return None


def get_canonical_power(power: str) -> Optional[float]:
    """
    Normalize power value to watts.
    
    Args:
        power: Power string with unit
        
    Returns:
        Power in watts or None if invalid
    """
    if not power:
        return None
    
    match = re.match(r'(\d+)\s?(\S*)\S*$', power)
    if not match:
        return None
    
    value = float(match.group(1))
    unit = match.group(2)
    
    if not unit:
        return value
    
    if unit == 'kW':
        return value * 1000
    elif unit == 'W':
        return value
    elif unit == 'mW':
        return int(value / 1000)
    
    return None


def compare_version(major: int, minor: int, min_major: int, min_minor: int) -> bool:
    """
    Compare version numbers.
    
    Args:
        major: Current major version
        minor: Current minor version
        min_major: Minimum required major version
        min_minor: Minimum required minor version
        
    Returns:
        True if current version meets minimum requirements
    """
    major = major or 0
    minor = minor or 0
    min_major = min_major or 0
    min_minor = min_minor or 0
    
    return (major > min_major or 
            (major == min_major and minor >= min_minor))


def glpi_version(version: str) -> int:
    """
    Convert version string to integer for comparison.
    
    Args:
        version: Version string (e.g., "1.2.3" or "v1.2.3")
        
    Returns:
        Integer representation of version
    """
    if not version:
        return 0
    
    match = re.match(r'^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?', version)
    if not match:
        return 0
    
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    
    return major * 1_000_000 + minor * 1000 + patch


def get_utf8_string(text: str) -> Optional[str]:
    """
    Ensure string is properly UTF-8 encoded.
    
    Args:
        text: Input string
        
    Returns:
        UTF-8 encoded string
    """
    if text is None:
        return None
    
    # Python 3 strings are already Unicode, but ensure proper encoding
    if isinstance(text, bytes):
        try:
            return text.decode('utf-8')
        except UnicodeDecodeError:
            return text.decode('utf-8', errors='replace')
    
    return text


def get_sanitized_string(text: str) -> Optional[str]:
    """
    Remove control characters and ensure UTF-8 encoding.
    
    Args:
        text: Input string
        
    Returns:
        Sanitized UTF-8 string
    """
    if text is None:
        return None
    
    # Remove control characters (except tab, newline, carriage return)
    sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    return get_utf8_string(sanitized)


def trim_whitespace(value: str) -> Optional[str]:
    """
    Trim and normalize whitespace.
    
    Args:
        value: Input string
        
    Returns:
        Trimmed string with normalized whitespace
    """
    if value is None:
        return None
    
    # Strip leading/trailing whitespace and normalize internal whitespace
    return re.sub(r'\s+', ' ', value.strip())


def get_directory_handle(directory: str, logger=None) -> Optional[Iterator[str]]:
    """
    Get directory listing.
    
    Args:
        directory: Directory path
        logger: Logger object
        
    Returns:
        Iterator over directory entries
    """
    if not directory:
        raise ValueError("No directory parameter given")
    
    try:
        return iter(os.listdir(directory))
    except OSError as e:
        if logger:
            logger.error(f"Can't open directory {directory}: {e}")
        return None


def get_file_handle(command: Union[str, List[str]] = None, 
                   file: str = None, 
                   string: str = None,
                   mode: str = 'r',
                   logger=None,
                   no_error_log: bool = False,
                   local: bool = False) -> Optional[IO]:
    """
    Get file handle for command, file, or string.
    
    Args:
        command: Command to execute
        file: File path to open
        string: String to treat as file content
        mode: File open mode
        logger: Logger object
        no_error_log: Suppress error logging
        local: Force local operation even with remote
        
    Returns:
        File handle or None
    """
    if _remote and not local and (file or command):
        return _remote.get_remote_file_handle(
            command=command, file=file, string=string, mode=mode,
            logger=logger, no_error_log=no_error_log
        )
    
    if file:
        try:
            return open(file, mode, encoding='utf-8', errors='replace')
        except OSError as e:
            if logger and not no_error_log:
                logger.error(f"Can't open file {file}: {e}")
            return None
    
    elif command:
        try:
            # Log command (truncate if too long)
            log_command = ' '.join(command) if isinstance(command, list) else command
            while len(log_command) > 120 and ' ' in log_command:
                log_command = log_command.rsplit(' ', 1)[0] + " ..."
            
            if logger and hasattr(logger, 'debug_level') and logger.debug_level():
                logger.debug2(f"executing {log_command}")
            
            # Set environment for command execution
            env = os.environ.copy()
            env.update({'LC_ALL': 'C', 'LANG': 'C'})
            
            # Remove LD_LIBRARY_PATH for AppImage compatibility
            if (env.get('LD_LIBRARY_PATH') and 
                env.get('APPRUN_STARTUP_APPIMAGE_UUID') and 
                env.get('APPDIR')):
                env.pop('LD_LIBRARY_PATH', None)
                env.pop('LD_PRELOAD', None)
            
            if isinstance(command, list):
                proc = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, env=env, encoding='utf-8', errors='replace'
                )
            else:
                proc = subprocess.Popen(
                    command, shell=True, stdout=subprocess.PIPE, 
                    stderr=subprocess.DEVNULL, text=True, env=env,
                    encoding='utf-8', errors='replace'
                )
            
            return proc.stdout
            
        except OSError as e:
            if logger and not no_error_log:
                logger.error(f"Can't run command {log_command}: {e}")
            return None
    
    elif string is not None:
        from io import StringIO
        return StringIO(string)
    
    else:
        raise ValueError("Neither command, file, nor string parameter given")


def get_first_line(command: Union[str, List[str]] = None, 
                  file: str = None, 
                  string: str = None,
                  logger=None,
                  no_error_log: bool = False) -> Optional[str]:
    """Get first line from command output, file, or string."""
    handle = get_file_handle(
        command=command, file=file, string=string,
        logger=logger, no_error_log=no_error_log
    )
    
    if not handle:
        return None
    
    try:
        line = handle.readline()
        return line.rstrip('\n\r') if line else None
    finally:
        handle.close()


def get_last_line(command: Union[str, List[str]] = None, 
                 file: str = None, 
                 string: str = None,
                 logger=None,
                 no_error_log: bool = False) -> Optional[str]:
    """Get last line from command output, file, or string."""
    handle = get_file_handle(
        command=command, file=file, string=string,
        logger=logger, no_error_log=no_error_log
    )
    
    if not handle:
        return None
    
    try:
        last_line = None
        for line in handle:
            last_line = line
        return last_line.rstrip('\n\r') if last_line else None
    finally:
        handle.close()


def get_first_match(pattern: str,
                   command: Union[str, List[str]] = None, 
                   file: str = None, 
                   string: str = None,
                   logger=None,
                   no_error_log: bool = False) -> Optional[Union[str, List[str]]]:
    """Get first regex match from command output, file, or string."""
    if not pattern:
        return None
    
    lines = get_all_lines(
        command=command, file=file, string=string,
        logger=logger, no_error_log=no_error_log
    )
    
    if not lines:
        return None
    
    if isinstance(lines, str):
        lines = lines.splitlines()
    
    compiled_pattern = re.compile(pattern)
    
    for line in lines:
        match = compiled_pattern.search(line)
        if match:
            groups = match.groups()
            return groups if len(groups) > 1 else (groups[0] if groups else match.group(0))
    
    return None


def get_all_lines(command: Union[str, List[str]] = None, 
                 file: str = None, 
                 string: str = None,
                 logger=None,
                 no_error_log: bool = False) -> Optional[Union[str, List[str]]]:
    """Get all lines from command output, file, or string."""
    handle = get_file_handle(
        command=command, file=file, string=string,
        logger=logger, no_error_log=no_error_log
    )
    
    if not handle:
        return None
    
    try:
        content = handle.read()
        return content.splitlines() if content else []
    finally:
        handle.close()


def get_lines_count(command: Union[str, List[str]] = None, 
                   file: str = None, 
                   string: str = None,
                   logger=None,
                   no_error_log: bool = False) -> int:
    """Get number of lines from command output, file, or string."""
    lines = get_all_lines(
        command=command, file=file, string=string,
        logger=logger, no_error_log=no_error_log
    )
    
    if not lines:
        return 0
    
    return len(lines) if isinstance(lines, list) else len(lines.splitlines())


def can_run(binary: str) -> bool:
    """Check if binary can be executed."""
    if _remote:
        return _remote.remote_can_run(binary)
    
    if os.path.isabs(binary):
        return os.access(binary, os.X_OK)
    else:
        return shutil.which(binary) is not None


def hex2char(value: str) -> Optional[str]:
    """Convert hex string to character."""
    if value is None:
        return None
    
    if not value.startswith('0x'):
        return value
    
    try:
        hex_str = value[2:]  # Remove '0x' prefix
        return bytes.fromhex(hex_str).decode('utf-8', errors='replace')
    except (ValueError, UnicodeDecodeError):
        return None


def hex2dec(value: str) -> Optional[int]:
    """Convert hex string to decimal."""
    if value is None:
        return None
    
    if not value.startswith('0x'):
        try:
            return int(value)
        except ValueError:
            return None
    
    try:
        return int(value, 16)
    except ValueError:
        return None


def dec2hex(value: Union[str, int]) -> Optional[str]:
    """Convert decimal to hex string."""
    if value is None:
        return None
    
    if isinstance(value, str) and value.startswith('0x'):
        return value
    
    try:
        return f"0x{int(value):x}"
    except (ValueError, TypeError):
        return None


def any_func(predicate: Callable, iterable) -> bool:
    """Return True if any element matches predicate."""
    return any(predicate(item) for item in iterable)


def all_func(predicate: Callable, iterable) -> bool:
    """Return True if all elements match predicate."""
    return all(predicate(item) for item in iterable)


def none_func(predicate: Callable, iterable) -> bool:
    """Return True if no elements match predicate."""
    return not any(predicate(item) for item in iterable)


def uniq(iterable) -> List[Any]:
    """Return unique elements preserving order."""
    seen = set()
    result = []
    for item in iterable:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def file2module(file_path: str) -> str:
    """Convert file path to module name."""
    module = file_path
    if module.endswith('.py'):
        module = module[:-3]
    return module.replace('/', '.').replace('\\', '.')


def module2file(module: str) -> str:
    """Convert module name to file path."""
    return module.replace('.', '/') + '.py'


def run_function(module: str, function: str, params=None, 
                logger=None, timeout: Optional[int] = None, 
                load: bool = False) -> Any:
    """
    Run a function from a module with optional timeout.
    
    Args:
        module: Module name
        function: Function name
        params: Parameters to pass (dict, list, or single value)
        logger: Logger object
        timeout: Timeout in seconds
        load: Whether to load module first
        
    Returns:
        Function result
    """
    if load:
        try:
            importlib.import_module(module)
        except ImportError as e:
            if logger:
                logger.debug(f"Failed to load {module}: {e}")
            return None
    
    result = None
    
    def target():
        nonlocal result
        try:
            mod = importlib.import_module(module)
            
            # Try to get function directly from module
            func = None
            if hasattr(mod, function):
                func = getattr(mod, function)
            else:
                # Try snake_case version (isEnabled -> is_enabled, doInventory -> do_inventory)
                snake_func = function.replace('isEnabled', 'is_enabled').replace('doInventory', 'do_inventory')
                if hasattr(mod, snake_func):
                    func = getattr(mod, snake_func)
                else:
                    # Try to find a class in the module
                    # Get class name from last part of module name (e.g., CPU from GLPI.Agent.Task.Inventory.Win32.CPU)
                    module_parts = module.split('.')
                    class_name = module_parts[-1] if module_parts else ''
                    
                    if class_name and hasattr(mod, class_name):
                        cls = getattr(mod, class_name)
                        # Try to get method from class (try both camelCase and snake_case)
                        method_name = None
                        if hasattr(cls, function):
                            method_name = function
                        elif hasattr(cls, snake_func):
                            method_name = snake_func
                        
                        if method_name:
                            # Create instance and call method
                            instance = cls()
                            func = getattr(instance, method_name)
            
            if func is None:
                raise AttributeError(f"module '{module}' has no attribute '{function}'")
            
            if isinstance(params, dict):
                result = func(**params)
            elif isinstance(params, list):
                result = func(*params)
            elif params is not None:
                result = func(params)
            else:
                result = func()
                
        except Exception as e:
            if logger:
                logger.debug(f"Unexpected error in {module}: {e}")
    
    if timeout:
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            if logger:
                logger.debug(f"{module} killed by timeout")
            return None
    else:
        target()
    
    return result


def month(month_name: str) -> Optional[int]:
    """
    Convert month name to number.
    
    Args:
        month_name: Three-letter month abbreviation
        
    Returns:
        Month number (1-12) or None
    """
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }
    
    return months.get(month_name.lower())


# Timeout/expiration functionality placeholder
def set_expiration_time(timeout: Optional[int] = None):
    """Set expiration time for operations."""
    # This would be implemented based on GLPI::Agent::Tools::Expiration
    pass


if __name__ == "__main__":
    # Basic tests
    print("GLPI Agent Tools - Python Implementation")
    print(f"OS Name: {get_os_name()}")
    print(f"Can run 'ls': {can_run('ls')}")
    print(f"Empty test: {empty('')} {empty('not empty')}")
    print(f"Version comparison: {compare_version(2, 1, 2, 0)}")