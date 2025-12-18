"""
GLPI Agent Core Module

This module contains the main agent classes and functionality.

Note: The main GLPIAgent class is defined in GLPI.Agent (the Agent.py file).
This __init__.py makes the Agent directory a proper Python package and
re-exports the main classes from the parent module.
"""

# Import from the parent Agent.py module
# Since we're in GLPI/Agent/__init__.py, we need to go up one level
import sys
import os
from pathlib import Path

# Get the parent directory (GLPI)
_parent_dir = Path(__file__).parent.parent
_parent_module_path = str(_parent_dir)

# Add parent to path if not already there
if _parent_module_path not in sys.path:
    sys.path.insert(0, _parent_module_path)

# Import from the Agent.py file in the parent directory
try:
    # Try direct import first (works in normal Python and PyInstaller)
    try:
        from ..Agent import GLPIAgent, VERSION_STRING, COMMENTS, VERSION, PROVIDER
    except (ImportError, ValueError):
        # Fallback: use importlib for file-based import (development mode)
        import importlib.util
        agent_file = _parent_dir / 'Agent.py'
        if agent_file.exists():
            spec = importlib.util.spec_from_file_location("GLPI.Agent", agent_file)
            if spec and spec.loader:
                agent_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(agent_module)
                
                # Re-export the main classes and constants
                GLPIAgent = getattr(agent_module, 'GLPIAgent', None)
                VERSION_STRING = getattr(agent_module, 'VERSION_STRING', None)
                COMMENTS = getattr(agent_module, 'COMMENTS', None)
                VERSION = getattr(agent_module, 'VERSION', None)
                PROVIDER = getattr(agent_module, 'PROVIDER', None)
            else:
                raise ImportError("Could not load Agent module spec")
        else:
            raise ImportError(f"Agent.py not found at {agent_file}")
except Exception as e:
    # If import fails, raise an error instead of silently setting to None
    import sys
    print(f"CRITICAL: Failed to import GLPIAgent from GLPI.Agent: {e}", file=sys.stderr)
    raise ImportError(f"Could not import GLPIAgent: {e}") from e

__all__ = ['GLPIAgent', 'VERSION_STRING', 'COMMENTS', 'VERSION', 'PROVIDER']


