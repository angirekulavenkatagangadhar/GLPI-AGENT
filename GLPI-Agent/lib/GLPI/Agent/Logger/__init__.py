"""
GLPI Agent Logger Package

Logger backends for the GLPI Agent.
"""

# Import Logger class from parent Logger.py file
import sys
import os
import importlib.util

# Get the Logger.py file path (sibling to Logger/ directory)
logger_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Logger.py')
if os.path.exists(logger_file):
    spec = importlib.util.spec_from_file_location("GLPI.Agent.LoggerModule", logger_file)
    if spec and spec.loader:
        logger_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(logger_module)
        Logger = logger_module.Logger
else:
    Logger = None

from GLPI.Agent.Logger.Backend import Backend
from GLPI.Agent.Logger.File import File
from GLPI.Agent.Logger.Stderr import Stderr
from GLPI.Agent.Logger.Syslog import Syslog

__all__ = ['Logger', 'Backend', 'File', 'Stderr', 'Syslog']

