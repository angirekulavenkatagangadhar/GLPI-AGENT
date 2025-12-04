# glpi_agent/task/inventory/win32/batteries.py

import os

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import can_run, has_folder, has_file, get_all_lines
from glpi_agent.tools.batteries import (
    InventoryBatteries, sanitize_battery_serial, get_canonical_capacity
)
from glpi_agent.xml import XML


class Batteries(InventoryModule):
    """Windows Batteries inventory module."""
    
    @staticmethod
    def category():
        return "battery"
    
    @staticmethod
    def run_after_if_enabled():
        return ['GLPI::Agent::Task::Inventory::Generic::Dmidecode::Battery']
    
    def is_enabled(self, **params):
        return can_run('powercfg')
    
    def do_inventory(self, **params):
        logger = params.get('logger')
        inventory = params.get('inventory')
        datadir = params.get('datadir')
        
        batteries = InventoryBatteries(logger=logger)
        section = inventory.get_section('BATTERIES') or []
        
        # Empty current BATTERIES section into a new batteries list
        while section:
            battery = section.pop(0)
            batteries.add(battery)
        
        # Merge batteries reported by powercfg
        for battery in self._get_batteries_from_powercfg(
            folder=datadir,
            logger=logger
        ):
            batteries.merge(battery)
        
        # Add back merged batteries into inventories
        for battery in batteries.list():
            inventory.add_entry(
                section='BATTERIES',
                entry=battery
            )
    
    def _get_batteries_from_powercfg(self, **params):
        folder = params.pop('folder', '.')
        folder = folder.replace('/', '\\')
        
        # Check to support RemoteInventory
        if not has_folder(folder):
            folder = '.'
        
        xmlfile = f'{folder}\\batteries.xml'
        
        # Just run command to generate xmlfile
        get_all_lines(
            command=f'powercfg /batteryreport /xml /output "{xmlfile}"',
            **params
        )
        
        xmlfile = xmlfile.replace('\\', '/')
        
        test_file = params.get('file')
        if not has_file(xmlfile) and not (test_file and has_file(test_file)):
            return []
        
        # Support RemoteInventory
        xmlcontent = get_all_lines(file=xmlfile)
        if not xmlcontent:
            return []
        
        xml = XML(
            force_array=['Battery'],
            string=xmlcontent,
            **params
        )
        
        # Cleanup generated xml file after it has been loaded
        try:
            if os.path.exists(xmlfile):
                os.unlink(xmlfile)
        except:
            pass
        
        powercfg = xml.dump_as_hash()
        if not powercfg:
            return []
        
        # Check validity
        if not (isinstance(powercfg, dict) and 
                isinstance(powercfg.get('BatteryReport'), dict) and
                isinstance(powercfg['BatteryReport'].get('Batteries'), dict)):
            return []
        
        batteries_data = powercfg['BatteryReport']['Batteries']
        if not (isinstance(batteries_data.get('Battery'), list)):
            return []
        
        batteries = []
        for data in batteries_data['Battery']:
            battery = {
                'NAME': data.get('Id'),
                'MANUFACTURER': data.get('Manufacturer'),
                'CHEMISTRY': data.get('Chemistry'),
                'SERIAL': sanitize_battery_serial(data.get('SerialNumber')),
            }
            
            if data.get('DesignCapacity'):
                capacity = get_canonical_capacity(f"{data['DesignCapacity']} mWh")
                if capacity:
                    battery['CAPACITY'] = capacity
            
            if data.get('FullChargeCapacity'):
                real_capacity = get_canonical_capacity(f"{data['FullChargeCapacity']} mWh")
                if real_capacity is not None and str(real_capacity):
                    battery['REAL_CAPACITY'] = real_capacity
            
            batteries.append(battery)
        
        return batteries