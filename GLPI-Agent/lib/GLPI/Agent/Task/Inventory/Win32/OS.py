# glpi_agent/task/inventory/win32/os.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import hex2dec
from GLPI.Agent.Tools.Win32 import (
    get_wmi_objects, is64bit, get_formated_wmi_datetime,
    get_registry_value, get_formated_local_time
)


class OS(InventoryModule):
    """Windows OS inventory module."""
    
    @staticmethod
    def category():
        return "os"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        operating_system_objs = get_wmi_objects(
            class_name='Win32_OperatingSystem',
            properties=[
                'Caption', 'Version', 'CSDVersion', 'LastBootUpTime', 
                'InstallDate', 'BuildNumber', 'OSArchitecture'
            ]
        )
        operating_system = operating_system_objs[0] if operating_system_objs else {}
        
        computer_system_objs = get_wmi_objects(
            class_name='Win32_ComputerSystem',
            properties=['Name', 'DNSHostName', 'Domain']
        )
        computer_system = computer_system_objs[0] if computer_system_objs else {}
        
        # Determine architecture
        if is64bit():
            os_arch = operating_system.get('OSArchitecture', '')
            if 'ARM' in os_arch.upper():
                arch = 'Arm64'
            else:
                arch = '64-bit'
        else:
            arch = '32-bit'
        
        boottime = get_formated_wmi_datetime(operating_system.get('LastBootUpTime'))
        
        install_date = get_formated_wmi_datetime(operating_system.get('InstallDate'))
        if not install_date:
            install_date = self._get_install_date()
        
        os_info = {
            'NAME': 'Windows',
            'ARCH': arch,
            'INSTALL_DATE': install_date,
            'BOOT_TIME': boottime,
            'KERNEL_VERSION': operating_system.get('Version'),
            'FULL_NAME': operating_system.get('Caption'),
        }
        
        # UBR (Update Build Revision) replace Service Pack after XP/2003
        ubr = hex2dec(get_registry_value(
            path='HKEY_LOCAL_MACHINE/Software/Microsoft/Windows NT/CurrentVersion/UBR',
            method='GetDWORDValue'
        ))
        
        if ubr:
            build_number = operating_system.get('BuildNumber')
            if build_number:
                os_info['SERVICE_PACK'] = f"{build_number}.{ubr}"
            else:
                os_info['SERVICE_PACK'] = str(ubr)
        elif operating_system.get('CSDVersion'):
            os_info['SERVICE_PACK'] = operating_system['CSDVersion']
        
        # Support DisplayVersion as Operating system version from Windows 10 20H1
        display_version = get_registry_value(
            path='HKEY_LOCAL_MACHINE/Software/Microsoft/Windows NT/CurrentVersion/DisplayVersion'
        )
        
        if display_version:
            os_info['VERSION'] = display_version
        else:
            # Support ReleaseID as Operating system version for Windows 10
            release_id = get_registry_value(
                path='HKEY_LOCAL_MACHINE/Software/Microsoft/Windows NT/CurrentVersion/ReleaseId'
            )
            if release_id:
                os_info['VERSION'] = release_id
        
        if computer_system.get('Domain'):
            os_info['DNS_DOMAIN'] = computer_system['Domain']
        
        inventory.set_operating_system(os_info)
    
    def _get_install_date(self):
        install_date = get_registry_value(
            path='HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/Windows NT/CurrentVersion/InstallDate'
        )
        
        if not install_date:
            return None
        
        dec = hex2dec(install_date)
        if not dec:
            return None
        
        return get_formated_local_time(dec)