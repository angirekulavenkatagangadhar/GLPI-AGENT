# glpi_agent/task/inventory/win32/hardware.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import trim_whitespace
from glpi_agent.tools.hostname import get_hostname
from glpi_agent.tools.license import decode_microsoft_key
from GLPI.Agent.Tools.Win32 import get_wmi_objects, get_registry_value


class Hardware(InventoryModule):
    """Windows Hardware inventory module."""
    
    @staticmethod
    def category():
        return "hardware"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        remote = inventory.get_remote()
        
        operating_system_objs = get_wmi_objects(
            class_name='Win32_OperatingSystem',
            properties=[
                'OSLanguage', 'SerialNumber', 'Organization', 
                'RegisteredUser', 'TotalSwapSpaceSize'
            ]
        )
        operating_system = operating_system_objs[0] if operating_system_objs else {}
        
        computer_system_objs = get_wmi_objects(
            class_name='Win32_ComputerSystem',
            properties=[
                'Name', 'DNSHostName', 'Domain', 'Workgroup', 
                'PrimaryOwnerName', 'TotalPhysicalMemory'
            ]
        )
        computer_system = computer_system_objs[0] if computer_system_objs else {}
        
        computer_system_product_objs = get_wmi_objects(
            class_name='Win32_ComputerSystemProduct',
            properties=['UUID']
        )
        computer_system_product = computer_system_product_objs[0] if computer_system_product_objs else {}
        
        # Try to get Windows product key
        key = None
        digital_product_id = get_registry_value(
            path='HKEY_LOCAL_MACHINE/Software/Microsoft/Windows NT/CurrentVersion/DigitalProductId',
            method='GetBinaryValue'
        )
        if digital_product_id:
            key = decode_microsoft_key(digital_product_id)
        
        if not key:
            digital_product_id4 = get_registry_value(
                path='HKEY_LOCAL_MACHINE/Software/Microsoft/Windows NT/CurrentVersion/DigitalProductId4',
                method='GetBinaryValue'
            )
            if digital_product_id4:
                key = decode_microsoft_key(digital_product_id4)
        
        description = get_registry_value(
            path='HKEY_LOCAL_MACHINE/SYSTEM/CurrentControlSet/Services/lanmanserver/Parameters/srvcomment'
        )
        
        # Calculate swap
        swap = None
        total_swap = operating_system.get('TotalSwapSpaceSize')
        if total_swap and str(total_swap).isdigit():
            swap = int(int(total_swap) / (1024 * 1024))
        
        # Calculate memory
        memory = None
        total_physical = computer_system.get('TotalPhysicalMemory')
        if total_physical and str(total_physical).isdigit():
            memory = int(int(total_physical) / (1024 * 1024))
        
        # Get UUID
        uuid = None
        uuid_val = computer_system_product.get('UUID')
        if uuid_val:
            import re
            # Check if UUID is not all zeros
            if not re.match(r'^[0-]+$', uuid_val):
                uuid = uuid_val
        
        # Get hostname
        hostname = computer_system.get('DNSHostName') or computer_system.get('Name')
        if not hostname and not remote:
            hostname = get_hostname(short=True)
        
        inventory.set_hardware({
            'NAME': hostname,
            'DESCRIPTION': description,
            'UUID': uuid,
            'WINPRODKEY': key,
            'WINLANG': operating_system.get('OSLanguage'),
            'WINPRODID': operating_system.get('SerialNumber'),
            'WINCOMPANY': operating_system.get('Organization'),
            'WINOWNER': (operating_system.get('RegisteredUser') or
                        computer_system.get('PrimaryOwnerName')),
            'SWAP': swap,
            'MEMORY': memory,
            'WORKGROUP': (computer_system.get('Domain') or
                         computer_system.get('Workgroup')),
        })