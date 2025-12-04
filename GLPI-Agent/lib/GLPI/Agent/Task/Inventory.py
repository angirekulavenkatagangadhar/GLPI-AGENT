#!/usr/bin/env python3
"""
GLPI Agent Inventory Task - Complete Python Implementation

Main inventory collection task that coordinates all inventory modules
and handles submission to various target types.
"""

import os
import sys
import time
import signal
import importlib
from typing import Any, Dict, List, Optional

# Import base classes and dependencies
try:
    from GLPI.Agent.Task import GLPITask
    from GLPI.Agent.Tools import trim_whitespace, run_function, any_func, empty
    from GLPI.Agent.Inventory import Inventory
    from GLPI.Agent.Event import Event
    from GLPI.Agent.Task.Inventory.Module import InventoryModule
    from GLPI.Agent.Task.Inventory.Version import VERSION
    from GLPI.Agent.Protocol.Message import ProtocolMessage
except ImportError as e:
    import sys
    print(f"Warning: Could not import dependencies for InventoryTask: {e}", file=sys.stderr)
    try:
        from ..Task import GLPITask
        from ..Tools import trim_whitespace, run_function, any_func, empty
        from ..Inventory import Inventory
        from ..Event import Event
        from .Inventory.Module import InventoryModule
        from .Inventory.Version import VERSION
    except ImportError:
        # Fallback implementations
        class GLPITask:
            def __init__(self, **kwargs): pass
        class Inventory:
            def __init__(self, **kwargs): pass
        class InventoryModule:
            pass
        VERSION = "1.22"
        ProtocolMessage = None  # Will be imported when needed


