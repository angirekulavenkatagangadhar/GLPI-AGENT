# glpi_agent/task/inventory/win32/slots.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Slots(InventoryModule):
    """Windows Slots inventory module."""
    
    STATUS_MAP = {
        3: 'free',
        4: 'used'
    }
    
    @staticmethod
    def category():
        return "slot"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        logger = params.get('logger')
        
        for obj in get_wmi_objects(
            class_name='Win32_SystemSlot',
            properties=['Name', 'Description', 'SlotDesignation', 'CurrentUsage']
        ):
            current_usage = obj.get('CurrentUsage')
            if current_usage is None:
                if logger and obj.get('Name'):
                    logger.debug2(f"ignoring usage-less '{obj['Name']}' slot")
                continue
            
            inventory.add_entry(
                section='SLOTS',
                entry={
                    'NAME': obj.get('Name'),
                    'DESCRIPTION': obj.get('Description'),
                    'DESIGNATION': obj.get('SlotDesignation'),
                    'STATUS': self.STATUS_MAP.get(current_usage)
                }
            )