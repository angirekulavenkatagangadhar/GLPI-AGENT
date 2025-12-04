"""Compatibility: glpi_agent.task.inventory -> GLPI.Agent.Task.Inventory"""
import sys
try:
    from GLPI.Agent.Task import Inventory
    sys.modules['glpi_agent.task.inventory'] = Inventory
except ImportError:
    pass

