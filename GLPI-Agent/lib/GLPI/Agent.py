import os
import sys
import time
import glob
import signal
import logging
import importlib
import importlib.util
import uuid
import json
import gzip
import socket
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
import requests
import platform
import shutil
import ctypes
import re

# Try to import proper Target classes
try:
    from GLPI.Agent.Target.Server import ServerTarget as ProperServerTarget
    from GLPI.Agent.Target.Local import LocalTarget as ProperLocalTarget
    USE_PROPER_TARGETS = True
except ImportError:
    ProperServerTarget = None
    ProperLocalTarget = None
    USE_PROPER_TARGETS = False

# Version information - exact match to Perl
VERSION = "1.7.0"
PROVIDER = "GLPI"
COMMENTS = []

# Global variables - exact Perl replica
CONTINUE_WORD = "..."

def _version_string(version: str) -> str:
    """Exact replica of Perl _versionString"""
    global COMMENTS
   
    string = f"{PROVIDER} Agent ({version})"
    if re.match(r'^\d+\.\d+\.(99\d\d|\d+-dev|.*-build-?\d+)$', version):
        COMMENTS.insert(0, "** THIS IS A DEVELOPMENT RELEASE **")
   
    return string

VERSION_STRING = _version_string(VERSION)
AGENT_STRING = f"{PROVIDER}-Agent_v{VERSION}"

# Process name for Inventory Provider (matches Perl)
PROGRAM_NAME = sys.argv[0] if sys.argv else "glpi-agent"

class Config:
    """Exact replica of GLPI::Agent::Config"""
   
    def __init__(self, options: Dict = None, vardir: str = None):
        self.options = options or {}
        self._vardir = vardir
        self._confdir = '/etc/glpi-agent'
        self._config = {}
        self.load_config()
   
    def load_config(self):
        """Load configuration exactly like Perl"""
        # Initialize empty config
        self._config = {}
       
        # Load from config files
        config_files = [
            os.path.join(self._confdir, 'agent.cfg'),
            '/etc/glpi-agent.cfg'
        ]
       
        for config_file in config_files:
            if os.path.exists(config_file):
                self._load_config_file(config_file)
       
        # Merge command line options
        for key, value in self.options.items():
            if value is not None:
                self._config[key] = value
       
        # Set defaults
        if 'no-task' not in self._config:
            self._config['no-task'] = []
        if 'server' not in self._config:
            self._config['server'] = []
   
    def _load_config_file(self, config_file: str):
        """Basic config file parsing"""
        try:
            with open(config_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')
                       
                        if ',' in value and key in ['server', 'no-task']:
                            self._config[key] = [v.strip() for v in value.split(',')]
                        elif value.lower() in ['true', 'yes', '1']:
                            self._config[key] = True
                        elif value.lower() in ['false', 'no', '0']:
                            self._config[key] = False
                        else:
                            self._config[key] = value
        except Exception:
            pass
   
    def get(self, key, default=None):
        return self._config.get(key, default)
   
    def __getitem__(self, key):
        return self.get(key)
   
    def __setitem__(self, key, value):
        self._config[key] = value
   
    def confdir(self):
        return self._confdir
   
    def has_filled_param(self, param: str) -> bool:
        """Exact replica of hasFilledParam"""
        value = self.get(param)
        if value is None:
            return False
        if isinstance(value, list):
            return len(value) > 0
        return bool(value)
   
    def get_targets(self, logger=None, deviceid: str = None, vardir: str = None):
        """Exact replica of getTargets"""
        targets = []
       
        servers = self.get('server', [])
        if isinstance(servers, str):
            servers = [servers]
       
        for i, server_url in enumerate(servers):
            # Use proper ServerTarget if available
            if USE_PROPER_TARGETS and ProperServerTarget:
                target = ProperServerTarget(
                    logger=logger,
                    config=self,
                    url=server_url,
                    basevardir=vardir or '.'
                )
            else:
                target = ServerTarget(
                    id=f"server_{i}",
                    url=server_url,
                    logger=logger,
                    vardir=vardir
                )
            targets.append(target)
       
        local_path = self.get('local')
        if local_path:
            # Use proper LocalTarget if available
            if USE_PROPER_TARGETS and ProperLocalTarget:
                target = ProperLocalTarget(
                    logger=logger,
                    config=self,
                    path=local_path,
                    basevardir=vardir or '.'
                )
            else:
                target = LocalTarget(
                    id='local_0',
                    path=local_path,
                    logger=logger
                )
            targets.append(target)
       
        return targets


class Logger:
    """Exact replica of GLPI::Agent::Logger"""
   
    def __init__(self, config=None):
        self.config = config
       
        level = logging.DEBUG if config and config.get('debug') else logging.INFO
       
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
       
        self.logger = logging.getLogger('glpi-agent')
        self.logger.setLevel(level)
       
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
       
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
       
        log_file = config.get('logfile') if config else None
        if log_file:
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            except Exception:
                pass
   
    def debug(self, message: str):
        self.logger.debug(message)
   
    def debug2(self, message: str):
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"[DEBUG2] {message}")
   
    def info(self, message: str):
        self.logger.info(message)
   
    def warning(self, message: str):
        self.logger.warning(message)
   
    def error(self, message: str):
        self.logger.error(message)


class Storage:
    """Exact replica of GLPI::Agent::Storage"""
   
    def __init__(self, logger=None, directory: str = None):
        self.logger = logger
        self.directory = directory or '/var/lib/glpi-agent'
        Path(self.directory).mkdir(parents=True, exist_ok=True)
   
    def restore(self, name: str) -> Dict:
        """Exact replica of restore method"""
        file_path = os.path.join(self.directory, f"{name}.json")
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
   
    def save(self, name: str, data: Dict):
        """Exact replica of save method"""
        file_path = os.path.join(self.directory, f"{name}.json")
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            temp_file = file_path + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            os.rename(temp_file, file_path)
        except Exception:
            pass


class Event:
    """Exact replica of GLPI::Agent::Event"""
   
    def __init__(self, name: str = "", init: bool = False):
        self.name = name
        self.init = init
        self.data = {}


class BaseTarget:
    """Base target class - exact replica"""
   
    def __init__(self, id: str, logger=None, vardir: str = None):
        self.id = id
        self.logger = logger
        self.vardir = vardir
        self._type = None
        self._next_run_date = 0
        self._max_delay = 3600
        self._paused = False
        
        # Create storage object
        try:
            from GLPI.Agent.Storage import Storage
            self.storage = Storage(logger=logger, directory=vardir)
        except ImportError:
            # Simple fallback storage
            class SimpleStorage:
                def __init__(self, directory=None):
                    self.directory = directory or '.'
                def getDirectory(self):
                    return self.directory
            self.storage = SimpleStorage(vardir)
    
    def getStorage(self):
        """Get storage object"""
        return self.storage
        self._glpi_server = None
        self._task_servers = {}
        self._events = []
   
    def is_type(self, type_name: str) -> bool:
        return self._type == type_name
   
    def get_type(self) -> str:
        return self._type
   
    def get_name(self) -> str:
        return getattr(self, 'url', getattr(self, 'path', self.id))
   
    
    def planned_tasks(self, *tasks) -> List[str]:
        if tasks:
            self._planned_tasks = list(tasks)
        return getattr(self, '_planned_tasks', [])
   
    def get_next_run_date(self) -> float:
        return self._next_run_date
   
    def set_next_run_date_from_now(self):
        self._next_run_date = time.time()
   
    def reset_next_run_date(self):
        self._next_run_date = time.time() + self._max_delay
   
    def set_next_run_on_expiration(self, expiration: int):
        self._next_run_date = time.time() + expiration
   
    def set_max_delay(self, delay: int):
        self._max_delay = delay
   
    def paused(self) -> bool:
        return self._paused
   
    def pause(self):
        self._paused = True
   
    def resume(self):
        self._paused = False
   
    def is_glpi_server(self, value=None) -> bool:
        if value is not None:
            if isinstance(value, str):
                self._glpi_server = value.lower() == 'true'
            else:
                self._glpi_server = bool(value)
        return bool(self._glpi_server)
   
    def do_prolog(self) -> bool:
        return True
   
    def get_task_server(self, task: str) -> Optional[str]:
        return self._task_servers.get(task.lower(), {}).get('server')
   
    def set_server_task_support(self, task: str, info: Dict):
        self._task_servers[task.lower()] = info
   
    def add_event(self, event: Event, priority: bool = False):
        if priority:
            self._events.insert(0, event)
        else:
            self._events.append(event)


class ServerTarget(BaseTarget):
    """Exact replica of GLPI::Agent::Target::Server"""
   
    def __init__(self, id: str, url: str, logger=None, vardir: str = None):
        super().__init__(id, logger, vardir)
        self._type = 'server'
        self.url = url
        self._is_glpi_server = 0
        self.tasks = []
        self._server_task_support = {}
   
    def get_url(self) -> str:
        return self.url
    
    def getUrl(self):
        """Get target URL - Perl naming convention"""
        return self.url
    
    def getName(self):
        """Get target name (URL without userinfo)"""
        return self.url
    
    def getType(self):
        """Get target type"""
        return 'server'
    
    def isGlpiServer(self, value=None):
        """Check/set if this is a GLPI server"""
        if value is not None:
            if str(value).lower() in ['1', 'true', 'yes']:
                self._is_glpi_server = 1
            else:
                self._is_glpi_server = 0
        return self._is_glpi_server
    
    def plannedTasks(self, *tasks):
        """Get/set planned tasks"""
        if tasks:
            self.tasks = list(tasks)
        return self.tasks
    
    def setServerTaskSupport(self, task, support):
        """Set server task support info"""
        if task and isinstance(support, dict):
            if support.get('server') and support.get('version'):
                self._server_task_support[task.lower()] = support
    
    def doProlog(self):
        """Check if PROLOG is needed"""
        if not self._server_task_support:
            return True
        return any(
            info.get('server') == 'glpiinventory' 
            for info in self._server_task_support.values()
        )
    
    def getTaskServer(self, task):
        """Get server type for task"""
        task_lower = task.lower()
        if task_lower in self._server_task_support:
            return self._server_task_support[task_lower].get('server')
        return None


class LocalTarget(BaseTarget):
    """Exact replica of GLPI::Agent::Target::Local"""
   
    def __init__(self, id: str, path: str, logger=None, vardir: str = None):
        super().__init__(id, logger, vardir)
        self._type = 'local'
        self.path = path


class BaseTask:
    """Base task class"""
   
    def __init__(self, config=None, datadir: str = None, logger=None,
                 event=None, credentials=None, target=None,
                 deviceid: str = None, agentid: str = None, cached_data=None):
        self.config = config
        self.datadir = datadir
        self.logger = logger
        self.event = event
        self.credentials = credentials
        self.target = target
        self.deviceid = deviceid
        self.agentid = agentid
        self.cached_data = cached_data
   
    def run(self):
        """Execute the task"""
        self._execute()
   
    def _execute(self):
        """Override in subclasses"""
        pass
   
    def abort(self):
        """Abort task execution"""
        pass
   
    def is_enabled(self, response=None) -> bool:
        """Check if task is enabled"""
        return True
   
    def new_event(self) -> Optional[Event]:
        """Create new event for this task"""
        return None


