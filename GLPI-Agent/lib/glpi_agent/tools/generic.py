"""Compatibility: glpi_agent.tools.generic -> GLPI.Agent.Tools.Generic"""
from GLPI.Agent.Tools.Generic import get_cpus_from_dmidecode, get_canonical_manufacturer
__all__ = ['get_cpus_from_dmidecode', 'get_canonical_manufacturer']

