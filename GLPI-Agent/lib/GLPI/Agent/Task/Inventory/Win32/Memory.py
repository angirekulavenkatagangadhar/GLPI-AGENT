# glpi_agent/task/inventory/win32/memory.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import get_canonical_speed
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Memory(InventoryModule):
    """Windows Memory inventory module."""
    
    FORM_FACTOR_VALUES = [
        'Unknown',
        'Other',
        'SIP',
        'DIP',
        'ZIP',
        'SOJ',
        'Proprietary',
        'SIMM',
        'DIMM',
        'TSOP',
        'PGA',
        'RIMM',
        'SODIMM',
        'SRIMM',
        'SMD',
        'SSMP',
        'QFP',
        'TQFP',
        'SOIC',
        'LCC',
        'PLCC',
        'BGA',
        'FPBGA',
        'LGA',
    ]
    
    MEMORY_TYPE_VALUES = [
        'Unknown',
        'Other',
        'DRAM',
        'Synchronous DRAM',
        'Cache DRAM',
        'EDO',
        'EDRAM',
        'VRAM',
        'SRAM',
        'RAM',
        'ROM',
        'Flash',
        'EEPROM',
        'FEPROM',
        'EPROM',
        'CDRAM',
        '3DRAM',
        'SDRAM',
        'SGRAM',
        'RDRAM',
        'DDR',
        'DDR-2',
    ]
    
    MEMORY_ERROR_PROTECTION = [
        None,
        'Other',
        None,
        'None',
        'Parity',
        'Single-bit ECC',
        'Multi-bit ECC',
        'CRC',
    ]
    
    @staticmethod
    def category():
        return "memory"
    
    @staticmethod
    def run_me_if_these_checks_failed():
        return ["GLPI::Agent::Task::Inventory::Generic::Dmidecode"]
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        for memory in self._get_memories():
            inventory.add_entry(
                section='MEMORIES',
                entry=memory
            )
    
    def _get_memories(self):
        cpt = 0
        memories = []
        
        for obj in get_wmi_objects(
            class_name='Win32_PhysicalMemory',
            properties=[
                'Capacity', 'Caption', 'Description', 'FormFactor', 
                'Removable', 'Speed', 'MemoryType', 'SerialNumber'
            ]
        ):
            # Ignore ROM storages (BIOS ROM)
            memory_type_idx = obj.get('MemoryType', 0)
            if memory_type_idx is None:
                memory_type_idx = 0
            
            mem_type = self.MEMORY_TYPE_VALUES[memory_type_idx] if memory_type_idx < len(self.MEMORY_TYPE_VALUES) else None
            
            if mem_type and mem_type == 'ROM':
                continue
            if mem_type and mem_type == 'Flash':
                continue
            
            capacity = None
            if obj.get('Capacity'):
                capacity = obj['Capacity'] / (1024 * 1024)
            
            form_factor_idx = obj.get('FormFactor', 0)
            if form_factor_idx is None:
                form_factor_idx = 0
            
            memories.append({
                'CAPACITY': capacity,
                'CAPTION': obj.get('Caption'),
                'DESCRIPTION': obj.get('Description'),
                'FORMFACTOR': self.FORM_FACTOR_VALUES[form_factor_idx] if form_factor_idx < len(self.FORM_FACTOR_VALUES) else None,
                'REMOVABLE': 1 if obj.get('Removable') else 0,
                'SPEED': get_canonical_speed(obj.get('Speed')),
                'TYPE': mem_type,
                'NUMSLOTS': cpt,
                'SERIALNUMBER': obj.get('SerialNumber')
            })
            cpt += 1
        
        for obj in get_wmi_objects(
            class_name='Win32_PhysicalMemoryArray',
            properties=['MemoryDevices', 'SerialNumber', 'MemoryErrorCorrection']
        ):
            memory_devices = obj.get('MemoryDevices')
            if memory_devices is not None:
                memory = memories[memory_devices - 1] if memory_devices > 0 and memory_devices <= len(memories) else memories[0] if memories else None
            else:
                memory = memories[0] if memories else None
            
            if not memory:
                continue
            
            if not memory.get('SERIALNUMBER'):
                memory['SERIALNUMBER'] = obj.get('SerialNumber')
            
            mem_error_corr = obj.get('MemoryErrorCorrection')
            if mem_error_corr is not None:
                if mem_error_corr < len(self.MEMORY_ERROR_PROTECTION):
                    memory['MEMORYCORRECTION'] = self.MEMORY_ERROR_PROTECTION[mem_error_corr]
                    
                    if memory.get('MEMORYCORRECTION') and mem_error_corr > 3:
                        desc = memory.get('DESCRIPTION', '')
                        memory['DESCRIPTION'] = f"{desc} ({memory['MEMORYCORRECTION']})"
        
        return memories