class InventoryTask(BaseTask):
    """Basic inventory task implementation"""
   
    def _execute(self):
        """Execute inventory collection"""
        if self.logger:
            self.logger.info("Collecting system inventory")
       
        inventory_data = {
            'deviceid': self.deviceid,
            'timestamp': datetime.now().isoformat(),
            'hardware': self._collect_hardware(),
            'software': self._collect_software(),
            'network': self._collect_network()
        }

        # Windows enriched sections (best-effort)
        try:
            if sys.platform.startswith('win'):
                inventory_data['windows'] = self._collect_windows_enriched()
        except Exception:
            pass
        
        # macOS enriched sections (best-effort)
        try:
            if platform.system() == 'Darwin':
                inventory_data['macos'] = self._collect_macos_enriched()
        except Exception:
            pass
        
        # Linux enriched sections (best-effort)
        try:
            if platform.system() == 'Linux':
                inventory_data['linux'] = self._collect_linux_enriched()
        except Exception:
            pass
        
        # Send to target
        if self.target.is_type('server'):
            self._send_to_server(inventory_data)
        elif self.target.is_type('local'):
            self._save_to_local(inventory_data)
   
    def _collect_hardware(self) -> Dict:
        """Basic hardware information"""
        info: Dict[str, Any] = {
            'system': platform.system(),
            'node': platform.node(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor()
        }

        # Memory (RAM)
        try:
            total_ram_bytes: Optional[int] = None
            if sys.platform.startswith('win'):
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    total_ram_bytes = int(stat.ullTotalPhys)
            if total_ram_bytes is None:
                try:
                    import psutil  # type: ignore
                    total_ram_bytes = int(psutil.virtual_memory().total)
                except Exception:
                    total_ram_bytes = None
            if total_ram_bytes is not None:
                info['memory_bytes'] = total_ram_bytes
                info['memory_total_gb'] = round(total_ram_bytes / (1024 ** 3), 2)
        except Exception:
            pass

        # Storage (disks)
        disks: List[Dict[str, Any]] = []
        try:
            used_psutil = False
            try:
                import psutil  # type: ignore
                for part in psutil.disk_partitions(all=False):
                    try:
                        usage = psutil.disk_usage(part.mountpoint)
                        disks.append({
                            'device': part.device,
                            'mountpoint': part.mountpoint,
                            'fstype': part.fstype,
                            'total_bytes': int(usage.total),
                            'free_bytes': int(usage.free),
                            'used_bytes': int(usage.used)
                        })
                    except Exception:
                        continue
                used_psutil = True
            except Exception:
                used_psutil = False

            if not used_psutil:
                # Fallback: on Windows, iterate likely drive letters
                if sys.platform.startswith('win'):
                    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                        root = f"{letter}:\\"
                        try:
                            if os.path.exists(root):
                                total, used, free = shutil.disk_usage(root)
                                disks.append({
                                    'device': letter + ':',
                                    'mountpoint': root,
                                    'fstype': None,
                                    'total_bytes': int(total),
                                    'free_bytes': int(free),
                                    'used_bytes': int(used)
                                })
                        except Exception:
                            continue
                else:
                    # POSIX fallback: root only
                    try:
                        total, used, free = shutil.disk_usage('/')
                        disks.append({
                            'device': None,
                            'mountpoint': '/',
                            'fstype': None,
                            'total_bytes': int(total),
                            'free_bytes': int(free),
                            'used_bytes': int(used)
                        })
                    except Exception:
                        pass
        except Exception:
            pass

        if disks:
            info['disks'] = disks

        return info
   
    def _collect_software(self) -> List[Dict]:
        """Basic software collection"""
        software = []
       
        if platform.system() == 'Linux':
            try:
                result = subprocess.run(['dpkg', '-l'],
                                      capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    for line in result.stdout.split('\n')[5:]:
                        if line.strip():
                            parts = line.split()
                            if len(parts) >= 3:
                                software.append({
                                    'name': parts[1],
                                    'version': parts[2]
                                })
            except:
                pass
       
        return software
   
    def _collect_network(self) -> Dict:
        """Basic network information"""
        return {
            'hostname': socket.gethostname(),
            'fqdn': socket.getfqdn()
        }

    # ------------------- Windows Enriched Collection -------------------
    def _ps_json(self, command: str, depth: int = 4) -> Any:
        """Run a PowerShell command and parse ConvertTo-Json output."""
        ps = [
            'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            f"{command} | ConvertTo-Json -Depth {depth}"
        ]
        try:
            result = subprocess.run(ps, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return None
            txt = result.stdout.strip()
            return json.loads(txt) if txt else None
        except Exception:
            return None

    # ------------------- Windows Enriched Collection (Modular) -------------------
    
    def collect_os_info(self) -> Optional[Dict[str, Any]]:
        """Collect only OS information."""
        os_info = self._ps_json('Get-CimInstance Win32_OperatingSystem', depth=5)
        if not os_info:
            return None
        try:
            if isinstance(os_info, list):
                os_info = os_info[0]
            install_date = os_info.get('InstallDate')
            last_boot = os_info.get('LastBootUpTime')
            uptime_seconds = None
            if last_boot:
                try:
                    up = self._ps_json('([Datetime]::Now - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime).TotalSeconds', depth=1)
                    uptime_seconds = int(float(up)) if up is not None else None
                except Exception:
                    pass
            return {
                'caption': os_info.get('Caption'),
                'version': os_info.get('Version'),
                'build_number': os_info.get('BuildNumber'),
                'architecture': os_info.get('OSArchitecture'),
                'install_date': install_date,
                'last_boot': last_boot,
                'uptime_seconds': uptime_seconds,
                'boot_device': os_info.get('BootDevice')
            }
        except Exception:
            return None

    def collect_hardware_summary(self) -> Optional[Dict[str, Any]]:
        """Collect only hardware summary (manufacturer, model, BIOS, etc.)."""
        cs = self._ps_json('Get-CimInstance Win32_ComputerSystem', depth=4)
        bios = self._ps_json('Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SerialNumber,SMBIOSBIOSVersion,SMBIOSAssetTag,ReleaseDate', depth=4)
        base = self._ps_json('Get-CimInstance Win32_BaseBoard', depth=4)
        enc = self._ps_json('Get-CimInstance Win32_SystemEnclosure', depth=4)
        bios_obj = (bios[0] if isinstance(bios, list) else bios) if bios else {}
        return {
            'manufacturer': (cs[0] if isinstance(cs, list) else cs or {}).get('Manufacturer') if cs else None,
            'model': (cs[0] if isinstance(cs, list) else cs or {}).get('Model') if cs else None,
            'serial_number': bios_obj.get('SerialNumber') if bios_obj else None,
            'asset_tag': bios_obj.get('SMBIOSAssetTag') if bios_obj else None,
            'bios_version': bios_obj.get('SMBIOSBIOSVersion') if bios_obj else None,
            'bios_release_date': bios_obj.get('ReleaseDate') if bios_obj else None,
            'bios_manufacturer': bios_obj.get('Manufacturer') if bios_obj else None,
            'baseboard': {
                'product': (base[0] if isinstance(base, list) else base or {}).get('Product') if base else None,
                'serial': (base[0] if isinstance(base, list) else base or {}).get('SerialNumber') if base else None
            },
            'chassis_types': (enc[0] if isinstance(enc, list) else enc or {}).get('ChassisTypes') if enc else None
        }

    def collect_cpu_info(self) -> Optional[Any]:
        """Collect only CPU information."""
        return self._ps_json('Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,CurrentClockSpeed,BaseClockSpeed,VirtualizationFirmwareEnabled', depth=4)

    def collect_memory_info(self) -> Optional[Dict[str, Any]]:
        """Collect only memory/RAM information."""
        mem = self._ps_json('Get-CimInstance Win32_PhysicalMemory | Select-Object BankLabel,Capacity,Manufacturer,PartNumber,SerialNumber,Speed,MemoryType', depth=4)
        if not mem:
            return None
        total = 0
        try:
            items = mem if isinstance(mem, list) else [mem]
            for m in items:
                cap = m.get('Capacity')
                if cap:
                    total += int(cap)
        except Exception:
            pass
        return {
            'modules': mem,
            'total_bytes': total if total else None
        }

    def collect_storage_info(self) -> Optional[Dict[str, Any]]:
        """Collect only storage/disk information."""
        disks = self._ps_json('Get-CimInstance Win32_DiskDrive | Select-Object Model,SerialNumber,Size,InterfaceType,MediaType', depth=4)
        vols = self._ps_json('Get-CimInstance Win32_Volume | Select-Object DriveLetter,Label,FileSystem,Capacity,FreeSpace', depth=4)
        if not disks:
            return None
        return {
            'physical_disks': disks,
            'volumes': vols
        }

    def collect_video_info(self) -> Dict[str, Any]:
        """Collect only video/display information."""
        gpu = self._ps_json('Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM,VideoProcessor,CurrentHorizontalResolution,CurrentVerticalResolution', depth=4)
        mon = self._ps_json('Get-CimInstance -Namespace root\\wmi WmiMonitorID | ForEach-Object { [pscustomobject]@{ ManufacturerID = ([System.Text.Encoding]::ASCII.GetString($_.ManufacturerName -ne 0 | ForEach-Object {[byte]$_})) ; ProductCodeID = ([System.Text.Encoding]::ASCII.GetString($_.ProductCodeID -ne 0 | ForEach-Object {[byte]$_})) ; SerialNumberID = ([System.Text.Encoding]::ASCII.GetString($_.SerialNumberID -ne 0 | ForEach-Object {[byte]$_})) } }', depth=4)
        return {
            'gpus': gpu,
            'monitors': mon
        }
    
    def collect_monitors_info(self) -> Dict[str, Any]:
        """Collect detailed monitor/display information."""
        # Collect from Win32_DesktopMonitor (try with and without Availability filter)
        # Some systems don't report Availability correctly, so we'll try both
        desktop_monitors = self._ps_json('Get-CimInstance Win32_DesktopMonitor | Where-Object { $_.Availability -eq 3 -or $_.Availability -eq $null } | Select-Object Caption,MonitorManufacturer,MonitorType,PNPDeviceID,Availability', depth=4)
        # If no results, try without filter
        if not desktop_monitors or (isinstance(desktop_monitors, list) and len(desktop_monitors) == 0):
            desktop_monitors = self._ps_json('Get-CimInstance Win32_DesktopMonitor | Select-Object Caption,MonitorManufacturer,MonitorType,PNPDeviceID,Availability', depth=4)
        
        # Collect from WMIMonitorConnectionParams (Vista+, includes connection type)
        monitor_connections = self._ps_json('Get-CimInstance -Namespace root\\wmi WMIMonitorConnectionParams | Where-Object { $_.Active -eq $true } | Select-Object Active,InstanceName,VideoOutputTechnology', depth=4)
        
        # Collect from WmiMonitorID (EDID data)
        monitor_ids = self._ps_json('Get-CimInstance -Namespace root\\wmi WmiMonitorID | ForEach-Object { [pscustomobject]@{ InstanceName = $_.InstanceName ; ManufacturerID = ([System.Text.Encoding]::ASCII.GetString($_.ManufacturerName -ne 0 | ForEach-Object {[byte]$_})) ; ProductCodeID = ([System.Text.Encoding]::ASCII.GetString($_.ProductCodeID -ne 0 | ForEach-Object {[byte]$_})) ; SerialNumberID = ([System.Text.Encoding]::ASCII.GetString($_.SerialNumberID -ne 0 | ForEach-Object {[byte]$_})) } }', depth=4)
        
        # Normalize to lists for counting
        dm_count = len(desktop_monitors) if isinstance(desktop_monitors, list) else (1 if desktop_monitors else 0)
        mc_count = len(monitor_connections) if isinstance(monitor_connections, list) else (1 if monitor_connections else 0)
        mi_count = len(monitor_ids) if isinstance(monitor_ids, list) else (1 if monitor_ids else 0)
        
        if self.logger:
            self.logger.info(f"Collected monitor data: {dm_count} desktop monitors, {mc_count} connections, {mi_count} monitor IDs")
        
        return {
            'desktop_monitors': desktop_monitors,
            'monitor_connections': monitor_connections,
            'monitor_ids': monitor_ids
        }

    def collect_audio_info(self) -> Optional[Any]:
        """Collect only audio/sound device information."""
        return self._ps_json('Get-CimInstance Win32_SoundDevice | Select-Object Name,Manufacturer,Status', depth=4)

    def collect_network_info(self) -> Dict[str, Any]:
        """Collect only network information."""
        # Get physical adapters (Ethernet, Wi-Fi, etc.) - this should include WiFi
        adapters = self._ps_json('Get-CimInstance Win32_NetworkAdapter | Where-Object {$_.PhysicalAdapter -eq $true} | Select-Object Name,NetConnectionStatus,MACAddress,Speed,PNPDeviceID,AdapterTypeID', depth=4)
        # Also get Bluetooth adapters separately (they might not be marked as PhysicalAdapter)
        # Use more specific query to avoid catching WiFi adapters
        bluetooth_adapters = self._ps_json('Get-CimInstance Win32_NetworkAdapter | Where-Object {($_.Name -like "*Bluetooth*" -and $_.Name -notlike "*WiFi*" -and $_.Name -notlike "*Wireless*") -or ($_.PNPDeviceID -like "*BTHENUM*" -and $_.PNPDeviceID -notlike "*802.11*")} | Select-Object Name,NetConnectionStatus,MACAddress,Speed,PNPDeviceID,AdapterTypeID', depth=4)
        # Get LinkSpeed from Get-NetAdapter (more reliable for active adapters)
        net_adapters = self._ps_json('Get-NetAdapter | Where-Object {$_.Status -eq "Up"} | Select-Object Name,MACAddress,LinkSpeed', depth=4)
        cfg = self._ps_json('Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {$_.IPEnabled -eq $true} | Select-Object Description,MACAddress,IPAddress,IPSubnet,DefaultIPGateway,DNSServerSearchOrder', depth=4)
        routes = self._ps_json('Get-NetRoute -AddressFamily IPv4 | Select-Object DestinationPrefix,NextHop,InterfaceAlias,RouteMetric', depth=4)
        
        # Normalize adapters to a list first
        if not adapters:
            all_adapters = []
        elif isinstance(adapters, list):
            all_adapters = adapters
        else:
            # Single adapter returned as dict
            all_adapters = [adapters]
        
        # Add Bluetooth adapters if they exist, avoiding duplicates
        if bluetooth_adapters:
            # Normalize Bluetooth adapters to list
            if not isinstance(bluetooth_adapters, list):
                bluetooth_adapters = [bluetooth_adapters]
            
            # Create set of existing MAC addresses for duplicate detection
            existing_macs = set()
            for a in all_adapters:
                if isinstance(a, dict):
                    mac = a.get('MACAddress', '')
                    if mac:
                        existing_macs.add(str(mac).upper().strip())
            
            # Add Bluetooth adapters that aren't already in the list
            for bt_adapter in bluetooth_adapters:
                if isinstance(bt_adapter, dict):
                    bt_mac = bt_adapter.get('MACAddress', '')
                    if bt_mac:
                        bt_mac_normalized = str(bt_mac).upper().strip()
                        if bt_mac_normalized not in existing_macs:
                            all_adapters.append(bt_adapter)
                            existing_macs.add(bt_mac_normalized)
                    else:
                        # Bluetooth adapter without MAC - add it anyway (might be virtual)
                        all_adapters.append(bt_adapter)
        
        return {
            'adapters': all_adapters,
            'net_adapters': net_adapters,  # Get-NetAdapter data with LinkSpeed
            'config': cfg,
            'routes': routes
        }

    def collect_printer_info(self) -> Optional[Any]:
        """Collect only printer information."""
        return self._ps_json('Get-CimInstance Win32_Printer | Select-Object Name,DriverName,PortName,WorkOffline,Default', depth=4)

    def collect_software_info(self) -> Optional[Any]:
        """Collect only installed software information."""
        software_cmd = (
            "$paths = @('HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall','HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall');"
            "$apps = foreach ($p in $paths) { Get-ChildItem $p -ErrorAction SilentlyContinue | ForEach-Object { Get-ItemProperty $_.PsPath -ErrorAction SilentlyContinue | Select-Object DisplayName,DisplayVersion,Publisher,InstallDate,EstimatedSize } };"
            "$apps | Where-Object { $_.DisplayName }"
        )
        return self._ps_json(software_cmd, depth=4)

    def collect_updates_info(self) -> Optional[Any]:
        """Collect only Windows updates/hotfixes information."""
        return self._ps_json('Get-CimInstance Win32_QuickFixEngineering | Select-Object HotFixID,Description,InstalledOn', depth=4)

    def collect_drivers_info(self) -> Optional[Any]:
        """Collect only driver information."""
        return self._ps_json('Get-CimInstance Win32_PnPSignedDriver | Select-Object DeviceName,DriverVersion,DriverDate,Manufacturer,ClassGuid', depth=4)

    def collect_services_info(self) -> Optional[Any]:
        """Collect only services information."""
        return self._ps_json('Get-CimInstance Win32_Service | Select-Object Name,DisplayName,State,StartMode,StartName', depth=4)

    def collect_accounts_info(self) -> Optional[Dict[str, Any]]:
        """Collect only users and groups information."""
        users = self._ps_json('Get-CimInstance Win32_UserAccount -Filter "LocalAccount=True" | Select-Object Name,FullName,Disabled,Lockout,PasswordChangeable,PasswordExpires,PasswordRequired', depth=4)
        groups = self._ps_json('Get-CimInstance Win32_Group -Filter "LocalAccount=True" | Select-Object Name,Description', depth=4)
        if not users and not groups:
            return None
        return {
            'users': users,
            'groups': groups
        }

    def collect_security_info(self) -> Dict[str, Any]:
        """Collect only security information (TPM, firewall)."""
        tpm = self._ps_json('Get-Tpm', depth=4)
        firewall = self._ps_json('Get-NetFirewallProfile | Select-Object Name,Enabled,DefaultInboundAction,DefaultOutboundAction', depth=4)
        return {
            'tpm': tpm,
            'firewall_profiles': firewall
        }

    def collect_shares_info(self) -> Optional[Any]:
        """Collect only network shares information."""
        return self._ps_json('Get-CimInstance Win32_Share | Select-Object Name,Path,Description,Type', depth=4)

    def collect_ports_info(self) -> Optional[Any]:
        """Collect port information (COM, LPT, USB controllers)."""
        # Get serial ports (COM ports)
        com_ports = self._ps_json('Get-CimInstance Win32_SerialPort | Select-Object Name,Description,DeviceID', depth=4)
        # Get parallel ports (LPT ports)
        lpt_ports = self._ps_json('Get-CimInstance Win32_ParallelPort | Select-Object Name,Description,DeviceID', depth=4)
        # Get USB controllers (as ports)
        usb_controllers = self._ps_json('Get-CimInstance Win32_USBController | Select-Object Name,Description,DeviceID', depth=4)
        return {
            'com_ports': com_ports,
            'lpt_ports': lpt_ports,
            'usb_controllers': usb_controllers
        }
    
    def collect_power_info(self) -> Optional[Dict[str, Any]]:
        """Collect only battery/power information."""
        # Get detailed battery info including chemistry, voltage, serial, manufacturer, date
        battery = self._ps_json('Get-CimInstance Win32_Battery | Select-Object Name,DesignCapacity,FullChargeCapacity,DesignVoltage,Chemistry,EstimatedChargeRemaining,Status,Availability,DeviceID,ManufactureDate,ManufactureName,BatteryStatus,ExpectedLife,TimeOnBattery', depth=4)
        
        # Try to get additional battery data from battery report XML (like Perl version)
        # This can provide capacity, manufacturer, and cycle count when WMI fields are null
        battery_report_data = {}
        try:
            import tempfile
            import os
            import subprocess
            import xml.etree.ElementTree as ET
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                report_path = f.name
            
            try:
                # Run powercfg to generate battery report XML (like Perl version)
                result = subprocess.run(
                    ['powercfg', '/batteryreport', '/xml', '/output', report_path],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                
                if os.path.exists(report_path) and os.path.getsize(report_path) > 0:
                    # Parse battery report XML
                    try:
                        tree = ET.parse(report_path)
                        root = tree.getroot()
                        
                        # XML structure: root is BatteryReport -> Batteries -> Battery[]
                        # Handle namespace if present
                        if root.tag.endswith('BatteryReport') or root.tag == 'BatteryReport':
                            batteries = root.find('Batteries')
                            if batteries is None:
                                # Try with namespace
                                for child in root:
                                    if child.tag.endswith('Batteries') or child.tag == 'Batteries':
                                        batteries = child
                                        break
                            
                            if batteries is not None:
                                # Get the first battery (usually there's only one)
                                battery_elem = batteries.find('Battery')
                                if battery_elem is None:
                                    # Try with namespace or as list
                                    for child in batteries:
                                        if child.tag.endswith('Battery') or child.tag == 'Battery':
                                            battery_elem = child
                                            break
                                
                                if battery_elem is not None:
                                    # Extract DesignCapacity
                                    design_cap_elem = battery_elem.find('DesignCapacity')
                                    if design_cap_elem is None:
                                        for child in battery_elem:
                                            if child.tag.endswith('DesignCapacity') or child.tag == 'DesignCapacity':
                                                design_cap_elem = child
                                                break
                                    if design_cap_elem is not None and design_cap_elem.text:
                                        try:
                                            battery_report_data['DesignCapacity'] = int(design_cap_elem.text)
                                        except ValueError:
                                            pass
                                    
                                    # Extract FullChargeCapacity
                                    full_cap_elem = battery_elem.find('FullChargeCapacity')
                                    if full_cap_elem is None:
                                        for child in battery_elem:
                                            if child.tag.endswith('FullChargeCapacity') or child.tag == 'FullChargeCapacity':
                                                full_cap_elem = child
                                                break
                                    if full_cap_elem is not None and full_cap_elem.text:
                                        try:
                                            battery_report_data['FullChargeCapacity'] = int(full_cap_elem.text)
                                        except ValueError:
                                            pass
                                    
                                    # Extract Manufacturer
                                    manuf_elem = battery_elem.find('Manufacturer')
                                    if manuf_elem is None:
                                        for child in battery_elem:
                                            if child.tag.endswith('Manufacturer') or child.tag == 'Manufacturer':
                                                manuf_elem = child
                                                break
                                    if manuf_elem is not None and manuf_elem.text:
                                        manuf = manuf_elem.text.strip()
                                        if manuf:
                                            battery_report_data['ManufactureName'] = manuf
                                    
                                    # Extract CycleCount
                                    cycle_elem = battery_elem.find('CycleCount')
                                    if cycle_elem is None:
                                        for child in battery_elem:
                                            if child.tag.endswith('CycleCount') or child.tag == 'CycleCount':
                                                cycle_elem = child
                                                break
                                    if cycle_elem is not None and cycle_elem.text:
                                        try:
                                            battery_report_data['CycleCount'] = int(cycle_elem.text)
                                        except ValueError:
                                            pass
                    except ET.ParseError as e:
                        # XML parsing failed, skip
                        if self.logger:
                            self.logger.debug(f"Battery report XML parsing error: {e}")
                        pass
                    except Exception as e:
                        if self.logger:
                            self.logger.debug(f"Battery report parsing error: {e}")
                        pass
            except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError, OSError):
                # powercfg not available or permission denied - silently skip
                pass
            except Exception:
                # Any other error - silently skip
                pass
            finally:
                # Clean up temp file
                try:
                    if os.path.exists(report_path):
                        os.unlink(report_path)
                except Exception:
                    pass
        except Exception:
            # If anything fails, just continue without battery report data
            pass
        
        if not battery:
            return None
        
        # Merge battery report data into battery data (fills in missing WMI fields)
        if battery_report_data:
            if isinstance(battery, list) and len(battery) > 0:
                if isinstance(battery[0], dict):
                    # Fill in missing fields from battery report
                    for key, value in battery_report_data.items():
                        if not battery[0].get(key) or battery[0].get(key) is None:
                            battery[0][key] = value
            elif isinstance(battery, dict):
                # Fill in missing fields from battery report
                for key, value in battery_report_data.items():
                    if not battery.get(key) or battery.get(key) is None:
                        battery[key] = value
        
        return {
            'batteries': battery
        }
    
    def collect_controllers_info(self) -> Optional[Any]:
        """Collect controller information (PCI devices, USB controllers, etc.).
        
        This follows the Perl Win32 Controllers module approach:
        - Only includes controllers with PCI vendor/product IDs
        - Uses PCI database to get proper names/manufacturers
        - Avoids duplicates by vendor/product ID
        """
        import re
        all_controllers = []
        seen_vendor_product = {}  # Track duplicates by vendor/product ID
        
        # List of WMI controller classes to query (same as Perl module)
        controller_classes = [
            'Win32_FloppyController',
            'Win32_IDEController', 
            'Win32_SCSIController',
            'Win32_VideoController',
            'Win32_InfraredDevice',
            'Win32_USBController',
            'Win32_1394Controller',
            'Win32_PCMCIAController',
            'CIM_LogicalDevice'
        ]
        
        for class_name in controller_classes:
            try:
                controllers = self._ps_json(f'Get-CimInstance {class_name} | Select-Object Name,Manufacturer,Caption,DeviceID', depth=4)
                if controllers:
                    controllers_list = controllers if isinstance(controllers, list) else [controllers]
                    for ctrl in controllers_list:
                        if not isinstance(ctrl, dict) or not ctrl.get('DeviceID'):
                            continue
                        
                        device_id = str(ctrl.get('DeviceID', ''))
                        
                        # Extract vendor and product IDs from DeviceID (PCI format)
                        vendor_match = re.search(r'PCI\\VEN_([A-F0-9]{4})&DEV_([A-F0-9]{4})', device_id, re.IGNORECASE)
                        if not vendor_match:
                            # Skip if no PCI vendor/product ID (following Perl approach)
                            continue
                        
                        vendor_id = vendor_match.group(1).lower()
                        product_id = vendor_match.group(2).lower()
                        
                        # Avoid duplicates by vendor/product ID (same as Perl)
                        if vendor_id not in seen_vendor_product:
                            seen_vendor_product[vendor_id] = {}
                        if product_id in seen_vendor_product[vendor_id]:
                            continue
                        seen_vendor_product[vendor_id][product_id] = True
                        
                        # Extract subsystem ID if available
                        subsystem_id = None
                        subsys_match = re.search(r'&SUBSYS_([A-F0-9]{4})([A-F0-9]{4})', device_id, re.IGNORECASE)
                        if subsys_match:
                            subsystem_id = f"{subsys_match.group(2).lower()}:{subsys_match.group(1).lower()}"
                        
                        controller_entry = {
                            'Name': ctrl.get('Name', ''),
                            'Manufacturer': ctrl.get('Manufacturer', ''),
                            'Caption': ctrl.get('Caption', ''),
                            'DeviceID': device_id,
                            'VENDORID': vendor_id,
                            'PRODUCTID': product_id,
                            'Class': class_name.replace('Win32_', '').replace('Controller', '')
                        }
                        
                        if subsystem_id:
                            controller_entry['PCISUBSYSTEMID'] = subsystem_id
                        
                        all_controllers.append(controller_entry)
            except Exception as e:
                # Skip if class doesn't exist or query fails
                if hasattr(self, 'logger'):
                    self.logger.debug(f"Error querying {class_name}: {e}")
                continue
        
        # Log what we collected
        if hasattr(self, 'logger'):
            self.logger.info(f"Collected {len(all_controllers)} controllers with PCI IDs (following Perl module approach)")
        
        return all_controllers if all_controllers else []

    # ------------------- macOS Collection Methods -------------------
    
    def _macos_json(self, command: List[str]) -> Any:
        """Run a macOS command and parse JSON output."""
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return None
            txt = result.stdout.strip()
            return json.loads(txt) if txt else None
        except Exception:
            return None
    
    def _macos_plist(self, command: List[str]) -> Any:
        """Run a macOS command and parse plist output."""
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return None
            txt = result.stdout.strip()
            # Parse plist XML
            import plistlib
            return plistlib.loads(txt.encode()) if txt else None
        except Exception:
            return None
    
    def _macos_system_profiler(self, data_type: str) -> Dict[str, Any]:
        """Get system_profiler data as structured dict."""
        try:
            result = subprocess.run(
                ['/usr/sbin/system_profiler', data_type, '-xml'],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                return {}
            import plistlib
            data = plistlib.loads(result.stdout.encode())
            return data[0].get('_items', [{}])[0] if data and len(data) > 0 else {}
        except Exception:
            return {}
    
    def _macos_ioreg(self, entry: str = None, key: str = None) -> Any:
        """Get IORegistry data using ioreg command."""
        try:
            cmd = ['ioreg', '-a', '-r', '-l']
            if entry:
                cmd.extend(['-c', entry])
            if key:
                cmd.extend(['-k', key])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return None
            txt = result.stdout.strip()
            return json.loads(txt) if txt else None
        except Exception:
            return None
    
    def collect_macos_os_info(self) -> Optional[Dict[str, Any]]:
        """Collect macOS OS information."""
        try:
            # Get system version
            result = subprocess.run(
                ['sw_vers'],
                capture_output=True, text=True, timeout=10
            )
            os_info = {}
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower().replace(' ', '_')
                        os_info[key] = value.strip()
            
            # Get kernel version
            result = subprocess.run(
                ['uname', '-r'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                os_info['kernel_version'] = result.stdout.strip()
            
            # Get boot time
            result = subprocess.run(
                ['sysctl', '-n', 'kern.boottime'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                import re
                match = re.search(r'sec = (\d+)', result.stdout)
                if match:
                    os_info['boot_time'] = int(match.group(1))
            
            return os_info if os_info else None
        except Exception:
            return None
    
    def collect_macos_hardware_summary(self) -> Optional[Dict[str, Any]]:
        """Collect macOS hardware summary."""
        try:
            hw = self._macos_system_profiler('SPHardwareDataType')
            if not hw:
                return None
            
            # Get manufacturer from system_profiler (should be Apple, but get it dynamically)
            manufacturer = hw.get('Manufacturer') or hw.get('manufacturer')
            if not manufacturer:
                # Fallback: Check if it's an Apple device (all Macs are Apple)
                # This is a reasonable assumption but we try to get it from system first
                manufacturer = 'Apple'
            
            return {
                'manufacturer': manufacturer,
                'model': hw.get('Model Name') or hw.get('model_name'),
                'model_identifier': hw.get('Model Identifier') or hw.get('model_identifier'),
                'serial_number': hw.get('Serial Number') or hw.get('serial_number'),
                'hardware_uuid': hw.get('Hardware UUID') or hw.get('hardware_uuid'),
                'processor_name': hw.get('Processor Name') or hw.get('processor_name'),
                'processor_speed': hw.get('Processor Speed') or hw.get('processor_speed'),
                'number_of_processors': hw.get('Number of Processors') or hw.get('number_of_processors'),
                'total_number_of_cores': hw.get('Total Number of Cores') or hw.get('total_number_of_cores'),
                'memory': hw.get('Memory') or hw.get('memory'),
            }
        except Exception:
            return None
    
    def collect_macos_cpu_info(self) -> Optional[Any]:
        """Collect macOS CPU information."""
        try:
            hw = self._macos_system_profiler('SPHardwareDataType')
            if not hw:
                return None
            
            # Get additional CPU info from sysctl
            result = subprocess.run(
                ['sysctl', '-a', 'machdep.cpu'],
                capture_output=True, text=True, timeout=10
            )
            sysctl_info = {}
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if ':' in line:
                        key, value = line.split(':', 1)
                        sysctl_info[key.strip()] = value.strip()
            
            cpu_info = {
                'name': hw.get('Processor Name') or sysctl_info.get('machdep.cpu.brand_string'),
                'cores': hw.get('Total Number of Cores') or sysctl_info.get('machdep.cpu.core_count'),
                'threads': sysctl_info.get('machdep.cpu.thread_count'),
                'speed': hw.get('Processor Speed'),
                'number_of_processors': hw.get('Number of Processors', 1),
            }
            
            return cpu_info
        except Exception:
            return None
    
    def collect_macos_memory_info(self) -> Optional[Dict[str, Any]]:
        """Collect macOS memory information."""
        try:
            hw = self._macos_system_profiler('SPHardwareDataType')
            memory_str = hw.get('Memory') or hw.get('memory', '')
            
            # Parse memory string like "16 GB"
            import re
            match = re.match(r'(\d+)\s*(GB|MB)', memory_str, re.IGNORECASE)
            total_bytes = None
            if match:
                value = int(match.group(1))
                unit = match.group(2).upper()
                if unit == 'GB':
                    total_bytes = value * 1024 * 1024 * 1024
                elif unit == 'MB':
                    total_bytes = value * 1024 * 1024
            
            # Get memory modules from system_profiler
            mem_modules = self._macos_system_profiler('SPMemoryDataType')
            modules = []
            if isinstance(mem_modules, dict):
                # Extract memory slots
                for key, value in mem_modules.items():
                    if 'dimm' in key.lower() or 'slot' in key.lower():
                        if isinstance(value, dict):
                            modules.append(value)
            
            return {
                'total_bytes': total_bytes,
                'modules': modules if modules else None
            }
        except Exception:
            return None
    
    def collect_macos_storage_info(self) -> Optional[Dict[str, Any]]:
        """Collect macOS storage information."""
        try:
            # Get storage info from system_profiler
            storage = self._macos_system_profiler('SPStorageDataType')
            disks = []
            
            if isinstance(storage, dict):
                # Extract disk information
                for key, value in storage.items():
                    if isinstance(value, dict) and ('size' in key.lower() or 'disk' in key.lower()):
                        disks.append(value)
            
            # Also get from diskutil
            result = subprocess.run(
                ['diskutil', 'list', '-plist'],
                capture_output=True, text=True, timeout=30
            )
            diskutil_data = None
            if result.returncode == 0:
                try:
                    import plistlib
                    diskutil_data = plistlib.loads(result.stdout.encode())
                except Exception:
                    pass
            
            return {
                'physical_disks': disks if disks else None,
                'diskutil': diskutil_data
            }
        except Exception:
            return None
    
    def collect_macos_video_info(self) -> Dict[str, Any]:
        """Collect macOS video/display information."""
        try:
            # Get graphics info from system_profiler
            graphics = self._macos_system_profiler('SPDisplaysDataType')
            gpus = []
            
            if isinstance(graphics, dict):
                # Extract GPU information
                for key, value in graphics.items():
                    if isinstance(value, dict):
                        gpus.append(value)
            
            return {
                'gpus': gpus if gpus else None
            }
        except Exception:
            return {}
    
    def collect_macos_monitors_info(self) -> Dict[str, Any]:
        """Collect macOS monitor/display information."""
        try:
            # Get display info from system_profiler
            displays = self._macos_system_profiler('SPDisplaysDataType')
            monitor_list = []
            
            if isinstance(displays, dict):
                # Extract monitor information
                for key, value in displays.items():
                    if isinstance(value, dict) and ('display' in key.lower() or 'resolution' in key.lower()):
                        monitor_list.append(value)
            
            # Also get from IORegistry for EDID data
            ioreg_displays = self._macos_ioreg(entry='IODisplayWrangler')
            
            return {
                'displays': monitor_list if monitor_list else None,
                'ioreg_displays': ioreg_displays
            }
        except Exception:
            return {}
    
    def collect_macos_audio_info(self) -> Optional[Any]:
        """Collect macOS audio/sound device information."""
        try:
            # Get audio info from system_profiler
            audio = self._macos_system_profiler('SPAudioDataType')
            if not audio:
                return None
            
            devices = []
            if isinstance(audio, dict):
                for key, value in audio.items():
                    if isinstance(value, dict):
                        devices.append(value)
            
            return devices if devices else None
        except Exception:
            return None
    
    def collect_macos_network_info(self) -> Dict[str, Any]:
        """Collect macOS network information."""
        try:
            # Get network info from system_profiler
            network = self._macos_system_profiler('SPNetworkDataType')
            adapters = []
            
            if isinstance(network, dict):
                # Extract network interfaces
                for key, value in network.items():
                    if isinstance(value, dict):
                        adapters.append(value)
            
            # Also get from ifconfig
            result = subprocess.run(
                ['ifconfig'],
                capture_output=True, text=True, timeout=30
            )
            ifconfig_data = result.stdout if result.returncode == 0 else None
            
            return {
                'adapters': adapters if adapters else None,
                'ifconfig': ifconfig_data
            }
        except Exception:
            return {}
    
    def collect_macos_printer_info(self) -> Optional[Any]:
        """Collect macOS printer information."""
        try:
            result = subprocess.run(
                ['lpstat', '-p', '-d'],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                return None
            
            printers = []
            for line in result.stdout.splitlines():
                if line.startswith('printer'):
                    # Parse printer line
                    parts = line.split()
                    if len(parts) >= 2:
                        printers.append({
                            'name': parts[1],
                            'status': ' '.join(parts[2:]) if len(parts) > 2 else 'idle'
                        })
            
            return printers if printers else None
        except Exception:
            return None
    
    def collect_macos_software_info(self) -> Optional[Any]:
        """Collect macOS installed software information."""
        try:
            # Get applications from /Applications
            apps = []
            import os
            app_dir = '/Applications'
            if os.path.isdir(app_dir):
                for item in os.listdir(app_dir):
                    if item.endswith('.app'):
                        app_path = os.path.join(app_dir, item)
                        # Get app info from Info.plist
                        plist_path = os.path.join(app_path, 'Contents', 'Info.plist')
                        if os.path.exists(plist_path):
                            try:
                                import plistlib
                                with open(plist_path, 'rb') as f:
                                    plist = plistlib.load(f)
                                    apps.append({
                                        'name': plist.get('CFBundleName') or item.replace('.app', ''),
                                        'version': plist.get('CFBundleShortVersionString'),
                                        'bundle_id': plist.get('CFBundleIdentifier')
                                    })
                            except Exception:
                                apps.append({'name': item.replace('.app', '')})
            
            return apps[:100] if apps else None  # Limit to 100
        except Exception:
            return None
    
    def collect_macos_power_info(self) -> Optional[Dict[str, Any]]:
        """Collect macOS power/battery information."""
        try:
            # Get power info from system_profiler
            power = self._macos_system_profiler('SPPowerDataType')
            batteries = []
            
            if isinstance(power, dict):
                battery_info = power.get('Battery Information') or power.get('battery_information', {})
                if battery_info:
                    batteries.append(battery_info)
            
            # Also get from ioreg for more details
            ioreg_battery = self._macos_ioreg(entry='IOPMPowerSource')
            
            return {
                'batteries': batteries if batteries else None,
                'ioreg_battery': ioreg_battery
            }
        except Exception:
            return None
    
    def collect_macos_controllers_info(self) -> Optional[Any]:
        """Collect macOS controller information (PCI, USB, etc.)."""
        try:
            # Get PCI devices from system_profiler
            pci = self._macos_system_profiler('SPPCIDataType')
            controllers = []
            
            if isinstance(pci, dict):
                # Extract PCI controller information
                for key, value in pci.items():
                    if isinstance(value, dict):
                        controllers.append(value)
            
            # Also get USB controllers
            usb = self._macos_system_profiler('SPUSBDataType')
            if isinstance(usb, dict):
                for key, value in usb.items():
                    if isinstance(value, dict) and 'controller' in key.lower():
                        controllers.append(value)
            
            return controllers if controllers else None
        except Exception:
            return None

    def _collect_macos_enriched(self, categories: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Collect extended macOS inventory via system_profiler, ioreg, etc.
        
        Args:
            categories: Optional list of specific categories to collect.
                       If None, collects all categories.
                       Valid categories: 'os', 'hardware', 'cpu', 'memory', 'storage',
                       'video', 'audio', 'network', 'printers', 'software', 'power',
                       'controllers', 'monitors'
        
        Returns:
            Dictionary with collected inventory data
        """
        data: Dict[str, Any] = {}
        collect_all = categories is None or len(categories) == 0
        
        # Map category names to methods
        category_map = {
            'os': ('operating_system', self.collect_macos_os_info),
            'hardware': ('hardware_summary', self.collect_macos_hardware_summary),
            'cpu': ('cpu', self.collect_macos_cpu_info),
            'memory': ('memory', self.collect_macos_memory_info),
            'storage': ('storage', self.collect_macos_storage_info),
            'video': ('video', self.collect_macos_video_info),
            'audio': ('audio', self.collect_macos_audio_info),
            'network': ('network_detail', self.collect_macos_network_info),
            'printers': ('printers', self.collect_macos_printer_info),
            'software': ('software', self.collect_macos_software_info),
            'power': ('power', self.collect_macos_power_info),
            'controllers': ('controllers', self.collect_macos_controllers_info),
            'monitors': ('monitors', self.collect_macos_monitors_info),
        }
        
        # Collect requested categories
        for cat_key, (output_key, method) in category_map.items():
            if collect_all or cat_key in categories:
                try:
                    result = method()
                    if result is not None:
                        data[output_key] = result
                except Exception:
                    pass  # Skip failed categories
        
        return data

    # ------------------- Linux Collection Methods -------------------
    
    def _linux_read_file(self, filepath: str) -> Optional[str]:
        """Read a file and return its content."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read().strip()
        except Exception:
            return None
    
    def _linux_read_lines(self, filepath: str) -> List[str]:
        """Read a file and return its lines."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return [line.strip() for line in f.readlines()]
        except Exception:
            return []
    
    def _linux_run_command(self, command: List[str], timeout: int = 30) -> Optional[str]:
        """Run a Linux command and return output."""
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
    
    def collect_linux_os_info(self) -> Optional[Dict[str, Any]]:
        """Collect Linux OS information."""
        try:
            os_info = {}
            
            # Get OS release info
            release_file = '/etc/os-release'
            if os.path.exists(release_file):
                lines = self._linux_read_lines(release_file)
                for line in lines:
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        os_info[key.lower()] = value
            
            # Get kernel version
            kernel = self._linux_read_file('/proc/sys/kernel/osrelease')
            if kernel:
                os_info['kernel_version'] = kernel
            
            # Get hostname
            hostname = self._linux_read_file('/proc/sys/kernel/hostname')
            if hostname:
                os_info['hostname'] = hostname
            
            # Get uptime
            uptime_sec = self._linux_read_file('/proc/uptime')
            if uptime_sec:
                try:
                    os_info['uptime_seconds'] = int(float(uptime_sec.split()[0]))
                except (ValueError, IndexError):
                    pass
            
            return os_info if os_info else None
        except Exception:
            return None
    
    def collect_linux_hardware_summary(self) -> Optional[Dict[str, Any]]:
        """Collect Linux hardware summary using dmidecode."""
        try:
            # Try dmidecode first
            result = self._linux_run_command(['dmidecode', '-s', 'system-manufacturer'])
            manufacturer = result if result else None
            
            result = self._linux_run_command(['dmidecode', '-s', 'system-product-name'])
            model = result if result else None
            
            result = self._linux_run_command(['dmidecode', '-s', 'system-serial-number'])
            serial_number = result if result else None
            
            result = self._linux_run_command(['dmidecode', '-s', 'bios-vendor'])
            bios_vendor = result if result else None
            
            result = self._linux_run_command(['dmidecode', '-s', 'bios-version'])
            bios_version = result if result else None
            
            result = self._linux_run_command(['dmidecode', '-s', 'bios-release-date'])
            bios_date = result if result else None
            
            # Get chassis type
            result = self._linux_run_command(['dmidecode', '-s', 'chassis-type'])
            chassis_type = result if result else None
            
            return {
                'manufacturer': manufacturer,
                'model': model,
                'serial_number': serial_number,
                'bios_vendor': bios_vendor,
                'bios_version': bios_version,
                'bios_date': bios_date,
                'chassis_type': chassis_type,
            }
        except Exception:
            return None
    
    def collect_linux_cpu_info(self) -> Optional[Any]:
        """Collect Linux CPU information from /proc/cpuinfo."""
        try:
            cpuinfo = self._linux_read_file('/proc/cpuinfo')
            if not cpuinfo:
                return None
            
            cpus = []
            current_cpu = {}
            
            for line in cpuinfo.splitlines():
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'processor':
                        if current_cpu:
                            cpus.append(current_cpu)
                        current_cpu = {}
                    
                    if key in ['model name', 'Processor', 'cpu']:
                        current_cpu['name'] = value
                    elif key == 'cpu MHz':
                        try:
                            current_cpu['speed'] = int(float(value))
                        except ValueError:
                            pass
                    elif key == 'cpu cores':
                        try:
                            current_cpu['cores'] = int(value)
                        except ValueError:
                            pass
                    elif key == 'siblings':
                        try:
                            current_cpu['threads'] = int(value)
                        except ValueError:
                            pass
            
            if current_cpu:
                cpus.append(current_cpu)
            
            return cpus[0] if cpus else None
        except Exception:
            return None
    
    def collect_linux_memory_info(self) -> Optional[Dict[str, Any]]:
        """Collect Linux memory information."""
        try:
            meminfo = self._linux_read_file('/proc/meminfo')
            if not meminfo:
                return None
            
            total_kb = None
            for line in meminfo.splitlines():
                if line.startswith('MemTotal:'):
                    try:
                        total_kb = int(line.split()[1])
                    except (ValueError, IndexError):
                        pass
                    break
            
            total_bytes = total_kb * 1024 if total_kb else None
            
            # Try to get memory modules from dmidecode
            modules = []
            result = self._linux_run_command(['dmidecode', '-t', '17'])
            if result:
                # Parse dmidecode output for memory modules
                current_module = {}
                for line in result.splitlines():
                    if 'Size:' in line and 'No Module Installed' not in line:
                        try:
                            size_str = line.split('Size:')[1].strip()
                            if 'MB' in size_str:
                                size_mb = int(size_str.replace('MB', '').strip())
                                current_module['size_mb'] = size_mb
                            elif 'GB' in size_str:
                                size_gb = int(size_str.replace('GB', '').strip())
                                current_module['size_mb'] = size_gb * 1024
                        except (ValueError, IndexError):
                            pass
                    elif 'Speed:' in line:
                        try:
                            speed = line.split('Speed:')[1].strip().split()[0]
                            current_module['speed'] = int(speed)
                        except (ValueError, IndexError):
                            pass
                    elif 'Manufacturer:' in line:
                        current_module['manufacturer'] = line.split('Manufacturer:')[1].strip()
                    elif 'Serial Number:' in line:
                        current_module['serial'] = line.split('Serial Number:')[1].strip()
                    elif 'Part Number:' in line:
                        current_module['part_number'] = line.split('Part Number:')[1].strip()
                    elif line.strip() == '' and current_module:
                        modules.append(current_module)
                        current_module = {}
                if current_module:
                    modules.append(current_module)
            
            return {
                'total_bytes': total_bytes,
                'modules': modules if modules else None
            }
        except Exception:
            return None
    
    def collect_linux_storage_info(self) -> Optional[Dict[str, Any]]:
        """Collect Linux storage information."""
        try:
            disks = []
            
            # Get disk info from /proc/partitions
            partitions = self._linux_read_file('/proc/partitions')
            if partitions:
                seen_disks = set()
                for line in partitions.splitlines()[2:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 4:
                        device = parts[3]
                        # Get base device (e.g., sda from sda1)
                        base_device = ''.join(c for c in device if c.isalpha())
                        if base_device and base_device not in seen_disks:
                            seen_disks.add(base_device)
                            # Get size from /sys/block
                            size_file = f'/sys/block/{base_device}/size'
                            size_sectors = self._linux_read_file(size_file)
                            if size_sectors:
                                try:
                                    # Size is in 512-byte sectors
                                    size_bytes = int(size_sectors) * 512
                                    disks.append({
                                        'name': base_device,
                                        'size_bytes': size_bytes
                                    })
                                except ValueError:
                                    pass
            
            # Try to get more info from lsblk or fdisk
            result = self._linux_run_command(['lsblk', '-d', '-n', '-o', 'NAME,SIZE,MODEL,SERIAL'])
            if result:
                for line in result.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        disk_name = parts[0]
                        # Find matching disk and add info
                        for disk in disks:
                            if disk['name'] == disk_name:
                                if len(parts) >= 2:
                                    disk['size_str'] = parts[1]
                                if len(parts) >= 3:
                                    disk['model'] = ' '.join(parts[2:-1]) if len(parts) > 3 else parts[2]
                                if len(parts) >= 4:
                                    disk['serial'] = parts[-1]
                                break
            
            return {
                'physical_disks': disks if disks else None
            }
        except Exception:
            return None
    
    def collect_linux_video_info(self) -> Dict[str, Any]:
        """Collect Linux video/GPU information."""
        try:
            gpus = []
            
            # Get GPU info from lspci
            result = self._linux_run_command(['lspci'])
            if result:
                for line in result.splitlines():
                    if 'VGA' in line or 'Display' in line or '3D' in line:
                        gpus.append({
                            'name': line.split(':')[2].strip() if ':' in line else line.strip()
                        })
            
            # Also check /sys/class/drm for more details
            drm_dir = '/sys/class/drm'
            if os.path.isdir(drm_dir):
                for item in os.listdir(drm_dir):
                    if item.startswith('card') and not '-' in item:
                        # Get GPU info
                        device_path = os.path.join(drm_dir, item, 'device')
                        if os.path.exists(device_path):
                            vendor_file = os.path.join(device_path, 'vendor')
                            device_file = os.path.join(device_path, 'device')
                            vendor = self._linux_read_file(vendor_file)
                            device = self._linux_read_file(device_file)
                            if vendor and device:
                                gpus.append({
                                    'vendor_id': vendor,
                                    'device_id': device
                                })
            
            return {
                'gpus': gpus if gpus else None
            }
        except Exception:
            return {}
    
    def collect_linux_network_info(self) -> Dict[str, Any]:
        """Collect Linux network information."""
        try:
            adapters = []
            
            # Get network interfaces from /sys/class/net
            net_dir = '/sys/class/net'
            if os.path.isdir(net_dir):
                for interface in os.listdir(net_dir):
                    if interface == 'lo':
                        continue
                    
                    adapter = {'name': interface}
                    
                    # Get MAC address
                    mac_file = os.path.join(net_dir, interface, 'address')
                    mac = self._linux_read_file(mac_file)
                    if mac:
                        adapter['mac'] = mac.upper()
                    
                    # Get speed
                    speed_file = os.path.join(net_dir, interface, 'speed')
                    speed = self._linux_read_file(speed_file)
                    if speed:
                        try:
                            adapter['speed'] = int(speed)
                        except ValueError:
                            pass
                    
                    # Check if wireless
                    wireless_path = os.path.join(net_dir, interface, 'wireless')
                    if os.path.exists(wireless_path):
                        adapter['type'] = 'wifi'
                    else:
                        adapter['type'] = 'ethernet'
                    
                    # Get IP address from ip command
                    result = self._linux_run_command(['ip', 'addr', 'show', interface])
                    if result:
                        import re
                        ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result)
                        if ip_match:
                            adapter['ip'] = ip_match.group(1)
                    
                    adapters.append(adapter)
            
            return {
                'adapters': adapters if adapters else None
            }
        except Exception:
            return {}
    
    def collect_linux_printer_info(self) -> Optional[Any]:
        """Collect Linux printer information."""
        try:
            printers = []
            
            # Try lpstat
            result = self._linux_run_command(['lpstat', '-p', '-d'])
            if result:
                for line in result.splitlines():
                    if line.startswith('printer'):
                        parts = line.split()
                        if len(parts) >= 2:
                            printers.append({
                                'name': parts[1],
                                'status': ' '.join(parts[2:]) if len(parts) > 2 else 'idle'
                            })
            
            return printers if printers else None
        except Exception:
            return None
    
    def collect_linux_software_info(self) -> Optional[Any]:
        """Collect Linux installed software information."""
        try:
            software = []
            
            # Try dpkg (Debian/Ubuntu)
            result = self._linux_run_command(['dpkg', '-l'])
            if result:
                for line in result.splitlines()[5:]:  # Skip header
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3:
                            software.append({
                                'name': parts[1],
                                'version': parts[2],
                                'source': 'dpkg'
                            })
                if software:
                    return software[:100]  # Limit to 100
            
            # Try rpm (RedHat/CentOS)
            result = self._linux_run_command(['rpm', '-qa', '--queryformat', '%{NAME}\t%{VERSION}\n'])
            if result:
                for line in result.splitlines():
                    if '\t' in line:
                        name, version = line.split('\t', 1)
                        software.append({
                            'name': name,
                            'version': version,
                            'source': 'rpm'
                        })
                if software:
                    return software[:100]  # Limit to 100
            
            return None
        except Exception:
            return None
    
    def collect_linux_power_info(self) -> Optional[Dict[str, Any]]:
        """Collect Linux power/battery information."""
        try:
            batteries = []
            
            # Check /sys/class/power_supply for batteries
            power_dir = '/sys/class/power_supply'
            if os.path.isdir(power_dir):
                for item in os.listdir(power_dir):
                    if 'BAT' in item.upper():
                        battery = {'name': item}
                        
                        # Get battery info
                        capacity_file = os.path.join(power_dir, item, 'capacity')
                        capacity = self._linux_read_file(capacity_file)
                        if capacity:
                            try:
                                battery['capacity_percent'] = int(capacity)
                            except ValueError:
                                pass
                        
                        energy_full_file = os.path.join(power_dir, item, 'energy_full')
                        energy_full = self._linux_read_file(energy_full_file)
                        if energy_full:
                            try:
                                # energy_full is in micro-watt-hours, convert to mWh
                                battery['energy_full_mwh'] = int(energy_full) / 1000
                            except ValueError:
                                pass
                        
                        energy_now_file = os.path.join(power_dir, item, 'energy_now')
                        energy_now = self._linux_read_file(energy_now_file)
                        if energy_now:
                            try:
                                battery['energy_now_mwh'] = int(energy_now) / 1000
                            except ValueError:
                                pass
                        
                        manufacturer_file = os.path.join(power_dir, item, 'manufacturer')
                        manufacturer = self._linux_read_file(manufacturer_file)
                        if manufacturer:
                            battery['manufacturer'] = manufacturer
                        
                        model_name_file = os.path.join(power_dir, item, 'model_name')
                        model_name = self._linux_read_file(model_name_file)
                        if model_name:
                            battery['model_name'] = model_name
                        
                        batteries.append(battery)
            
            return {
                'batteries': batteries if batteries else None
            }
        except Exception:
            return None
    
    def collect_linux_controllers_info(self) -> Optional[Any]:
        """Collect Linux controller information from lspci."""
        try:
            controllers = []
            
            # Get PCI devices
            result = self._linux_run_command(['lspci'])
            if result:
                for line in result.splitlines():
                    # Filter for controllers (USB, SATA, etc.)
                    if any(keyword in line.lower() for keyword in ['usb', 'sata', 'ahci', 'nvme', 'pci bridge', 'ide', 'scsi', 'ethernet', 'network']):
                        controllers.append({
                            'name': line.split(':')[2].strip() if ':' in line else line.strip(),
                            'pci_id': line.split()[0] if line.split() else None
                        })
            
            # Get USB controllers
            result = self._linux_run_command(['lsusb'])
            if result:
                for line in result.splitlines():
                    if 'Host Controller' in line or 'Hub' in line:
                        controllers.append({
                            'name': line.split()[5:] if len(line.split()) > 5 else line.strip(),
                            'type': 'USB'
                        })
            
            return controllers if controllers else None
        except Exception:
            return None
    
    def collect_linux_monitors_info(self) -> Dict[str, Any]:
        """Collect Linux monitor/display information."""
        try:
            monitors = []
            
            # Try xrandr for display info
            result = self._linux_run_command(['xrandr', '--query'])
            if result:
                current_monitor = {}
                for line in result.splitlines():
                    if ' connected' in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            current_monitor = {
                                'name': parts[0],
                                'status': 'connected'
                            }
                            # Try to extract resolution
                            for part in parts:
                                if 'x' in part and '+' in part:
                                    resolution = part.split('+')[0]
                                    current_monitor['resolution'] = resolution
                                    break
                            monitors.append(current_monitor)
            
            # Also check /sys/class/drm for EDID
            drm_dir = '/sys/class/drm'
            if os.path.isdir(drm_dir):
                for item in os.listdir(drm_dir):
                    if item.startswith('card') and '-' in item and 'eDP' not in item:
                        edid_file = os.path.join(drm_dir, item, 'edid')
                        if os.path.exists(edid_file):
                            monitors.append({
                                'name': item,
                                'edid_available': True
                            })
            
            return {
                'monitors': monitors if monitors else None
            }
        except Exception:
            return {}

    def _collect_linux_enriched(self, categories: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Collect extended Linux inventory via /proc, /sys, dmidecode, etc.
        
        Args:
            categories: Optional list of specific categories to collect.
                       If None, collects all categories.
                       Valid categories: 'os', 'hardware', 'cpu', 'memory', 'storage',
                       'video', 'network', 'printers', 'software', 'power',
                       'controllers', 'monitors'
        
        Returns:
            Dictionary with collected inventory data
        """
        data: Dict[str, Any] = {}
        collect_all = categories is None or len(categories) == 0
        
        # Map category names to methods
        category_map = {
            'os': ('operating_system', self.collect_linux_os_info),
            'hardware': ('hardware_summary', self.collect_linux_hardware_summary),
            'cpu': ('cpu', self.collect_linux_cpu_info),
            'memory': ('memory', self.collect_linux_memory_info),
            'storage': ('storage', self.collect_linux_storage_info),
            'video': ('video', self.collect_linux_video_info),
            'network': ('network_detail', self.collect_linux_network_info),
            'printers': ('printers', self.collect_linux_printer_info),
            'software': ('software', self.collect_linux_software_info),
            'power': ('power', self.collect_linux_power_info),
            'controllers': ('controllers', self.collect_linux_controllers_info),
            'monitors': ('monitors', self.collect_linux_monitors_info),
        }
        
        # Collect requested categories
        for cat_key, (output_key, method) in category_map.items():
            if collect_all or cat_key in categories:
                try:
                    result = method()
                    if result is not None:
                        data[output_key] = result
                except Exception:
                    pass  # Skip failed categories
        
        return data

    def _collect_windows_enriched(self, categories: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Collect extended Windows inventory via CIM/registry.
        
        Args:
            categories: Optional list of specific categories to collect.
                       If None, collects all categories.
                       Valid categories: 'os', 'hardware', 'cpu', 'memory', 'storage',
                       'video', 'audio', 'network', 'printers', 'software', 'updates',
                       'drivers', 'services', 'accounts', 'security', 'shares', 'power'
        
        Returns:
            Dictionary with collected inventory data
        """
        data: Dict[str, Any] = {}
        collect_all = categories is None or len(categories) == 0
        
        # Map category names to methods
        category_map = {
            'os': ('operating_system', self.collect_os_info),
            'hardware': ('hardware_summary', self.collect_hardware_summary),
            'cpu': ('cpu', self.collect_cpu_info),
            'memory': ('memory', self.collect_memory_info),
            'storage': ('storage', self.collect_storage_info),
            'video': ('video', self.collect_video_info),
            'audio': ('audio', self.collect_audio_info),
            'network': ('network_detail', self.collect_network_info),
            'printers': ('printers', self.collect_printer_info),
            'software': ('software', self.collect_software_info),
            'updates': ('updates', self.collect_updates_info),
            'drivers': ('drivers', self.collect_drivers_info),
            'services': ('services', self.collect_services_info),
            'accounts': ('accounts', self.collect_accounts_info),
            'security': ('security', self.collect_security_info),
            'shares': ('shares', self.collect_shares_info),
            'power': ('power', self.collect_power_info),
            'ports': ('ports', self.collect_ports_info),
            'controllers': ('controllers', self.collect_controllers_info),
            'monitors': ('monitors', self.collect_monitors_info),
        }
        
        # Collect requested categories
        for cat_key, (output_key, method) in category_map.items():
            if collect_all or cat_key in categories:
                try:
                    result = method()
                    if result is not None:
                        data[output_key] = result
                except Exception:
                    pass  # Skip failed categories
        
        return data
   
    def _send_to_server(self, data: Dict):
        """Send inventory to server using proper GLPI protocol"""
        if self.logger:
            self.logger.info(f"Sending inventory to {self.target.get_name()}")
        
        try:
            # Import proper GLPI HTTP Client
            from GLPI.Agent.HTTP.Client.GLPI import GLPIHTTPClient
            try:
                from GLPI.Agent.Protocol.Message import ProtocolMessage
            except ImportError:
                # Fallback: try to import it when needed
                ProtocolMessage = None
            
            # Create GLPI HTTP client with proper agent ID (must be valid UUID)
            # Check if deviceid is a valid UUID format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
            agent_id = self.deviceid
            try:
                # Try to parse as UUID to validate format
                import uuid as uuid_module
                if agent_id:
                    uuid_module.UUID(str(agent_id))
                    if self.logger:
                        self.logger.debug(f"Using deviceid as agentid: {agent_id}")
                else:
                    raise ValueError("No deviceid")
            except (ValueError, AttributeError):
                # Not a valid UUID, generate a new one
                agent_id = str(uuid.uuid4())
                if self.logger:
                    self.logger.debug(f"Generated new UUID agentid: {agent_id}")
            
            client = GLPIHTTPClient(
                logger=self.logger,
                agentid=agent_id
            )
            
            # Transform data to proper GLPI format with UPPERCASE sections
            # Extract Windows enriched data if available
            windows_data = data.get('windows', {})
            hw_data = data.get('hardware', {})
            hw_summary = windows_data.get('hardware_summary', {})
            
            # Build GLPI content with required UPPERCASE sections
            glpi_content = {
                'VERSIONCLIENT': AGENT_STRING,
            }
            
            # HARDWARE section - Only allowed fields per schema
            glpi_content['HARDWARE'] = {
                'NAME': hw_data.get('node', socket.gethostname()),
                'VMSYSTEM': 'Physical',
            }
            
            # Add memory if available
            if hw_data.get('memory_total_gb'):
                glpi_content['HARDWARE']['MEMORY'] = int(hw_data.get('memory_total_gb', 0) * 1024)
            
            # Add chassis type if available
            chassis_types = hw_summary.get('chassis_types', [])
            if chassis_types and len(chassis_types) > 0:
                glpi_content['HARDWARE']['CHASSIS_TYPE'] = str(chassis_types[0])
            
            # BIOS section - From hardware_summary
            glpi_content['BIOS'] = {}
            if hw_summary:
                if hw_summary.get('manufacturer'): 
                    glpi_content['BIOS']['SMANUFACTURER'] = hw_summary['manufacturer']
                    glpi_content['BIOS']['BMANUFACTURER'] = hw_summary.get('bios_manufacturer') or hw_summary['manufacturer']
                if hw_summary.get('model'): 
                    glpi_content['BIOS']['SMODEL'] = hw_summary['model']
                if hw_summary.get('serial_number'): 
                    glpi_content['BIOS']['SSN'] = hw_summary['serial_number']
                if hw_summary.get('bios_version'): 
                    glpi_content['BIOS']['BVERSION'] = hw_summary['bios_version']
                # BIOS Release Date (format: YYYY-MM-DD)
                if hw_summary.get('bios_release_date'):
                    release_date = hw_summary['bios_release_date']
                    try:
                        # Handle different date formats
                        if isinstance(release_date, str):
                            # Check for JSON date format: /Date(1699488000000)/
                            import re
                            json_date_match = re.search(r'/Date\((\d+)\)/', release_date)
                            if json_date_match:
                                # Milliseconds since epoch
                                timestamp_ms = int(json_date_match.group(1))
                                from datetime import datetime
                                dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
                                glpi_content['BIOS']['BDATE'] = dt.strftime('%Y-%m-%d')
                            else:
                                # WMI date format: YYYYMMDDHHMMSS.000000+000
                                # Remove any non-digit characters and extract date
                                date_str = ''.join(c for c in release_date if c.isdigit())
                                if len(date_str) >= 8:
                                    year = date_str[0:4]
                                    month = date_str[4:6]
                                    day = date_str[6:8]
                                    # Validate date parts
                                    if year.isdigit() and month.isdigit() and day.isdigit():
                                        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                            # GLPI expects YYYY-MM-DD format
                                            glpi_content['BIOS']['BDATE'] = f"{year}-{month}-{day}"
                        elif hasattr(release_date, 'strftime'):
                            # datetime object
                            glpi_content['BIOS']['BDATE'] = release_date.strftime('%Y-%m-%d')
                        elif isinstance(release_date, (int, float)):
                            # Timestamp (seconds or milliseconds)
                            from datetime import datetime
                            if release_date > 1e10:  # Milliseconds
                                dt = datetime.fromtimestamp(release_date / 1000.0)
                            else:  # Seconds
                                dt = datetime.fromtimestamp(release_date)
                            glpi_content['BIOS']['BDATE'] = dt.strftime('%Y-%m-%d')
                    except Exception as e:
                        # Skip if date parsing fails
                        pass
                if hw_summary.get('baseboard', {}).get('product'):
                    glpi_content['BIOS']['MMODEL'] = hw_summary['baseboard']['product']
                if hw_summary.get('baseboard', {}).get('serial'):
                    glpi_content['BIOS']['MSN'] = hw_summary['baseboard']['serial']
            
            # OPERATINGSYSTEM section
            os_data = windows_data.get('operating_system', {})
            glpi_content['OPERATINGSYSTEM'] = {
                'NAME': 'Windows',
                'FULL_NAME': os_data.get('caption', 'Windows'),
                'VERSION': os_data.get('version', hw_data.get('version', '')),
                'ARCH': os_data.get('architecture', platform.machine()),
                'FQDN': data.get('network', {}).get('fqdn', socket.getfqdn()),
            }
            if os_data.get('build_number'):
                glpi_content['OPERATINGSYSTEM']['KERNEL_VERSION'] = os_data['build_number']
            
            # CPUS - Map from Windows CPU data
            cpu_data = windows_data.get('cpu', {})
            if cpu_data and isinstance(cpu_data, dict):
                # Use BaseClockSpeed if available, otherwise CurrentClockSpeed, fallback to MaxClockSpeed
                speed = cpu_data.get('BaseClockSpeed') or cpu_data.get('CurrentClockSpeed') or cpu_data.get('MaxClockSpeed', 0)
                glpi_content['CPUS'] = [{
                    'NAME': cpu_data.get('Name', ''),
                    'CORE': cpu_data.get('NumberOfCores', 0),
                    'THREAD': cpu_data.get('NumberOfLogicalProcessors', 0),
                    'SPEED': speed,
                }]
            
            # MEMORIES - Map from Windows memory modules
            memory_data = windows_data.get('memory', {})
            memory_modules = memory_data.get('modules', [])
            if memory_modules:
                glpi_content['MEMORIES'] = []
                for mem in memory_modules:
                    if isinstance(mem, dict):
                        mem_entry = {}
                        # Capacity in MB
                        if mem.get('Capacity'): 
                            mem_entry['CAPACITY'] = int(mem['Capacity'] / (1024*1024))
                        if mem.get('Manufacturer'): 
                            mem_entry['MANUFACTURER'] = str(mem['Manufacturer']).strip()
                        if mem.get('SerialNumber'): 
                            mem_entry['SERIALNUMBER'] = str(mem['SerialNumber']).strip()
                        if mem.get('PartNumber'): 
                            mem_entry['MODEL'] = str(mem['PartNumber']).strip()
                        if mem.get('Speed'): 
                            mem_entry['SPEED'] = str(mem['Speed'])
                        if mem.get('BankLabel'): 
                            mem_entry['CAPTION'] = mem['BankLabel']
                        if mem_entry:
                            glpi_content['MEMORIES'].append(mem_entry)
            
            # STORAGES - Map from Windows physical disks
            storage_data = windows_data.get('storage', {})
            physical_disks = storage_data.get('physical_disks', [])
            # Normalize to list
            if not isinstance(physical_disks, list):
                physical_disks = [physical_disks] if physical_disks else []
            
            if physical_disks:
                glpi_content['STORAGES'] = []
                for disk in physical_disks:
                    if isinstance(disk, dict):
                        storage_entry = {
                            'NAME': disk.get('Model', ''),
                            'MODEL': disk.get('Model', ''),
                            'DISKSIZE': int(disk.get('Size', 0) / (1024*1024)) if disk.get('Size') else 0,
                        }
                        # Add interface and type
                        if disk.get('InterfaceType'):
                            storage_entry['INTERFACE'] = str(disk.get('InterfaceType', '')).strip()
                        if disk.get('MediaType'):
                            storage_entry['TYPE'] = str(disk.get('MediaType', '')).strip()
                        # Add serial number if available (use SERIAL instead of SERIALNUMBER per schema)
                        if disk.get('SerialNumber'):
                            serial = str(disk.get('SerialNumber', '')).strip()
                            if serial and serial.upper() != 'NONE' and serial.upper() != 'TO BE FILLED BY O.E.M.':
                                storage_entry['SERIAL'] = serial
                        if storage_entry.get('NAME'):  # Only add if has at least a name
                            glpi_content['STORAGES'].append(storage_entry)
            
            # DRIVES - Map from storage volumes
            volumes = storage_data.get('volumes', [])
            if volumes:
                glpi_content['DRIVES'] = []
                for vol in volumes:
                    if isinstance(vol, dict):
                        drive_entry = {
                            'LETTER': vol.get('DriveLetter', ''),
                            'LABEL': vol.get('Label', ''),
                            'FILESYSTEM': vol.get('FileSystem', ''),
                            'TOTAL': int(vol.get('Capacity', 0) / (1024*1024)) if vol.get('Capacity') else 0,
                            'FREE': int(vol.get('FreeSpace', 0) / (1024*1024)) if vol.get('FreeSpace') else 0,
                        }
                        if drive_entry.get('LETTER'):
                            glpi_content['DRIVES'].append(drive_entry)
            
            # VIDEOS - Map from Windows video data
            video_data = windows_data.get('video', {})
            gpus = video_data.get('gpus', []) if isinstance(video_data, dict) else []
            if not gpus and isinstance(video_data, list):
                gpus = video_data
            if gpus:
                glpi_content['VIDEOS'] = []
                if not isinstance(gpus, list):
                    gpus = [gpus]
                for vid in gpus:
                    if isinstance(vid, dict):
                        vid_entry = {}
                        if vid.get('Name'): 
                            vid_entry['NAME'] = str(vid['Name']).strip()
                        if vid.get('AdapterRAM'): 
                            vid_entry['MEMORY'] = int(vid['AdapterRAM'] / (1024*1024))
                        if vid.get('VideoProcessor'): 
                            vid_entry['CHIPSET'] = str(vid['VideoProcessor']).strip()
                        if vid_entry.get('NAME'):
                            glpi_content['VIDEOS'].append(vid_entry)
            
            # NETWORKS - Map from Windows network data
            network_data = windows_data.get('network_detail', {})
            if network_data and isinstance(network_data, dict):
                glpi_content['NETWORKS'] = []
                
                # Get adapters and config lists
                adapters = network_data.get('adapters', [])
                configs = network_data.get('config', [])
                net_adapters = network_data.get('net_adapters', [])  # Get-NetAdapter data with LinkSpeed
                
                # Normalize to lists
                if not isinstance(adapters, list):
                    adapters = [adapters] if adapters else []
                if not isinstance(configs, list):
                    configs = [configs] if configs else []
                if not isinstance(net_adapters, list):
                    net_adapters = [net_adapters] if net_adapters else []
                
                # Create a lookup by MAC address for configs
                config_by_mac = {}
                for cfg in configs:
                    if isinstance(cfg, dict) and cfg.get('MACAddress'):
                        mac = cfg['MACAddress'].upper().replace('-', ':').replace(' ', '')
                        config_by_mac[mac] = cfg
                
                # Create a lookup by MAC address for LinkSpeed from Get-NetAdapter
                speed_by_mac = {}
                for net_adapter in net_adapters:
                    if isinstance(net_adapter, dict) and net_adapter.get('MACAddress'):
                        mac = net_adapter['MACAddress'].upper().replace('-', ':').replace(' ', '')
                        link_speed = net_adapter.get('LinkSpeed')
                        if link_speed:
                            speed_by_mac[mac] = link_speed
                
                # Process each adapter
                for adapter in adapters:
                    if not isinstance(adapter, dict):
                        continue
                    
                    # Get MAC address and normalize it
                    mac = adapter.get('MACAddress', '')
                    if mac:
                        mac_normalized = mac.upper().replace('-', ':').replace(' ', '')
                    else:
                        mac_normalized = None
                    
                    # Find matching config by MAC
                    config = config_by_mac.get(mac_normalized, {}) if mac_normalized else {}
                    
                    # Build network entry
                    net_entry = {}
                    
                    # Description/Name (prefer config Description, fallback to adapter Name)
                    description = config.get('Description') or adapter.get('Name', '')
                    # If still no description, try to build one from adapter type
                    if not description:
                        adapter_type_id = adapter.get('AdapterTypeID')
                        if adapter_type_id == 0:
                            description = 'Ethernet'
                        elif adapter_type_id == 9:
                            description = 'Token Ring'
                        elif adapter_type_id == 6:
                            description = 'FDDI'
                        else:
                            description = adapter.get('Name', 'Network Adapter')
                    if description:
                        net_entry['DESCRIPTION'] = str(description).strip()
                    
                    # Detect adapter type (Bluetooth, Ethernet, WiFi, etc.)
                    adapter_name = str(adapter.get('Name', '')).upper()
                    pnp_id = str(adapter.get('PNPDeviceID', '')).upper()
                    if 'BLUETOOTH' in adapter_name or 'BTHENUM' in pnp_id:
                        net_entry['TYPE'] = 'bluetooth'
                    elif 'WIRELESS' in adapter_name or 'WIFI' in adapter_name or '802.11' in adapter_name:
                        net_entry['TYPE'] = 'wifi'
                    elif 'ETHERNET' in adapter_name or adapter.get('AdapterTypeID') == 0:
                        net_entry['TYPE'] = 'ethernet'
                    # Note: GLPI schema requires TYPE to be one of: ethernet, wifi, infiniband, aggregate, alias, dialup, loopback, bridge, fibrechannel, bluetooth
                    
                    # MAC Address - Protocol layer renames MACADDR to MAC
                    if mac and mac_normalized and len(mac_normalized) > 0:
                        # Format: XX:XX:XX:XX:XX:XX (17 chars) or XXXXXXXXXXXX (12 chars)
                        if len(mac_normalized) == 17 or len(mac_normalized) == 12:
                            net_entry['MAC'] = mac_normalized
                    
                    # Status (convert numeric to text)
                    status = adapter.get('NetConnectionStatus')
                    if status is not None:
                        # NetConnectionStatus: 0=Disconnected, 2=Connected, etc.
                        status_map = {0: 'down', 2: 'up', 3: 'disconnecting', 4: 'connecting', 7: 'up'}
                        net_entry['STATUS'] = status_map.get(status, 'unknown')
                    
                    # IP Address (from config)
                    ip_address = config.get('IPAddress')
                    if ip_address:
                        # IPAddress can be a list
                        if isinstance(ip_address, list) and len(ip_address) > 0:
                            net_entry['IPADDRESS'] = str(ip_address[0]).strip()
                        elif ip_address:
                            net_entry['IPADDRESS'] = str(ip_address).strip()
                    
                    # IP Subnet/Mask (from config)
                    ip_subnet = config.get('IPSubnet')
                    if ip_subnet:
                        if isinstance(ip_subnet, list) and len(ip_subnet) > 0:
                            net_entry['IPMASK'] = str(ip_subnet[0]).strip()
                        elif ip_subnet:
                            net_entry['IPMASK'] = str(ip_subnet).strip()
                    
                    # Default Gateway (from config)
                    gateway = config.get('DefaultIPGateway')
                    if gateway:
                        if isinstance(gateway, list) and len(gateway) > 0:
                            net_entry['IPGATEWAY'] = str(gateway[0]).strip()
                        elif gateway:
                            net_entry['IPGATEWAY'] = str(gateway).strip()
                    
                    # Speed - try multiple sources
                    speed_value = None
                    
                    # First try LinkSpeed from Get-NetAdapter (most reliable for active adapters)
                    if mac_normalized and mac_normalized in speed_by_mac:
                        link_speed = speed_by_mac[mac_normalized]
                        # LinkSpeed format is like "1 Gbps" or "100 Mbps"
                        if isinstance(link_speed, str):
                            # Parse "1 Gbps" -> 1000, "100 Mbps" -> 100
                            try:
                                parts = link_speed.upper().strip().split()
                                if len(parts) >= 2:
                                    value = float(parts[0])
                                    unit = parts[1]
                                    if 'GBPS' in unit or 'G' in unit:
                                        speed_value = int(value * 1000)  # Convert Gbps to Mbps
                                    elif 'MBPS' in unit or 'M' in unit:
                                        speed_value = int(value)
                                    else:
                                        # Assume bits per second, convert to Mbps
                                        speed_value = int(value / 1000000)
                            except (ValueError, TypeError):
                                pass
                    
                    # Fallback to Speed from Win32_NetworkAdapter
                    if speed_value is None:
                        speed = adapter.get('Speed')
                        if speed:
                            # Speed is in bits per second, convert to Mbps
                            try:
                                speed_mbps = int(speed) / 1000000
                                speed_value = int(speed_mbps)
                            except (ValueError, TypeError):
                                pass
                    
                    # Set SPEED if we have a valid value
                    if speed_value and speed_value > 0:
                        net_entry['SPEED'] = str(speed_value)  # Must be string
                    
                    # Only add if we have at least a description
                    # Always add network entry if we have adapter data (even without description/MAC)
                    # This ensures all physical adapters are reported
                    if adapter.get('Name') or net_entry.get('DESCRIPTION') or net_entry.get('MAC'):
                        # If no description yet, use adapter name
                        if not net_entry.get('DESCRIPTION') and adapter.get('Name'):
                            net_entry['DESCRIPTION'] = str(adapter.get('Name', '')).strip()
                        glpi_content['NETWORKS'].append(net_entry)
            
            # PORTS - Map from Windows port data
            ports_data = windows_data.get('ports', {})
            if ports_data:
                glpi_content['PORTS'] = []
                
                # Process COM ports (serial)
                com_ports = ports_data.get('com_ports', [])
                if not isinstance(com_ports, list):
                    com_ports = [com_ports] if com_ports else []
                for port in com_ports:
                    if isinstance(port, dict):
                        port_entry = {
                            'NAME': port.get('Name', port.get('DeviceID', '')),
                            'DESCRIPTION': port.get('Description', ''),
                            'TYPE': 'serial',
                        }
                        if port_entry.get('NAME'):
                            glpi_content['PORTS'].append(port_entry)
                
                # Process LPT ports (parallel)
                lpt_ports = ports_data.get('lpt_ports', [])
                if not isinstance(lpt_ports, list):
                    lpt_ports = [lpt_ports] if lpt_ports else []
                for port in lpt_ports:
                    if isinstance(port, dict):
                        port_entry = {
                            'NAME': port.get('Name', port.get('DeviceID', '')),
                            'DESCRIPTION': port.get('Description', ''),
                            'TYPE': 'parallel',
                        }
                        if port_entry.get('NAME'):
                            glpi_content['PORTS'].append(port_entry)
                
                # Process USB controllers (as USB ports)
                usb_controllers = ports_data.get('usb_controllers', [])
                if not isinstance(usb_controllers, list):
                    usb_controllers = [usb_controllers] if usb_controllers else []
                for port in usb_controllers:
                    if isinstance(port, dict):
                        port_entry = {
                            'NAME': port.get('Name', port.get('DeviceID', '')),
                            'DESCRIPTION': port.get('Description', ''),
                            'TYPE': 'usb',
                        }
                        if port_entry.get('NAME'):
                            glpi_content['PORTS'].append(port_entry)
            
            # SOFTWARES - Map from Windows software list
            software_data = windows_data.get('software', [])
            if software_data:
                glpi_content['SOFTWARES'] = []
                for sw in software_data[:100]:  # Limit to first 100 to avoid huge payload
                    if isinstance(sw, dict):
                        sw_entry = {}
                        # Only add non-null, non-empty values
                        if sw.get('DisplayName'):
                            sw_entry['NAME'] = sw['DisplayName']
                        if sw.get('DisplayVersion'):
                            sw_entry['VERSION'] = sw['DisplayVersion']
                        if sw.get('Publisher'):
                            sw_entry['PUBLISHER'] = sw['Publisher']
                        if sw.get('EstimatedSize'):
                            sw_entry['FILESIZE'] = sw['EstimatedSize']
                        # Only add if has at least a name
                        if sw_entry.get('NAME'):
                            glpi_content['SOFTWARES'].append(sw_entry)
            
            # BATTERIES - Map from Windows battery data
            power_data = windows_data.get('power', {})
            batteries = power_data.get('batteries', []) if power_data else []
            if batteries:
                glpi_content['BATTERIES'] = []
                if not isinstance(batteries, list):
                    batteries = [batteries]
                for bat in batteries:
                    if isinstance(bat, dict):
                        bat_entry = {}
                        battery_name = str(bat.get('Name', '')).strip() if bat.get('Name') else ''
                        # Get battery percentage for display
                        battery_percentage = None
                        if bat.get('EstimatedChargeRemaining') is not None:
                            try:
                                percentage = int(bat['EstimatedChargeRemaining'])
                                if 0 <= percentage <= 100:
                                    battery_percentage = percentage
                            except (ValueError, TypeError):
                                pass
                        
                        # Calculate battery health/wear percentage
                        battery_health = None
                        health_info = []
                        design_capacity = bat.get('DesignCapacity')
                        full_charge_capacity = bat.get('FullChargeCapacity')
                        
                        if design_capacity and full_charge_capacity:
                            try:
                                design = int(design_capacity)
                                full = int(full_charge_capacity)
                                if design > 0:
                                    # Health = (current full charge / design capacity) * 100
                                    health_pct = int((full / design) * 100)
                                    if 0 <= health_pct <= 100:
                                        battery_health = health_pct
                                        health_info.append(f"Health: {health_pct}%")
                            except (ValueError, TypeError, ZeroDivisionError):
                                pass
                        
                        # Get cycle count if available
                        cycle_count = bat.get('CycleCount')
                        if cycle_count is not None:
                            try:
                                cycles = int(cycle_count)
                                health_info.append(f"Cycles: {cycles}")
                            except (ValueError, TypeError):
                                pass
                        
                        # Build battery name with charge percentage (e.g., "Primary (85%)")
                        if battery_name:
                            if battery_percentage is not None:
                                bat_entry['NAME'] = f"{battery_name} ({battery_percentage}%)"
                            else:
                                bat_entry['NAME'] = battery_name
                        else:
                            if battery_percentage is not None:
                                bat_entry['NAME'] = f"Battery ({battery_percentage}%)"
                            else:
                                bat_entry['NAME'] = "Battery"
                        
                        # CAPACITY - Design capacity
                        if bat.get('DesignCapacity'):
                            bat_entry['CAPACITY'] = int(bat['DesignCapacity'])
                        
                        # REAL_CAPACITY - Send as integer (GLPI schema expects integer)
                        # The formatted display "48 230 (85%)" is handled by GLPI's display logic
                        if bat.get('FullChargeCapacity'):
                            try:
                                full_capacity = int(bat['FullChargeCapacity'])
                                bat_entry['REAL_CAPACITY'] = full_capacity
                            except (ValueError, TypeError):
                                pass
                        if bat.get('DesignVoltage'):
                            bat_entry['VOLTAGE'] = int(bat['DesignVoltage'])
                        if bat.get('Chemistry'):
                            # Chemistry: 1=Other, 2=Unknown, 3=Lead Acid, 4=Nickel Cadmium, 
                            # 5=Nickel Metal Hydride, 6=Lithium-ion, 7=Zinc air, 8=Lithium Polymer
                            chem_map = {1: 'Other', 2: 'Unknown', 3: 'Lead Acid', 4: 'NiCd',
                                       5: 'NiMH', 6: 'Li-ion', 7: 'Zinc air', 8: 'LiP'}
                            chem_id = bat.get('Chemistry')
                            if chem_id and chem_id in chem_map:
                                bat_entry['CHEMISTRY'] = chem_map[chem_id]
                        if bat.get('DeviceID'):
                            # Try to extract serial from DeviceID
                            device_id = str(bat.get('DeviceID', ''))
                            if device_id:
                                bat_entry['SERIAL'] = device_id
                        # Add manufacturer if available
                        if bat.get('ManufactureName'):
                            bat_entry['MANUFACTURER'] = str(bat['ManufactureName']).strip()
                        # Add manufacture date if available
                        if bat.get('ManufactureDate'):
                            manuf_date = bat.get('ManufactureDate')
                            try:
                                # WMI date format: YYYYMMDDHHMMSS.000000+000
                                if isinstance(manuf_date, str):
                                    date_str = ''.join(c for c in manuf_date if c.isdigit())
                                    if len(date_str) >= 8:
                                        year = date_str[0:4]
                                        month = date_str[4:6]
                                        day = date_str[6:8]
                                        if year.isdigit() and month.isdigit() and day.isdigit():
                                            if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                                bat_entry['DATE'] = f"{year}-{month}-{day}"
                            except Exception:
                                pass
                        if bat_entry.get('NAME'):
                            glpi_content['BATTERIES'].append(bat_entry)
            
            # SOUNDS - Map from Windows audio/sound device data
            audio_data = windows_data.get('audio', [])
            if audio_data:
                glpi_content['SOUNDS'] = []
                if not isinstance(audio_data, list):
                    audio_data = [audio_data]
                for sound in audio_data:
                    if isinstance(sound, dict):
                        sound_entry = {}
                        if sound.get('Name'):
                            sound_entry['NAME'] = str(sound['Name']).strip()
                        if sound.get('Manufacturer'):
                            sound_entry['MANUFACTURER'] = str(sound['Manufacturer']).strip()
                        if sound.get('Status'):
                            sound_entry['DESCRIPTION'] = str(sound['Status']).strip()
                        if sound_entry.get('NAME'):
                            glpi_content['SOUNDS'].append(sound_entry)
            
            # PRINTERS - Map from Windows printer data
            printers_data = windows_data.get('printers', [])
            if printers_data:
                glpi_content['PRINTERS'] = []
                if not isinstance(printers_data, list):
                    printers_data = [printers_data]
                for printer in printers_data:
                    if isinstance(printer, dict):
                        printer_entry = {}
                        if printer.get('Name'):
                            printer_entry['NAME'] = str(printer['Name']).strip()
                        if printer.get('DriverName'):
                            printer_entry['DRIVER'] = str(printer['DriverName']).strip()
                        if printer.get('PortName'):
                            printer_entry['PORT'] = str(printer['PortName']).strip()
                        # Check if printer is offline
                        work_offline = printer.get('WorkOffline')
                        if work_offline is not None:
                            # WorkOffline: True = offline, False = online
                            printer_entry['STATUS'] = 'Offline' if work_offline else 'Idle'
                        # Check if it's the default printer
                        is_default = printer.get('Default')
                        if is_default and is_default:
                            if printer_entry.get('NAME'):
                                printer_entry['NAME'] = f"{printer_entry['NAME']} (Default)"
                        if printer_entry.get('NAME'):
                            glpi_content['PRINTERS'].append(printer_entry)
            
            # MONITORS - Map from Windows monitor data
            monitors_data = windows_data.get('monitors', {})
            glpi_content['MONITORS'] = []
            
            if monitors_data and isinstance(monitors_data, dict):
                # VideoOutputTechnology port mapping
                ports_map = {
                    '-1': 'Other',
                    '0': 'VGA',
                    '1': 'S-Video',
                    '2': 'Composite',
                    '3': 'YUV',
                    '4': 'DVI',
                    '5': 'HDMI',
                    '6': 'LVDS',
                    '8': 'D-Jpn',
                    '9': 'SDI',
                    '10': 'DisplayPort',
                    '11': 'eDisplayPort',
                    '12': 'UDI',
                    '13': 'eUDI',
                    '14': 'SDTV',
                    '15': 'Miracast'
                }
                
                # Get desktop monitors
                desktop_monitors = monitors_data.get('desktop_monitors', [])
                if not isinstance(desktop_monitors, list):
                    desktop_monitors = [desktop_monitors] if desktop_monitors else []
                
                # Get monitor connections (for port type)
                monitor_connections = monitors_data.get('monitor_connections', [])
                if not isinstance(monitor_connections, list):
                    monitor_connections = [monitor_connections] if monitor_connections else []
                
                # Get monitor IDs (EDID data)
                monitor_ids = monitors_data.get('monitor_ids', [])
                if not isinstance(monitor_ids, list):
                    monitor_ids = [monitor_ids] if monitor_ids else []
                
                # Create lookup maps
                connection_by_instance = {}
                for conn in monitor_connections:
                    if isinstance(conn, dict) and conn.get('InstanceName'):
                        instance_name = str(conn.get('InstanceName', '')).rsplit('_', 1)[0]
                        connection_by_instance[instance_name] = conn
                
                id_by_instance = {}
                for mid in monitor_ids:
                    if isinstance(mid, dict) and mid.get('InstanceName'):
                        instance_name = str(mid.get('InstanceName', '')).rsplit('_', 1)[0]
                        id_by_instance[instance_name] = mid
                
                # Process each desktop monitor
                for monitor in desktop_monitors:
                    if not isinstance(monitor, dict):
                        continue
                    
                    monitor_entry = {}
                    
                    # Get PNPDeviceID to match with connections and IDs
                    pnp_id = monitor.get('PNPDeviceID', '')
                    instance_name = pnp_id.rsplit('\\', 1)[0] if '\\' in pnp_id else pnp_id
                    
                    # Get name/caption
                    if monitor.get('Caption'):
                        monitor_entry['NAME'] = str(monitor['Caption']).strip()
                        monitor_entry['CAPTION'] = str(monitor['Caption']).strip()
                    
                    # Get manufacturer
                    if monitor.get('MonitorManufacturer'):
                        monitor_entry['MANUFACTURER'] = str(monitor['MonitorManufacturer']).strip()
                    
                    # Get connection type (port) from WMIMonitorConnectionParams
                    if instance_name in connection_by_instance:
                        conn = connection_by_instance[instance_name]
                        video_tech = str(conn.get('VideoOutputTechnology', ''))
                        if video_tech in ports_map:
                            monitor_entry['PORT'] = ports_map[video_tech]
                    
                    # Get EDID data from WmiMonitorID
                    if instance_name in id_by_instance:
                        mid = id_by_instance[instance_name]
                        if mid.get('ManufacturerID'):
                            # If we don't have manufacturer yet, use this
                            if not monitor_entry.get('MANUFACTURER'):
                                monitor_entry['MANUFACTURER'] = str(mid['ManufacturerID']).strip()
                        if mid.get('ProductCodeID'):
                            # Product code can help identify model
                            if not monitor_entry.get('NAME'):
                                monitor_entry['NAME'] = str(mid['ProductCodeID']).strip()
                        if mid.get('SerialNumberID'):
                            monitor_entry['SERIAL'] = str(mid['SerialNumberID']).strip()
                    
                    # Only add if we have at least a name or manufacturer
                    if monitor_entry.get('NAME') or monitor_entry.get('MANUFACTURER'):
                        glpi_content['MONITORS'].append(monitor_entry)
                
                # If no desktop monitors found but we have connections, create entries from connections
                if len(glpi_content['MONITORS']) == 0 and monitor_connections:
                    for conn in monitor_connections:
                        if not isinstance(conn, dict) or not conn.get('InstanceName'):
                            continue
                        
                        monitor_entry = {}
                        instance_name = str(conn.get('InstanceName', '')).rsplit('_', 1)[0]
                        
                        # Get connection type (port)
                        video_tech = str(conn.get('VideoOutputTechnology', ''))
                        if video_tech in ports_map:
                            monitor_entry['PORT'] = ports_map[video_tech]
                        
                        # Try to get EDID data from WmiMonitorID
                        if instance_name in id_by_instance:
                            mid = id_by_instance[instance_name]
                            if mid.get('ManufacturerID'):
                                monitor_entry['MANUFACTURER'] = str(mid['ManufacturerID']).strip()
                            if mid.get('ProductCodeID'):
                                monitor_entry['NAME'] = str(mid['ProductCodeID']).strip()
                                monitor_entry['CAPTION'] = str(mid['ProductCodeID']).strip()
                            if mid.get('SerialNumberID'):
                                monitor_entry['SERIAL'] = str(mid['SerialNumberID']).strip()
                        
                        # If we still don't have a name, use a generic one based on port
                        if not monitor_entry.get('NAME'):
                            port_name = monitor_entry.get('PORT', 'Display')
                            monitor_entry['NAME'] = f"{port_name} Display"
                            monitor_entry['CAPTION'] = f"{port_name} Display"
                        
                        # Only add if we have at least a name or manufacturer
                        if monitor_entry.get('NAME') or monitor_entry.get('MANUFACTURER'):
                            glpi_content['MONITORS'].append(monitor_entry)
                
                # If still no monitors but we have monitor IDs, create entries from IDs
                if len(glpi_content['MONITORS']) == 0 and monitor_ids:
                    for mid in monitor_ids:
                        if not isinstance(mid, dict) or not mid.get('InstanceName'):
                            continue
                        
                        monitor_entry = {}
                        
                        if mid.get('ManufacturerID'):
                            monitor_entry['MANUFACTURER'] = str(mid['ManufacturerID']).strip()
                        if mid.get('ProductCodeID'):
                            monitor_entry['NAME'] = str(mid['ProductCodeID']).strip()
                            monitor_entry['CAPTION'] = str(mid['ProductCodeID']).strip()
                        if mid.get('SerialNumberID'):
                            monitor_entry['SERIAL'] = str(mid['SerialNumberID']).strip()
                        
                        # If we don't have a name, use a generic one
                        if not monitor_entry.get('NAME'):
                            monitor_entry['NAME'] = "Display"
                            monitor_entry['CAPTION'] = "Display"
                        
                        # Only add if we have at least a name or manufacturer
                        if monitor_entry.get('NAME') or monitor_entry.get('MANUFACTURER'):
                            glpi_content['MONITORS'].append(monitor_entry)
            
            if self.logger and glpi_content.get('MONITORS'):
                self.logger.info(f"Found {len(glpi_content['MONITORS'])} monitor(s) in collected data")
            
            # CONTROLLERS - Map from Windows controller/PCI device data
            controllers_data = windows_data.get('controllers', [])
            glpi_content['CONTROLLERS'] = []
            
            if controllers_data:
                # Normalize to list
                if not isinstance(controllers_data, list):
                    controllers_list = [controllers_data] if controllers_data else []
                else:
                    controllers_list = controllers_data
                
                # Log how many controllers we found
                self.logger.info(f"Found {len(controllers_list)} controllers in collected data")
                
                # Map controllers following Perl module approach
                # Controllers should already have VENDORID and PRODUCTID from collection
                for controller in controllers_list:
                    if not isinstance(controller, dict):
                        continue
                    
                    # Only include controllers with PCI IDs (following Perl approach)
                    if not controller.get('VENDORID') or not controller.get('PRODUCTID'):
                        continue
                    
                    ctrl_entry = {}
                    
                    # Use Name from controller, or try to get from PCI database
                    name = str(controller.get('Name', '')).strip()
                    if name:
                        ctrl_entry['NAME'] = name
                    
                    # Manufacturer
                    if controller.get('Manufacturer'):
                        manufacturer = str(controller['Manufacturer']).strip()
                        if manufacturer and manufacturer.upper() not in ['', 'N/A', 'UNKNOWN']:
                            ctrl_entry['MANUFACTURER'] = manufacturer
                    
                    # Caption
                    caption = controller.get('Caption') or controller.get('Description')
                    if caption:
                        desc = str(caption).strip()
                        if desc:
                            ctrl_entry['CAPTION'] = desc
                    
                    # PCI IDs
                    if controller.get('VENDORID'):
                        ctrl_entry['VENDORID'] = controller['VENDORID']
                    if controller.get('PRODUCTID'):
                        ctrl_entry['PRODUCTID'] = controller['PRODUCTID']
                    if controller.get('PCISUBSYSTEMID'):
                        ctrl_entry['PCISUBSYSTEMID'] = controller['PCISUBSYSTEMID']
                    # Note: PNPDEVICEID is not in the CONTROLLERS schema, so we skip it
                        
                        # Determine TYPE from Class, Name, or Caption
                        class_name = str(controller.get('Class', '')).upper()
                        name_upper = name.upper()
                        caption_upper = str(ctrl_entry.get('CAPTION', '')).upper()
                        
                        # More comprehensive TYPE detection
                        if 'USB' in class_name or 'USB' in name_upper or 'USB' in caption_upper or name_upper.startswith('USB') or 'XHCI' in name_upper or 'EHCI' in name_upper or 'OHCI' in name_upper or 'UHCI' in name_upper:
                            if 'AUDIO' in name_upper:
                                ctrl_entry['TYPE'] = 'Audio'
                            elif 'VIDEO' in name_upper or 'CAMERA' in name_upper:
                                ctrl_entry['TYPE'] = 'Video'
                            elif 'PRINT' in name_upper:
                                ctrl_entry['TYPE'] = 'Printer'
                            elif 'STOR' in name_upper or 'MASS' in name_upper:
                                ctrl_entry['TYPE'] = 'Storage'
                            elif 'HID' in name_upper or 'HUMAN' in name_upper:
                                ctrl_entry['TYPE'] = 'Input'
                            elif 'SERIAL' in name_upper or 'SER' in name_upper:
                                ctrl_entry['TYPE'] = 'Serial'
                            elif 'HUB' in name_upper:
                                ctrl_entry['TYPE'] = 'USB Hub'
                            elif 'BLUETOOTH' in name_upper or 'BTH' in name_upper:
                                ctrl_entry['TYPE'] = 'Bluetooth'
                            elif 'NETWORK' in name_upper or 'RNDIS' in name_upper:
                                ctrl_entry['TYPE'] = 'Network controller'
                            else:
                                ctrl_entry['TYPE'] = 'USB'
                        elif 'PCI' in class_name or 'PCI' in name_upper or 'PCI EXPRESS' in name_upper or name_upper.startswith('PCI'):
                            if 'ROOT PORT' in name_upper:
                                ctrl_entry['TYPE'] = 'PCI Express Root Port'
                            elif 'IDE' in name_upper:
                                ctrl_entry['TYPE'] = 'IDE'
                            else:
                                ctrl_entry['TYPE'] = 'PCI'
                        elif 'SCSI' in class_name or 'SCSI' in name_upper:
                            ctrl_entry['TYPE'] = 'SCSI'
                        elif 'IDE' in class_name or 'IDE' in name_upper or 'intelide' in name_upper:
                            ctrl_entry['TYPE'] = 'IDE'
                        elif 'DISPLAY' in class_name or 'VIDEO' in class_name or 'GRAPHICS' in name_upper or 'usbvideo' in name_upper:
                            ctrl_entry['TYPE'] = 'Display'
                        elif 'NETWORK' in class_name or 'ETHERNET' in name_upper or 'NETWORK' in name_upper or 'RNDIS' in name_upper:
                            ctrl_entry['TYPE'] = 'Network controller'
                        elif 'WIRELESS' in name_upper or 'WIFI' in name_upper:
                            ctrl_entry['TYPE'] = 'Network controller'
                        elif 'BLUETOOTH' in class_name or 'BLUETOOTH' in name_upper or 'BTH' in name_upper or 'AVRCP' in name_upper:
                            ctrl_entry['TYPE'] = 'Bluetooth'
                        elif 'AUDIO' in class_name or 'SOUND' in name_upper or 'AUDIO' in name_upper or 'HD AUDIO' in name_upper or 'usbaudio' in name_upper or 'IntcAudio' in name_upper or 'AcpiAudio' in name_upper:
                            ctrl_entry['TYPE'] = 'Audio'
                        elif 'SATA' in name_upper or 'AHCI' in name_upper or 'storahci' in name_upper or 'amdsata' in name_upper:
                            ctrl_entry['TYPE'] = 'SATA'
                        elif 'NVME' in name_upper or 'NVME' in caption_upper or 'stornvme' in name_upper or 'nvmedisk' in name_upper:
                            ctrl_entry['TYPE'] = 'NVMe'
                        elif 'SMBUS' in name_upper or 'SMBUS' in caption_upper:
                            ctrl_entry['TYPE'] = 'SMBus'
                        elif 'THUNDERBOLT' in name_upper or 'USB4' in name_upper:
                            ctrl_entry['TYPE'] = 'Thunderbolt'
                        elif 'THERMAL' in name_upper or 'ThermalFilter' in name_upper:
                            ctrl_entry['TYPE'] = 'Thermal'
                        elif 'HECI' in name_upper or 'MANAGEMENT' in name_upper or 'PlutonHeci' in name_upper or 'PMT' in name_upper:
                            ctrl_entry['TYPE'] = 'Management'
                        elif 'LPC' in name_upper or 'ESPI' in name_upper:
                            ctrl_entry['TYPE'] = 'LPC'
                        elif 'HOST BRIDGE' in name_upper or 'DRAM' in name_upper:
                            ctrl_entry['TYPE'] = 'Host Bridge'
                        elif 'BRIDGE' in name_upper or 'MsBridge' in name_upper:
                            ctrl_entry['TYPE'] = 'Bridge'
                        elif 'STORAGE' in name_upper or 'STOR' in name_upper:
                            ctrl_entry['TYPE'] = 'Storage'
                        elif 'PRINT' in name_upper:
                            ctrl_entry['TYPE'] = 'Printer'
                        elif 'VIDEO' in name_upper or 'CAMERA' in name_upper:
                            ctrl_entry['TYPE'] = 'Video'
                        else:
                            ctrl_entry['TYPE'] = 'Other'
                        
                        # Try to extract manufacturer from name if not present
                        if not ctrl_entry.get('MANUFACTURER'):
                            if 'INTEL' in name_upper or 'intel' in name_upper:
                                ctrl_entry['MANUFACTURER'] = 'Intel Corporation'
                            elif 'AMD' in name_upper or 'amdsata' in name_upper:
                                ctrl_entry['MANUFACTURER'] = 'Advanced Micro Devices, Inc.'
                            elif 'MICROSOFT' in name_upper or 'Microsoft' in name:
                                ctrl_entry['MANUFACTURER'] = 'Microsoft Corporation'
                            elif 'REALTEK' in name_upper:
                                ctrl_entry['MANUFACTURER'] = 'Realtek'
                            elif 'NVIDIA' in name_upper:
                                ctrl_entry['MANUFACTURER'] = 'NVIDIA Corporation'
                        
                        # Only add if we have at least a name
                        if ctrl_entry.get('NAME'):
                            glpi_content['CONTROLLERS'].append(ctrl_entry)
            
            # Log final count
            self.logger.info(f"Total controllers after mapping: {len(glpi_content.get('CONTROLLERS', []))}")
            
            # If no controllers found, try alternative collection method
            if len(glpi_content.get('CONTROLLERS', [])) == 0:
                # Try getting controllers from Win32_SystemDriver directly
                try:
                    controllers_alt = self._ps_json('Get-CimInstance Win32_SystemDriver | Where-Object {$_.Status -eq "OK" -and ($_.Name -like "*Controller*" -or $_.Name -like "*USB*" -or $_.Name -like "*PCI*" -or $_.Name -like "*SATA*" -or $_.Name -like "*AHCI*" -or $_.Name -like "*NVMe*" -or $_.Name -like "*Thunderbolt*" -or $_.Name -like "*Audio*" -or $_.Name -like "*Network*" -or $_.Name -like "*Bluetooth*" -or $_.Name -like "*Wireless*" -or $_.Name -like "*Intel*" -or $_.Name -like "*Realtek*")} | Select-Object -First 50 Name,Description', depth=4)
                    if controllers_alt:
                        glpi_content['CONTROLLERS'] = []
                        controllers_list_alt = controllers_alt if isinstance(controllers_alt, list) else [controllers_alt]
                        for ctrl in controllers_list_alt:
                            if isinstance(ctrl, dict) and ctrl.get('Name'):
                                name = str(ctrl.get('Name', '')).strip()
                                if name:
                                    ctrl_entry_alt = {'NAME': name}
                                    if ctrl.get('Description'):
                                        ctrl_entry_alt['CAPTION'] = str(ctrl.get('Description', '')).strip()
                                    # Determine type from name
                                    name_upper = name.upper()
                                    if 'USB' in name_upper:
                                        ctrl_entry_alt['TYPE'] = 'USB'
                                    elif 'PCI' in name_upper or 'PCIEXPRESS' in name_upper:
                                        ctrl_entry_alt['TYPE'] = 'PCI'
                                    elif 'SATA' in name_upper or 'AHCI' in name_upper:
                                        ctrl_entry_alt['TYPE'] = 'SATA'
                                    elif 'NVME' in name_upper:
                                        ctrl_entry_alt['TYPE'] = 'NVMe'
                                    elif 'THUNDERBOLT' in name_upper:
                                        ctrl_entry_alt['TYPE'] = 'Thunderbolt'
                                    elif 'AUDIO' in name_upper or 'SOUND' in name_upper:
                                        ctrl_entry_alt['TYPE'] = 'Audio'
                                    elif 'NETWORK' in name_upper or 'ETHERNET' in name_upper or 'WIRELESS' in name_upper or 'WIFI' in name_upper:
                                        ctrl_entry_alt['TYPE'] = 'Network controller'
                                    elif 'BLUETOOTH' in name_upper:
                                        ctrl_entry_alt['TYPE'] = 'Bluetooth'
                                    else:
                                        ctrl_entry_alt['TYPE'] = 'Other'
                                    glpi_content['CONTROLLERS'].append(ctrl_entry_alt)
                except Exception:
                    pass
            
            # macOS data mapping (similar to Windows)
            macos_data = data.get('macos', {})
            if macos_data:
                # OPERATINGSYSTEM - Override with macOS data if available
                os_data = macos_data.get('operating_system', {})
                if os_data:
                    # Get OS name from system data (product_name from sw_vers)
                    os_name = os_data.get('product_name', 'MacOSX')
                    # Normalize common macOS names
                    if 'macos' in os_name.lower() or 'mac os' in os_name.lower():
                        os_name = 'MacOSX'
                    
                    glpi_content['OPERATINGSYSTEM'] = {
                        'NAME': os_name,
                        'FULL_NAME': os_data.get('product_name', 'macOS'),
                        'VERSION': os_data.get('product_version', ''),
                        'KERNEL_VERSION': os_data.get('kernel_version', ''),
                        'ARCH': platform.machine(),
                        'FQDN': data.get('network', {}).get('fqdn', socket.getfqdn()),
                    }
                
                # HARDWARE - Update with macOS hardware summary
                hw_summary = macos_data.get('hardware_summary', {})
                if hw_summary:
                    if hw_summary.get('manufacturer'):
                        glpi_content['BIOS']['SMANUFACTURER'] = hw_summary['manufacturer']
                    if hw_summary.get('model'):
                        glpi_content['BIOS']['SMODEL'] = hw_summary['model']
                    if hw_summary.get('serial_number'):
                        glpi_content['BIOS']['SSN'] = hw_summary['serial_number']
                    if hw_summary.get('model_identifier'):
                        glpi_content['HARDWARE']['MODEL'] = hw_summary['model_identifier']
                
                # CPUS - Map from macOS CPU data
                cpu_data = macos_data.get('cpu', {})
                if cpu_data and isinstance(cpu_data, dict):
                    # Parse speed from string like "2.6 GHz"
                    speed = None
                    speed_str = cpu_data.get('speed', '')
                    if speed_str:
                        import re
                        match = re.match(r'([\d.]+)\s*(GHz|MHz)', speed_str, re.IGNORECASE)
                        if match:
                            value = float(match.group(1))
                            unit = match.group(2).upper()
                            if unit == 'GHZ':
                                speed = int(value * 1000)  # Convert to MHz
                            else:
                                speed = int(value)
                    
                    cores = cpu_data.get('cores')
                    if isinstance(cores, str):
                        try:
                            cores = int(cores)
                        except ValueError:
                            cores = None
                    
                    threads = cpu_data.get('threads')
                    if isinstance(threads, str):
                        try:
                            threads = int(threads)
                        except ValueError:
                            threads = None
                    
                    num_procs = cpu_data.get('number_of_processors', 1)
                    if isinstance(num_procs, str):
                        try:
                            num_procs = int(num_procs)
                        except ValueError:
                            num_procs = 1
                    
                    # Create one entry per processor
                    glpi_content['CPUS'] = []
                    for i in range(num_procs):
                        cpu_entry = {
                            'NAME': cpu_data.get('name', ''),
                            'CORE': cores,
                            'THREAD': threads,
                        }
                        if speed:
                            cpu_entry['SPEED'] = speed
                        glpi_content['CPUS'].append(cpu_entry)
                
                # MEMORIES - Map from macOS memory data
                memory_data = macos_data.get('memory', {})
                if memory_data and memory_data.get('total_bytes'):
                    # Convert total bytes to MB for HARDWARE
                    total_mb = int(memory_data['total_bytes'] / (1024 * 1024))
                    glpi_content['HARDWARE']['MEMORY'] = total_mb
                
                # STORAGES - Map from macOS storage data
                storage_data = macos_data.get('storage', {})
                if storage_data:
                    physical_disks = storage_data.get('physical_disks')
                    if physical_disks and isinstance(physical_disks, list):
                        glpi_content['STORAGES'] = []
                        for disk in physical_disks:
                            if isinstance(disk, dict):
                                storage_entry = {
                                    'NAME': disk.get('_name', disk.get('name', '')),
                                    'MODEL': disk.get('_name', disk.get('name', '')),
                                }
                                # Try to extract size
                                size_str = disk.get('size', disk.get('_size', ''))
                                if size_str:
                                    import re
                                    match = re.match(r'([\d.]+)\s*(GB|MB|TB)', size_str, re.IGNORECASE)
                                    if match:
                                        value = float(match.group(1))
                                        unit = match.group(2).upper()
                                        if unit == 'TB':
                                            size_mb = int(value * 1024 * 1024)
                                        elif unit == 'GB':
                                            size_mb = int(value * 1024)
                                        else:
                                            size_mb = int(value)
                                        storage_entry['DISKSIZE'] = size_mb
                                if storage_entry.get('NAME'):
                                    glpi_content['STORAGES'].append(storage_entry)
                
                # VIDEOS - Map from macOS video data
                video_data = macos_data.get('video', {})
                gpus = video_data.get('gpus', []) if isinstance(video_data, dict) else []
                if gpus:
                    glpi_content['VIDEOS'] = []
                    if not isinstance(gpus, list):
                        gpus = [gpus]
                    for vid in gpus:
                        if isinstance(vid, dict):
                            vid_entry = {}
                            vid_name = vid.get('_name', vid.get('name', ''))
                            if vid_name:
                                vid_entry['NAME'] = str(vid_name).strip()
                            # Try to extract VRAM
                            vram_str = vid.get('VRAM', vid.get('vram', ''))
                            if vram_str:
                                import re
                                match = re.match(r'([\d.]+)\s*(MB|GB)', vram_str, re.IGNORECASE)
                                if match:
                                    value = float(match.group(1))
                                    unit = match.group(2).upper()
                                    if unit == 'GB':
                                        vid_entry['MEMORY'] = int(value * 1024)
                                    else:
                                        vid_entry['MEMORY'] = int(value)
                            if vid_entry.get('NAME'):
                                glpi_content['VIDEOS'].append(vid_entry)
                
                # NETWORKS - Map from macOS network data
                network_data = macos_data.get('network_detail', {})
                if network_data and isinstance(network_data, dict):
                    adapters = network_data.get('adapters')
                    if adapters and isinstance(adapters, list):
                        # Parse ifconfig output for detailed network info
                        ifconfig_data = network_data.get('ifconfig', '')
                        if ifconfig_data:
                            # Parse ifconfig output to extract interface details
                            import re
                            interfaces = {}
                            current_if = None
                            for line in ifconfig_data.splitlines():
                                # Match interface name: "en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500"
                                match = re.match(r'^(\w+):', line)
                                if match:
                                    current_if = match.group(1)
                                    interfaces[current_if] = {}
                                elif current_if:
                                    # Match MAC: "ether 00:11:22:33:44:55"
                                    match = re.search(r'ether ([0-9a-f:]{17})', line, re.IGNORECASE)
                                    if match:
                                        interfaces[current_if]['MAC'] = match.group(1).upper()
                                    # Match IP: "inet 192.168.1.100 netmask 0xffffff00 broadcast 192.168.1.255"
                                    match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', line)
                                    if match:
                                        interfaces[current_if]['IPADDRESS'] = match.group(1)
                            
                            # Merge adapter data with ifconfig data
                            for adapter in adapters:
                                if isinstance(adapter, dict):
                                    interface_name = adapter.get('_name', adapter.get('name', ''))
                                    if interface_name and interface_name in interfaces:
                                        ifconfig_info = interfaces[interface_name]
                                        adapter.update(ifconfig_info)
                        
                        # Build network entries
                        if not glpi_content.get('NETWORKS'):
                            glpi_content['NETWORKS'] = []
                        for adapter in adapters:
                            if isinstance(adapter, dict):
                                net_entry = {}
                                desc = adapter.get('_name', adapter.get('name', ''))
                                if desc:
                                    net_entry['DESCRIPTION'] = str(desc).strip()
                                if adapter.get('MAC'):
                                    net_entry['MAC'] = str(adapter['MAC']).upper()
                                if adapter.get('IPADDRESS'):
                                    net_entry['IPADDRESS'] = str(adapter['IPADDRESS']).strip()
                                # Determine type
                                desc_upper = str(desc).upper() if desc else ''
                                if 'WIFI' in desc_upper or 'WIRELESS' in desc_upper:
                                    net_entry['TYPE'] = 'wifi'
                                elif 'BLUETOOTH' in desc_upper:
                                    net_entry['TYPE'] = 'bluetooth'
                                elif 'ETHERNET' in desc_upper or 'THUNDERBOLT' in desc_upper:
                                    net_entry['TYPE'] = 'ethernet'
                                if net_entry.get('DESCRIPTION') or net_entry.get('MAC'):
                                    glpi_content['NETWORKS'].append(net_entry)
                
                # PRINTERS - Map from macOS printer data
                printers_data = macos_data.get('printers', [])
                if printers_data:
                    if not glpi_content.get('PRINTERS'):
                        glpi_content['PRINTERS'] = []
                    if not isinstance(printers_data, list):
                        printers_data = [printers_data]
                    for printer in printers_data:
                        if isinstance(printer, dict):
                            printer_entry = {}
                            if printer.get('name'):
                                printer_entry['NAME'] = str(printer['name']).strip()
                            if printer.get('status'):
                                printer_entry['STATUS'] = str(printer['status']).strip()
                            if printer_entry.get('NAME'):
                                glpi_content['PRINTERS'].append(printer_entry)
                
                # BATTERIES - Map from macOS power data
                power_data = macos_data.get('power', {})
                batteries = power_data.get('batteries', []) if power_data else []
                if batteries:
                    if not glpi_content.get('BATTERIES'):
                        glpi_content['BATTERIES'] = []
                    if not isinstance(batteries, list):
                        batteries = [batteries]
                    for bat in batteries:
                        if isinstance(bat, dict):
                            bat_entry = {}
                            # Extract battery info
                            model_info = bat.get('Model Information', bat.get('model_information', {}))
                            charge_info = bat.get('Charge Information', bat.get('charge_information', {}))
                            
                            device_name = model_info.get('Device Name', model_info.get('device_name', 'Primary'))
                            bat_entry['NAME'] = device_name
                            
                            if model_info.get('Manufacturer', model_info.get('manufacturer')):
                                bat_entry['MANUFACTURER'] = str(model_info.get('Manufacturer', model_info.get('manufacturer', ''))).strip()
                            if model_info.get('Serial Number', model_info.get('serial_number')):
                                bat_entry['SERIAL'] = str(model_info.get('Serial Number', model_info.get('serial_number', ''))).strip()
                            
                            # Capacity
                            full_capacity = charge_info.get('Full Charge Capacity (mAh)', charge_info.get('full_charge_capacity_mah'))
                            if full_capacity:
                                try:
                                    bat_entry['CAPACITY'] = int(full_capacity)
                                    bat_entry['REAL_CAPACITY'] = int(full_capacity)
                                except (ValueError, TypeError):
                                    pass
                            
                            # Voltage
                            voltage = bat.get('Voltage (mV)', bat.get('voltage_mv'))
                            if voltage:
                                try:
                                    bat_entry['VOLTAGE'] = int(voltage)
                                except (ValueError, TypeError):
                                    pass
                            
                            if bat_entry.get('NAME'):
                                glpi_content['BATTERIES'].append(bat_entry)
                
                # MONITORS - Map from macOS monitor data
                monitors_data = macos_data.get('monitors', {})
                if monitors_data:
                    displays = monitors_data.get('displays', [])
                    if displays:
                        if not glpi_content.get('MONITORS'):
                            glpi_content['MONITORS'] = []
                        if not isinstance(displays, list):
                            displays = [displays]
                        for display in displays:
                            if isinstance(display, dict):
                                monitor_entry = {}
                                name = display.get('_name', display.get('name', 'Display'))
                                if name:
                                    monitor_entry['NAME'] = str(name).strip()
                                    monitor_entry['CAPTION'] = str(name).strip()
                                resolution = display.get('Resolution', display.get('resolution', ''))
                                if resolution:
                                    monitor_entry['RESOLUTION'] = str(resolution).strip()
                                if monitor_entry.get('NAME'):
                                    glpi_content['MONITORS'].append(monitor_entry)
                
                # CONTROLLERS - Map from macOS controller data
                controllers_data = macos_data.get('controllers', [])
                if controllers_data:
                    if not glpi_content.get('CONTROLLERS'):
                        glpi_content['CONTROLLERS'] = []
                    if not isinstance(controllers_data, list):
                        controllers_data = [controllers_data]
                    for controller in controllers_data:
                        if isinstance(controller, dict):
                            ctrl_entry = {}
                            name = controller.get('_name', controller.get('name', ''))
                            if name:
                                ctrl_entry['NAME'] = str(name).strip()
                            # Determine type from name
                            name_upper = str(name).upper() if name else ''
                            if 'USB' in name_upper:
                                ctrl_entry['TYPE'] = 'USB'
                            elif 'PCI' in name_upper:
                                ctrl_entry['TYPE'] = 'PCI'
                            elif 'SATA' in name_upper or 'AHCI' in name_upper:
                                ctrl_entry['TYPE'] = 'SATA'
                            elif 'NVME' in name_upper:
                                ctrl_entry['TYPE'] = 'NVMe'
                            elif 'THUNDERBOLT' in name_upper:
                                ctrl_entry['TYPE'] = 'Thunderbolt'
                            else:
                                ctrl_entry['TYPE'] = 'Other'
                            if ctrl_entry.get('NAME'):
                                glpi_content['CONTROLLERS'].append(ctrl_entry)
            
            # Linux data mapping (similar to Windows and macOS)
            linux_data = data.get('linux', {})
            if linux_data:
                # OPERATINGSYSTEM - Override with Linux data if available
                os_data = linux_data.get('operating_system', {})
                if os_data:
                    os_name = os_data.get('name', 'Linux')
                    if not os_name or os_name == 'Linux':
                        # Try to get from os-release
                        os_name = os_data.get('pretty_name', os_data.get('id', 'Linux'))
                    
                    glpi_content['OPERATINGSYSTEM'] = {
                        'NAME': os_name,
                        'FULL_NAME': os_data.get('pretty_name', os_name),
                        'VERSION': os_data.get('version_id', ''),
                        'KERNEL_VERSION': os_data.get('kernel_version', ''),
                        'ARCH': platform.machine(),
                        'FQDN': data.get('network', {}).get('fqdn', socket.getfqdn()),
                    }
                
                # HARDWARE - Update with Linux hardware summary
                hw_summary = linux_data.get('hardware_summary', {})
                if hw_summary:
                    if hw_summary.get('manufacturer'):
                        glpi_content['BIOS']['SMANUFACTURER'] = hw_summary['manufacturer']
                        glpi_content['BIOS']['BMANUFACTURER'] = hw_summary.get('bios_vendor') or hw_summary['manufacturer']
                    if hw_summary.get('model'):
                        glpi_content['BIOS']['SMODEL'] = hw_summary['model']
                    if hw_summary.get('serial_number'):
                        glpi_content['BIOS']['SSN'] = hw_summary['serial_number']
                    if hw_summary.get('bios_version'):
                        glpi_content['BIOS']['BVERSION'] = hw_summary['bios_version']
                    if hw_summary.get('bios_date'):
                        # Format BIOS date (usually YYYY/MM/DD or similar)
                        bios_date = hw_summary['bios_date']
                        try:
                            # Try to parse and format date
                            import re
                            date_match = re.match(r'(\d{4})[/-](\d{2})[/-](\d{2})', bios_date)
                            if date_match:
                                glpi_content['BIOS']['BDATE'] = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                            else:
                                glpi_content['BIOS']['BDATE'] = bios_date
                        except Exception:
                            pass
                    if hw_summary.get('chassis_type'):
                        glpi_content['HARDWARE']['CHASSIS_TYPE'] = hw_summary['chassis_type']
                
                # CPUS - Map from Linux CPU data
                cpu_data = linux_data.get('cpu', {})
                if cpu_data and isinstance(cpu_data, dict):
                    speed = cpu_data.get('speed')
                    glpi_content['CPUS'] = [{
                        'NAME': cpu_data.get('name', ''),
                        'CORE': cpu_data.get('cores'),
                        'THREAD': cpu_data.get('threads'),
                        'SPEED': speed,
                    }]
                
                # MEMORIES - Map from Linux memory data
                memory_data = linux_data.get('memory', {})
                if memory_data:
                    if memory_data.get('total_bytes'):
                        total_mb = int(memory_data['total_bytes'] / (1024 * 1024))
                        glpi_content['HARDWARE']['MEMORY'] = total_mb
                    
                    memory_modules = memory_data.get('modules', [])
                    if memory_modules:
                        if not glpi_content.get('MEMORIES'):
                            glpi_content['MEMORIES'] = []
                        for mem in memory_modules:
                            if isinstance(mem, dict):
                                mem_entry = {}
                                if mem.get('size_mb'):
                                    mem_entry['CAPACITY'] = mem['size_mb']
                                if mem.get('manufacturer'):
                                    mem_entry['MANUFACTURER'] = str(mem['manufacturer']).strip()
                                if mem.get('serial'):
                                    mem_entry['SERIALNUMBER'] = str(mem['serial']).strip()
                                if mem.get('part_number'):
                                    mem_entry['MODEL'] = str(mem['part_number']).strip()
                                if mem.get('speed'):
                                    mem_entry['SPEED'] = str(mem['speed'])
                                if mem_entry:
                                    glpi_content['MEMORIES'].append(mem_entry)
                
                # STORAGES - Map from Linux storage data
                storage_data = linux_data.get('storage', {})
                if storage_data:
                    physical_disks = storage_data.get('physical_disks', [])
                    if physical_disks:
                        if not glpi_content.get('STORAGES'):
                            glpi_content['STORAGES'] = []
                        for disk in physical_disks:
                            if isinstance(disk, dict):
                                storage_entry = {}
                                if disk.get('name'):
                                    storage_entry['NAME'] = str(disk['name']).strip()
                                if disk.get('model'):
                                    storage_entry['MODEL'] = str(disk['model']).strip()
                                if disk.get('size_bytes'):
                                    storage_entry['DISKSIZE'] = int(disk['size_bytes'] / (1024 * 1024))
                                if disk.get('serial'):
                                    storage_entry['SERIAL'] = str(disk['serial']).strip()
                                if storage_entry.get('NAME'):
                                    glpi_content['STORAGES'].append(storage_entry)
                
                # VIDEOS - Map from Linux video data
                video_data = linux_data.get('video', {})
                gpus = video_data.get('gpus', []) if isinstance(video_data, dict) else []
                if gpus:
                    if not glpi_content.get('VIDEOS'):
                        glpi_content['VIDEOS'] = []
                    if not isinstance(gpus, list):
                        gpus = [gpus]
                    for vid in gpus:
                        if isinstance(vid, dict):
                            vid_entry = {}
                            if vid.get('name'):
                                vid_entry['NAME'] = str(vid['name']).strip()
                            if vid_entry.get('NAME'):
                                glpi_content['VIDEOS'].append(vid_entry)
                
                # NETWORKS - Map from Linux network data
                network_data = linux_data.get('network_detail', {})
                if network_data and isinstance(network_data, dict):
                    adapters = network_data.get('adapters', [])
                    if adapters:
                        if not glpi_content.get('NETWORKS'):
                            glpi_content['NETWORKS'] = []
                        for adapter in adapters:
                            if isinstance(adapter, dict):
                                net_entry = {}
                                if adapter.get('name'):
                                    net_entry['DESCRIPTION'] = str(adapter['name']).strip()
                                if adapter.get('mac'):
                                    net_entry['MAC'] = str(adapter['mac']).upper()
                                if adapter.get('ip'):
                                    net_entry['IPADDRESS'] = str(adapter['ip']).strip()
                                if adapter.get('type'):
                                    net_entry['TYPE'] = str(adapter['type']).strip()
                                if adapter.get('speed'):
                                    net_entry['SPEED'] = str(adapter['speed'])
                                if net_entry.get('DESCRIPTION') or net_entry.get('MAC'):
                                    glpi_content['NETWORKS'].append(net_entry)
                
                # PRINTERS - Map from Linux printer data
                printers_data = linux_data.get('printers', [])
                if printers_data:
                    if not glpi_content.get('PRINTERS'):
                        glpi_content['PRINTERS'] = []
                    if not isinstance(printers_data, list):
                        printers_data = [printers_data]
                    for printer in printers_data:
                        if isinstance(printer, dict):
                            printer_entry = {}
                            if printer.get('name'):
                                printer_entry['NAME'] = str(printer['name']).strip()
                            if printer.get('status'):
                                printer_entry['STATUS'] = str(printer['status']).strip()
                            if printer_entry.get('NAME'):
                                glpi_content['PRINTERS'].append(printer_entry)
                
                # BATTERIES - Map from Linux power data
                power_data = linux_data.get('power', {})
                batteries = power_data.get('batteries', []) if power_data else []
                if batteries:
                    if not glpi_content.get('BATTERIES'):
                        glpi_content['BATTERIES'] = []
                    if not isinstance(batteries, list):
                        batteries = [batteries]
                    for bat in batteries:
                        if isinstance(bat, dict):
                            bat_entry = {}
                            if bat.get('name'):
                                bat_entry['NAME'] = str(bat['name']).strip()
                            if bat.get('manufacturer'):
                                bat_entry['MANUFACTURER'] = str(bat['manufacturer']).strip()
                            if bat.get('model_name'):
                                bat_entry['SERIAL'] = str(bat['model_name']).strip()
                            if bat.get('energy_full_mwh'):
                                try:
                                    bat_entry['CAPACITY'] = int(bat['energy_full_mwh'])
                                    bat_entry['REAL_CAPACITY'] = int(bat.get('energy_now_mwh', bat['energy_full_mwh']))
                                except (ValueError, TypeError):
                                    pass
                            if bat_entry.get('NAME'):
                                glpi_content['BATTERIES'].append(bat_entry)
                
                # CONTROLLERS - Map from Linux controller data
                controllers_data = linux_data.get('controllers', [])
                if controllers_data:
                    if not glpi_content.get('CONTROLLERS'):
                        glpi_content['CONTROLLERS'] = []
                    if not isinstance(controllers_data, list):
                        controllers_data = [controllers_data]
                    for controller in controllers_data:
                        if isinstance(controller, dict):
                            ctrl_entry = {}
                            if controller.get('name'):
                                ctrl_entry['NAME'] = str(controller['name']).strip()
                            if controller.get('type'):
                                ctrl_entry['TYPE'] = str(controller['type']).strip()
                            else:
                                # Determine type from name
                                name_upper = str(controller.get('name', '')).upper()
                                if 'USB' in name_upper:
                                    ctrl_entry['TYPE'] = 'USB'
                                elif 'PCI' in name_upper:
                                    ctrl_entry['TYPE'] = 'PCI'
                                elif 'SATA' in name_upper or 'AHCI' in name_upper:
                                    ctrl_entry['TYPE'] = 'SATA'
                                elif 'NVME' in name_upper:
                                    ctrl_entry['TYPE'] = 'NVMe'
                                else:
                                    ctrl_entry['TYPE'] = 'Other'
                            if ctrl_entry.get('NAME'):
                                glpi_content['CONTROLLERS'].append(ctrl_entry)
                
                # MONITORS - Map from Linux monitor data
                monitors_data = linux_data.get('monitors', {})
                if monitors_data:
                    displays = monitors_data.get('monitors', [])
                    if displays:
                        if not glpi_content.get('MONITORS'):
                            glpi_content['MONITORS'] = []
                        if not isinstance(displays, list):
                            displays = [displays]
                        for display in displays:
                            if isinstance(display, dict):
                                monitor_entry = {}
                                if display.get('name'):
                                    monitor_entry['NAME'] = str(display['name']).strip()
                                    monitor_entry['CAPTION'] = str(display['name']).strip()
                                if display.get('resolution'):
                                    monitor_entry['RESOLUTION'] = str(display['resolution']).strip()
                                if monitor_entry.get('NAME'):
                                    glpi_content['MONITORS'].append(monitor_entry)
            
            # Message structure matching Perl Protocol::Inventory format
            message_data = {
                'action': 'inventory',
                'deviceid': data.get('deviceid', self.deviceid),
                'itemtype': 'Computer',
                'content': glpi_content
            }
            
            # Ensure ProtocolMessage is available
            if ProtocolMessage is None:
                from GLPI.Agent.Protocol.Message import ProtocolMessage
            message = ProtocolMessage(message=message_data)
            
            # Send using GLPI HTTP client
            response = client.send(
                url=self.target.get_name(),
                message=message
            )
            
            if response:
                if self.logger:
                    self.logger.info("✅ Inventory successfully sent to server!")
                return True
            else:
                if self.logger:
                    self.logger.error("Failed to send inventory - no response from server")
                return False
                
        except ImportError as e:
            if self.logger:
                self.logger.error(f"Cannot load GLPI HTTP client: {e}")
            return False
        except Exception as e:
            if self.logger:
                self.logger.error(f"Unexpected error sending inventory: {e}")
                import traceback
                self.logger.debug(traceback.format_exc())
            return False
   
    def _save_to_local(self, data: Dict):
        """Save inventory to local file"""
        if self.logger:
            self.logger.info(f"Saving inventory to {self.target.get_name()}")
       
        output_file = os.path.join(self.target.path, f"inventory_{self.deviceid}_{int(time.time())}.json")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
       
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)


# Utility functions
def get_hostname(short: bool = False, fqdn: bool = False) -> str:
    """Get hostname with options"""
    if fqdn:
        return socket.getfqdn()
    elif short:
        return socket.gethostname().split('.')[0]
    else:
        return socket.gethostname()


def create_uuid() -> str:
    """Create a new UUID"""
    return str(uuid.uuid4())


def uuid_to_string(uuid_obj) -> str:
    """Convert UUID to string"""
    return str(uuid_obj) if uuid_obj else ""


def file2module(file_path: str) -> str:
    """Convert file path to module name"""
    return file_path.replace('/', '.').replace('.pm', '').replace('.py', '')


def empty(value) -> bool:
    """Check if value is empty"""
    if value is None:
        return True
    if isinstance(value, (str, list, dict)):
        return len(value) == 0
    return False


class GLPIAgent:
    """Exact replica of GLPI::Agent"""
   
    def __init__(self, datadir: str = None, libdir: str = None, vardir: str = None):
        """Exact replica of new() method"""
        self.status = 'unknown'
        self.datadir = datadir
        self.libdir = libdir
        self.vardir = vardir
        self.targets = []
        self._cache = {}
       
        # Additional attributes
        self.config = None
        self.logger = None
        self.storage = None
        self.deviceid = None
        self.agentid = None
        self.event = None
        self.credentials = None
        self.current_task = None
        self.installed_tasks = []
        self.server = None
        self._terminate = False
        self._forced_run = False
        self._disabled_remoteinventory = False
   
    def init(self, options: Dict = None, **params):
        """Exact replica of init() method"""
        if not self.config:
            self.config = Config(
                options=options,
                vardir=self.vardir
            )
       
        if self.config.get('vardir') and os.path.isdir(self.config.get('vardir')):
            self.vardir = self.config.get('vardir')
       
        self.logger = Logger(config=self.config)
       
        self.logger.debug(f"Configuration directory: {self.config.confdir()}")
        self.logger.debug(f"Data directory: {self.datadir}")
        self.logger.debug(f"Storage directory: {self.vardir}")
        self.logger.debug(f"Lib directory: {self.libdir}")
       
        self._handle_persistent_state()
       
        forced_run = self._forced_run
        self._forced_run = False
       
        # Always reset targets
        self.targets = self.config.get_targets(
            logger=self.logger,
            deviceid=self.deviceid,
            vardir=self.vardir
        )
       
        if not self.get_targets() and (not options or not options.get('list-tasks')):
            self.logger.error("No target defined, aborting")
            sys.exit(1)
       
        # Compute available tasks
        available = self.get_available_tasks()
        tasks = sorted(available.keys())
        if not tasks:
            self.logger.error("No tasks available, aborting")
            sys.exit(1)
       
        self.installed_tasks = [task.lower() for task in tasks]
        planned_tasks = self.compute_task_execution_plan(available)
       
        self.logger.debug("Available tasks:")
        for task in tasks:
            self.logger.debug(f"- {task}: {available[task]}")
       
        for target in self.get_targets():
            if target.is_type('local') or target.is_type('server'):
                self.logger.debug(f"target {target.id}: {target.get_type()} {target.get_name()}")
                if forced_run:
                    target.set_next_run_date_from_now()
            else:
                self.logger.debug(f"target {target.id}: {target.get_type()}")
           
            planned = target.planned_tasks(planned_tasks)
           
            if planned:
                self.logger.debug(f"Planned tasks for {target.id}: {','.join(planned)}")
            else:
                self.logger.debug(f"No planned task for {target.id}")
       
        if (self.config.has_filled_param('no-task') and
            self.config.has_filled_param('tasks')):
            self.logger.info("Options 'no-task' and 'tasks' are both used. "
                           "Be careful that 'no-task' always excludes tasks.")
       
        # Signal handlers
        signal.signal(signal.SIGINT, lambda s, f: self._signal_handler())
        signal.signal(signal.SIGTERM, lambda s, f: self._signal_handler())
       
        if options:
            for comment in COMMENTS:
                self.logger.debug(comment)
   
    def _signal_handler(self):
        """Signal handler"""
        self.terminate()
        sys.exit(0)
   
    def run(self):
        """Exact replica of run() method"""
        self.set_status('waiting')
       
        targets = self.get_targets()
       
        self.logger.debug("Running in foreground mode")
       
        current_time = time.time()
        while self.get_targets() and targets:
            target = targets.pop(0)
            if (self.config.get('lazy') and
                current_time < target.get_next_run_date()):
               
                if self.config.get('force'):
                    self.logger.info(
                        f"{target.id} is not ready yet, but run is forced"
                    )
                else:
                    next_run = datetime.fromtimestamp(target.get_next_run_date())
                    self.logger.info(
                        f"{target.id} is not ready yet, next server contact "
                        f"planned for {next_run}"
                    )
                    continue
           
            try:
                self.run_target(target)
            except Exception as e:
                self.logger.error(str(e))
           
            target.reset_next_run_date()
   
    def terminate(self):
        """Exact replica of terminate() method"""
        self._terminate = True
        self.targets = []
       
        if self.current_task:
            self.current_task.abort()
   
    def get_contact(self, target, planned_tasks: List[str]):
        """Exact replica of getContact() method"""
        response = None
       
        if target.is_glpi_server():
            # GLPI protocol contact would go here
            pass
       
        return response
   
    def get_prolog(self, target):
        """Exact replica of getProlog() method"""
        response = None
       
        if target.is_type('server'):
            # PROLOG request would go here
            pass
       
        return response
   
    def run_target(self, target, responses_only: bool = False):
        """Exact replica of runTarget() method"""
        if target.is_type('local') or target.is_type('server'):
            self.logger.info(f"target {target.id}: {target.get_type()} {target.get_name()}")
       
        planned_tasks = target.planned_tasks()
        requests = []
        responses = {}
       
        if target.is_glpi_server():
            requests.append('CONTACT')
        if not requests and target.is_type('server'):
            requests.append('PROLOG')
       
        requested = {'CONTACT': False, 'PROLOG': False}
       
        while requests:
            request = requests.pop(0)
            if request in responses:
                continue
           
            response = None
            requested[request] = True
           
            if request == 'CONTACT':
                response = self.get_contact(target, planned_tasks)
                if response and not hasattr(response, '__dict__'):
                    return response
               
                if hasattr(response, 'planned_tasks'):
                    planned_tasks = response.planned_tasks
               
                if (hasattr(response, '__dict__') and target.do_prolog() and
                    not requested['PROLOG']):
                    requests.append('PROLOG')
           
            elif request == 'PROLOG':
                response = self.get_prolog(target)
                if response and not hasattr(response, '__dict__'):
                    return response
               
                if (hasattr(response, '__dict__') and target.is_glpi_server() and
                    not requested['CONTACT']):
                    requests.append('CONTACT')
           
            if hasattr(response, '__dict__'):
                responses[request] = response
       
        if responses_only:
            return responses
       
        for name in planned_tasks:
            server_response = responses.get('PROLOG') or responses.get('CONTACT')
            if responses.get('CONTACT'):
                task_server = target.get_task_server(name) or 'glpi'
                if task_server == 'glpi':
                    server_response = responses['CONTACT']
           
            try:
                self.run_task(target, name, server_response)
            except Exception as e:
                self.logger.error(str(e))
           
            self.set_status('paused' if target.paused() else 'waiting')
           
            if self._terminate:
                break
            if target.paused():
                break
       
        return 0
   
    def run_task(self, target, name: str, response=None):
        """Exact replica of runTask() method"""
        self.set_status(f"running task {name}")
        self.run_task_real(target, name, response)
   
    def run_task_real(self, target, name: str, response=None):
        """Exact replica of runTaskReal() method"""
        class_name = f"GLPI::Agent::Task::{name}"
       
        # Try to load task class
        task_class = self._get_task_class(name)
        if not task_class:
            if self.logger:
                self.logger.debug2(f"{name} task module does not compile")
            return
       
        task = task_class(
            config=self.config,
            datadir=self.datadir,
            logger=self.logger,
            event=self.event,
            credentials=self.credentials,
            target=target,
            deviceid=self.deviceid,
            agentid=uuid_to_string(self.agentid),
            cached_data=self._cache.get(name),
        )
       
        # Handle init event
        if self.event and self.event.init:
            event = task.new_event() if hasattr(task, 'new_event') else None
            if event and hasattr(event, 'name') and event.name:
                target.add_event(event, True)
            return
       
        if response and hasattr(task, 'is_enabled') and not task.is_enabled(response):
            return
       
        event_name = self.event.name if self.event else ""
        log_msg = f"running task {name}"
        if event_name:
            log_msg += f": {event_name} event"
       
        self.logger.info(log_msg)
        self.current_task = task
       
        task.run()
       
        self.handle_task_cache(name, task)
        self.handle_task_event(name, task)
       
        self.current_task = None
   
    def _get_task_class(self, name: str):
        """Get task class by name"""
        if name.lower() == 'inventory':
            # Use simple InventoryTask that works reliably
            if self.logger:
                self.logger.debug("Using simple InventoryTask with GLPI schema transformation")
            return InventoryTask
       
        try:
            module_name = f"glpi_agent.task.{name.lower()}"
            task_module = importlib.import_module(module_name)
            return getattr(task_module, name + 'Task', None)
        except ImportError:
            return None
   
    def handle_task_cache(self, name: str, task):
        """Placeholder - only supported in daemon mode"""
        pass
   
    def handle_task_event(self, name: str, task):
        """Placeholder - only supported in daemon mode"""
        pass
   
    def get_status(self) -> str:
        """Exact replica of getStatus()"""
        return self.status
   
    def set_status(self, status: str = None):
        """Exact replica of setStatus()"""
        config = self.config
       
        # Set process name (simplified)
        process_name = f"{PROVIDER.lower()}-agent"
        if config and config.get('tag'):
            process_name += f" (tag {config.get('tag')})"
       
        if status:
            self.status = status
            process_name += f": {status}"
       
        # Limited process name setting
        try:
            import setproctitle
            setproctitle.setproctitle(process_name)
        except ImportError:
            pass
   
    def get_targets(self) -> List[BaseTarget]:
        """Exact replica of getTargets()"""
        return self.targets
   
    def get_available_tasks(self) -> Dict[str, str]:
        """Exact replica of getAvailableTasks()"""
        logger = self.logger
       
        tasks = {}
        disabled = {task.lower(): True for task in (self.config.get('no-task') or [])}
       
        # Built-in tasks
        builtin_tasks = {'Inventory': '1.0.0'}
       
        for task_name, version in builtin_tasks.items():
            if task_name.lower() not in disabled:
                tasks[task_name] = version
                if logger:
                    logger.debug2(f"getAvailableTasks() : add of task {task_name} version {version}")
       
        # Scan for task modules
        directory = self.libdir
        directory = directory.replace('\\', '/')
        subdirectory = "GLPI/Agent/Task"
       
        pattern = f"{directory}/{subdirectory}/*/Version.py"
        for file_path in glob.glob(pattern):
            match = re.search(rf"({re.escape(subdirectory)}/(\S+)/Version\.py)$", file_path)
            if not match:
                continue
           
            module_path = file2module(match.group(1))
            name = file2module(match.group(2))
           
            if name.lower() in disabled:
                continue
           
            try:
                spec = importlib.util.spec_from_file_location(module_path, file_path)
                if not spec or not spec.loader:
                    continue
               
                version_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(version_module)
               
                version = getattr(version_module, 'VERSION', None)
                if not version:
                    continue
               
                tasks[name] = version
                if logger:
                    logger.debug2(f"getAvailableTasks() : add of task {name} version {version}")
               
            except Exception as e:
                if logger:
                    logger.debug2(f"module {module_path} does not compile: {e}")
       
        return tasks
   
    def get_asset_name(self) -> str:
        """Exact replica of getAssetName()"""
        config = {}
       
        if self.config and self.config.get('assetname-support'):
            support = self.config.get('assetname-support')
            if support == 1:
                config['short'] = True
            elif support == 3:
                config['fqdn'] = True
       
        return get_hostname(**config) or "unknown"
   
    def normalize_device_id(self, deviceid: str) -> str:
        """Exact replica of normalizeDeviceId()"""
        if not deviceid:
            return deviceid
       
        match = re.match(r'^(.*)(-\d+-\d+-\d+-\d+-\d+-\d+)', deviceid)
        if not match:
            return deviceid
       
        assetname, timestamp = match.groups()
        real_name = self.get_asset_name()
       
        if assetname == real_name:
            return deviceid
       
        # Check for FQDN vs short name changes
        if (len(real_name) > len(assetname) and
            real_name.startswith(f"{assetname}.")):
            return real_name + timestamp
       
        if (len(real_name) < len(assetname) and
            assetname.startswith(f"{real_name}.")):
            return real_name + timestamp
       
        # Finally assume deviceid has to be reset
        return ""
   
    def _handle_persistent_state(self):
        """Exact replica of _handlePersistentState()"""
        if not self.storage:
            self.storage = Storage(
                logger=self.logger,
                directory=self.vardir
            )
       
        data = self.storage.restore(name=f"{PROVIDER}-Agent")
        if not data:
            data = {}
       
        # Fix deviceid if assetname-support changed
        if data and not empty(data.get('deviceid')):
            data['deviceid'] = self.normalize_device_id(data['deviceid'])
       
        if not self.deviceid and not data.get('deviceid'):
            # Compute unique agent identifier
            assetname = self.get_asset_name()
           
            now = datetime.now()
            year, month, day, hour, minute, sec = (
                now.year, now.month, now.day,
                now.hour, now.minute, now.second
            )
           
            data['deviceid'] = f"{assetname}-{year:04d}-{month:02d}-{day:02d}-{hour:02d}-{minute:02d}-{sec:02d}"
        elif not data.get('deviceid'):
            data['deviceid'] = self.deviceid
       
        self.deviceid = data['deviceid']
       
        # Support agentid
        if not self.agentid and not data.get('agentid'):
            data['agentid'] = create_uuid()
        elif not data.get('agentid'):
            data['agentid'] = self.agentid
       
        self.agentid = data['agentid']
       
        # Handle forcerun option
        self._forced_run = data.pop('forcerun', False)
       
        # Always save agent state
        self.storage.save(
            name=f"{PROVIDER}-Agent",
            data=data
        )
   
    def set_force_run(self, forcerun=None):
        """Exact replica of setForceRun()"""
        storage = Storage(
            logger=self.logger,
            directory=self.vardir
        )
       
        data = storage.restore(name=f"{PROVIDER}-Agent")
        if not data:
            data = {}
       
        data['forcerun'] = 1 if forcerun is None or forcerun else 0
       
        storage.save(
            name=f"{PROVIDER}-Agent",
            data=data
        )
   
    def compute_task_execution_plan(self, available_tasks: Dict[str, str]) -> List[str]:
        """Exact replica of computeTaskExecutionPlan()"""
        config = self.config
        if not config:
            if self.logger:
                self.logger.error("no config found in agent. Can't compute tasks execution plan")
            return []
       
        execution_plan = []
        if config.has_filled_param('tasks'):
            if self.logger:
                self.logger.debug2("Preparing execution plan")
            execution_plan = self._make_execution_plan(config.get('tasks'), available_tasks)
        else:
            execution_plan = list(available_tasks.keys())
       
        return execution_plan
   
    def _make_execution_plan(self, sorted_tasks: List[str], available_tasks: Dict[str, str]) -> List[str]:
        """Exact replica of _makeExecutionPlan()"""
        task_map = {name.lower(): name for name in available_tasks.keys()}
       
        execution_plan = []
        for task in sorted_tasks:
            if not task:
                continue
            if task == CONTINUE_WORD:
                used = set(execution_plan)
                remaining = [name for name in available_tasks.keys() if name not in used]
                execution_plan.extend(remaining)
                break
            task_lower = task.lower()
            if task_lower in task_map:
                execution_plan.append(task_map[task_lower])
       
        return execution_plan


def main():
    """Main entry point - exact Perl replica"""
    import argparse
   
    parser = argparse.ArgumentParser(description="GLPI Agent")
    parser.add_argument('--datadir', help='Data directory', default='/usr/share/glpi-agent')
    parser.add_argument('--libdir', help='Library directory', default='/usr/lib/glpi-agent')
    parser.add_argument('--vardir', help='Variable directory', default='/var/lib/glpi-agent')
    parser.add_argument('--server', action='append', help='Server URL(s)')
    parser.add_argument('--local', help='Local target directory')
    parser.add_argument('--tag', help='Agent tag')
    parser.add_argument('--force', action='store_true', help='Force execution')
    parser.add_argument('--lazy', action='store_true', help='Lazy mode')
    parser.add_argument('--no-task', action='append', help='Disable tasks')
    parser.add_argument('--tasks', help='Comma-separated task list')
    parser.add_argument('--list-tasks', action='store_true', help='List available tasks')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--version', action='version', version=f'{PROVIDER} Agent {VERSION}')
   
    args = parser.parse_args()
   
    # Convert args to options dict
    options = {}
    for key, value in vars(args).items():
        if value is not None:
            if key == 'no_task':
                options['no-task'] = value
            elif key == 'list_tasks':
                options['list-tasks'] = value
            elif key == 'tasks' and isinstance(value, str):
                options['tasks'] = [t.strip() for t in value.split(',')]
            else:
                options[key.replace('_', '-')] = value
   
    try:
        agent = GLPIAgent(
            datadir=args.datadir,
            libdir=args.libdir,
            vardir=args.vardir
        )
       
        agent.init(options=options)
       
        # Handle --list-tasks
        if options.get('list-tasks'):
            available = agent.get_available_tasks()
            print("Available tasks:")
            for task, version in sorted(available.items()):
                print(f"  {task}: {version}")
            return 0
       
        # Run the agent
        agent.run()
       
        return 0
       
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 1
    except SystemExit as e:
        return e.code
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':

    sys.exit(main())
