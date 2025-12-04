#!/usr/bin/env python3
"""
GLPI Agent Task - Python Implementation

Base class for agent tasks, including logger, config, event management,
cache handling, remote status, and dynamic module discovery.
"""

import os
import sys
import copy
import importlib
import pkgutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Import actual Logger from converted module
try:
    from .logger import Logger
except ImportError:
    try:
        from glpi_agent.logger import Logger
    except ImportError:
        # Fallback logger
        import logging
        class Logger:
            def __init__(self):
                self.logger = logging.getLogger("GLPIAgent")
                if not self.logger.handlers:
                    handler = logging.StreamHandler()
                    formatter = logging.Formatter('%(levelname)s: %(message)s')
                    handler.setFormatter(formatter)
                    self.logger.addHandler(handler)
                    self.logger.setLevel(logging.INFO)
            
            def info(self, msg): self.logger.info(msg)
            def debug(self, msg): self.logger.debug(msg)
            def debug2(self, msg): self.logger.debug(msg)
            def warning(self, msg): self.logger.warning(msg)
            def error(self, msg): self.logger.error(msg)


class GLPITask(ABC):
    """
    Abstract base class for GLPI Agent tasks.
    
    Provides common functionality for all task types including:
    - Logger management
    - Configuration access
    - Event handling
    - Data caching
    - Remote task status
    - Dynamic module discovery
    """
    
    def __init__(self, **params: Any):
        """
        Initialize task.
        
        Args:
            **params: Task parameters including:
                - target: Target object (required)
                - logger: Logger instance (optional)
                - config: Configuration object (optional)
                - datadir: Data directory path (optional)
                - event: Event object (optional)
                - credentials: Credentials dict (optional)
                - deviceid: Device identifier (optional)
                - agentid: Agent identifier (optional)
                - cached_data: Cached data (optional)
                
        Raises:
            Exception: If target parameter is missing
        """
        if 'target' not in params or params['target'] is None:
            raise Exception('no target parameter')

        self.logger: Logger = params.get('logger', Logger())
        self.config: Optional[Any] = params.get('config')
        self.datadir: Optional[str] = params.get('datadir')
        self._event: Optional[Any] = params.get('event')
        self.credentials: Optional[Dict] = params.get('credentials')
        self.target: Any = params.get('target')
        self.deviceid: Optional[str] = params.get('deviceid')
        self.agentid: Optional[str] = params.get('agentid')
        
        # Cache management
        self._cached: Optional[Any] = params.get('cached_data')
        self._keepcache: int = 1 if params.get('cached_data') is not None else 0
        
        # Remote task tracking
        self._remote: str = ''
        
        # Event queue
        self._events: List[Any] = []

    @abstractmethod
    def isEnabled(self, contact: Any) -> bool:
        """
        Check if task is enabled.
        
        Args:
            contact: Contact object with server information
            
        Returns:
            True if task should run, False otherwise
        """
        pass

    @abstractmethod
    def run(self) -> Any:
        """
        Execute the task.
        
        Returns:
            Task result
        """
        pass

    def abort(self) -> None:
        """Abort the current task execution."""
        self.logger.info("aborting task")

    def getModules(self, task: Optional[str] = None) -> List[str]:
        """
        Discover Python modules for the given task.
        
        Args:
            task: Task name (e.g., 'Inventory', 'Deploy')
            
        Returns:
            List of module names
        """
        if not task:
            # Default to current class name
            task = self.__class__.__name__.replace('Task', '')
        
        modules = []
        
        # Determine package name
        # If this is glpi_agent.task.inventory.InventoryTask,
        # we want to find modules in glpi_agent.task.inventory package
        current_module = self.__class__.__module__
        parts = current_module.split('.')
        
        # Build package path
        if len(parts) >= 3 and parts[-2] == 'task':
            # We're in glpi_agent.task.something
            package_name = '.'.join(parts[:-1])
        else:
            # Try to construct from task name
            if '.' in current_module:
                base = '.'.join(current_module.split('.')[:-1])
                package_name = f"{base}.task.{task.lower()}"
            else:
                package_name = f"glpi_agent.task.{task.lower()}"
        
        try:
            # Import the package
            self.logger.debug2(f"Trying to import package: {package_name}")
            package = importlib.import_module(package_name)
            package_path = getattr(package, '__path__', None)
            
            if package_path:
                self.logger.debug2(f"Package path: {package_path}")
                # Discover all modules in the package (including subdirectories)
                for importer, modname, ispkg in pkgutil.walk_packages(
                    path=package_path,
                    prefix=f"{package_name}.",
                    onerror=lambda x: None  # Ignore errors on individual modules
                ):
                    # Only include actual module files, not __init__ or directories
                    if not modname.endswith('.__init__') and not ispkg:
                        # Keep full module path for import
                        modules.append(modname)
                        self.logger.debug2(f"Found module: {modname}")
            else:
                self.logger.debug(f"Package {package_name} has no __path__ attribute")
            
        except ImportError as e:
            self.logger.debug(f"Could not import package {package_name}: {e}")
            # Try alternative: GLPI.Agent.Task.Inventory directly
            if task and task.lower() == 'inventory':
                alt_package = "GLPI.Agent.Task.Inventory"
                try:
                    self.logger.debug2(f"Trying alternative package: {alt_package}")
                    package = importlib.import_module(alt_package)
                    package_path = getattr(package, '__path__', None)
                    if package_path:
                        for importer, modname, ispkg in pkgutil.walk_packages(
                            path=package_path,
                            prefix=f"{alt_package}.",
                            onerror=lambda x: None
                        ):
                            if not modname.endswith('.__init__') and not ispkg:
                                # Keep full module path for import
                                modules.append(modname)
                                self.logger.debug2(f"Found module (alt): {modname}")
                except Exception as e2:
                    self.logger.debug(f"Alternative package also failed: {e2}")
        except Exception as e:
            self.logger.debug(f"Error discovering modules: {e}")
        
        self.logger.debug(f"Discovered {len(modules)} modules for task {task}")
        return sorted(modules)

    def getRemote(self) -> str:
        """
        Get remote task status.
        
        Returns:
            Remote task identifier or empty string
        """
        return self._remote or ''

    def setRemote(self, task: Optional[str] = None) -> str:
        """
        Set remote task status.
        
        Args:
            task: Remote task identifier
            
        Returns:
            Updated remote task identifier
        """
        self._remote = task if task else ''
        return self._remote

    def _deepCopy(self, ref: Any) -> Any:
        """
        Create a deep copy of a data structure.
        
        Args:
            ref: Data structure to copy
            
        Returns:
            Deep copy of the data structure
        """
        # Use Python's built-in deepcopy
        return copy.deepcopy(ref)

    def cachedata(self, data: Optional[Any] = None) -> Optional[Any]:
        """
        Get or set cached data.
        
        Args:
            data: Data to cache (if provided)
            
        Returns:
            Cached data
        """
        if data is not None:
            self._cached = self._deepCopy(data)
        
        return self._cached

    def keepcache(self, boolval: Optional[int] = None) -> int:
        """
        Get or set cache retention flag.
        
        Args:
            boolval: Cache retention flag (if provided)
            
        Returns:
            Current cache retention flag
        """
        if boolval is not None:
            self._keepcache = boolval
        
        return self._keepcache

    def event(self, event_val: Optional[Any] = None) -> Optional[Any]:
        """
        Get or set current event.
        
        Args:
            event_val: Event object (if provided)
            
        Returns:
            Current event object
        """
        if event_val is not None:
            self._event = event_val
        
        return self._event

    def events(self) -> List[Any]:
        """
        Get all pending events.
        
        Returns:
            List of event objects
        """
        events = []
        
        # Get reset event (current event)
        next_event = self.resetEvent()
        if next_event is not None:
            events.append(next_event)
        
        # Get queued events
        if self._events:
            events.extend(self._events)
            self._events = []
        
        return events

    def resetEvent(self, event: Optional[Any] = None) -> Optional[Any]:
        """
        Reset or set current event.
        
        Args:
            event: New event object (if provided)
            
        Returns:
            Previous event object (if resetting), or new event (if setting)
        """
        if event is not None:
            self._event = event
            return event
        else:
            temp = self._event
            self._event = None
            return temp

    def addEvent(self, event: Any) -> None:
        """
        Add event to queue.
        
        Args:
            event: Event object to add
        """
        self._events.append(event)

    def newEvent(self, **params: Any) -> Any:
        """
        Create a new event object.
        
        Args:
            **params: Event parameters
            
        Returns:
            New event object
        """
        # This would create an Event object from glpi_agent.event
        # For now, return a simple dict
        return params


