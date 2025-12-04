#!/usr/bin/env python3
"""
GLPI Agent Inventory - Python Implementation

Data structure for hardware and software inventory collection.
Handles inventory content, validation, checksums, and serialization.
"""

import os
import re
import json
import time
import hashlib
import glob as file_glob
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# Import dependencies
try:
    from .logger import Logger
    from .tools import get_sanitized_string, empty, glpi_version
    from .xml_handler import XMLHandler
    from .protocol.message import ProtocolMessage
    from .protocol.inventory import ProtocolInventory
    from .version import VERSION, PROVIDER, AGENT_STRING
except ImportError:
    try:
        from glpi_agent.logger import Logger
        from glpi_agent.tools import get_sanitized_string, empty, glpi_version
        from glpi_agent.xml_handler import XMLHandler
        from glpi_agent.protocol.message import ProtocolMessage
        from glpi_agent.protocol.inventory import ProtocolInventory
        from glpi_agent.version import VERSION, PROVIDER, AGENT_STRING
    except ImportError:
        # Fallbacks
        class Logger:
            def debug(self, msg): pass
            def error(self, msg): print(f"[ERROR] {msg}")
            def info(self, msg): print(f"[INFO] {msg}")
        
        def get_sanitized_string(s): return s
        def empty(s): return not s
        def glpi_version(v): return 10000000
        
        VERSION = "1.22"
        PROVIDER = "GLPI"
        AGENT_STRING = "GLPI-Agent"


