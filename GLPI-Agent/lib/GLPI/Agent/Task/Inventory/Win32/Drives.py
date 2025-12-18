# glpi_agent/task/inventory/win32/drives.py

import struct

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Drives(InventoryModule):
    """Windows Drives inventory module."""
    
    DRIVE_TYPES = [
        'Unknown',
        'No Root Directory',
        'Removable Disk',
        'Local Disk',
        'Network Drive',
        'Compact Disc',
        'RAM Disk'
    ]
    
    # See https://docs.microsoft.com/en-us/windows/desktop/secprov/getencryptionmethod-win32-encryptablevolume
    ENCRYPTION_METHODS = [
        'None', 'AES_128_WITH_DIFFUSER', 'AES_256_WITH_DIFFUSER',
        'AES_128', 'AES_256', 'HARDWARE_ENCRYPTION',
        'XTS_AES_128', 'XTS_AES_256'
    ]
    
    @staticmethod
    def category():
        return "drive"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        logger = params.get('logger')
        
        for drive in self._get_drives(logger=logger):
            inventory.add_entry(
                section='DRIVES',
                entry=drive
            )
    
    def _get_drives(self, **params):
        logger = params.get('logger')
        
        system_drive = "c:"
        for obj in get_wmi_objects(
            class_name='Win32_OperatingSystem',
            properties=['SystemDrive']
        ):
            if obj.get('SystemDrive'):
                system_drive = obj['SystemDrive'].lower()
        
        drives = []
        seen = {}
        
        # Scan Win32_LogicalDisk
        for obj in get_wmi_objects(
            class_name='Win32_LogicalDisk',
            properties=[
                'InstallDate', 'Description', 'FreeSpace', 'FileSystem',
                'VolumeName', 'Caption', 'VolumeSerialNumber', 'DeviceID',
                'Size', 'DriveType', 'ProviderName'
            ]
        ):
            free_space = None
            if obj.get('FreeSpace'):
                free_space = int(obj['FreeSpace'] / (1024 * 1024))
            
            size = None
            if obj.get('Size'):
                size = int(obj['Size'] / (1024 * 1024))
            
            filesystem = obj.get('FileSystem')
            if obj.get('DriveType') == 4 and obj.get('ProviderName'):
                provider_name = obj['ProviderName']
                if '\\DavWWWRoot\\' in provider_name:
                    filesystem = "WebDav"
                elif provider_name.startswith('\\\\vmware-host\\'):
                    filesystem = "HGFS"
                elif not filesystem or filesystem != 'NFS':
                    filesystem = "CIFS"
            
            device_id = obj.get('DeviceID') or obj.get('Caption')
            
            # Ensure LABEL is always a string, not None
            label = obj.get('VolumeName') or ''
            if label is None:
                label = ''
            
            # Ensure all string fields are not None
            serial = obj.get('VolumeSerialNumber') or ''
            if serial is None:
                serial = ''
            
            drive = {
                'CREATEDATE': obj.get('InstallDate'),
                'DESCRIPTION': obj.get('Description') or '',
                'FREE': free_space,
                'FILESYSTEM': filesystem or '',
                'LABEL': label,
                'LETTER': device_id or '',
                'SERIAL': serial,
                'SYSTEMDRIVE': device_id and device_id.lower() == system_drive,
                'TOTAL': size,
                'TYPE': self.DRIVE_TYPES[obj.get('DriveType', 0)] if obj.get('DriveType', 0) < len(self.DRIVE_TYPES) else 'Unknown',
                'VOLUMN': label,
            }
            
            seen[device_id] = drive
            drives.append(drive)
        
        # Scan Win32_Volume to check for mounted point drives
        for obj in get_wmi_objects(
            class_name='Win32_Volume',
            properties=[
                'InstallDate', 'Description', 'FreeSpace', 'FileSystem',
                'Name', 'Caption', 'DriveLetter', 'SerialNumber', 'Capacity',
                'DriveType', 'Label', 'DeviceID'
            ]
        ):
            # Skip volume already seen as instance of Win32_LogicalDisk class
            if drives and obj.get('DriveLetter'):
                if obj['DriveLetter'] in seen:
                    continue
            
            free_space = None
            if obj.get('FreeSpace'):
                free_space = int(obj['FreeSpace'] / (1024 * 1024))
            
            capacity = None
            if obj.get('Capacity'):
                capacity = int(obj['Capacity'] / (1024 * 1024))
            
            name = obj.get('Name') or obj.get('Caption')
            if name and name.startswith('\\\\?\\Volume'):
                letter = obj.get('Label')
            else:
                letter = name
            
            drive_letter = obj.get('DriveLetter')
            systemdrive = drive_letter and drive_letter.lower() == system_drive
            
            drive_type = obj.get('DriveType', 0)
            if drive_type is None:
                drive_type = 0
            
            # Ensure LABEL is always a string, not None
            label = obj.get('Label') or ''
            if label is None:
                label = ''
            
            # Ensure all string fields are not None
            filesystem = obj.get('FileSystem') or ''
            if filesystem is None:
                filesystem = ''
            
            letter_str = letter or ''
            if letter_str is None:
                letter_str = ''
            
            serial = self._encode_serial_number(obj.get('SerialNumber')) or ''
            if serial is None:
                serial = ''
            
            drive = {
                'CREATEDATE': obj.get('InstallDate'),
                'DESCRIPTION': obj.get('Description') or '',
                'FREE': free_space,
                'FILESYSTEM': filesystem,
                'LABEL': label,
                'LETTER': letter_str,
                'SERIAL': serial,
                'SYSTEMDRIVE': systemdrive,
                'TOTAL': capacity,
                'TYPE': self.DRIVE_TYPES[drive_type] if drive_type < len(self.DRIVE_TYPES) else 'Unknown',
                'VOLUMN': label,
            }
            
            device_id = obj.get('DeviceID') or drive_letter or obj.get('Caption')
            seen[device_id] = drive
            drives.append(drive)
        
        # Scan Win32_EncryptableVolume to check for BitLocker crypted volumes
        for obj in get_wmi_objects(
            moniker='winmgmts://./root/CIMV2/Security/MicrosoftVolumeEncryption',
            class_name='Win32_EncryptableVolume',
            properties=['DeviceID', 'EncryptionMethod', 'ProtectionStatus', 'DriveLetter']
        ):
            obj_id = obj.get('DeviceID')
            if obj_id not in seen:
                obj_id = obj.get('DriveLetter')
            
            if obj_id not in seen:
                if logger:
                    logger.error(f"Unknown {obj_id} encryptable drive")
                continue
            
            method = obj.get('EncryptionMethod', 0)
            if method is None:
                method = 0
            
            encrypt_algo = self.ENCRYPTION_METHODS[method] if method < len(self.ENCRYPTION_METHODS) else 'Unknown'
            
            protection_status = obj.get('ProtectionStatus')
            encrypted = protection_status if protection_status is not None else 2
            
            seen[obj_id]['ENCRYPT_NAME'] = 'BitLocker'
            seen[obj_id]['ENCRYPT_ALGO'] = encrypt_algo
            
            if encrypted == 0:
                seen[obj_id]['ENCRYPT_STATUS'] = 'No'
            elif encrypted == 1:
                seen[obj_id]['ENCRYPT_STATUS'] = 'Yes'
            else:
                seen[obj_id]['ENCRYPT_STATUS'] = 'Unknown'
        
        return drives
    
    def _encode_serial_number(self, serial):
        if not serial:
            return ''
        
        # Win32_Volume serial is a uint32 but returned as signed int32 by API
        serial_str = str(serial)
        if not serial_str.lstrip('-').isdigit():
            return serial
        
        # Re-encode serial as uint32 and return hexadecimal string
        serial_int = int(serial_str)
        packed = struct.pack('l', serial_int)  # signed int32
        unpacked = struct.unpack('L', packed)[0]  # unsigned int32
        
        return f"{unpacked:08X}"