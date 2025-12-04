# glpi_agent/task/inventory/win32/sounds.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Sounds(InventoryModule):
    """Windows Sounds inventory module."""
    
    @staticmethod
    def category():
        return "sound"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        for obj in get_wmi_objects(
            class_name='Win32_SoundDevice',
            properties=['Name', 'Manufacturer', 'Caption', 'Description']
        ):
            inventory.add_entry(
                section='SOUNDS',
                entry={
                    'NAME': obj.get('Name'),
                    'CAPTION': obj.get('Caption'),
                    'MANUFACTURER': obj.get('Manufacturer'),
                    'DESCRIPTION': obj.get('Description'),
                }
            )