# glpi_agent/task/inventory/win32/chassis.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Chassis(InventoryModule):
    """Windows Chassis inventory module."""
    
    CHASSIS_TYPES = [
        'Unknown',
        'Other',
        'Unknown',
        'Desktop',
        'Low Profile Desktop',
        'Pizza Box',
        'Mini Tower',
        'Tower',
        'Portable',
        'Laptop',
        'Notebook',
        'Hand Held',
        'Docking Station',
        'All in One',
        'Sub Notebook',
        'Space-Saving',
        'Lunch Box',
        'Main System Chassis',
        'Expansion Chassis',
        'SubChassis',
        'Bus Expansion Chassis',
        'Peripheral Chassis',
        'Storage Chassis',
        'Rack Mount Chassis',
        'Sealed-Case PC'
    ]
    
    @staticmethod
    def category():
        return "hardware"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        logger = params.get('logger')
        
        inventory.set_hardware({
            'CHASSIS_TYPE': self._get_chassis(logger=logger)
        })
    
    def _get_chassis(self, **params):
        chassis = None
        
        for obj in get_wmi_objects(
            class_name='Win32_SystemEnclosure',
            properties=['ChassisTypes']
        ):
            chassis_types = obj.get('ChassisTypes')
            
            if isinstance(chassis_types, list) and len(chassis_types) > 0:
                chassis_type_idx = chassis_types[0]
                if isinstance(chassis_type_idx, int) and chassis_type_idx < len(self.CHASSIS_TYPES):
                    chassis = self.CHASSIS_TYPES[chassis_type_idx]
            elif chassis_types and str(chassis_types).isdigit():
                chassis_type_idx = int(chassis_types)
                if chassis_type_idx < len(self.CHASSIS_TYPES):
                    chassis = self.CHASSIS_TYPES[chassis_type_idx]
        
        return chassis