"""Compatibility: glpi_agent.tools -> GLPI.Agent.Tools"""
from GLPI.Agent.Tools import trim_whitespace, any_func as any, run_function, empty
__all__ = ['trim_whitespace', 'any', 'run_function', 'empty']

