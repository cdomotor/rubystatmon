# File: statmon_daemon/scheduler.py
"""
scheduler.py - Simple task scheduler for StatMon daemon

This scheduler allows you to register functions to run at fixed intervals
(in minutes or seconds). It tracks the last run time and only executes
when the interval has elapsed.

Example:
    from scheduler import Scheduler

    scheduler = Scheduler()
    scheduler.every(5).minutes.do(my_function)
    scheduler.every(10).seconds.do(another_function)

    while True:
        scheduler.run_pending()
        time.sleep(1)
"""

import time
import logging

logger = logging.getLogger("statmon_daemon")

class Scheduler:
    def __init__(self):
        self.jobs = []

    def every(self, interval):
        """Start defining a new scheduled job."""
        return JobBuilder(self, interval)

    def add_job(self, func, interval_seconds):
        """Register a new job."""
        self.jobs.append({
            "func": func,
            "interval": interval_seconds,
            "last_run": 0
        })
        logger.info(f"Scheduled job: {func.__name__} every {interval_seconds} seconds")

    def run_pending(self):
        """Run any jobs whose interval has elapsed."""
        now = time.time()
        for job in self.jobs:
            if now - job["last_run"] >= job["interval"]:
                try:
                    logger.debug(f"Running job: {job['func'].__name__}")
                    job["func"]()
                except Exception as e:
                    logger.exception(f"Error running job {job['func'].__name__}: {e}")
                finally:
                    job["last_run"] = now


class JobBuilder:
    """Helper class for fluent syntax: scheduler.every(5).minutes.do(task)"""
    def __init__(self, scheduler, interval):
        self.scheduler = scheduler
        self.interval = interval
        self.unit = None

    @property
    def seconds(self):
        self.unit = "seconds"
        return self

    @property
    def minutes(self):
        self.unit = "minutes"
        return self

    def do(self, func):
        if self.unit == "seconds":
            seconds = self.interval
        elif self.unit == "minutes":
            seconds = self.interval * 60
        else:
            raise ValueError("Time unit not set (use .seconds or .minutes)")
        self.scheduler.add_job(func, seconds)
