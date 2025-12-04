"""Compatibility: glpi_agent.task -> GLPI.Agent.Task"""
import sys
# Make sure glpi_agent is set up first
if 'glpi_agent' not in sys.modules:
    import GLPI
    sys.modules['glpi_agent'] = GLPI

# Import and expose Task
try:
    import GLPI.Agent.Task as Task
    sys.modules['glpi_agent.task'] = Task
    # Also make it available as an attribute
    sys.modules['glpi_agent'].task = Task
except ImportError:
    pass