class InventoryTask(GLPITask):
    """
    Main inventory collection task.
    
    Discovers and runs inventory modules, collects system information,
    and submits results to configured targets.
    """
    
    VERSION = VERSION
    
    def __init__(self, **params: Any):
        """Initialize inventory task."""
        super().__init__(**params)
        self.aborted: int = 0
        self.modules: Dict[str, Dict[str, Any]] = {}
        self.params: Optional[List[Dict]] = None
        self.disabled: Dict[str, int] = {}
        self.registry: Optional[List] = None
        self.inventory: Optional[Inventory] = None
        self.nochecksum: bool = False
    
    def isEnabled(self, contact: Any) -> bool:
        """
        Check if inventory task is enabled.
        
        Args:
            contact: Contact object with server information
            
        Returns:
            True if task should run
        """
        # Always enabled for local target
        if self.target.isType('local'):
            return True
        
        if self.target.isGlpiServer():
            # Store any inventory params
            tasks = contact.get("tasks") if hasattr(contact, 'get') else None
            
            if (isinstance(tasks, dict) and 
                isinstance(tasks.get('inventory'), dict) and 
                isinstance(tasks['inventory'].get('params'), list)):
                
                if tasks['inventory']['params']:
                    # Process parameters from GLPI server
                    disabled = {cat: 1 for cat in self.config.get('no-category', [])}
                    params = []
                    cant_load_glpi_client = False
                    
                    for param in tasks['inventory']['params']:
                        validated = []
                        
                        if (not param.get('category') or 
                            param['category'] in disabled):
                            pass
                        
                        elif param.get('params_id'):
                            # Handle remotely triggered events
                            categories = [
                                trim_whitespace(cat) 
                                for cat in param['category'].split(',')
                            ]
                            
                            for category in categories:
                                ids = [
                                    trim_whitespace(id_str) 
                                    for id_str in param['params_id'].split(',')
                                ]
                                
                                for params_id in ids:
                                    this_param = {
                                        'use': param.get('use'),
                                        'category': category,
                                        'params_id': params_id,
                                    }
                                    
                                    use_key = f"use[{params_id}]"
                                    use = param.get(use_key)
                                    if use:
                                        this_param['use'] = [
                                            trim_whitespace(u) 
                                            for u in use.split(',')
                                        ]
                                    
                                    # Setup GLPI server client
                                    if this_param.get('use'):
                                        try:
                                            from glpi_agent.http.client.glpi import GLPIHTTPClient
                                            
                                            this_param['_glpi_client'] = GLPIHTTPClient(
                                                logger=self.logger,
                                                config=self.config,
                                                agentid=self.agentid,
                                            )
                                            this_param['_glpi_url'] = self.target.getUrl()
                                            validated.append(this_param)
                                            
                                        except ImportError as e:
                                            if not cant_load_glpi_client:
                                                self.logger.error(
                                                    "Can't load GLPI client API to handle get_params"
                                                )
                                                cant_load_glpi_client = True
                        
                        elif param.get('use'):
                            validated.append(param)
                        
                        if validated:
                            params.extend(validated)
                        else:
                            debug_parts = [
                                f"{k}={v}" for k, v in param.items()
                            ]
                            self.logger.debug(
                                f"Skipping invalid params: {'&'.join(debug_parts)}"
                            )
                    
                    if params:
                        self.params = params
            
            return True
        
        else:
            # Non-GLPI server
            content = contact.getContent() if hasattr(contact, 'getContent') else None
            
            if (not content or not content.get('RESPONSE') or 
                content['RESPONSE'] != 'SEND'):
                
                if self.config.get('force'):
                    self.logger.debug(
                        "Inventory task execution not requested, but execution forced"
                    )
                else:
                    self.logger.debug("Inventory task execution not requested")
                    return False
            
            if hasattr(contact, 'getOptionsInfoByName'):
                self.registry = contact.getOptionsInfoByName('REGISTRY')
        
        return True
    
    def run(self) -> Any:
        """
        Execute the inventory task.
        
        Returns:
            Task result or None
        """
        # Warn if not running as root/admin
        if hasattr(os, 'getuid') and os.getuid() != 0:
            self.logger.warning(
                "You should execute this task as super-user"
            )
        
        self.aborted = 0
        self.modules = {}
        
        tag = self.config.get('tag')
        
        # Create inventory object
        self.inventory = Inventory(
            statedir=self.target.getStorage().getDirectory(),
            deviceid=self.deviceid,
            datadir=self.datadir,
            logger=self.logger,
            glpi=self.target.getTaskVersion('inventory'),
            required=self.config.get('required-category', []),
            itemtype=(
                "Computer" if empty(self.config.get('itemtype')) 
                else self.config['itemtype']
            ),
            tag=tag
        )
        
        # Log inventory start
        event = self.event()
        name = getattr(event, 'name', 'inventory') if event else "inventory"
        tag_suffix = f" (tag={tag})" if tag else ""
        
        self.logger.info(
            f"New {name} from {self.inventory.getDeviceId()} "
            f"for {self.target.id}{tag_suffix}"
        )
        
        # Set inventory as remote if needed
        if self.getRemote():
            self.inventory.setRemote(self.getRemote())
        
        # Ensure PATH is set
        if not os.environ.get('PATH'):
            os.environ['PATH'] = (
                '/sbin:/usr/sbin:/usr/local/sbin:'
                '/bin:/usr/bin:/usr/local/bin'
            )
            self.logger.debug(
                f"PATH is not set, using {os.environ['PATH']} as default"
            )
        
        # Set credentials if available
        if self.credentials:
            self.inventory.credentials(self.credentials)
        
        # Build disabled categories set
        self.disabled = {
            cat: 1 for cat in self.config.get('no-category', [])
        }
        
        # Setup event-specific configuration
        if event and not self.setupEvent():
            self.logger.info(
                f"Skipping Inventory task event on {self.target.getId()}"
            )
            return None
        
        # Determine output format
        format_type = 'json'
        if self.target.isType('local'):
            if not self.inventory.isPartial():
                format_type = getattr(self.target, 'format', 'json')
        elif not self.target.isGlpiServer():
            # Server other than GLPI, or listener target
            format_type = 'xml'
        
        self.inventory.setFormat(format_type)
        
        # Disable unsupported categories in XML format
        if ((self.target.isType('local') and format_type == 'xml') or
            (self.target.isType('server') and not self.target.isGlpiServer())):
            self.disabled['database'] = 1
        
        # Initialize and run modules
        self._initModulesList()
        
        if not self.aborted:
            self._feedInventory()
        
        # Clean up modules from memory
        self.modules = {}
        
        if self.aborted:
            return None
        
        return self.submit()
    
    def setupEvent(self) -> bool:
        """
        Setup inventory based on event configuration.
        
        Returns:
            True if setup successful, False to skip task
        """
        event = self.resetEvent()
        
        if not event:
            return True
        
        # Validate event type for target
        if (self.target.isType('server') and 
            not self.target.isGlpiServer() and 
            getattr(event, 'partial', False)):
            self.logger.debug(
                f"{self.target.getId()}: server target for partial inventory "
                "events need to be a GLPI server"
            )
            return False
        
        # Check for supported event types
        if not (getattr(event, 'taskrun', False) or 
                getattr(event, 'partial', False)):
            self.logger.debug(
                "Only support taskrun or partial inventory events for Inventory task"
            )
            return False
        
        # Set full/partial status
        is_full = (
            not getattr(event, 'partial', False) and
            getattr(event, 'taskrun', False) and
            (getattr(event, 'get', lambda x: False)("full") if hasattr(event, 'get') else False)
        )
        self.inventory.isFull(is_full)
        self.inventory.isPartial(not self.inventory.isFull())
        
        # Handle partial inventory with specific categories
        if (getattr(event, 'partial', False) and 
            getattr(event, 'category', None)):
            
            # Build keep list
            categories_str = event.category
            keep = {
                cat.lower(): 1 
                for cat in categories_str.split(',')
                if cat and cat not in self.disabled
            }
            
            if not keep:
                self.logger.info("Nothing to inventory on partial inventory event")
                return False
            
            # Validate categories
            all_categories = self.getCategories()
            valid = False
            for category in keep:
                if category in all_categories:
                    valid = True
                else:
                    self.logger.error(
                        f"Unknown category on partial inventory event: {category}"
                    )
            
            if not valid:
                self.logger.error(
                    "Invalid partial inventory event with no supported category"
                )
                return False
            
            # Handle cached data
            cached = self.cachedata()
            if cached:
                self.inventory.mergeContent(cached)
                self.keepcache(0)
            else:
                # Need hardware and bios for caching
                keep['hardware'] = 1
                keep['bios'] = 1
                # OS required with software
                if 'software' in keep:
                    keep['os'] = 1
                self.keepcache(1)
            
            # Disable non-selected categories
            for category in all_categories:
                if category not in keep:
                    self.disabled[category] = 1
            
            # Skip checksum for partial inventory
            self.nochecksum = True
        
        return True
    
    def submit(self) -> Any:
        """
        Submit inventory to target.
        
        Returns:
            Submission result
        """
        inventory = self.inventory
        
        # Cache data for next partial inventory
        if inventory.isPartial() and self.keepcache() and not self.cachedata():
            keep = {}
            for section in ['BIOS', 'HARDWARE']:
                content = inventory.getSection(section)
                if content:
                    keep[section] = content
            if keep:
                self.cachedata(keep)
        
        # Submit based on target type
        if self.target.isType('local'):
            file = inventory.save(self.target.getFullPath())
            if file:
                location = (
                    "dumped on standard output" if file == '-' 
                    else f"saved in {file}"
                )
                self.logger.info(f"Inventory {location}")
        
        elif self.target.isGlpiServer():
            try:
                from glpi_agent.http.client.glpi import GLPIHTTPClient
            except ImportError:
                return self.logger.error("Can't load GLPI client API")
            
            client = GLPIHTTPClient(
                logger=self.logger,
                config=self.config,
                agentid=self.agentid,
            )
            
            response = client.send(
                url=self.target.getUrl(),
                message=inventory.getContent(
                    server_version=self.target.getTaskVersion('inventory')
                )
            )
            return response
        
        elif self.target.isType('server'):
            try:
                from glpi_agent.http.client.ocs import OCSHTTPClient
            except ImportError:
                return self.logger.error("Can't load OCS client API")
            
            try:
                from glpi_agent.xml.query.inventory import InventoryXMLQuery
            except ImportError:
                return self.logger.error("Can't load Inventory XML Query API")
            
            client = OCSHTTPClient(
                logger=self.logger,
                config=self.config,
                agentid=self.agentid,
            )
            
            message = InventoryXMLQuery(
                deviceid=inventory.getDeviceId(),
                content=inventory.getContent()
            )
            
            response = client.send(
                url=self.target.getUrl(),
                message=message
            )
            return response
        
        elif self.target.isType('listener'):
            try:
                from glpi_agent.xml.query.inventory import InventoryXMLQuery
            except ImportError:
                return self.logger.error("Can't load Inventory XML Query API")
            
            query = InventoryXMLQuery(
                deviceid=inventory.getDeviceId(),
                content=inventory.getContent()
            )
            
            # Store inventory XML with listener target
            self.target.inventory_xml(query.getContent())
        
        return None
    
    def getCategories(self) -> List[str]:
        """
        Get all available inventory categories.
        
        Returns:
            List of category names
        """
        modules = self.getModules('Inventory')
        if not modules:
            raise Exception("no inventory module found")
        
        categories = {}
        
        for module_name in sorted(modules):
            # Skip special modules
            if module_name.endswith(('Version', 'Module')):
                continue
            
            try:
                module = importlib.import_module(module_name)
                
                # Get main category
                if hasattr(module, 'category'):
                    cat = module.category()
                    if cat:
                        categories[cat] = 1
                
                # Get additional categories
                if hasattr(module, 'other_categories'):
                    for cat in module.other_categories():
                        categories[cat] = 1
            
            except ImportError:
                continue
        
        return list(categories.keys())
    
    def _initModulesList(self) -> None:
        """Initialize list of inventory modules and check dependencies."""
        logger = self.logger
        config = self.config
        
        modules = self.getModules('Inventory')
        if not modules:
            raise Exception("no inventory module found")
        
        # Support aborting
        signal.signal(signal.SIGTERM, lambda sig, frame: setattr(self, 'aborted', 1))
        
        # First pass: determine enabled modules
        for module_name in sorted(modules):
            if self.aborted:
                return
            
            # Compute parent module
            parts = module_name.split('.')
            parent = '.'.join(parts[:-1]) if len(parts) > 5 else ''
            
            # Skip special modules
            if module_name.endswith(('Version', 'Module')):
                self.modules[module_name] = {'enabled': 0}
                continue
            
            # Skip if parent not enabled (but only if parent is actually a discovered module, not just a package directory)
            if parent and parent in modules:
                if not self.modules.get(parent, {}).get('enabled'):
                    logger.debug2(
                        f"  {module_name} disabled: implicit dependency {parent} not enabled"
                    )
                    self.modules[module_name] = {'enabled': 0}
                    continue
            
            # Try to load module
            try:
                module = importlib.import_module(module_name)
            except ImportError as e:
                logger.debug(
                    f"module {module_name} disabled: failure to load ({e})"
                )
                self.modules[module_name] = {'enabled': 0}
                continue
            
            # Check category
            if hasattr(module, 'category'):
                category = module.category()
                if category and self.disabled.get(category):
                    logger.debug2(
                        f"module {module_name} disabled: '{category}' category disabled"
                    )
                    self.modules[module_name] = {'enabled': 0}
                    continue
            
            # Check if enabled
            enabled = run_function(
                module=module_name,
                function="isEnabled",
                logger=logger,
                timeout=config.get('backend-collect-timeout', 180),
                params={
                    'datadir': self.datadir,
                    'logger': self.logger,
                    'registry': self.registry,
                    'scan_homedirs': config.get('scan-homedirs'),
                    'scan_profiles': config.get('scan-profiles'),
                    'remote': self.getRemote(),
                }
            )
            
            if not enabled:
                logger.debug2(f"module {module_name} disabled")
                self.modules[module_name] = {'enabled': 0}
                continue
            
            # Module is enabled
            run_after = [parent] if parent else []
            if hasattr(module, 'runAfter'):
                run_after.extend(module.runAfter)
            if hasattr(module, 'runAfterIfEnabled'):
                run_after.extend(module.runAfterIfEnabled)
            
            run_after_if_enabled = {}
            if hasattr(module, 'runAfterIfEnabled'):
                run_after_if_enabled = {
                    m: 1 for m in module.runAfterIfEnabled
                }
            
            self.modules[module_name] = {
                'enabled': 1,
                'done': 0,
                'used': 0,
                'runAfter': run_after,
                'runAfterIfEnabled': run_after_if_enabled
            }
        
        # Second pass: disable fallback modules
        for module_name in modules:
            if self.aborted:
                return
            
            if not self.modules.get(module_name, {}).get('enabled'):
                continue
            
            try:
                module = importlib.import_module(module_name)
                if not hasattr(module, 'runMeIfTheseChecksFailed'):
                    continue
                
                failed = None
                for other in module.runMeIfTheseChecksFailed:
                    if self.modules.get(other, {}).get('enabled'):
                        failed = other
                        break
                
                if failed:
                    self.modules[module_name]['enabled'] = 0
                    logger.debug(
                        f"module {module_name} disabled because of {failed}"
                    )
            
            except ImportError:
                continue
    
    def _runModule(self, module_name: str) -> None:
        """
        Run a single inventory module.
        
        Args:
            module_name: Full module name to run
        """
        logger = self.logger
        
        if self.modules[module_name]['done']:
            return
        
        self.modules[module_name]['used'] = 1  # Lock
        
        # Run dependencies first
        for other in self.modules[module_name]['runAfter']:
            if other not in self.modules:
                raise Exception(
                    f"module {other}, needed before {module_name}, not found"
                )
            
            if not self.modules[other]['enabled']:
                if other in self.modules[module_name]['runAfterIfEnabled']:
                    # Soft dependency
                    continue
                else:
                    # Hard dependency
                    raise Exception(
                        f"module {other}, needed before {module_name}, not enabled"
                    )
            
            if self.modules[other]['used']:
                raise Exception(
                    f"circular dependency between {module_name} and {other}"
                )
            
            self._runModule(other)
        
        logger.debug(f"Running {module_name}")
        
        # Execute module
        run_function(
            module=module_name,
            function="doInventory",
            logger=logger,
            timeout=self.config.get('backend-collect-timeout', 180),
            params={
                'datadir': self.datadir,
                'inventory': self.inventory,
                'no_category': self.disabled,
                'logger': self.logger,
                'registry': self.registry,
                'params': self.params,
                'scan_homedirs': self.config.get('scan-homedirs'),
                'scan_profiles': self.config.get('scan-profiles'),
                'assetname_support': self.config.get('assetname-support'),
            }
        )
        
        self.modules[module_name]['done'] = 1
        self.modules[module_name]['used'] = 0  # Unlock
    
    def _feedInventory(self) -> None:
        """Run all enabled inventory modules."""
        begin = time.time()
        
        enabled_modules = [
            name for name, info in self.modules.items()
            if info.get('enabled')
        ]
        
        # Support aborting
        signal.signal(signal.SIGTERM, lambda sig, frame: setattr(self, 'aborted', 1))
        
        for module_name in sorted(enabled_modules):
            self._runModule(module_name)
            if self.aborted:
                return
        
        # Inject additional content
        self._injectContent()
        
        # Set execution time
        versionprovider = self.inventory.getSection("VERSIONPROVIDER")
        if versionprovider:
            versionprovider['ETIME'] = int(time.time() - begin)
        
        # Compute checksum (unless partial or disabled)
        if not self.nochecksum:
            postpone_str = str(self.config.get('full-inventory-postpone', 0))
            postpone = int(postpone_str) if postpone_str.isdigit() else 0
            self.inventory.computeChecksum(postpone)
    
    def _injectContent(self) -> None:
        """Inject additional content from file if configured."""
        file = self.config.get('additional-content')
        if not file:
            return
        
        if not os.path.isfile(file):
            return
        
        self.logger.debug(f"importing {file} file content to the inventory")
        
        content = None
        
        if file.endswith('.xml'):
            try:
                from glpi_agent.xml_handler import XMLHandler
                tree = XMLHandler(file=file).dump_as_hash()
                content = tree.get('REQUEST', {}).get('CONTENT')
            except Exception as e:
                self.logger.error(f"Failed to load XML file: {e}")
        
        elif file.endswith('.json'):
            try:
                # Import ProtocolMessage (may not be available if import failed at top)
                try:
                    from GLPI.Agent.Protocol.Message import ProtocolMessage
                except ImportError:
                    ProtocolMessage = None
                
                if ProtocolMessage is None:
                    raise ImportError("ProtocolMessage not available")
                
                protocol_msg = ProtocolMessage(file=file)
                content = protocol_msg.get('content')
                if not content:
                    self.logger.error(
                        f"failing to import {file} file content in the inventory"
                    )
            except Exception as e:
                self.logger.error(f"Can't load GLPI Protocol Message library: {e}")
        
        else:
            self.logger.error(f"unknown file type {file}")
            return
        
        if not content:
            self.logger.error("no suitable content found")
            return
        
        self.inventory.mergeContent(content)


if __name__ == "__main__":
    print(f"GLPI Agent Inventory Task Version {InventoryTask.VERSION}")