# glpi_agent/target/server.py
"""
Server Target Implementation for GLPI Agent

Handles communication with remote inventory servers (GLPI or OCS Inventory).
Manages server URLs, task versioning, and communication setup.
"""

import sys
import re
from urllib.parse import urlparse, urlunparse, parse_qs
from typing import Dict, List, Optional, Any

from ..Target import Target
from ..Logger import Logger
from ..Config import Config

# Module-level counter for unique IDs
_count = 0


class ServerTargetError(Exception):
    """Base exception for ServerTarget errors"""
    pass


class InvalidURLError(ServerTargetError):
    """Raised when URL is invalid"""
    pass


class ServerTarget(Target):
    """
    Server target for remote inventory submission.
    
    Communicates with GLPI or OCS Inventory servers via HTTP/HTTPS.
    Handles server detection, task versioning, and request scheduling.
    
    Attributes:
        url: Server URL
        _is_glpi_server: Whether server is GLPI (vs OCS)
        _server_task_support: Dict tracking server's supported tasks and versions
        _max_delay: Maximum delay before next contact (seconds)
        _next_run_date: Timestamp for next scheduled run
    """
    
    def __init__(self, logger: Optional[Logger] = None, config: Optional[Config] = None, **params):
        global _count
        
        if not params.get('url'):
            raise ValueError("no url parameter for server target")
        
        super().__init__(logger=logger, config=config, **params)
        
        self.url = self._getCanonicalURL(params['url'])
        self.logger = logger
        self.config = config
        
        # Compute storage subdirectory from url
        parsed = urlparse(self.url)
        # Remove userinfo (user:pass@) for storage path
        netloc = parsed.netloc.split('@')[-1] if '@' in parsed.netloc else parsed.netloc
        clean_parsed = parsed._replace(netloc=netloc)
        url_str = urlunparse(clean_parsed)
        
        subdir = url_str
        subdir = subdir.replace('/', '_')
        if sys.platform.startswith('win'):
            subdir = subdir.replace(':', '..')
        # Remove trailing underscores
        subdir = subdir.rstrip('_')
        
        # Provide oldvardir for migration from older versions
        oldvardir = str(self.url)
        oldvardir = oldvardir.replace('/', '_')
        if sys.platform.startswith('win'):
            oldvardir = oldvardir.replace(':', '..')
        # Leave empty if unchanged
        if subdir == oldvardir:
            oldvardir = ""
        
        # Initialize server-specific attributes BEFORE _init() which calls getMaxDelay()
        self._server_task_support: Dict[str, Dict[str, Any]] = {}
        self._is_glpi_server: bool = False
        self._glpi_server = ""  # Alias for compatibility
        self._max_delay: Optional[int] = None
        self._next_run_date: Optional[int] = None
        self._deviceid: Optional[str] = None
        self._glpi: str = ""  # Default GLPI version
        
        self._init(
            id=f'server{_count}',
            vardir=f"{params['basevardir']}/{subdir}",
            oldvardir=f"{params['basevardir']}/{oldvardir}" if oldvardir else ""
        )
        
        _count += 1
    
    @classmethod
    def reset(cls):
        """Reset the server target counter."""
        global _count
        _count = 0
    
    def _getCanonicalURL(self, url_string: str) -> str:
        """
        Parse and canonicalize URL string.
        
        Handles:
        - Bare hostnames (adds http://)
        - Path normalization
        - Protocol validation
        
        Args:
            url_string: Raw URL string
            
        Returns:
            Canonicalized URL
            
        Raises:
            InvalidURLError: If URL is invalid or uses unsupported protocol
        """
        if not url_string or not url_string.strip():
            raise InvalidURLError("URL cannot be empty")
        
        url_string = url_string.strip()
        parsed = urlparse(url_string)
        
        if not parsed.scheme:
            # This is likely a bare hostname
            if '/' in url_string:
                # Split on first slash to get host and path
                parts = url_string.split('/', 1)
                host = parts[0]
                path = '/' + parts[1] if len(parts) > 1 else '/'
            else:
                host = url_string
                path = '/'
            
            # Reconstruct as http URL
            parsed = parsed._replace(scheme='http', netloc=host, path=path)
        else:
            if parsed.scheme not in ('http', 'https'):
                raise InvalidURLError(
                    f"invalid protocol for URL: {url_string}. "
                    "Only http and https are supported"
                )
            
            # Ensure path exists
            if not parsed.path or parsed.path == '':
                parsed = parsed._replace(path='/')
        
        # Validate hostname
        if not parsed.netloc:
            raise InvalidURLError(f"invalid URL, missing hostname: {url_string}")
        
        return urlunparse(parsed)
    
    def getUrl(self) -> str:
        """Return the server URL for this target."""
        return self.url
    
    def setUrl(self, url: str):
        """
        Update server URL.
        
        Args:
            url: New server URL
        """
        self.url = self._getCanonicalURL(url)
    
    def getName(self) -> str:
        """
        Return the target name (URL without credentials).
        
        Returns:
            Clean URL string suitable for display
        """
        parsed = urlparse(self.url)
        # Remove userinfo (credentials)
        netloc = parsed.netloc.split('@')[-1] if '@' in parsed.netloc else parsed.netloc
        clean_parsed = parsed._replace(netloc=netloc)
        return urlunparse(clean_parsed)
    
    def get_name(self):
        """Alias for getName (snake_case version)"""
        return self.getName()
    
    def getType(self) -> str:
        """Return the target type."""
        return 'server'
    
    def isGlpiServer(self, value: Optional[bool] = None) -> bool:
        """
        Set or get GLPI server status.
        
        Args:
            value: If provided, sets GLPI server status
            
        Returns:
            Current GLPI server status
        """
        if value is not None:
            if isinstance(value, str):
                self._is_glpi_server = value.lower() in ('1', 'true', 'yes')
            else:
                self._is_glpi_server = bool(value)
        
        return self._is_glpi_server
    
    def is_glpi_server(self, value: Optional[bool] = None) -> bool:
        """Alias for isGlpiServer (snake_case version)"""
        return self.isGlpiServer(value)
    
    def plannedTasks(self, tasks: Optional[List[str]] = None) -> List[str]:
        """
        Set or get planned tasks for this target.
        
        Args:
            tasks: If provided, sets the planned tasks list
            
        Returns:
            Current list of planned tasks
        """
        if tasks is not None:
            self.tasks = list(tasks)
        
        return getattr(self, 'tasks', [])
    
    def planned_tasks(self, tasks: Optional[List[str]] = None) -> List[str]:
        """Alias for plannedTasks (snake_case version)"""
        return self.plannedTasks(tasks)
    
    def setServerTaskSupport(self, task: str, support: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Store server's support information for a specific task.
        
        Called after server contact to record which tasks the server supports
        and their versions.
        
        Args:
            task: Task name (e.g., 'inventory', 'deploy')
            support: Dict with 'server' and 'version' keys
            
        Returns:
            The support dict if valid, None otherwise
        """
        if not task or not isinstance(support, dict):
            return None
        
        if not (support.get('server') and support.get('version')):
            if self.logger:
                self.logger.debug(
                    f"Invalid task support for {task}: missing server or version"
                )
            return None
        
        self._server_task_support[task.lower()] = support
        
        if self.logger:
            self.logger.debug(
                f"Server supports {task}: {support['server']} v{support['version']}"
            )
        
        return support
    
    def doProlog(self) -> bool:
        """
        Check if any server-supported task requires PROLOG request.
        
        PROLOG is used by some servers (like GLPI with FusionInventory)
        to send task instructions to the agent.
        
        Returns:
            True if PROLOG should be performed
        """
        if not self._server_task_support:
            # No known support, assume PROLOG needed
            return True
        
        # Check if any task has glpiinventory or fusioninventory server
        for task_support in self._server_task_support.values():
            server = task_support.get('server', '').lower()
            if server in ('glpiinventory', 'fusioninventory'):
                return True
        
        return False
    
    def getTaskServer(self, task: str) -> Optional[str]:
        """
        Return server name for a supported task.
        
        Args:
            task: Task name
            
        Returns:
            Server name (e.g., 'glpiinventory') or None
        """
        task = task.lower()
        
        if not (task and self._server_task_support and task in self._server_task_support):
            return None
        
        return self._server_task_support[task].get('server')
    
    def getTaskVersion(self, task: str) -> str:
        """
        Return version of supported task.
        
        Args:
            task: Task name
            
        Returns:
            Task version string or default GLPI version
        """
        task = task.lower()
        
        if not (task and self._server_task_support and task in self._server_task_support):
            return self._glpi
        
        return self._server_task_support[task].get('version', self._glpi)
    
    def setMaxDelay(self, delay: int):
        """
        Set maximum delay before next server contact.
        
        Args:
            delay: Delay in seconds
        """
        self._max_delay = int(delay) if delay else None
    
    def getMaxDelay(self) -> Optional[int]:
        """
        Get maximum delay before next server contact.
        
        Returns:
            Delay in seconds or None
        """
        # Use _max_delay if set, otherwise fall back to parent's maxDelay
        return self._max_delay if self._max_delay is not None else self.maxDelay
    
    def setNextRunDate(self, timestamp: int):
        """
        Set next scheduled run timestamp.
        
        Args:
            timestamp: Unix timestamp
        """
        self._next_run_date = int(timestamp) if timestamp else None
    
    def getNextRunDate(self) -> Optional[int]:
        """
        Get next scheduled run timestamp.
        
        Returns:
            Unix timestamp or None
        """
        return self._next_run_date
    
    def setDeviceid(self, deviceid: str):
        """
        Set agent device ID.
        
        Args:
            deviceid: Unique device identifier
        """
        self._deviceid = deviceid
    
    def getDeviceid(self) -> Optional[str]:
        """
        Get agent device ID.
        
        Returns:
            Device identifier or None
        """
        return self._deviceid
    
    def setGlpiVersion(self, version: str):
        """
        Set default GLPI version.
        
        Args:
            version: GLPI version string
        """
        self._glpi = version or ""
    
    def getGlpiVersion(self) -> str:
        """
        Get default GLPI version.
        
        Returns:
            GLPI version string
        """
        return self._glpi