import os
from pathlib import Path
from typing import List, Optional

from ..Target import Target

# Module-level counter for unique IDs
_count = 0

class LocalTarget(Target):
    def __init__(self, **params):
        global _count
        
        if not params.get('path'):
            raise ValueError("no path parameter for local target")
        
        super().__init__(**params)
        
        self.path = params['path']
        
        # Set fullpath unless path is '-' (stdout)
        if self.path != '-':
            self.fullpath = str(Path(self.path).resolve())
        else:
            self.fullpath = None
        
        # Determine output format
        if params.get('json'):
            self.format = 'json'
        elif params.get('html'):
            self.format = 'html'
        else:
            self.format = 'xml'
        
        self._init(
            id=f'local{_count}',
            vardir=f"{params['basevardir']}/__LOCAL__"
        )
        
        _count += 1
    
    @classmethod
    def reset(cls):
        """Reset the local target counter."""
        global _count
        _count = 0
    
    def getPath(self) -> str:
        """Return the local output directory for this target."""
        return self.path
    
    def getFullPath(self, subfolder: Optional[str] = None) -> str:
        """Get full path optionally with subfolder"""
        fullpath = self.fullpath or self.path
        if subfolder:
            return f"{fullpath}/{subfolder}"
        return fullpath
    
    def setPath(self, path: str):
        """Set the local output directory for this target."""
        if path and Path(path).is_dir():
            self.path = path
    
    def setFullPath(self, path: str):
        """Set full path if directory exists"""
        if path and Path(path).is_dir():
            self.fullpath = path
    
    def getName(self) -> str:
        """Return the target name"""
        return self.path
    
    def getType(self) -> str:
        """Return the target type"""
        return 'local'
    
    def plannedTasks(self, tasks: Optional[List[str]] = None) -> List[str]:
        """Set or get planned tasks - local only supports inventory tasks"""
        if tasks is not None:
            # Keep only inventory tasks
            self.tasks = [task for task in tasks 
                         if task.lower() in ('inventory', 'remoteinventory')]
        
        return getattr(self, 'tasks', [])