# Field definitions for each inventory section
FIELDS = {
    'BIOS': ['SMODEL', 'SMANUFACTURER', 'SSN', 'BDATE', 'BVERSION',
             'BMANUFACTURER', 'MMANUFACTURER', 'MSN', 'MMODEL', 'ASSETTAG',
             'ENCLOSURESERIAL', 'BIOSSERIAL', 'SKUNUMBER'],
    'HARDWARE': ['NAME', 'SWAP', 'TYPE', 'WORKGROUP', 'DESCRIPTION', 'MEMORY', 'UUID', 'DNS',
                 'LASTLOGGEDUSER', 'DATELASTLOGGEDUSER', 'DEFAULTGATEWAY', 'VMSYSTEM',
                 'WINOWNER', 'WINPRODID', 'WINPRODKEY', 'WINCOMPANY', 'WINLANG', 'CHASSIS_TYPE'],
    'OPERATINGSYSTEM': ['KERNEL_NAME', 'KERNEL_VERSION', 'NAME', 'VERSION', 'FULL_NAME',
                        'SERVICE_PACK', 'INSTALL_DATE', 'FQDN', 'DNS_DOMAIN', 'HOSTID',
                        'SSH_KEY', 'ARCH', 'BOOT_TIME', 'TIMEZONE'],
    'ACCESSLOG': ['USERID', 'LOGDATE'],
    'ANTIVIRUS': ['COMPANY', 'ENABLED', 'GUID', 'NAME', 'UPTODATE', 'VERSION',
                  'EXPIRATION', 'BASE_CREATION', 'BASE_VERSION'],
    'BATTERIES': ['CAPACITY', 'CHEMISTRY', 'DATE', 'NAME', 'SERIAL', 'MANUFACTURER',
                  'VOLTAGE', 'REAL_CAPACITY'],
    'CONTROLLERS': ['CAPTION', 'DRIVER', 'NAME', 'MANUFACTURER', 'PCICLASS', 'VENDORID',
                    'SERIAL', 'MODEL', 'PRODUCTID', 'PCISUBSYSTEMID', 'PCISLOT', 'TYPE', 'REV'],
    'CPUS': ['CACHE', 'CORE', 'DESCRIPTION', 'MANUFACTURER', 'NAME', 'THREAD',
             'SERIAL', 'STEPPING', 'FAMILYNAME', 'FAMILYNUMBER', 'MODEL',
             'SPEED', 'ID', 'EXTERNAL_CLOCK', 'ARCH', 'CORECOUNT'],
    'DATABASES_SERVICES': ['TYPE', 'NAME', 'VERSION', 'MANUFACTURER', 'PORT', 'PATH', 'SIZE',
                           'IS_ACTIVE', 'IS_ONBACKUP', 'LAST_BOOT_DATE', 'LAST_BACKUP_DATE',
                           'DATABASES'],
    'DRIVES': ['CREATEDATE', 'DESCRIPTION', 'FREE', 'FILESYSTEM', 'LABEL',
               'LETTER', 'SERIAL', 'SYSTEMDRIVE', 'TOTAL', 'TYPE', 'VOLUMN',
               'ENCRYPT_NAME', 'ENCRYPT_ALGO', 'ENCRYPT_STATUS', 'ENCRYPT_TYPE'],
    'ENVS': ['KEY', 'VAL'],
    'INPUTS': ['NAME', 'MANUFACTURER', 'CAPTION', 'DESCRIPTION', 'INTERFACE',
               'LAYOUT', 'POINTINGTYPE', 'TYPE'],
    'FIREWALL': ['PROFILE', 'STATUS', 'DESCRIPTION', 'IPADDRESS', 'IPADDRESS6'],
    'LICENSEINFOS': ['NAME', 'FULLNAME', 'KEY', 'COMPONENTS', 'TRIAL', 'UPDATE', 'OEM',
                     'ACTIVATION_DATE', 'PRODUCTID'],
    'LOCAL_GROUPS': ['ID', 'MEMBER', 'NAME'],
    'LOCAL_USERS': ['HOME', 'ID', 'LOGIN', 'NAME', 'SHELL'],
    'LOGICAL_VOLUMES': ['LV_NAME', 'VG_NAME', 'ATTR', 'SIZE', 'LV_UUID', 'SEG_COUNT', 'VG_UUID'],
    'MEMORIES': ['CAPACITY', 'CAPTION', 'FORMFACTOR', 'REMOVABLE', 'PURPOSE',
                 'SPEED', 'SERIALNUMBER', 'TYPE', 'DESCRIPTION', 'NUMSLOTS',
                 'MEMORYCORRECTION', 'MANUFACTURER', 'MODEL'],
    'MODEMS': ['DESCRIPTION', 'NAME', 'TYPE', 'MODEL'],
    'MONITORS': ['BASE64', 'CAPTION', 'DESCRIPTION', 'MANUFACTURER', 'SERIAL',
                 'UUENCODE', 'NAME', 'TYPE', 'ALTSERIAL', 'PORT'],
    'NETWORKS': ['DESCRIPTION', 'MANUFACTURER', 'MODEL', 'MANAGEMENT', 'TYPE',
                 'VIRTUALDEV', 'MACADDR', 'WWN', 'DRIVER', 'FIRMWARE', 'PCIID',
                 'PCISLOT', 'PNPDEVICEID', 'MTU', 'SPEED', 'STATUS', 'SLAVES', 'BASE',
                 'IPADDRESS', 'IPSUBNET', 'IPMASK', 'IPDHCP', 'IPGATEWAY',
                 'IPADDRESS6', 'IPSUBNET6', 'IPMASK6', 'WIFI_BSSID', 'WIFI_SSID',
                 'WIFI_MODE', 'WIFI_VERSION'],
    'PHYSICAL_VOLUMES': ['DEVICE', 'PV_PE_COUNT', 'PV_UUID', 'FORMAT', 'ATTR',
                         'SIZE', 'FREE', 'PE_SIZE', 'VG_UUID'],
    'PORTS': ['CAPTION', 'DESCRIPTION', 'NAME', 'TYPE'],
    'POWERSUPPLIES': ['PARTNUM', 'SERIALNUMBER', 'MANUFACTURER', 'POWER_MAX', 'NAME',
                      'HOTREPLACEABLE', 'PLUGGED', 'STATUS', 'LOCATION', 'MODEL'],
    'PRINTERS': ['COMMENT', 'DESCRIPTION', 'DRIVER', 'NAME', 'NETWORK', 'PORT',
                 'RESOLUTION', 'SHARED', 'STATUS', 'ERRSTATUS', 'SERVERNAME',
                 'SHARENAME', 'PRINTPROCESSOR', 'SERIAL'],
    'PROCESSES': ['USER', 'PID', 'CPUUSAGE', 'MEM', 'VIRTUALMEMORY', 'TTY', 'STARTED', 'CMD'],
    'REGISTRY': ['NAME', 'REGVALUE', 'HIVE'],
    'REMOTE_MGMT': ['ID', 'TYPE'],
    'RUDDER': ['AGENT', 'UUID', 'HOSTNAME', 'SERVER_ROLES', 'AGENT_CAPABILITIES'],
    'SLOTS': ['DESCRIPTION', 'DESIGNATION', 'NAME', 'STATUS'],
    'SOFTWARES': ['COMMENTS', 'FILESIZE', 'FOLDER', 'FROM', 'HELPLINK', 'INSTALLDATE',
                  'NAME', 'NO_REMOVE', 'RELEASE_TYPE', 'PUBLISHER',
                  'UNINSTALL_STRING', 'URL_INFO_ABOUT', 'VERSION',
                  'VERSION_MINOR', 'VERSION_MAJOR', 'GUID', 'ARCH', 'USERNAME',
                  'USERID', 'SYSTEM_CATEGORY'],
    'SOUNDS': ['CAPTION', 'DESCRIPTION', 'MANUFACTURER', 'NAME'],
    'STORAGES': ['DESCRIPTION', 'DISKSIZE', 'INTERFACE', 'MANUFACTURER', 'MODEL',
                 'NAME', 'TYPE', 'SERIAL', 'SERIALNUMBER', 'FIRMWARE', 'SCSI_COID',
                 'SCSI_CHID', 'SCSI_UNID', 'SCSI_LUN', 'WWN',
                 'ENCRYPT_NAME', 'ENCRYPT_ALGO', 'ENCRYPT_STATUS', 'ENCRYPT_TYPE'],
    'VIDEOS': ['CHIPSET', 'MEMORY', 'NAME', 'RESOLUTION', 'PCISLOT', 'PCIID'],
    'USBDEVICES': ['VENDORID', 'PRODUCTID', 'MANUFACTURER', 'CAPTION', 'SERIAL',
                   'CLASS', 'SUBCLASS', 'NAME'],
    'USERS': ['LOGIN', 'DOMAIN'],
    'VIRTUALMACHINES': ['MEMORY', 'NAME', 'UUID', 'STATUS', 'SUBSYSTEM', 'VMTYPE', 'VCPU',
                        'MAC', 'COMMENT', 'OWNER', 'SERIAL', 'IMAGE', 'IPADDRESS', 'OPERATINGSYSTEM'],
    'VOLUME_GROUPS': ['VG_NAME', 'PV_COUNT', 'LV_COUNT', 'ATTR', 'SIZE', 'FREE', 'VG_UUID',
                      'VG_EXTENT_SIZE'],
    'VERSIONPROVIDER': ['NAME', 'VERSION', 'COMMENTS', 'PERL_EXE', 'PERL_VERSION', 'PERL_ARGS',
                        'PROGRAM', 'PERL_CONFIG', 'PERL_INC', 'PERL_MODULE', 'ETIME']
}

