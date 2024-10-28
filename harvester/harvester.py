from .browser import Browser
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import requests
from requests_html import HTML
import pathlib
import random
import os
import datetime
from distutils.dir_util import copy_tree
import logging
import sys

class Harvester(Browser):
    harvester_count = 0

    BASE_DIR = pathlib.Path(os.path.dirname(os.path.realpath(__file__)))
    PROFILES_DIR = BASE_DIR / 'chrome_profiles' / 'harvester'
    EXTENSION_BLUEPRINT_DIR = BASE_DIR / 'extension'

    def __init__(self, url: str, sitekey: str, proxy: str = None, log_in: bool = False,
                 chrome_executable: str = None, chromedriver_executable: str = None,
                 download_js: bool = True, auto_close_login: bool = True,
                 open_youtube: bool = False, harvester_width: int = 420,
                 harvester_height: int = 600, youtube_width: int = 480,
                 youtube_height: int = 380):
        """Initialize the Harvester"""

        self.setup_paths()

        super().__init__(
            executable=chromedriver_executable,
            options=self.get_chrome_options(proxy),
            experimental_options=self.get_experimental_options()
        )

        self.configure_instance(
            url, sitekey, proxy, log_in, chrome_executable,
            download_js, auto_close_login, open_youtube,
            harvester_width, harvester_height,
            youtube_width, youtube_height
        )

    def setup_paths(self):
        """Setup all required directories and paths"""
        self.PROFILES_DIR.mkdir(parents=True, exist_ok=True)

        self.profile_path = self.PROFILES_DIR / str(Harvester.harvester_count)
        self.extension_path = self.profile_path / 'extension'
        self.proxy_auth_extension_path = self.profile_path / 'proxy_auth_extension'

        self.profile_path.mkdir(parents=True, exist_ok=True)
        self.extension_path.mkdir(parents=True, exist_ok=True)
        self.proxy_auth_extension_path.mkdir(parents=True, exist_ok=True)

        if self.EXTENSION_BLUEPRINT_DIR.exists():
            copy_tree(str(self.EXTENSION_BLUEPRINT_DIR), str(self.extension_path))
        else:
            logging.error(f"Extension blueprint directory not found at: {self.EXTENSION_BLUEPRINT_DIR}")
            raise FileNotFoundError(f"Extension directory not found: {self.EXTENSION_BLUEPRINT_DIR}")

    def configure_instance(self, url, sitekey, proxy, log_in, chrome_executable,
                         download_js, auto_close_login, open_youtube,
                         harvester_width, harvester_height,
                         youtube_width, youtube_height):
        """Configure the harvester instance"""
        self.url = url
        self.sitekey = sitekey
        self.proxy = proxy
        self.log_in = log_in
        self.chrome_executable = chrome_executable
        self.download_js = download_js
        self.auto_close_login = auto_close_login
        self.open_youtube = open_youtube
        self.harvester_width = harvester_width
        self.harvester_height = harvester_height
        self.youtube_width = youtube_width
        self.youtube_height = youtube_height

        self.setup_paths()

        chrome_options = self.create_chrome_options()
        experimental_options = self.create_experimental_options()

        super().__init__(
            executable=chromedriver_executable,
            options=chrome_options,
            experimental_options=experimental_options
        )

        self.response_queue = []
        self.control_element = f'controlElement{random.randint(0, 10**10)}'
        self.is_youtube_setup = False
        self.ticking = False
        self.closed = False

        Harvester.harvester_count += 1

    def create_chrome_options(self) -> list:
        """Create Chrome options for the browser"""
        options = [
            f'--window-size={self.harvester_width},{self.harvester_height}',
            f'--user-data-dir={self.profile_path}',
            '--disable-infobars',
            '--disable-menubar',
            '--disable-toolbar',
            '--mute-audio',
            '--log-level=3',
            '--disable-notifications',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-gpu',
        ]
        chrome_experimental_options = {
            'prefs': {'profile': {'exit_type': 'Normal'}}
        }

        self.use_proxy_extension = False

        if proxy:
            if len(proxy.split(':')) >= 4:

                self.use_proxy_extension = True
                chrome_options.append('--proxy-server=' + proxy.split(':')[0] + ':' + proxy.split(':')[1])
                manifest_json, background_js = self.get_proxy_auth_extension(proxy)

                with open(self.proxy_auth_extension_path + '/manifest.json', 'w') as file:
                    file.write(manifest_json)

                with open(self.proxy_auth_extension_path + '/background.js', 'w') as file:
                    file.write(background_js)

                chrome_options.append(f'--load-extension={self.proxy_auth_extension_path}')
            else:
                chrome_options.append('--proxy-server=' + proxy)

        super(Harvester, self).__init__(executable=self.chromedriver_executable, options=chrome_options, experimental_options=chrome_experimental_options)

        if self.log_in:
            self.start = self.login_decorator(self.start)

        self.ip_done = False

    def login_decorator(self, func):
        def wrapper(*args, **kwargs):
            self.login()
            rv = func(*args, **kwargs)
            return rv
        return wrapper

    def login(self) -> None:

        if self.auto_close_login:
            start_url = LOGIN_AUTO_CLOSE_URL
            # This JS script is opening new window and closing window that was open before to get around the Chrome rule "Scripts may close only the windows that were opened by them.", so after user log in to Google, window can be closed automatically.
            content_js = f'if(document.location.href.includes("{start_url}")){{window.open("{LOGIN_URL}", "", "scrollbars=yes,status=yes,menubar=no,toolbar=no");window.close();}}if(document.location.href.includes("{LOGGED_URL}")){{window.close();}}'
        else:
            start_url = LOGIN_URL
            content_js = ''

        with open(f'{self.extension_path}/content.js', 'w') as f:
            f.write(content_js)

        chrome_args = [
            f'--app={start_url}',
            f'--window-size={self.harvester_width},{self.harvester_height}',
            f'--user-data-dir="{self.profile_path}"',
            '--disable-infobars',
            '--disable-menubar',
            '--disable-toolbar',
            '--log-level=3',
            f'--load-extension="{self.extension_path}"',
        ]

        if self.proxy:
            if self.use_proxy_extension:
                chrome_args.append('--proxy-server=' + self.proxy.split(':')[0] + ':' + self.proxy.split(':')[1])
                chrome_args.append(f'--load-extension="{self.extension_path}","{self.proxy_auth_extension_path}"')
            else:
                chrome_args.append('--proxy-server=' + self.proxy)

        command = ''
        for arg in chrome_args:
            command += f' {arg}'

        chrome_paths = (self.chrome_executable,) + DEFAULT_CHROME_PATHS if self.chrome_executable else DEFAULT_CHROME_PATHS

        for chrome_path in chrome_paths:
            if os.path.isfile(chrome_path):
                command = f'"{chrome_path}"' + command
                os.popen(command).close()
                break

    def setup(self) -> None:
        if not self.is_open:
            return
        if self.is_set:
            return

        captcha_js = "(function(){var w=window,C='___grecaptcha_cfg',cfg=w[C]=w[C]||{},N='grecaptcha';var gr=w[N]=w[N]||{};gr.ready=gr.ready||function(f){(cfg['fns']=cfg['fns']||[]).push(f);};w['__recaptcha_api']='https://www.google.com/recaptcha/api2/';(cfg['render']=cfg['render']||[]).push('onload');w['__google_recaptcha_client']=true;var d=document,po=d.createElement('script');po.type='text/javascript';po.async=true;po.src='https://www.gstatic.com/recaptcha/releases/-FJgYf1d3dZ_QPcZP7bd85hc/recaptcha__en.js';po.crossOrigin='anonymous';po.integrity='sha384-w2lIrXdcsRgXIRsq1Y2C2rGrB0G3iE5CLYGxlFzUAbix3gGjUFYcQavOqddMOp1u';var e=d.querySelector('script[nonce]'),n=e&&(e['nonce']||e.getAttribute('nonce'));if(n){po.setAttribute('nonce',n);}var s=d.getElementsByTagName('script')[0];s.parentNode.insertBefore(po, s);})();"

        harvester_title = f'Harvester {self.id}'
        if self.proxy:
            if len(self.proxy.split(':')) >= 4:
                options.append(f'--proxy-server={self.proxy.split(":")[0]}:{self.proxy.split(":")[1]}')
                self.setup_proxy_auth(self.proxy)
                options.append(f'--load-extension={self.proxy_auth_extension_path}')
            else:
                options.append(f'--proxy-server={self.proxy}')

        return options

    def create_experimental_options(self) -> dict:
        """Create experimental options for Chrome"""
        return {
            'prefs': {
                'profile': {'exit_type': 'Normal'},
                'credentials_enable_service': False,
                'profile.password_manager_enabled': False
            },
            'excludeSwitches': ['enable-automation'],
            'useAutomationExtension': False
        }

    def setup_proxy_auth(self, proxy: str) -> None:
        """Setup proxy authentication if needed"""
        proxy_parts = proxy.split(':')
        if len(proxy_parts) >= 4:
            manifest_json = '''{
                "version": "1.0.0",
                "manifest_version": 2,
                "name": "Chrome Proxy",
                "permissions": [
                    "proxy",
                    "tabs",
                    "unlimitedStorage",
                    "storage",
                    "<all_urls>",
                    "webRequest",
                    "webRequestBlocking"
                ],
                "background": {
                    "scripts": ["background.js"]
                }
            }'''

            background_js = f'''
                var config = {{
                    mode: "fixed_servers",
                    rules: {{
                        singleProxy: {{
                            scheme: "http",
                            host: "{proxy_parts[0]}",
                            port: parseInt({proxy_parts[1]})
                        }},
                        bypassList: ["localhost"]
                    }}
                }};

                chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

                function callbackFn(details) {{
                    return {{
                        authCredentials: {{
                            username: "{proxy_parts[2]}",
                            password: "{proxy_parts[3]}"
                        }}
                    }};
                }}

                chrome.webRequest.onAuthRequired.addListener(
                    callbackFn,
                    {{urls: ["<all_urls>"]}},
                    ['blocking']
                );
            '''

            with open(self.proxy_auth_extension_path / 'manifest.json', 'w') as f:
                f.write(manifest_json)
            with open(self.proxy_auth_extension_path / 'background.js', 'w') as f:
                f.write(background_js)

    def setup_paths(self):
        """Setup all required directories and paths"""
        self.PROFILES_DIR.mkdir(parents=True, exist_ok=True)

        self.profile_path = self.PROFILES_DIR / str(Harvester.harvester_count)
        self.extension_path = self.profile_path / 'extension'
        self.proxy_auth_extension_path = self.profile_path / 'proxy_auth_extension'

        self.profile_path.mkdir(parents=True, exist_ok=True)
        self.extension_path.mkdir(parents=True, exist_ok=True)
        self.proxy_auth_extension_path.mkdir(parents=True, exist_ok=True)

        if self.EXTENSION_BLUEPRINT_DIR.exists():
            copy_tree(str(self.EXTENSION_BLUEPRINT_DIR), str(self.extension_path))
        else:
            logging.error(f"Extension blueprint directory not found at: {self.EXTENSION_BLUEPRINT_DIR}")
            raise FileNotFoundError(f"Extension directory not found: {self.EXTENSION_BLUEPRINT_DIR}")

        return {}

    def reset_harvester(self) -> None:
        """Reset the captcha for a new solve"""
        if not self.is_open:
            return

        try:
            self.execute_script('grecaptcha.reset();')
        except Exception as e:
            logging.error(f"Failed to reset harvester: {e}")

    def window_size_check(self) -> None:
        """Ensure window size remains correct"""
        if not self.is_open:
            return

        try:
            size = self.get_window_size()
            if size['width'] != self.harvester_width or size['height'] != self.harvester_height:
                self.set_window_size(self.harvester_width, self.harvester_height)
        except Exception as e:
            logging.error(f"Failed to check/set window size: {e}")

    def setup_youtube(self) -> None:
        """Setup YouTube window for solving assistance"""
        if not self.is_open or self.is_youtube_setup or not self.open_youtube:
            return

        try:
            self.execute_script(
                    f"window.open('https://www.youtube.com', '_blank', "
                    f"'toolbar=no').resizeTo({self.youtube_width}, {self.youtube_height});"
            )

            if len(self.window_handles) > 1:
                self.switch_to.window(self.window_handles[1])

                # Find and click a video
                video_links = self.find_elements(By.CSS_SELECTOR, 'a#video-title')
                for link in video_links:
                    if link.get_attribute('href'):
                        self.get(link.get_attribute('href'))
                        self.refresh()
                        break

                self.is_youtube_setup = True
                self.switch_to.window(self.window_handles[0])

        except Exception as e:
            logging.error(f"Failed to setup YouTube: {e}")

    def tick(self) -> None:
        """Main update loop for the harvester"""
        self.ticking = True

        try:
            self.setup()
            self.setup_youtube()
            self.response_check()
            self.window_size_check()
        except Exception as e:
            logging.error(f"Harvester tick failed: {e}")
            self.closed = True

        self.ticking = False

    def response_check(self) -> None:
        """Check for and handle new captcha responses"""
        response = self.get_response()
        if response:
            self.reset_harvester()
            self.response_queue.append(response)

    @property
    def is_set(self) -> bool:
        """Check if harvester is properly configured"""
        try:
            return bool(self.find_elements(By.CLASS_NAME, self.control_element))
        except Exception:
            return False

    def pull_response_queue(self) -> list:
        """Get and clear all responses"""
        responses = self.response_queue.copy()
        self.response_queue.clear()
        return responses

    def pull_response(self) -> dict:
        """Get and remove oldest response"""
        return self.response_queue.pop(0) if self.response_queue else {}
