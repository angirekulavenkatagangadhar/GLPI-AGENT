# glpi_agent/task/inventory/win32/cpu.py

import os
import re

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import trim_whitespace, any_func as any
from GLPI.Agent.Tools.Win32 import get_wmi_objects, get_registry_key
from GLPI.Agent.Tools.Generic import get_cpus_from_dmidecode, get_canonical_manufacturer


class CPU(InventoryModule):
    """Windows CPU inventory module."""
    
    @staticmethod
    def category():
        return "cpu"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        cpus = self._get_cpus(**params)
        
        for cpu in cpus:
            inventory.add_entry(
                section='CPUS',
                entry=cpu
            )
        
        if any(cpu.get('NAME') and 'QEMU' in cpu['NAME'].upper() for cpu in cpus):
            inventory.set_hardware({'VMSYSTEM': 'QEMU'})
    
    def _get_cpus(self, **params):
        inventory = params.get('inventory')
        remote = inventory.get_remote() if inventory else None
        
        # Check if running on Win2003
        try:
            import platform
            is_win2003 = 'Win2003' in platform.platform()
        except:
            is_win2003 = False
        
        # Get dmidecode info if available
        dmidecode_infos = []
        if not remote and not is_win2003:
            dmidecode_infos = get_cpus_from_dmidecode()
        
        # Get CPU info from registry
        registry_infos = get_registry_key(
            path="HKEY_LOCAL_MACHINE/Hardware/Description/System/CentralProcessor",
            required=['Identifier', 'ProcessorNameString', 'VendorIdentifier']
        )
        
        cpu_id = 0
        logical_id = 0
        cpus = []
        
        for obj in get_wmi_objects(
            class_name='Win32_Processor',
            properties=[
                'NumberOfCores', 'NumberOfLogicalProcessors', 'ProcessorId',
                'MaxClockSpeed', 'SerialNumber', 'Name', 'Description', 'Manufacturer'
            ]
        ):
            dmidecode_info = dmidecode_infos[cpu_id] if cpu_id < len(dmidecode_infos) else {}
            registry_info = registry_infos.get(f"{logical_id}/", {}) if registry_infos else {}
            
            # Compute WMI threads for this CPU if not available in dmidecode
            wmi_threads = None
            if (not dmidecode_info.get('THREAD') and 
                obj.get('NumberOfCores') and 
                obj.get('NumberOfLogicalProcessors')):
                wmi_threads = obj['NumberOfLogicalProcessors'] / obj['NumberOfCores']
            
            # Support case thread count is not an integer
            if wmi_threads and wmi_threads > int(wmi_threads):
                wmi_threads = int(wmi_threads) + 1
            
            # Split CPUID from its value inside registry
            identifier = registry_info.get('/Identifier') or obj.get('Description', '')
            splitted_identifier = re.split(r' |\n', identifier)
            
            # Get CPU name
            name = dmidecode_info.get('NAME')
            if not name:
                name = trim_whitespace(
                    registry_info.get('/ProcessorNameString') or obj.get('Name', '')
                )
                if name:
                    name = re.sub(r'\((R|TM)\)', '', name, flags=re.IGNORECASE)
            
            cpu = {
                'CORE': dmidecode_info.get('CORE') or obj.get('NumberOfCores'),
                'THREAD': dmidecode_info.get('THREAD') or wmi_threads,
                'DESCRIPTION': (dmidecode_info.get('DESCRIPTION') or 
                               registry_info.get('/Identifier') or 
                               obj.get('Description')),
                'NAME': name,
                'MANUFACTURER': (dmidecode_info.get('MANUFACTURER') or 
                                get_canonical_manufacturer(
                                    registry_info.get('/VendorIdentifier') or 
                                    obj.get('Manufacturer')
                                )),
                'SERIAL': dmidecode_info.get('SERIAL') or obj.get('SerialNumber'),
                'SPEED': dmidecode_info.get('SPEED') or obj.get('MaxClockSpeed'),
                'FAMILYNUMBER': (dmidecode_info.get('FAMILYNUMBER') or 
                                (splitted_identifier[2] if len(splitted_identifier) > 2 else None)),
                'MODEL': (dmidecode_info.get('MODEL') or 
                         (splitted_identifier[4] if len(splitted_identifier) > 4 else None)),
                'STEPPING': (dmidecode_info.get('STEPPING') or 
                            (splitted_identifier[6] if len(splitted_identifier) > 6 else None)),
                'ID': dmidecode_info.get('ID') or obj.get('ProcessorId')
            }
            
            # Some information are missing on Win2000
            if not cpu['NAME'] and not remote and os.environ.get('PROCESSOR_IDENTIFIER'):
                cpu['NAME'] = os.environ['PROCESSOR_IDENTIFIER']
                match = re.search(r',\s(\S+)$', cpu['NAME'])
                if match:
                    cpu['MANUFACTURER'] = match.group(1)
                    cpu['NAME'] = re.sub(r',\s\S+$', '', cpu['NAME'])
            
            if cpu.get('SERIAL'):
                cpu['SERIAL'] = cpu['SERIAL'].replace(' ', '')
            
            # Extract speed from name if not available
            if not cpu.get('SPEED') and cpu.get('NAME'):
                match = re.search(r'([\d\.]+)\s*(GHZ|MHZ)', cpu['NAME'], re.IGNORECASE)
                if match:
                    speed_value = float(match.group(1))
                    unit = match.group(2).lower()
                    multiplier = 1000 if unit == 'ghz' else 1
                    cpu['SPEED'] = multiplier * speed_value
            
            # Support CORECOUNT total available cores
            if dmidecode_info.get('CORECOUNT'):
                cpu['CORECOUNT'] = dmidecode_info['CORECOUNT']
            
            cpus.append(cpu)
            
            cpu_id += 1
            num_logical = obj.get('NumberOfLogicalProcessors', 1)
            logical_id = logical_id + (num_logical if num_logical else 1)
        
        return cpus