# Convert to dict of sets for fast lookup
FIELDS_SETS = {section: set(fields) for section, fields in FIELDS.items()}

# Validation checks
CHECKS = {
    'BIOS': {
        'SECURE_BOOT': re.compile(r'^(enabled|disabled|unsupported)$')
    },
    'STORAGES': {
        'STATUS': re.compile(r'^(up|down)$'),
        'INTERFACE': {
            'not_since': glpi_version('10.0.4'),
            'regexp': re.compile(r'^(SCSI|HDC|IDE|USB|1394|SATA|SAS|ATAPI)$')
        }
    },
    'VIRTUALMACHINES': {
        'STATUS': re.compile(r'^(running|blocked|idle|paused|shutdown|crashed|dying|off)$')
    },
    'SLOTS': {
        'STATUS': re.compile(r'^(free|used)$')
    },
    'NETWORKS': {
        'TYPE': re.compile(r'^(ethernet|wifi|infiniband|aggregate|alias|dialup|loopback|bridge|fibrechannel|bluetooth)$')
    },
    'CPUS': {
        'ARCH': re.compile(r'^(mips|mips64|alpha|sparc|sparc64|m68k|i386|x86_64|powerpc|powerpc64|arm.*|aarch64)$')
    }
}

# Category to section mapping
CATEGORY_MAP = {
    'os': ['OPERATINGSYSTEM'],
    'battery': ['BATTERIES'],
    'controller': ['CONTROLLERS'],
    'cpu': ['CPUS'],
    'database': ['DATABASES_SERVICES'],
    'drive': ['DRIVES'],
    'environment': ['ENVS'],
    'input': ['INPUTS'],
    'licenseinfo': ['LICENSEINFOS'],
    'local_group': ['LOCAL_GROUPS'],
    'local_user': ['LOCAL_USERS'],
    'lvm': ['LOGICAL_VOLUMES', 'PHYSICAL_VOLUMES', 'VOLUME_GROUPS'],
    'memory': ['MEMORIES'],
    'modem': ['MODEMS'],
    'monitor': ['MONITORS'],
    'network': ['NETWORKS'],
    'port': ['PORTS'],
    'psu': ['POWERSUPPLIES'],
    'printer': ['PRINTERS'],
    'process': ['PROCESSES'],
    'slot': ['SLOTS'],
    'software': ['SOFTWARES', 'OPERATINGSYSTEM'],
    'sound': ['SOUNDS'],
    'storage': ['STORAGES'],
    'video': ['VIDEOS'],
    'usb': ['USBDEVICES'],
    'user': ['USERS'],
    'virtualmachine': ['VIRTUALMACHINES'],
    'provider': ['VERSIONPROVIDER'],
}

