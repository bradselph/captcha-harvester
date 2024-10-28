from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
import os
import logging

class Browser(Chrome):
    def __init__(self, executable: str = None, options: list = None, experimental_options: dict = None):
        """
        Initialize the browser

        Args:
            executable: Path to ChromeDriver executable
            options: List of Chrome options
            experimental_options: Dictionary of experimental options
        """
        self.executable = executable
        if executable and not os.path.isfile(executable):
            self.executable = None

        self.options = ChromeOptions()

        # Add options
        if options:
            for option in options:
                self.options.add_argument(option)

        # Add experimental options
        if experimental_options:
            if 'prefs' in experimental_options:
                self.options.add_experimental_option('prefs', experimental_options['prefs'])
            if 'excludeSwitches' in experimental_options:
                self.options.add_experimental_option('excludeSwitches',
                                                  experimental_options['excludeSwitches'])
            if 'useAutomationExtension' in experimental_options:
                self.options.add_experimental_option('useAutomationExtension',
                                                  experimental_options['useAutomationExtension'])

    def start(self, url: str = None) -> None:
        """Start the browser"""
        service = Service(self.executable) if self.executable else Service(ChromeDriverManager().install())
        super(Browser, self).__init__(service=service, options=self.options)

        if url:
            self.get(url)
            self.wait_for_ready_state()

    def wait_for_ready_state(self, timeout: int = 30) -> bool:
        """Wait for page to be ready"""
        try:
            return WebDriverWait(self, timeout).until(
                lambda driver: driver.execute_script('return document.readyState;') == 'complete'
            )
        except Exception:
            return False

    @property
    def is_website_ready(self) -> bool:
        return self.execute_script('return document.readyState;') == 'complete'

    @property
    def is_open(self) -> bool:
        try:
            log = self.get_log('driver')
            if not log:
                return True
            return log[0].get('message') != DRIVER_CLOSED_MESSAGE
        except Exception:
            return False

    def find_element_safe(self, by: By, value: str, timeout: int = 10):
        """Safe element finding with wait"""
        try:
            return WebDriverWait(self, timeout).until(
                EC.presence_of_element_located((by, value))
            )
        except Exception:
            return None

    def execute_script_safe(self, script: str, *args):
        """Safely execute JavaScript"""
        try:
            return self.execute_script(script, *args)
        except Exception as e:
            logging.error(f"Script execution failed: {e}")
            return None
