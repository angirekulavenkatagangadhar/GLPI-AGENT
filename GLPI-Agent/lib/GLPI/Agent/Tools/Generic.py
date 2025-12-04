#!/usr/bin/env python3
"""
GLPI Agent Tools Generic - Python Implementation

Generic OS-independent utility functions for hardware inventory.

This module provides core utility functions that work across all platforms.
"""

import re
import subprocess
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

try:
    from GLPI.Agent.Tools import (get_all_lines, get_first_match, trim_whitespace,
                                   get_canonical_manufacturer, get_canonical_speed,
                                   get_canonical_size)
    from GLPI.Agent.Tools.Network import get_canon_mac_address
except ImportError:
    # Stub implementations
    def get_all_lines(**params):
        return []
    def get_first_match(**params):
        return None
    def trim_whitespace(s):
        return s.strip() if s else s
    def get_canonical_manufacturer(s):
        return s
    def get_canonical_speed(s):
        return s
    def get_canonical_size(s):
        return s
    def get_canon_mac_address(s):
        return s


__all__ = [
    'get_dmidecode_infos',
    'get_cpu_info',
    'get_hardware_addresses',
    'get_infos_from_dmidecode',
    'parse_dmidecode_memory_bank',
    'parse_lspci',
    'get_pci_devices',
    'get_edid_info',
    'get_hdparm_info'
]


def get_dmidecode_infos(**params) -> Dict[str, List[Dict]]:
    """
    Get hardware information from dmidecode output.
    
    Args:
        **params: Parameters including command, file, logger
        
    Returns:
        Dictionary mapping hardware types to lists of devices
    """
    if 'command' not in params:
        params['command'] = 'dmidecode'
    
    lines = get_all_lines(**params)
    if not lines:
        return {}
    
    infos = {}
    current_section = None
    current_item = {}
    
    for line in lines:
        # New section starts
        if re.match(r'^Handle ', line):
            if current_section and current_item:
                if current_section not in infos:
                    infos[current_section] = []
                infos[current_section].append(current_item)
            current_item = {}
            current_section = None
            continue
        
        # Section type
        if line and not line.startswith('\t'):
            current_section = line.strip()
            continue
        
        # Property line
        if line.startswith('\t') and ':' in line:
            key, value = line.split(':', 1)
            current_item[key.strip()] = value.strip()
    
    # Add last item
    if current_section and current_item:
        if current_section not in infos:
            infos[current_section] = []
        infos[current_section].append(current_item)
    
    return infos


def get_cpu_info(**params) -> List[Dict]:
    """
    Get CPU information from dmidecode.
    
    Args:
        **params: Parameters including logger
        
    Returns:
        List of CPU dictionaries
    """
    infos = get_dmidecode_infos(**params)
    processors = infos.get('Processor Information', [])
    
    cpus = []
    for proc in processors:
        cpu = {
            'NAME': proc.get('Version', ''),
            'MANUFACTURER': proc.get('Manufacturer', ''),
            'SPEED': proc.get('Current Speed', ''),
            'SERIAL': proc.get('Serial Number', ''),
            'CORE': proc.get('Core Count', '')
        }
        cpus.append(cpu)
    
    return cpus


def get_hardware_addresses(**params) -> List[str]:
    """
    Get all hardware MAC addresses from the system.
    
    Args:
        **params: Parameters including logger
        
    Returns:
        List of MAC addresses
    """
    addresses = []
    
    # This would need platform-specific implementation
    # Stub for now
    
    return addresses


def get_infos_from_dmidecode(**params) -> Dict:
    """
    Get structured information from dmidecode.
    
    Args:
        **params: Parameters including logger
        
    Returns:
        Dictionary with BIOS, System, and other information
    """
    infos = get_dmidecode_infos(**params)
    
    result = {
        'BIOS': {},
        'SYSTEM': {},
        'BASEBOARD': {},
        'CHASSIS': {}
    }
    
    # Extract BIOS information
    if 'BIOS Information' in infos and infos['BIOS Information']:
        bios = infos['BIOS Information'][0]
        result['BIOS'] = {
            'BMANUFACTURER': bios.get('Vendor', ''),
            'BVERSION': bios.get('Version', ''),
            'BDATE': bios.get('Release Date', '')
        }
    
    # Extract System information
    if 'System Information' in infos and infos['System Information']:
        system = infos['System Information'][0]
        result['SYSTEM'] = {
            'MANUFACTURER': system.get('Manufacturer', ''),
            'PRODUCTNAME': system.get('Product Name', ''),
            'SERIAL': system.get('Serial Number', ''),
            'UUID': system.get('UUID', '')
        }
    
    return result