# Sections to always keep
ALWAYS_KEEP_SECTIONS = {'BIOS', 'HARDWARE'}
DONT_CHECK_SECTIONS = {'ACCESSLOG', 'VERSIONPROVIDER'}
CHECKED_SECTIONS = sorted([s for s in FIELDS.keys() if s not in DONT_CHECK_SECTIONS])


class Inventory:
    """
    Inventory data structure for GLPI Agent.
    
    Stores and manages hardware/software inventory information,
    handles validation, checksums, and serialization to various formats.
    """
    
    def __init__(self, **params: Any):
        """
        Initialize inventory.
        
        Args:
            **params: Parameters including:
                - deviceid: Device identifier
                - datadir: Data directory path
                - statedir: State directory path
                - logger: Logger instance
                - glpi: GLPI version string
                - required: List of required categories
                - itemtype: Item type (default: "Computer")
                - tag: Inventory tag
        """
        self.deviceid: Optional[str] = params.get('deviceid')
        self.datadir: Optional[str] = params.get('datadir')
        self.statedir: str = params.get('statedir', '')
        self.logger: Logger = params.get('logger', Logger())
        self.fields: Dict[str, set] = FIELDS_SETS
        self._format: str = ''
        self._glpi_version: int = glpi_version('v10')
        self._required: List[str] = params.get('required', [])
        self._itemtype: str = "Computer" if empty(params.get('itemtype')) else params['itemtype']
        self._remote: str = ''
        self._full: bool = False
        self._partial: bool = False
        self._credentials: Optional[List[Dict]] = None
        self._json_merge: Optional[Any] = None
        self.last_state_file: Optional[str] = None
        self.last_state_content: Optional[Any] = None
        
        # Initialize content
        agent_string = AGENT_STRING or f"{PROVIDER}-Inventory_v{VERSION}"
        self.content: Dict[str, Any] = {
            'HARDWARE': {
                'VMSYSTEM': 'Physical'  # Default value
            },
            'VERSIONCLIENT': agent_string
        }
        
        if params.get('glpi'):
            self._glpi_version = glpi_version(params['glpi'])
        
        if params.get('tag'):
            self.setTag(params['tag'])
        
        if self.statedir:
            self.last_state_file = os.path.join(self.statedir, 'last_state.json')
    
    def getRemote(self) -> str:
        """Get remote task status."""
        return self._remote or ''
    
    def setRemote(self, task: Optional[str] = None) -> str:
        """Set remote task status."""
        self._remote = task or ''
        return self._remote
    
    def getFormat(self) -> str:
        """Get output format."""
        return self._format
    
    def setFormat(self, format_type: Optional[str] = None) -> None:
        """Set output format (json, xml, html)."""
        self._format = format_type or 'json'
    
    def isFull(self, full: Optional[bool] = None) -> bool:
        """Get or set full inventory flag."""
        if full is not None:
            self._full = full
        return self._full
    
    def isPartial(self, partial: Optional[bool] = None) -> bool:
        """Get or set partial inventory flag."""
        if partial is not None:
            self._partial = partial
        return self._partial
    
    def getDeviceId(self) -> str:
        """
        Get device identifier.
        
        Returns:
            Device ID string
        """
        if self.deviceid:
            return self.deviceid
        
        # Compute unique identifier
        hostname = self.content.get('HARDWARE', {}).get('NAME')
        
        if hostname:
            workgroup = self.content.get('HARDWARE', {}).get('WORKGROUP')
            if workgroup:
                hostname = f"{hostname}.{workgroup}"
        else:
            try:
                import socket
                hostname = socket.gethostname()
            except Exception:
                hostname = f'device-by-{PROVIDER.lower()}-agent'
        
        if not hostname:
            hostname = f'device-by-{PROVIDER.lower()}-agent'
        
        # Create timestamp-based ID
        now = time.localtime()
        self.deviceid = (
            f"{hostname}-{now.tm_year:04d}-{now.tm_mon:02d}-{now.tm_mday:02d}-"
            f"{now.tm_hour:02d}-{now.tm_min:02d}-{now.tm_sec:02d}"
        )
        
        return self.deviceid
    
    def getFields(self) -> Dict[str, set]:
        """Get field definitions."""
        return self.fields
    
    def getContent(self, **params: Any) -> Any:
        """
        Get inventory content in specified format.
        
        Args:
            **params: Parameters including server_version
            
        Returns:
            Formatted content object
        """
        if self._format == 'json':
            content = ProtocolInventory(
                logger=self.logger,
                deviceid=self.getDeviceId(),
                content=self.content,
                partial=self.isPartial(),
                itemtype=self._itemtype
            )
            
            # Merge additional JSON content
            if self._json_merge:
                content.mergeContent(content=self._json_merge)
                self._json_merge = None
            
            # Normalize content
            content.normalize(params.get('server_version'))
            
            return content
        
        elif self._format == 'xml':
            # Fix for deprecated XML format
            if (self.content.get('VERSIONPROVIDER') and 
                'ETIME' in self.content['VERSIONPROVIDER']):
                if 'HARDWARE' not in self.content:
                    self.content['HARDWARE'] = {}
                self.content['HARDWARE']['ETIME'] = self.content['VERSIONPROVIDER'].pop('ETIME')
        
        return self.content
    
    def getSection(self, section: str) -> Optional[Any]:
        """
        Get specific inventory section.
        
        Args:
            section: Section name
            
        Returns:
            Section content or None
        """
        return self.content.get(section)
    
    def getField(self, section: str, field: str) -> Optional[Any]:
        """
        Get specific field from section.
        
        Args:
            section: Section name
            field: Field name
            
        Returns:
            Field value or None
        """
        sect = self.getSection(section)
        if sect:
            return sect.get(field)
        return None
    
    def mergeContent(self, content: Dict) -> None:
        """
        Merge content into inventory.
        
        Args:
            content: Content dictionary to merge
        """
        if not content:
            raise ValueError("no content to merge")
        
        if self.getFormat() == 'json':
            self._json_merge = content
            return
        
        for section, data in content.items():
            if isinstance(data, list):
                # List of entries
                for entry in data:
                    self.addEntry(section=section, entry=entry)
            else:
                # Single entry
                if section == 'HARDWARE':
                    self.setHardware(data)
                elif section == 'OPERATINGSYSTEM':
                    self.setOperatingSystem(data)
                elif section == 'BIOS':
                    self.setBios(data)
                elif section == 'ACCESSLOG':
                    self.setAccessLog(data)
                else:
                    self.addEntry(section=section, entry=data)
    
    def addEntry(self, section: str, entry: Dict) -> None:
        """
        Add entry to inventory section.
        
        Args:
            section: Section name
            entry: Entry dictionary
        """
        if not entry:
            raise ValueError("no entry")
        
        if section not in FIELDS_SETS:
            raise ValueError(f"unknown section {section}")
        
        fields = FIELDS_SETS[section]
        checks = CHECKS.get(section, {})
        
        # Validate and sanitize fields
        for field in list(entry.keys()):
            if field not in fields:
                self.logger.debug(f"unknown field {field} for section {section}")
                del entry[field]
                continue
            
            if entry[field] is None:
                del entry[field]
                continue
            
            # Sanitize value
            value = get_sanitized_string(str(entry[field]))
            
            # Check value if applicable
            check = checks.get(field)
            if isinstance(check, dict):
                if (check.get('regexp') and check.get('not_since') and
                    check['not_since'] > self._glpi_version):
                    if not check['regexp'].match(value):
                        self.logger.debug(
                            f"invalid value {value} for field {field} for section {section}"
                        )
            elif check:
                if not check.match(value):
                    self.logger.debug(
                        f"invalid value {value} for field {field} for section {section}"
                    )
            
            entry[field] = value
        
        # Special handling for STORAGES
        if section == 'STORAGES' and not entry.get('SERIALNUMBER'):
            entry['SERIALNUMBER'] = entry.get('SERIAL', '')
        
        # Add to content
        if section not in self.content:
            self.content[section] = []
        self.content[section].append(entry)
    
    def setEntry(self, section: str, entry: Dict) -> None:
        """Set single entry (replacing existing)."""
        self.addEntry(section=section, entry=entry)
        if section in self.content and isinstance(self.content[section], list):
            self.content[section] = self.content[section][0]
    
    def getHardware(self, field: Optional[str] = None) -> Optional[Any]:
        """Get hardware field value."""
        return self.getField('HARDWARE', field) if field else self.getSection('HARDWARE')
    
    def setHardware(self, args: Dict) -> None:
        """Set hardware information."""
        if 'HARDWARE' not in self.content:
            self.content['HARDWARE'] = {}
        
        for field, value in args.items():
            if field not in FIELDS_SETS['HARDWARE']:
                self.logger.debug(f"unknown field {field} for section HARDWARE")
                continue
            
            # Don't overwrite with empty values
            if value is None or (isinstance(value, str) and not value):
                continue
            
            self.content['HARDWARE'][field] = get_sanitized_string(str(value))
    
    def setOperatingSystem(self, args: Dict) -> None:
        """Set operating system information."""
        if 'OPERATINGSYSTEM' not in self.content:
            self.content['OPERATINGSYSTEM'] = {}
        
        for field, value in args.items():
            if field not in FIELDS_SETS['OPERATINGSYSTEM']:
                self.logger.debug(f"unknown field {field} for section OPERATINGSYSTEM")
                continue
            
            self.content['OPERATINGSYSTEM'][field] = get_sanitized_string(str(value))
    
    def getBios(self, field: Optional[str] = None) -> Optional[Any]:
        """Get BIOS field value."""
        return self.getField('BIOS', field) if field else self.getSection('BIOS')
    
    def setBios(self, args: Dict) -> None:
        """Set BIOS information."""
        if 'BIOS' not in self.content:
            self.content['BIOS'] = {}
        
        for field, value in args.items():
            if field not in FIELDS_SETS['BIOS']:
                self.logger.debug(f"unknown field {field} for section BIOS")
                continue
            
            self.content['BIOS'][field] = get_sanitized_string(str(value))
    
    def setAccessLog(self, args: Dict) -> None:
        """Set access log information."""
        if 'ACCESSLOG' not in self.content:
            self.content['ACCESSLOG'] = {}
        
        for field, value in args.items():
            if field not in FIELDS_SETS['ACCESSLOG']:
                self.logger.debug(f"unknown field {field} for section ACCESSLOG")
                continue
            
            self.content['ACCESSLOG'][field] = get_sanitized_string(str(value))
    
    def setTag(self, tag: str) -> None:
        """Set inventory tag."""
        if not tag:
            return
        
        self.content['ACCOUNTINFO'] = [{
            'KEYNAME': 'TAG',
            'KEYVALUE': tag
        }]
    
    def _checksum(self, key: str, ref: Any, sha: Optional[Any] = None, 
                  length: int = 0) -> Tuple[Any, int]:
        """
        Compute checksum of data structure.
        
        Args:
            key: Key name
            ref: Reference to data
            sha: SHA hasher object
            length: Current length
            
        Returns:
            Tuple of (hasher, length)
        """
        if sha is None:
            sha = hashlib.sha256()
        
        if isinstance(ref, dict):
            for subkey in sorted(ref.keys()):
                sha, length = self._checksum(subkey, ref[subkey], sha, length)
        elif isinstance(ref, list):
            for item in ref:
                sha, length = self._checksum(key, item, sha, length)
        elif ref is not None:
            string = f"{key}:{ref}."
            sha.update(string.encode('utf-8'))
            length += len(string)
        
        return sha, length
    
    def computeChecksum(self, postpone_config: int = 0) -> None:
        """
        Compute inventory checksum and handle partial inventory logic.
        
        Args:
            postpone_config: Number of inventories to postpone between full inventories
        """
        logger = self.logger
        
        # Use alternate state file for remote inventory
        if self.getRemote() and self.statedir:
            remoteid = (
                self.getHardware('UUID') or self.getBios('SSN') or
                self.getBios('MSN') or self.getDeviceId()
            )
            self.last_state_file = os.path.join(
                self.statedir, f'last_remote_state-{remoteid}.json'
            )
        
        # Load last state
        last_state = None
        if self.last_state_file and not self.last_state_content:
            if os.path.isfile(self.last_state_file):
                try:
                    last_state = ProtocolMessage(file=self.last_state_file)
                except Exception:
                    self.last_state_content = {}
            else:
                logger.debug(f"last state file '{self.last_state_file}' doesn't exist")
        else:
            last_state = self.last_state_content
        
        if not last_state:
            last_state = ProtocolMessage()
        
        # Handle postpone logic
        postpone = 0
        current_count = last_state.get('_postpone_count', '0')
        
        # Reset count if partial not forced
        if int(current_count) > postpone_config and not self.isPartial():
            current_count = postpone_config
        
        if postpone_config:
            current = int(current_count) if str(current_count).isdigit() else 0
            postpone = (current + 1) % (postpone_config + 1)
        
        # Reset if partial forced after full should have been sent
        if self.isPartial() and int(current_count) >= postpone_config:
            postpone = int(current_count) + 1
        
        # Disable postpone if not JSON
        if self.getFormat() != 'json':
            postpone = 0
        
        # Handle required categories
        keep_section = {}
        if postpone and self._required:
            for category in self._required:
                if category in CATEGORY_MAP:
                    for sect in CATEGORY_MAP[category]:
                        keep_section[sect] = True
                else:
                    keep_section[category.upper()] = True
        
        # Check sections for changes
        delete_sections = []
        keep_os = False
        
        for section in CHECKED_SECTIONS:
            sha, length = self._checksum(section, self.content.get(section))
            state = last_state.get(section)
            
            if not length:
                if state:
                    logger.debug(f"Section {section} has disappeared since last inventory")
                    last_state.delete(section)
                    postpone = 0
                continue
            
            digest = sha.hexdigest()
            
            # Check if changed
            if (isinstance(state, dict) and
                state.get('len') == length and
                state.get('digest') == digest):
                # Consider for removal if postponing
                if postpone and section not in ALWAYS_KEEP_SECTIONS and section not in keep_section:
                    delete_sections.append(section)
                continue
            
            # Mark to keep OS if software changed
            if section == 'SOFTWARES':
                keep_os = True
            
            logger.debug(f"Section {section} has changed since last inventory")
            
            # Store new value
            last_state.merge({
                section: {
                    'digest': digest,
                    'len': length
                }
            })
        
        # Reset postpone if full inventory forced
        if postpone and self.isFull():
            postpone = 0
        
        # Remove sections if postponing
        if postpone and delete_sections:
            for section in delete_sections:
                # Keep OS if software category needs it
                if section == 'OPERATINGSYSTEM' and keep_os:
                    continue
                
                if section in self.content:
                    del self.content[section]
                
                # Clean HARDWARE section for USERS category
                if section == 'USERS' and 'HARDWARE' in self.content:
                    self.content['HARDWARE'].pop('LASTLOGGEDUSER', None)
                    self.content['HARDWARE'].pop('DATELASTLOGGEDUSER', None)
            
            self.isPartial(True)
        
        status = "postponed" if (postpone_config and self.isPartial()) else "kept"
        if postpone_config and self.isPartial():
            logger.debug(f"Full inventory postponed: {postpone}/{postpone_config}")
        else:
            logger.debug(f"Full inventory {status}")
        
        if postpone_config:
            last_state.merge({'_postpone_count': postpone})
        
        self.last_state_content = last_state
        self._saveLastState()
    
    def _saveLastState(self) -> None:
        """Save last state to file."""
        if not self.last_state_content:
            return
        
        logger = self.logger
        
        if self.last_state_file:
            try:
                with open(self.last_state_file, 'w') as f:
                    f.write(self.last_state_content.getRawContent())
            except IOError as e:
                logger.debug(f"can't create last state file, last state not saved: {e}")
        else:
            logger.debug("last state file is not defined, last state not saved")
        
        # Cleanup old remote state files
        if self.getRemote():
            self.canCleanupOldRemoteStateFile()
    
    _remote_state_file_timeout: Optional[int] = None
    _remote_state_file_count: int = 0
    
    def canCleanupOldRemoteStateFile(self) -> int:
        """
        Cleanup old remote state files.
        
        Returns:
            Number of remaining remote state files
        """
        # Don't cleanup more than once per hour
        if (self._remote_state_file_timeout and 
            time.time() < self._remote_state_file_timeout):
            return self._remote_state_file_count
        
        self._remote_state_file_timeout = int(time.time()) + 3600
        
        logger = self.logger
        
        # Expire files older than 30 days
        max_age = time.time() - 30 * 86400
        self._remote_state_file_count = 0
        
        pattern = os.path.join(self.statedir, "last_remote_state-*.json")
        for file_path in file_glob.glob(pattern):
            try:
                mtime = os.path.getmtime(file_path)
                
                if mtime > max_age:
                    self._remote_state_file_count += 1
                    continue
                
                os.unlink(file_path)
                logger.debug(f"deleted old remote state file: {file_path}")
            except Exception:
                pass
        
        return self._remote_state_file_count
    
    def credentials(self, credentials: Optional[List[str]] = None) -> Optional[List[Dict]]:
        """
        Get or set credentials.
        
        Args:
            credentials: List of credential definition strings
            
        Returns:
            Parsed credentials list
        """
        if credentials is None:
            return self._credentials
        
        self._credentials = []
        index = 0
        
        for definition in credentials:
            parsed = {}
            remaining = definition
            
            while remaining:
                # Extract key
                match = re.match(r'^(\w+):(.*)', remaining)
                if not match:
                    break
                
                key = match.group(1)
                remaining = match.group(2)
                
                if not remaining:
                    break
                
                # Extract value (quoted or unquoted)
                if remaining[0] in ('"', "'"):
                    quote = remaining[0]
                    # Handle escaped quotes
                    temp_marker = ',' * ord(quote)
                    remaining = remaining.replace(f'\\{quote}', f'\\{temp_marker}')
                    
                    match = re.match(rf'^[{quote}]([^{quote}]+)[{quote}](.*)', remaining)
                    if match:
                        value = match.group(1).replace(f'\\{temp_marker}', quote)
                        remaining = match.group(2).replace(f'\\{temp_marker}', f'\\{quote}')
                    else:
                        break
                else:
                    match = re.match(r'^([^,]+)(.*)', remaining)
                    if match:
                        value = match.group(1)
                        remaining = match.group(2)
                    else:
                        break
                
                parsed[key] = value
                
                # Check for comma separator
                if remaining:
                    if not remaining.startswith(','):
                        parsed = {}
                        break
                    remaining = remaining.lstrip(',')
            
            if not parsed:
                self.logger.debug(f"Invalid credential definition: {definition}")
                continue
            
            if 'params_id' not in parsed:
                parsed['params_id'] = index
            
            index += 1
            self._credentials.append(parsed)
        
        return self._credentials
    
    def save(self, path: str) -> Optional[str]:
        """
        Save inventory to file.
        
        Args:
            path: File path or directory (- for stdout)
            
        Returns:
            Saved file path or None
        """
        format_type = self.getFormat()
        
        if format_type not in ('json', 'xml', 'html'):
            if format_type:
                self.logger.error(f"Unsupported inventory format {format_type}, fallback on json")
            else:
                self.logger.info("Using json as default format")
            format_type = 'json'
        
        # Determine output handle
        if path == '-':
            handle = sys.stdout
            file_path = path
        elif os.path.isdir(path) or not os.path.exists(path):
            # Create directory if it doesn't exist
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
            file_path = os.path.join(path, f"{self.getDeviceId()}.{format_type}")
        else:
            file_path = path
        
        # Open file if not stdout
        if path != '-':
            try:
                handle = open(file_path, 'w', encoding='utf-8')
            except IOError as e:
                self.logger.error(f"Can't write to {file_path}: {e}")
                return None
        else:
            handle = sys.stdout
        
        try:
            if format_type == 'json':
                content = self.getContent()
                handle.write(content.getContent())
            
            elif format_type == 'xml':
                xml = XMLHandler()
                output = xml.write({
                    'REQUEST': {
                        'CONTENT': self.getContent(),
                        'DEVICEID': self.getDeviceId(),
                        'QUERY': 'INVENTORY'
                    }
                })
                handle.write(output)
            
            elif format_type == 'html':
                try:
                    from jinja2 import Template
                    
                    template_path = os.path.join(self.datadir, 'html/inventory.tpl')
                    with open(template_path) as f:
                        template = Template(f.read())
                    
                    output = template.render(
                        version=VERSION,
                        deviceid=self.getDeviceId(),
                        data=self.getContent(),
                        fields=self.getFields()
                    )
                    handle.write(output)
                except Exception as e:
                    self.logger.error(f"Can't generate HTML: {e}")
                    return None
            
        finally:
            if handle != sys.stdout:
                handle.close()
        
        return file_path


if __name__ == "__main__":
    # Basic test
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory = Inventory(
            statedir=tmpdir,
            deviceid="test-device-001",
            datadir="."
        )
        
        print(f"Device ID: {inventory.getDeviceId()}")
        print(f"Format: {inventory.getFormat()}")
        
        # Set some hardware info
        inventory.setHardware({
            'NAME': 'test-computer',
            'MEMORY': 8192,
            'UUID': 'test-uuid-123'
        })
        
        # Add a CPU entry
        inventory.addEntry(
            section='CPUS',
            entry={
                'NAME': 'Intel Core i7',
                'SPEED': 2400,
                'CORE': 4
            }
        )
        
        print(f"Hardware: {inventory.getHardware()}")
        print(f"CPU Count: {len(inventory.getSection('CPUS') or [])}")