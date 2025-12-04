# glpi_agent/task/inventory/win32/storages.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import can_run, trim_whitespace, empty
from GLPI.Agent.Tools.Generic import get_hdparm_info
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Storages(InventoryModule):
    """Windows Storages inventory module."""
    
    # Source: https://docs.microsoft.com/en-us/previous-versions/windows/desktop/stormgmt/msft-physicaldisk
    BUS_TYPES = {
        0: 'UNKNOWN',
        1: 'SCSI',
        2: 'ATAPI',
        3: 'ATA',
        4: 'IEEE 1394',
        5: 'SSA',
        6: 'Fibre Channel',
        7: 'USB',
        8: 'RAID',
        9: 'iSCSI',
        10: 'SAS',
        11: 'SATA',
        12: 'SD',
        13: 'MMC',
        15: 'File-Backed Virtual',
        16: 'Storage Spaces',
        17: 'NVMe',
    }
    
    MEDIA_TYPES = {
        0: 'UNKNOWN',
        3: 'HDD',
        4: 'SSD',
        5: 'SCM',
    }
    
    @staticmethod
    def category():
        return "storage"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        logger = params.get('logger')
        
        hdparm = can_run('hdparm')
        
        storages = self._get_drives(
            class_name='MSFT_PhysicalDisk',
            moniker='winmgmts://./root/microsoft/windows/storage',
            logger=logger
        )
        
        # Fallback on Win32_DiskDrive if new class fails
        if not storages:
            storages = self._get_drives(
                class_name='Win32_DiskDrive',
                logger=logger
            )
        
        for storage in storages:
            if hdparm and storage.get('NAME'):
                import re
                match = re.search(r'(\d+)$', storage['NAME'])
                if match:
                    disk_num = int(match.group(1))
                    device = f"/dev/hd{chr(ord('a') + disk_num)}"
                    info = get_hdparm_info(device=device, logger=logger)
                    
                    if info:
                        for k in ['MODEL', 'FIRMWARE', 'SERIALNUMBER', 'DISKSIZE']:
                            if k in info:
                                # Be sure to not override a value with an empty or null value
                                value = trim_whitespace(info[k])
                                if value:
                                    storage[k] = value
            
            inventory.add_entry(
                section='STORAGES',
                entry=storage
            )
        
        # CD-ROM drives
        storages = self._get_drives(
            class_name='Win32_CDROMDrive',
            logger=logger
        )
        
        for storage in storages:
            if hdparm and storage.get('NAME'):
                import re
                match = re.search(r'(\d+)$', storage['NAME'])
                if match:
                    disk_num = int(match.group(1))
                    device = f"/dev/scd{chr(ord('a') + disk_num)}"
                    info = get_hdparm_info(device=device, logger=logger)
                    
                    if info:
                        if info.get('model'):
                            storage['MODEL'] = info['model']
                        if info.get('firmware'):
                            storage['FIRMWARE'] = trim_whitespace(info['firmware'])
                        if info.get('serial'):
                            storage['SERIAL'] = info['serial']
                        if info.get('size'):
                            storage['DISKSIZE'] = info['size']
            
            inventory.add_entry(
                section='STORAGES',
                entry=storage
            )
        
        # Tape drives
        storages = self._get_drives(
            class_name='Win32_TapeDrive',
            logger=logger
        )
        
        for storage in storages:
            inventory.add_entry(
                section='STORAGES',
                entry=storage
            )
    
    def _get_drives(self, **params):
        drives = []
        
        class_name = params.get('class_name')
        properties = [
            'Manufacturer', 'Model', 'Caption', 'Description', 'Name', 
            'MediaType', 'InterfaceType', 'FirmwareRevision', 'SerialNumber', 
            'Size', 'SCSIPort', 'SCSILogicalUnit', 'SCSITargetId',
            'BusType', 'FriendlyName', 'DeviceId'
        ]
        
        if class_name == 'MSFT_PhysicalDisk':
            properties.extend(['FirmwareVersion', 'PhysicalLocation', 'AdapterSerialNumber'])
        
        for obj in get_wmi_objects(properties=properties, **params):
            drive = {
                'MANUFACTURER': obj.get('Manufacturer'),
                'MODEL': obj.get('Model') or obj.get('Caption') or obj.get('FriendlyName'),
                'DESCRIPTION': obj.get('Description') or obj.get('PhysicalLocation'),
                'NAME': obj.get('Name') if obj.get('Name') is not None else f"PhysicalDisk{obj.get('DeviceId', '0')}",
                'TYPE': self.MEDIA_TYPES.get(obj.get('MediaType'), obj.get('MediaType')),
                'INTERFACE': obj.get('InterfaceType'),
                'FIRMWARE': obj.get('FirmwareVersion') or obj.get('FirmwareRevision'),
                'SCSI_COID': obj.get('SCSIPort'),
                'SCSI_LUN': obj.get('SCSILogicalUnit'),
                'SCSI_UNID': obj.get('SCSITargetId'),
            }
            
            # Cleanup field which may contain spaces
            if drive.get('FIRMWARE'):
                drive['FIRMWARE'] = trim_whitespace(drive['FIRMWARE'])
            
            if obj.get('Size'):
                drive['DISKSIZE'] = int(obj['Size'] / 1_000_000)
            
            # First use AdapterSerialNumber as SerialNumber
            serial = trim_whitespace(obj.get('AdapterSerialNumber', ''))
            if empty(serial):
                serial = trim_whitespace(obj.get('SerialNumber', ''))
            
            if not empty(serial):
                import re
                match = re.match(r'^(\S+)', serial)
                if match:
                    serial = match.group(1)
            
            if not empty(serial):
                # Try to decode serial only for known case
                if drive.get('MODEL') and 'VBOX HARDDISK ATA' in drive['MODEL']:
                    drive['SERIAL'] = self._decode_serial_number(serial)
                else:
                    drive['SERIAL'] = serial
            
            if not drive.get('INTERFACE') and obj.get('BusType') is not None:
                drive['INTERFACE'] = self.BUS_TYPES.get(obj['BusType'], self.BUS_TYPES[0])
            
            if drive.get('MODEL') and 'VBOX' in drive['MODEL']:
                if not drive.get('DESCRIPTION'):
                    drive['DESCRIPTION'] = "Virtual device"
                if drive.get('TYPE') == 'UNKNOWN':
                    drive['TYPE'] = "Virtual"
            
            drives.append(drive)
        
        return drives
    
    def _decode_serial_number(self, serial):
        """Decode hex-encoded serial number."""
        import re
        
        if not re.match(r'^[0-9a-f]+$', serial):
            return serial
        
        # serial is a space padded string encoded in hex words (4 hex-digits by word)
        if len(serial) % 4:
            return serial
        
        # Map hex-encoded string to list of chars
        chars = [chr(int(serial[i:i+2], 16)) for i in range(0, len(serial), 2)]
        
        decoded = ''
        
        # Re-order chars (swap pairs)
        while chars:
            first = chars.pop(0)
            if chars:
                second = chars.pop(0)
                decoded += second + first
            else:
                decoded += first
        
        # Strip trailing spaces
        decoded = decoded.rstrip()
        
        return decoded