def parse_dmidecode_memory_bank(bank: Dict) -> Optional[Dict]:
    """
    Parse a dmidecode memory bank entry.
    
    Args:
        bank: Raw memory bank dictionary from dmidecode
        
    Returns:
        Parsed memory information or None
    """
    if not bank:
        return None
    
    memory = {
        'CAPACITY': bank.get('Size', ''),
        'DESCRIPTION': bank.get('Form Factor', ''),
        'CAPTION': bank.get('Locator', ''),
        'SPEED': bank.get('Speed', ''),
        'TYPE': bank.get('Type', ''),
        'SERIALNUMBER': bank.get('Serial Number', ''),
        'MANUFACTURER': bank.get('Manufacturer', '')
    }
    
    # Parse capacity to MB
    capacity_str = memory['CAPACITY']
    if capacity_str:
        match = re.match(r'(\d+)\s*([GMK]B)', capacity_str, re.I)
        if match:
            value, unit = match.groups()
            value = int(value)
            if unit.upper() == 'GB':
                memory['CAPACITY'] = value * 1024
            elif unit.upper() == 'KB':
                memory['CAPACITY'] = value // 1024
            else:
                memory['CAPACITY'] = value
    
    return memory


def parse_lspci(**params) -> List[Dict]:
    """
    Parse lspci output for PCI devices.
    
    Args:
        **params: Parameters including command, file, logger
        
    Returns:
        List of PCI device dictionaries
    """
    if 'command' not in params:
        params['command'] = 'lspci -vvv -nn'
    
    lines = get_all_lines(**params)
    if not lines:
        return []
    
    devices = []
    current_device = None
    
    for line in lines:
        # New device starts
        if line and not line.startswith('\t'):
            if current_device:
                devices.append(current_device)
            
            current_device = {}
            # Parse device line
            # Format: 00:00.0 Host bridge [0600]: Intel Corporation ...
            match = re.match(r'([\da-f:.]+)\s+([^[]+)(?:\[([^\]]+)\])?\s*:\s*(.+)', line, re.I)
            if match:
                current_device['PCISLOT'] = match.group(1)
                current_device['TYPE'] = match.group(2).strip()
                current_device['NAME'] = match.group(4).strip()
        
        elif current_device and line.startswith('\t'):
            # Parse device properties
            if 'Subsystem:' in line:
                match = re.search(r'Subsystem:\s*(.+)', line)
                if match:
                    current_device['SUBSYSTEM'] = match.group(1).strip()
    
    if current_device:
        devices.append(current_device)
    
    return devices


def get_pci_devices(**params) -> List[Dict]:
    """
    Get PCI devices information.
    
    Args:
        **params: Parameters including logger
        
    Returns:
        List of PCI device dictionaries
    """
    return parse_lspci(**params)


def get_edid_info(**params) -> Optional[Dict]:
    """
    Get EDID information for displays.
    
    Args:
        **params: Parameters including edid binary data or file
        
    Returns:
        Dictionary with display information or None
    """
    edid_data = params.get('edid')
    if not edid_data:
        return None
    
    # Parse EDID binary data
    # This requires binary parsing of EDID structure
    # Stub for now
    
    return {}


def get_hdparm_info(**params) -> Optional[Dict]:
    """
    Get hard drive information from hdparm.
    
    Args:
        **params: Parameters including device path
        
    Returns:
        Dictionary with drive information or None
    """
    device = params.get('device')
    if not device:
        return None
    
    params['command'] = f'hdparm -I {device}'
    lines = get_all_lines(**params)
    if not lines:
        return None
    
    info = {}
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            info[key.strip()] = value.strip()
    
    return info


def get_cpus_from_dmidecode(**params) -> List[Dict]:
    """
    Get CPU information from dmidecode.
    Wrapper around get_dmidecode_infos that extracts CPU data.
    
    Returns:
        List of CPU dictionaries
    """
    infos = get_dmidecode_infos(**params)
    cpus = []
    
    if 'Processor Information' in infos:
        for proc in infos['Processor Information']:
            cpu = {}
            if proc.get('Manufacturer'):
                cpu['MANUFACTURER'] = proc['Manufacturer']
            if proc.get('Version'):
                cpu['NAME'] = proc['Version']
            if proc.get('Max Speed'):
                cpu['SPEED'] = proc['Max Speed']
            if proc.get('Core Count'):
                cpu['CORE'] = proc['Core Count']
            if proc.get('Thread Count'):
                cpu['THREAD'] = proc['Thread Count']
            cpus.append(cpu)
    
    return cpus


def get_canonical_manufacturer(manufacturer: str) -> str:
    """
    Get canonical manufacturer name.
    
    Args:
        manufacturer: Raw manufacturer string
        
    Returns:
        Canonical manufacturer name
    """
    if not manufacturer:
        return ''
    
    # Simple canonicalization - can be expanded
    m = manufacturer.upper().strip()
    if 'INTEL' in m:
        return 'Intel'
    elif 'AMD' in m:
        return 'AMD'
    elif 'QUALCOMM' in m or 'SNAPDRAGON' in m:
        return 'Qualcomm'
    else:
        return manufacturer.strip()


if __name__ == '__main__':
    print("GLPI Agent Tools Generic Module")
    print("Generic OS-independent utility functions")
