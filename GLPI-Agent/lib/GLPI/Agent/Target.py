import time
import random
from typing import List, Dict, Optional, Any

from .Logger import Logger
from .Storage import Storage
from .Event import Event

# Module-level variable for error max delay
_err_max_delay = 0

class Target:
    def __init__(self, **params):
        global _err_max_delay
        
        if not params.get('basevardir'):
            raise ValueError("no basevardir parameter for target")
        
        # Set errMaxDelay once for agent lifetime
        if not _err_max_delay:
            _err_max_delay = params.get('delaytime', 3600)
        
        self.logger = params.get('logger') or Logger()
        self.maxDelay = params.get('maxDelay', 3600)
        self.errMaxDelay = _err_max_delay
        self.initialDelay = params.get('delaytime')
        self._glpi = params.get('glpi', '')
        self._events = []
        self._next_event = {}
        self._paused = False
        self._responses = None
        self._next_reload_check = 0
        
        # Will be set by _init()
        self.id = None
        self._logprefix = None
        self.storage = None
        self.nextRunDate = None
        self.baseRunDate = None
        self._nextrundelay = 0
        self._expiration = None
    
    def _init(self, **params):
        """Initialize target with ID and storage"""
        self.id = params['id']
        self._logprefix = f"[target {self.id}]"
        
        self.storage = Storage(
            logger=self.logger,
            directory=params['vardir'],
            oldvardir=params.get('oldvardir', '')
        )
        
        keepMaxDelay = self.getMaxDelay()
        
        # Load persistent state
        self._loadState()
        
        # Update maxDelay from config when not server
        if not self.isType('server'):
            self.setMaxDelay(keepMaxDelay)
        
        # Handle initial delay logic
        lastExpectedRunDateLimit = time.time() - self.getMaxDelay()
        if (self.initialDelay and self.nextRunDate and 
            self.nextRunDate >= lastExpectedRunDateLimit):
            self.initialDelay = None
        
        # Setup base run date
        if (not self.baseRunDate or 
            self.baseRunDate <= lastExpectedRunDateLimit):
            delay = self.initialDelay or self.getMaxDelay()
            self.baseRunDate = time.time() + delay
        
        # Set next run date
        if (not self.nextRunDate or 
            self.nextRunDate < lastExpectedRunDateLimit):
            self.nextRunDate = self.computeNextRunDate()
        
        self._saveState()
        
        # Log next run info
        if self.initialDelay:
            run_type = "server contact" if self.isType("server") else "tasks run"
            when = "now" if self.nextRunDate < time.time() else f"for {time.ctime(self.nextRunDate)}"
            self.logger.debug(f"{self._logprefix} Next {run_type} planned {when}")
        
        # Disable initial delay if next run is in future
        if (self.initialDelay and self.nextRunDate and 
            self.nextRunDate > time.time()):
            self.initialDelay = None
    
    def id(self) -> str:
        """Return target ID"""
        return self.id
    
    def getStorage(self) -> Storage:
        """Return storage object for this target"""
        return self.storage
    
    def setNextRunOnExpiration(self, expiration: Optional[int] = None):
        """Set next run date based on expiration"""
        self.nextRunDate = time.time() + (expiration or 0)
        self.baseRunDate = self.nextRunDate
        self._saveState()
        self._expiration = expiration
    
    def setNextRunDateFromNow(self, nextRunDelay: Optional[int] = None):
        """Set next run date from now with optional delay"""
        if nextRunDelay:
            # Double delay on consecutive calls until maxDelay
            if hasattr(self, '_nextrundelay') and self._nextrundelay:
                nextRunDelay = 2 * self._nextrundelay
            nextRunDelay = min(nextRunDelay, self.getMaxDelay(), self.errMaxDelay)
            self._nextrundelay = nextRunDelay
        
        self.nextRunDate = time.time() + (nextRunDelay or 0)
        self.baseRunDate = self.nextRunDate
        self._saveState()
        self.initialDelay = None
    
    def resetNextRunDate(self):
        """Reset next run date to computed value"""
        if self._expiration is not None:
            self._expiration = None
            return
        
        timeref = self.baseRunDate or time.time()
        max_delay = self.getMaxDelay()
        current_time = time.time()
        
        # Reset timeref if out of range
        if timeref < current_time - max_delay or timeref > current_time + max_delay:
            timeref = current_time
        
        self._nextrundelay = 0
        self.nextRunDate = self.computeNextRunDate(timeref)
        self.baseRunDate = timeref + max_delay
        self._saveState()
    
    def reset_next_run_date(self):
        """Alias for resetNextRunDate (snake_case version)"""
        return self.resetNextRunDate()
    
    def getNextRunDate(self) -> Optional[float]:
        """Get next run date, reloading state if needed"""
        if self._needToReloadState():
            self._loadState()
        return self.nextRunDate
    
    def triggerTaskInitEvents(self):
        """Trigger init events for all planned tasks"""
        if not (hasattr(self, 'tasks') and self.tasks):
            return
        
        for task in self.tasks:
            event = Event(
                task=task,
                init="yes",
                rundate=time.time() + 10
            )
            self._events.append(event)
    
    def triggerRunTasksNow(self, event: Event):
        """Trigger run now events for tasks"""
        if not (event and event.runnow() and hasattr(self, 'tasks') and self.tasks):
            return
        
        planned_tasks = {task.lower(): True for task in self.tasks}
        task = event.task()
        all_tasks = task == "all"
        tasks = self.tasks if all_tasks else task.split(',')
        reschedule_index = len(tasks) if all_tasks else 0
        
        for runtask in [t.lower() for t in tasks]:
            reschedule_index -= 1
            if runtask not in planned_tasks:
                continue
            
            event_params = {
                'taskrun': 'yes',
                'task': runtask,
                'delay': 0
            }
            
            if all_tasks and reschedule_index == 0:
                event_params['reschedule'] = '1'
            
            if runtask == "inventory":
                full = event.get("full")
                partial = event.get("partial")
                if full is not None:
                    event_params["full"] = full
                elif partial is not None:
                    event_params["partial"] = partial
                else:
                    event_params["full"] = "1"
            
            self.addEvent(Event(**event_params), safe=True)
        
        # Reset cached responses
        if hasattr(self, '_responses'):
            self._responses = None
    
    def addEvent(self, event: Event, safe: bool = False) -> Optional[Event]:
        """Add event to event queue"""
        if not (event and event.name()):
            return None
        
        logprefix = self._logprefix
        
        # Validate event types
        if not event.job() and (event.runnow() or event.taskrun()):
            if not event.task():
                self.logger.debug(f"{logprefix} Not supported {event.name()} event without task")
                return None
            task_desc = "" if event.task() in ("all", ) or "," in event.task() else "s"
            self.logger.debug(f"{logprefix} Adding {event.name()} event for {event.task()} task{task_desc}")
        
        elif event.partial():
            if not event.category():
                self.logger.debug(f"{logprefix} Not supported partial inventory request without selected category")
                return None
            self.logger.debug(f"{logprefix} Partial inventory event on category: {event.category()}")
            # Remove existing partial inventory events
            self._events = [e for e in self._events if not e.partial()]
        
        elif event.maintenance():
            if not event.task():
                self.logger.debug(f"{logprefix} Not supported maintenance request without selected task")
                return None
            # Remove existing maintenance events for same task/target
            old_count = len(self._events)
            self._events = [e for e in self._events 
                          if not (e.maintenance() and e.task() == event.task() and e.target() == event.target())]
            debug_prefix = "Replacing" if len(self._events) < old_count else "New"
            self.logger.debug(f"{logprefix} {debug_prefix} {event.name()} event on {event.task()} task")
        
        elif event.job():
            rundate = event.rundate()
            if rundate:
                self.logger.debug(f"{logprefix} Adding {event.name()} job event as {event.task()} task scheduled on {time.ctime(rundate)}")
            else:
                self.logger.debug(f"{logprefix} Adding {event.name()} job event as {event.task()} task")
        
        else:
            self.logger.debug(f"{logprefix} Not supported event request: {event.dump_as_string()}")
            return None
        
        # Check event overflow
        if len(self._events) >= 1024:
            self.logger.debug(f"{logprefix} Event requests overflow, skipping new event")
            return None
        
        # Check timing restrictions
        if self._next_event and not safe:
            next_time = self._next_event.get(event.name())
            if next_time and time.time() < next_time:
                self.logger.debug(f"{logprefix} Skipping too early new {event.name()} event")
                return None
            self._next_event[event.name()] = time.time() + 15
        
        # Set rundate for non-job events
        if not event.job():
            delay = event.delay() or 0
            event.rundate(time.time() + delay)
            if delay:
                self.logger.debug2(f"{logprefix} Event scheduled in {delay} seconds")
        
        # Insert event in sorted order
        if not self._events or event.rundate() > self._events[-1].rundate():
            self._events.append(event)
        else:
            self._events.append(event)
            self._events.sort(key=lambda e: e.rundate())
        
        return event
    
    def delEvent(self, event: Event):
        """Delete event from queue"""
        if not event.name():
            return
        
        # Allow new events for this name
        if self._next_event and event.name() in self._next_event:
            del self._next_event[event.name()]
        
        # Remove matching events
        self._events = [
            e for e in self._events 
            if not (e.name() == event.name() and 
                   (not (event.init() or event.maintenance() or event.taskrun()) or 
                    e.task() == event.task()))
        ]
    
    def nextEvent(self) -> Optional[Event]:
        """Get next ready event"""
        if not (self._events and time.time() >= self._events[0].rundate()):
            return None
        return self._events[0]
    
    def paused(self) -> bool:
        """Check if target is paused"""
        return self._paused
    
    def pause(self):
        """Pause target"""
        self._paused = True
    
    def resume(self):
        """Resume target (renamed from 'continue' which is Python keyword)"""
        self._paused = False
    
    def getFormatedNextRunDate(self) -> str:
        """Get formatted next run date"""
        if self.nextRunDate and self.nextRunDate > 1:
            return time.ctime(self.nextRunDate)
        return "now"
    
    def getMaxDelay(self) -> int:
        """Get max delay"""
        return self.maxDelay
    
    def setMaxDelay(self, maxDelay: int):
        """Set max delay"""
        self.maxDelay = maxDelay
        self._saveState()
    
    def isType(self, testtype: str) -> bool:
        """Check if target is of given type"""
        if not testtype:
            return False
        target_type = self.getType()
        return target_type == testtype if target_type else False
    
    def is_type(self, testtype: str) -> bool:
        """Alias for isType (snake_case version)"""
        return self.isType(testtype)
    
    def get_type(self) -> Optional[str]:
        """Alias for getType (snake_case version)"""
        return self.getType()
    
    def isGlpiServer(self) -> bool:
        """Check if target is GLPI server (override in subclasses)"""
        return False
    
    def computeNextRunDate(self, timeref: Optional[float] = None) -> float:
        """Compute next run date with random delay"""
        if timeref is None:
            timeref = time.time()
        
        if self.initialDelay:
            timeref += self.initialDelay - int(random.random() * self.initialDelay / 2)
            self.initialDelay = None
        else:
            # Compute random delay reduction
            max_random_delay = 3600  # 1 hour max
            if self.maxDelay < 21600:  # < 6 hours
                max_random_delay = self.maxDelay / 6
            elif self.maxDelay > 86400:  # > 24 hours  
                max_random_delay = self.maxDelay / 24
            
            timeref += self.maxDelay - int(random.random() * max_random_delay)
        
        return timeref
    
    def _loadState(self):
        """Load target state from storage"""
        data = self.storage.restore(name='target')
        
        if data:
            for key in ['maxDelay', 'nextRunDate', 'id', 'baseRunDate']:
                if key in data and data[key] is not None:
                    setattr(self, key, data[key])
            
            if data.get('is_glpi_server'):
                self.isGlpiServer(True)
    
    def _saveState(self):
        """Save target state to storage"""
        data = {
            'maxDelay': self.maxDelay,
            'nextRunDate': self.nextRunDate,
            'baseRunDate': self.baseRunDate,
            'type': self.getType(),
            'id': self.id
        }
        
        if self.isType('server'):
            if self.isGlpiServer():
                data['is_glpi_server'] = True
            if hasattr(self, 'getUrl'):
                url = self.getUrl()
                data['url'] = str(url)
        elif self.isType('local'):
            if hasattr(self, 'getPath'):
                data['path'] = self.getPath()
        
        self.storage.save(name='target', data=data)
    
    def _needToReloadState(self) -> bool:
        """Check if state needs reloading"""
        if self._next_reload_check and time.time() < self._next_reload_check:
            return False
        
        self._next_reload_check = time.time() + 30
        return self.storage.modified(name='target')
    
    def getTaskVersion(self) -> str:
        """Get task version"""
        return self._glpi
    
    def responses(self, responses: Optional[Any] = None) -> Any:
        """Get or set responses"""
        if responses is None:
            return getattr(self, '_responses', None)
        self._responses = responses
        return responses
    
    # Abstract methods that subclasses must implement
    def getName(self) -> str:
        """Return target name (must be implemented by subclasses)"""
        raise NotImplementedError("Subclasses must implement getName()")
    
    def getType(self) -> str:
        """Return target type (must be implemented by subclasses)"""
        raise NotImplementedError("Subclasses must implement getType()")
    
    def plannedTasks(self, tasks: Optional[List[str]] = None) -> List[str]:
        """Get or set planned tasks (must be implemented by subclasses)"""
        raise NotImplementedError("Subclasses must implement plannedTasks()")