# Example concrete task implementation
class ExampleTask(GLPITask):
    """Example task implementation for testing."""
    
    def isEnabled(self, contact: Any) -> bool:
        """Check if example task is enabled."""
        return True
    
    def run(self) -> str:
        """Run the example task."""
        self.logger.info("Running example task")
        return "Task completed"


if __name__ == "__main__":
    # Example usage
    class MockTarget:
        def __init__(self):
            self.id = "test-target"
    
    target = MockTarget()
    
    # Create task instance
    task = ExampleTask(
        target=target,
        datadir=".",
        deviceid="device-123",
        agentid="agent-456"
    )
    
    print("Task created successfully")
    print(f"Remote status: {task.getRemote()}")
    
    # Test cache
    task.cachedata({'test': 'data', 'numbers': [1, 2, 3]})
    cached = task.cachedata()
    print(f"Cached data: {cached}")
    
    # Test keepcache
    task.keepcache(1)
    print(f"Keep cache: {task.keepcache()}")
    
    # Test events
    task.addEvent({'type': 'test', 'data': 'event1'})
    task.addEvent({'type': 'test', 'data': 'event2'})
    events = task.events()
    print(f"Events: {events}")
    
    # Test module discovery
    modules = task.getModules('Inventory')
    print(f"Discovered modules: {modules}")
    
    # Test abstract methods
    print(f"Is enabled: {task.isEnabled(None)}")
    result = task.run()
    print(f"Run result: {result}")