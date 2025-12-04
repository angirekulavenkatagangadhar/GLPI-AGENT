"""
Compatibility package for glpi_agent -> GLPI imports
Allows modules using lowercase 'glpi_agent' imports to work with uppercase 'GLPI' package
"""
import sys
import types

# Create a new module object for glpi_agent
glpi_agent_module = types.ModuleType('glpi_agent')
sys.modules['glpi_agent'] = glpi_agent_module

# Import GLPI and make its Agent available
try:
    import GLPI
    if hasattr(GLPI, 'Agent'):
        glpi_agent_module.Agent = GLPI.Agent
except ImportError:
    pass

