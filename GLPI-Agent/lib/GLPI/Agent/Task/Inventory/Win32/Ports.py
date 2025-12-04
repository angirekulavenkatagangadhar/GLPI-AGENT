# glpi_agent/task/inventory/win32/ports.py

import re

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Ports(InventoryModule):
    """Windows Ports inventory module."""
    
    # cf http://msdn.microsoft.com/en-us/library/aa394486%28VS.85%29.aspx
    PORT_TYPES = [
        'Unknown',
        'Other',
        'Male',
        'Female',
        'Shielded',
        'Unshielded',
        'SCSI (A) High-Density (50 pins)',
        'SCSI (A) Low-Density (50 pins)',
        'SCSI (P) High-Density (68 pins)',
        'SCSI SCA-I (80 pins)',
        'SCSI SCA-II (80 pins)',
        'SCSI Fibre Channel (DB-9, Copper)',
        'SCSI Fibre Channel (Fibre)',
        'SCSI Fibre Channel SCA-II (40 pins)',
        'SCSI Fibre Channel SCA-II (20 pins)',
        'SCSI Fibre Channel BNC',
        'ATA 3-1/2 Inch (40 pins)',
        'ATA 2-1/2 Inch (44 pins)',
        'ATA-2',
        'ATA-3',
        'ATA/66',
        'DB-9',
        'DB-15',
        'DB-25',
        'DB-36',
        'RS-232C',
        'RS-422',
        'RS-423',
        'RS-485',
        'RS-449',
        'V.35',
        'X.21',
        'IEEE-488',
        'AUI',
        'UTP Category 3',
        'UTP Category 4',
        'UTP Category 5',
        'BNC',
        'RJ11',
        'RJ45',
        'Fiber MIC',
        'Apple AUI',
        'Apple GeoPort',
        'PCI',
        'ISA',
        'EISA',
        'VESA',
        'PCMCIA',
        'PCMCIA Type I',
        'PCMCIA Type II',
        'PCMCIA Type III',
        'ZV Port',
        'CardBus',
        'USB',
        'IEEE 1394',
        'HIPPI',
        'HSSDC (6 pins)',
        'GBIC',
        'DIN',
        'Mini-DIN',
        'Micro-DIN',
        'PS/2',
        'Infrared',
        'HP-HIL',
        'Access.bus',
        'NuBus',
        'Centronics',
        'Mini-Centronics',
        'Mini-Centronics Type-14',
        'Mini-Centronics Type-20',
        'Mini-Centronics Type-26',
        'Bus Mouse',
        'ADB',
        'AGP',
        'VME Bus',
        'VME64',
        'Proprietary',
        'Proprietary Processor Card Slot',
        'Proprietary Memory Card Slot',
        'Proprietary I/O Riser Slot',
        'PCI-66MHZ',
        'AGP2X',
        'AGP4X',
        'PC-98',
        'PC-98-Hireso',
        'PC-H98',
        'PC-98Note',
        'PC-98Full',
        'PCI-X',
        'SSA SCSI',
        'Circular',
        'On-Board IDE Connector',
        'On-Board Floppy Connector',
        '9 Pin Dual Inline',
        '25 Pin Dual Inline',
        '50 Pin Dual Inline',
        '68 Pin Dual Inline',
        'On-Board Sound Connector',
        'Mini-Jack',
        'PCI-X',
        'Sbus IEEE 1396-1993 32 Bit',
        'Sbus IEEE 1396-1993 64 Bit',
        'MCA',
        'GIO',
        'XIO',
        'HIO',
        'NGIO',
        'PMC',
        'MTRJ',
        'VF-45',
        'Future I/O',
        'SC',
        'SG',
        'Electrical',
        'Optical',
        'Ribbon',
        'GLM',
        '1x9',
        'Mini SG',
        'LC',
        'HSSC',
        'VHDCI Shielded (68 pins)',
        'InfiniBand',
        'AGP8X',
        'PCI-E',
    ]
    
    @staticmethod
    def category():
        return "port"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        # Serial ports
        for obj in get_wmi_objects(
            class_name='Win32_SerialPort',
            properties=['Name', 'Caption', 'Description']
        ):
            inventory.add_entry(
                section='PORTS',
                entry={
                    'NAME': obj.get('Name'),
                    'CAPTION': obj.get('Caption'),
                    'DESCRIPTION': obj.get('Description'),
                    'TYPE': 'Serial',
                }
            )
        
        # Parallel ports
        for obj in get_wmi_objects(
            class_name='Win32_ParallelPort',
            properties=['Name', 'Caption', 'Description']
        ):
            inventory.add_entry(
                section='PORTS',
                entry={
                    'NAME': obj.get('Name'),
                    'CAPTION': obj.get('Caption'),
                    'DESCRIPTION': obj.get('Description'),
                    'TYPE': 'Parallel',
                }
            )
        
        # Port connectors
        for obj in get_wmi_objects(
            class_name='Win32_PortConnector',
            properties=['ConnectorType', 'InternalReferenceDesignator']
        ):
            port_type = None
            connector_type = obj.get('ConnectorType')
            
            if connector_type:
                if isinstance(connector_type, list):
                    port_type = ', '.join([
                        self.PORT_TYPES[ct] if ct < len(self.PORT_TYPES) else 'Unknown'
                        for ct in connector_type
                    ])
                elif isinstance(connector_type, (int, str)) and str(connector_type).isdigit():
                    idx = int(connector_type)
                    if idx < len(self.PORT_TYPES):
                        port_type = self.PORT_TYPES[idx]
            
            if not port_type:
                port_type = obj.get('InternalReferenceDesignator')
                if port_type:
                    # Drop the port number
                    port_type = re.sub(r' \d.*', '', port_type)
            
            internal_ref = obj.get('InternalReferenceDesignator')
            
            if not port_type and not internal_ref:
                continue
            
            if internal_ref:
                if 'SERIAL' in internal_ref:
                    continue  # Already done
                if 'PARALLEL' in internal_ref:
                    continue  # Already done
            
            inventory.add_entry(
                section='PORTS',
                entry={
                    'NAME': internal_ref,
                    'CAPTION': internal_ref,
                    'DESCRIPTION': internal_ref,
                    'TYPE': port_type
                }
            )