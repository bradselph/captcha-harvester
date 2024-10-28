from .harvester import Harvester
import time
import datetime
import logging
from threading import Thread, Lock
from typing import Optional, Callable, List, Dict, Any

class HarvesterManager:
    def __init__(self, delay: float = 0.1, response_callback: Optional[Callable] = None):
        """
        Initialize the harvester manager

        Args:
            delay: Time between tick updates
            response_callback: Optional callback for new responses
        """
        self.delay = delay
        self.response_callback = response_callback

        self.harvesters: List[Harvester] = []
        self.response_queue: List[Dict[str, Any]] = []
        self.looping = False
        self._lock = Lock()

    def add_harvester(self, harvester: Harvester) -> None:
        """Add a new harvester to manage"""
        with self._lock:
            self.harvesters.append(harvester)

    def remove_harvester(self, harvester: Harvester) -> None:
        """Remove a harvester from management"""
        with self._lock:
            if harvester in self.harvesters:
                self.harvesters.remove(harvester)

    def start_harvesters(self, use_threads: bool = True) -> None:
        """Start all managed harvesters"""
        if use_threads:
            threads = []
            for harvester in self.harvesters:
                thread = Thread(target=harvester.start, daemon=True)
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()
        else:
            for harvester in self.harvesters:
                harvester.start()

    def main_loop(self) -> None:
        """Main update loop for the manager"""
        if self.looping:
            return

        self.looping = True
        while self.looping:
            try:
                self.tick()
                if not self.harvesters:
                    break
                time.sleep(self.delay)
            except Exception as e:
                logging.error(f"Manager loop error: {e}")
                break

        self.looping = False

    def tick(self) -> None:
        """Single update tick"""
        self.pull_responses_from_harvesters()
        self.response_queue_check()

        with self._lock:
            for harvester in self.harvesters[:]:  # Copy list to avoid modification during iteration
                if harvester.closed:
                    self.harvesters.remove(harvester)
                    continue

                if not harvester.ticking:
                    Thread(target=harvester.tick, daemon=True).start()

    def response_queue_check(self) -> None:
        """Remove expired responses"""
        now = datetime.datetime.now()
        with self._lock:
            self.response_queue = [
                response for response in self.response_queue
                if (now - response['timestamp']).seconds < 120
            ]

    def pull_responses_from_harvesters(self) -> None:
        """Collect responses from all harvesters"""
        with self._lock:
            for harvester in self.harvesters:
                responses = harvester.pull_response_queue()
                if self.response_callback:
                    for response in responses:
                        self.response_callback(response)
                else:
                    self.response_queue.extend(responses)

    def stop(self) -> None:
        """Stop the manager and all harvesters"""
        self.looping = False
        with self._lock:
            for harvester in self.harvesters:
                try:
                    harvester.quit()
                except Exception:
                    pass
            self.harvesters.clear()
            self.response_queue.clear()
