"""
GLPI::Agent::Logger::Syslog - A syslog backend for the logger

This is a syslog-based backend for the logger.
"""

try:
    import syslog
    HAS_SYSLOG = True
except ImportError:
    # syslog is not available on Windows
    HAS_SYSLOG = False
    syslog = None

from GLPI.Agent.Logger.Backend import Backend
from GLPI.Agent.Version import PROVIDER


# Map log levels to syslog priorities (only if syslog available)
if HAS_SYSLOG:
    SYSLOG_LEVELS = {
        'error': syslog.LOG_ERR,
        'warning': syslog.LOG_WARNING,
        'info': syslog.LOG_INFO,
        'debug': syslog.LOG_DEBUG,
        'debug2': syslog.LOG_DEBUG
    }

    # Syslog facility mapping
    SYSLOG_FACILITIES = {
        'LOG_USER': syslog.LOG_USER,
        'LOG_LOCAL0': syslog.LOG_LOCAL0,
        'LOG_LOCAL1': syslog.LOG_LOCAL1,
        'LOG_LOCAL2': syslog.LOG_LOCAL2,
        'LOG_LOCAL3': syslog.LOG_LOCAL3,
        'LOG_LOCAL4': syslog.LOG_LOCAL4,
        'LOG_LOCAL5': syslog.LOG_LOCAL5,
        'LOG_LOCAL6': syslog.LOG_LOCAL6,
        'LOG_LOCAL7': syslog.LOG_LOCAL7,
        'LOG_DAEMON': syslog.LOG_DAEMON,
    }
else:
    SYSLOG_LEVELS = {}
    SYSLOG_FACILITIES = {}


class Syslog(Backend):
    """Syslog-based logger backend."""
    
    def __init__(self, logfacility='LOG_USER', **params):
        """
        Initialize the syslog logger backend.
        
        Args:
            logfacility (str): The syslog facility to use (default: LOG_USER)
            **params: Additional parameters passed to parent
        """
        super().__init__(params.get('config'))
        
        if not HAS_SYSLOG:
            raise ImportError("syslog module not available on this platform")
        
        self.facility = logfacility or 'LOG_USER'
        
        # Get the syslog name from the provider
        syslog_name = f"{PROVIDER.lower()}-agent"
        
        # Get the facility value
        facility_value = SYSLOG_FACILITIES.get(self.facility, syslog.LOG_USER)
        
        # Open syslog
        syslog.openlog(
            syslog_name,
            syslog.LOG_CONS | syslog.LOG_PID,
            facility_value
        )
    
    def add_message(self, level, message):
        """
        Add a message to syslog.
        
        Args:
            level (str): Log level (debug, info, warning, error)
            message (str): Log message
        """
        level = level or 'info'
        priority = SYSLOG_LEVELS.get(level, syslog.LOG_INFO)
        syslog.syslog(priority, message)
    
    def reload(self):
        """Reload the syslog connection."""
        syslog.closelog()
        
        # Get the syslog name from the provider
        syslog_name = f"{PROVIDER.lower()}-agent"
        
        # Get the facility value
        facility_value = SYSLOG_FACILITIES.get(self.facility, syslog.LOG_USER)
        
        # Reopen syslog
        syslog.openlog(
            syslog_name,
            syslog.LOG_CONS | syslog.LOG_PID,
            facility_value
        )
    
    def __del__(self):
        """Close syslog on destruction."""
        try:
            syslog.closelog()
        except:
            pass
