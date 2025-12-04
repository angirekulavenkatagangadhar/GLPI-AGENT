# glpi_agent/task/inventory/win32/modems.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Modems(InventoryModule):
    """Windows Modems inventory module."""
    
    @staticmethod
    def category():
        return "modem"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        for obj in get_wmi_objects(
            class_name='Win32_POTSModem',
            properties=['Name', 'DeviceType', 'Model', 'Description']
        ):
            inventory.add_entry(
                section='MODEMS',
                entry={
                    'NAME': obj.get('Name'),
                    'TYPE': obj.get('DeviceType'),
                    'MODEL': obj.get('Model'),
                    'DESCRIPTION': obj.get('Description'),
                }
            )