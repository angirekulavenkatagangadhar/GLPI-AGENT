# glpi_agent/task/inventory/win32/videos.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_wmi_objects, get_registry_key
from GLPI.Agent.Tools import hex2dec


class Videos(InventoryModule):
    """Windows Videos inventory module."""
    
    @staticmethod
    def category():
        return "video"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        seen = set()
        inventory = params.get('inventory')
        logger = params.get('logger')
        
        for video in self._get_videos(logger=logger):
            if not video.get('NAME'):
                continue
            
            # avoid duplicates
            if video['NAME'] in seen:
                continue
            seen.add(video['NAME'])
            
            inventory.add_entry(
                section='VIDEOS',
                entry=video
            )
    
    def _get_videos(self, **params):
        videos = []
        
        for obj in get_wmi_objects(
            class_name='Win32_VideoController',
            properties=[
                'CurrentHorizontalResolution', 'CurrentVerticalResolution', 
                'VideoProcessor', 'AdapterRAM', 'Name', 'PNPDeviceID'
            ],
            **params
        ):
            if not obj.get('Name'):
                continue
            
            video = {
                'CHIPSET': obj.get('VideoProcessor'),
                'NAME': obj.get('Name'),
            }
            
            if obj.get('AdapterRAM') and obj['AdapterRAM'] > 0:
                video['MEMORY'] = obj['AdapterRAM']
            
            if obj.get('CurrentHorizontalResolution'):
                video['RESOLUTION'] = (
                    f"{obj['CurrentHorizontalResolution']}"
                    f"x{obj['CurrentVerticalResolution']}"
                )
            
            pnpdeviceid = self._pnpdeviceid(obj.get('PNPDeviceID'))
            if pnpdeviceid:
                # Try to get memory from registry
                videokey = get_registry_key(
                    path="HKEY_LOCAL_MACHINE/SYSTEM/CurrentControlSet/Control/Class/{4d36e968-e325-11ce-bfc1-08002be10318}",
                    required=['HardwareInformation.MemorySize', 
                             'HardwareInformation.qwMemorySize', 
                             'MatchingDeviceId'],
                    maxdepth=2
                )
                
                if videokey:
                    for subkey, subvalue in videokey.items():
                        if not (subkey.endswith('/') and subvalue and isinstance(subvalue, dict)):
                            continue
                        
                        this_pnpdeviceid = self._pnpdeviceid(subvalue.get('/MatchingDeviceId'))
                        if not this_pnpdeviceid or this_pnpdeviceid != pnpdeviceid:
                            continue
                        
                        # Try qwMemorySize first (64-bit)
                        if '/HardwareInformation.qwMemorySize' in subvalue:
                            qw_mem = subvalue['/HardwareInformation.qwMemorySize']
                            if isinstance(qw_mem, str) and qw_mem.isdigit():
                                memorysize = int(qw_mem)
                            elif isinstance(qw_mem, bytes):
                                import struct
                                memorysize = struct.unpack('Q', qw_mem)[0]
                            else:
                                memorysize = qw_mem
                            
                            if memorysize and memorysize > 0:
                                video['MEMORY'] = memorysize
                                break
                        
                        # Try MemorySize (32-bit)
                        elif '/HardwareInformation.MemorySize' in subvalue:
                            mem = subvalue['/HardwareInformation.MemorySize']
                            if isinstance(mem, str):
                                if mem.startswith('0x'):
                                    memorysize = hex2dec(mem)
                                elif mem.isdigit():
                                    memorysize = int(mem)
                                else:
                                    import struct
                                    memorysize = struct.unpack('L', mem.encode())[0] if isinstance(mem, str) else struct.unpack('L', mem)[0]
                            elif isinstance(mem, bytes):
                                import struct
                                memorysize = struct.unpack('L', mem)[0]
                            else:
                                memorysize = mem
                            
                            if memorysize and memorysize > 0:
                                video['MEMORY'] = memorysize
                                break
            
            if video.get('MEMORY'):
                video['MEMORY'] = int(video['MEMORY'] / (1024 * 1024))
            
            videos.append(video)
        
        return videos
    
    def _pnpdeviceid(self, pnpdeviceid):
        if not pnpdeviceid:
            return None
        
        parts = pnpdeviceid.split('&')
        if len(parts) <= 1:
            return None
        
        import re
        found = [p for p in parts if re.match(r'^(pci\\ven|dev)_', p, re.IGNORECASE)]
        if len(found) != 2:
            return None
        
        return '&'.join(found).lower()