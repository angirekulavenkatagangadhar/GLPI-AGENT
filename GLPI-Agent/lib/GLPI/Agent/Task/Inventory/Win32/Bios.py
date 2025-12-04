# glpi_agent/task/inventory/win32/bios.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import empty
from GLPI.Agent.Tools.Win32 import get_wmi_objects, get_registry_value
from GLPI.Agent.Tools.Generic import is_invalid_bios_value


class Bios(InventoryModule):
    """Windows BIOS inventory module."""
    
    @staticmethod
    def category():
        return "bios"
    
    @staticmethod
    def run_me_if_these_checks_failed():
        return ["GLPI::Agent::Task::Inventory::Generic::Dmidecode::Bios"]
    
    def is_enabled(self, **params):
        return True
    
    def _date_from_int_string(self, string):
        """Convert integer string date format to MM/DD/YYYY."""
        if not string:
            return string
        
        import re
        match = re.match(r'^(\d{4})(\d{2})(\d{2})', str(string))
        if match:
            return f"{match.group(2)}/{match.group(3)}/{match.group(1)}"
        
        return string
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        bios = {}
        
        # Get BIOS information
        for obj in get_wmi_objects(
            class_name='Win32_Bios',
            properties=[
                'SerialNumber', 'Version', 'Manufacturer', 
                'SMBIOSBIOSVersion', 'BIOSVersion', 'ReleaseDate'
            ]
        ):
            bios['BIOSSERIAL'] = obj.get('SerialNumber')
            bios['SSN'] = obj.get('SerialNumber')
            bios['BMANUFACTURER'] = obj.get('Manufacturer')
            bios['BVERSION'] = (obj.get('SMBIOSBIOSVersion') or
                               obj.get('BIOSVersion') or
                               obj.get('Version'))
            bios['BDATE'] = self._date_from_int_string(obj.get('ReleaseDate'))
        
        # Try to set Bios date from registry if not found via wmi
        if not bios.get('BDATE'):
            bios_date = get_registry_value(
                path="HKEY_LOCAL_MACHINE/Hardware/Description/System/BIOS/BIOSReleaseDate"
            )
            bios['BDATE'] = self._date_from_int_string(bios_date)
        
        # Get Computer System information
        for obj in get_wmi_objects(
            class_name='Win32_ComputerSystem',
            properties=['Manufacturer', 'Model']
        ):
            bios['SMANUFACTURER'] = obj.get('Manufacturer')
            bios['SMODEL'] = obj.get('Model')
        
        # Get System Enclosure information
        for obj in get_wmi_objects(
            class_name='Win32_SystemEnclosure',
            properties=['SerialNumber', 'SMBIOSAssetTag']
        ):
            if obj.get('SerialNumber'):
                bios['ENCLOSURESERIAL'] = obj['SerialNumber']
                if not bios.get('SSN'):
                    bios['SSN'] = obj['SerialNumber']
            
            if not empty(obj.get('SMBIOSAssetTag')):
                bios['ASSETTAG'] = obj['SMBIOSAssetTag']
        
        # Get BaseBoard information
        for obj in get_wmi_objects(
            class_name='Win32_BaseBoard',
            properties=['SerialNumber', 'Product', 'Manufacturer']
        ):
            if not empty(obj.get('SerialNumber')):
                bios['MSN'] = obj['SerialNumber']
                if not bios.get('SSN'):
                    bios['SSN'] = obj['SerialNumber']
            
            bios['MMODEL'] = obj.get('Product')
            
            if not empty(obj.get('Manufacturer')):
                bios['MMANUFACTURER'] = obj['Manufacturer']
                if not bios.get('SMANUFACTURER'):
                    bios['SMANUFACTURER'] = obj['Manufacturer']
        
        # Clean up BIOS data
        for key in list(bios.keys()):
            # Handle case we have an array of one string in place of the expected string
            if isinstance(bios[key], list):
                bios[key] = bios[key][0] if bios[key] else None
            
            # Strip trailing whitespace
            if bios[key] and isinstance(bios[key], str):
                bios[key] = bios[key].rstrip()
            
            # Remove invalid values
            if is_invalid_bios_value(bios[key]):
                del bios[key]
        
        inventory.set_bios(bios)