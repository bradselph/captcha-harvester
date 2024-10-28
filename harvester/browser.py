from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os
import logging

DRIVER_CLOSED_MESSAGE = 'Unable to evaluate script: disconnected: not connected to DevTools\n'

logging.getLogger('WDM').setLevel(logging.NOTSET)
os.environ['WDM_LOG_LEVEL'] = '0'


class Browser(Chrome):
    def __init__(self, executable: str = None, options: list = None, experimental_options: dict = None):
        self.executable = executable
        if executable and not os.path.isfile(executable):
            self.executable = None

        self.options = ChromeOptions()

        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-gpu')
        self.options.add_argument('--disable-infobars')
        self.options.add_argument('--disable-notifications')

        if options:
            for option in options:
                self.options.add_argument(option)

        self.options.add_argument("--lang=en-US")

        if experimental_options:
            for name, value in experimental_options.items():
                self.options.add_experimental_option(name, value)

        self.options.add_experimental_option('excludeSwitches', ['enable-automation'])
        self.options.add_experimental_option('useAutomationExtension', False)

    def start(self, url: str = None) -> None:
        service = Service(self.executable) if self.executable else Service(ChromeDriverManager().install())
        super(Browser, self).__init__(service=service, options=self.options)

        if url:
            self.get(url)
            self.wait_for_ready_state()

    def wait_for_ready_state(self, timeout: int = 30) -> bool:
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
        """Safe script execution with error handling"""
        try:
            return self.execute_script(script, *args)
        except Exception as e:
            logging.error(f"Script execution failed: {e}")
            return None
