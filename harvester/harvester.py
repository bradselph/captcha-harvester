from .browser import Browser
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from requests_html import HTML
import pathlib
import random
import os
import datetime
from distutils.dir_util import copy_tree
import logging


LOGIN_URL = 'https://accounts.google.com'
LOGGED_URL = 'https://myaccount.google.com'
LOGIN_AUTO_CLOSE_URL = 'https://www.google.com'

YOUTUBE_URL = 'https://www.youtube.com/'
YOUTUBE_VIDEO_URL_PREFIX = 'https://www.youtube.com/watch?v='

CAPTCHA_JS_URL = 'https://www.google.com/recaptcha/api.js'

DEFAULT_CHROME_PATHS = ('C:/Program Files (x86)/Google/Chrome/Application/chrome.exe', 'C:/Program Files/Google/Chrome/Application/chrome.exe')


class Harvester(Browser):
    harvester_count = 0

    def __init__(self, url: str, sitekey: str, proxy: str = None, log_in: bool = False,
                 chrome_executable: str = None, chromedriver_executable: str = None,
                 download_js: bool = True, auto_close_login: bool = True,
                 open_youtube: bool = False, harvester_width: int = 420,
                 harvester_height: int = 600, youtube_width: int = 480,
                 youtube_height: int = 380):

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
        os.chdir(os.path.dirname(os.path.realpath(__file__)))
        self.profile_path = pathlib.Path(f'chrome_profiles/harvester/{Harvester.harvester_count}')
        self.extension_path = self.profile_path / 'extension'
        self.proxy_auth_extension_path = self.profile_path / 'proxy_auth_extension'

        pathlib.Path('chrome_profiles/harvester').mkdir(parents=True, exist_ok=True)
        self.profile_path.mkdir(parents=True, exist_ok=True)
        self.proxy_auth_extension_path.mkdir(parents=True, exist_ok=True)

        extension_blueprint_path = pathlib.Path(__file__).parent / 'extension'
        copy_tree(str(extension_blueprint_path), str(self.extension_path))

    def get_chrome_options(self, proxy):
        options = [
            f'--user-data-dir={self.profile_path}',
            '--disable-infobars',
            '--disable-menubar',
            '--disable-toolbar',
            '--mute-audio',
            '--log-level=3',
            "--disable-notifications",
        ]

        if proxy:
            if len(proxy.split(':')) >= 4:
                options.append(f'--proxy-server={proxy.split(":")[0]}:{proxy.split(":")[1]}')
                self.setup_proxy_auth(proxy)
            else:
                options.append(f'--proxy-server={proxy}')

        return options

    def get_experimental_options(self):
        return {
            'prefs': {
                'profile': {'exit_type': 'Normal'},
                'credentials_enable_service': False,
                'profile.password_manager_enabled': False
            }
        }

    def configure_instance(self, url, sitekey, proxy, log_in, chrome_executable,
                         download_js, auto_close_login, open_youtube,
                         harvester_width, harvester_height,
                         youtube_width, youtube_height):
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

        self.response_queue = []
        self.control_element = f'controlElement{random.randint(0, 10**10)}'
        self.is_youtube_setup = False
        self.ticking = False
        self.closed = False

        Harvester.harvester_count += 1
        pathlib.Path(self.profile_path).mkdir(parents=True, exist_ok=True)
        pathlib.Path(self.proxy_auth_extension_path).mkdir(parents=True, exist_ok=True)
        copy_tree(self.extension_blueprint_path, self.extension_path)

        chrome_options = [
            # f'--app={self.url}',
            # Initially opening google to then redirect to harvest website, so when using proxy, the login popup will disappear
            f'--app=http://www.google.com/',
            f'--window-size={self.harvester_width},{self.harvester_height}',
            f'--user-data-dir={self.profile_path}',
            '--disable-infobars',
            '--disable-menubar',
            '--disable-toolbar',
            '--mute-audio',
            '--log-level=3',
            "--disable-notifications",
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
            if self.use_proxy_extension:
                harvester_title += f' (proxy: "{self.proxy.split(":")[0]}:{self.proxy.split(":")[1]}")'
            else:
                harvester_title += f' (proxy: "{self.proxy}")'
        harvester_icon = 'img/icon.png'
        harvester_html = f'<html><head><link rel="icon" href="{harvester_icon}"><title>{harvester_title}</title><script src="{CAPTCHA_JS_URL}" async defer></script></head><body><div class="{self.control_element}"></div><div id="container"><div id="g-recaptcha" class="g-recaptcha" data-sitekey="{self.sitekey}"></div></div></body></html>'
        harvester_loop_script = 'var tick = function(){var divs = document.querySelector("body").children;for(i=0; i<divs.length; i++){divs[i].style.left = 0;divs[i].style.top = 0;}setTimeout(tick, 100);};tick();'
        harvester_container = 'document.getElementById("container")'

        scripts = (
            f"document.documentElement.innerHTML = '{harvester_html}';",
            f'{harvester_container}.style.width = "305px";',
            f'{harvester_container}.style.marginLeft = "auto";',
            f'{harvester_container}.style.marginRight = "auto";',
            f'{harvester_container}.style.marginTop = "242px";',
            harvester_loop_script,
        )

        self.get(self.url) if self.current_url != self.url else None

        for script in scripts:
            self.execute_script(script)

        if self.download_js:
            try:
                captcha_js = requests.get(CAPTCHA_JS_URL).text
            except requests.RequestException:
                pass

        self.execute_script(captcha_js)

    def get_response(self) -> dict:
        if not self.is_open:
            return dict()
        response = self.execute_script('return grecaptcha.getResponse();')
        return {'timestamp': datetime.datetime.now(), 'response': response} if response else dict()

    def pull_response_queue(self) -> list:
        response_queue, self.response_queue = self.response_queue, list()
        return response_queue

    def pull_response(self) -> dict:
        return self.response_queue.pop(0) if self.response_queue else dict()

    def reset_harvester(self) -> None:
        if not self.is_open:
            return

        self.execute_script('grecaptcha.reset();')

    def window_size_check(self) -> None:
        if not self.is_open:
            return

        harvester_size = self.get_window_size()
        if harvester_size['width'] != self.harvester_width or harvester_size['height'] != self.harvester_height:
            self.set_window_size(self.harvester_width, self.harvester_height)

    def response_check(self) -> None:
        response = self.get_response()
        if response:
            self.reset_harvester()
            self.response_queue.append(response)

    def youtube_setup(self) -> None:
        if not self.is_open or self.is_youtube_setup or not self.open_youtube:
            return

        self.execute_script(f"window.open('{YOUTUBE_URL}', '_blank', 'toolbar=no').resizeTo({self.youtube_width}, {self.youtube_height});")

        if len(self.window_handles) > 1:
            self.switch_to.window(self.window_handles[1])
            for link in self.find_elements(By.TAG_NAME, 'a'):
                if not link.get_attribute('href'):
                    continue
                if YOUTUBE_VIDEO_URL_PREFIX in link.get_attribute('href'):
                    self.get(link.get_attribute('href'))
                    self.refresh()
                    break
            self.is_youtube_setup = True

        self.switch_to.window(self.window_handles[0])

    def tick(self) -> None:
        self.ticking = True
        # This try except to be upgraded...
        try:
            # self.show_ip()
            self.setup()
            self.youtube_setup()
            self.response_check()
            self.window_size_check()
        except WebDriverException as e:
            print(e)
            self.closed = True

        self.ticking = False

    @property
    def is_set(self) -> bool:
        try:
            return True if self.find_elements(By.CLASS_NAME, self.control_element) else False
        except:
            return False

    @staticmethod
    def get_sitekey(url: str) -> str:
        try:
            response = requests.get(url, timeout=10)
            if not response.ok:
                return None

            html = HTML(html=response.text)
            captcha_element = html.find('.g-recaptcha')

            if captcha_element:
                return captcha_element[0].attrs.get('data-sitekey')

            # Try finding in script tags
            html_formatted = ''.join(response.text.split())
            sitekey_index = html_formatted.find('sitekey')

            if sitekey_index != -1:
                return html_formatted[sitekey_index + 10:sitekey_index + 50].split("'")[0]

        except Exception as e:
            logging.error(f"Failed to get sitekey: {e}")

        return None

    def setup_proxy_auth(self, proxy):
        proxy_parts = proxy.split(':')
        manifest_json = self.get_proxy_manifest()
        background_js = self.get_proxy_background_js(proxy_parts[2], proxy_parts[3])

        with open(self.proxy_auth_extension_path / 'manifest.json', 'w') as f:
            f.write(manifest_json)
        with open(self.proxy_auth_extension_path / 'background.js', 'w') as f:
            f.write(background_js)

    @staticmethod
    def get_proxy_manifest():
        return '''{
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

    @staticmethod
    def get_proxy_background_js(username, password):
        return f'''
        var config = {{
            mode: "fixed_servers",
            rules: {{
                singleProxy: {{
                    scheme: "http",
                    host: "{username}",
                    port: parseInt({password})
                }},
                bypassList: ["localhost"]
            }}
        }};

        chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

        function callbackFn(details) {{
            return {{
                authCredentials: {{
                    username: "{username}",
                    password: "{password}"
                }}
            }};
        }}

        chrome.webRequest.onAuthRequired.addListener(
            callbackFn,
            {{urls: ["<all_urls>"]}},
            ['blocking']
        );
        '''

    def setup(self) -> None:
        if not self.is_open or self.is_set:
            return

        try:
            self.inject_harvester_html()
            self.configure_harvester_style()
            self.inject_recaptcha_script()
        except Exception as e:
            logging.error(f"Failed to setup harvester: {e}")
            self.closed = True

    def inject_harvester_html(self):
        harvester_html = f'''
        <html>
            <head>
                <title>Harvester {self.id}</title>
                <script src="https://www.google.com/recaptcha/api.js" async defer></script>
            </head>
            <body>
                <div class="{self.control_element}"></div>
                <div id="container">
                    <div id="g-recaptcha" class="g-recaptcha" data-sitekey="{self.sitekey}"></div>
                </div>
            </body>
        </html>
        '''
        self.execute_script(f"document.documentElement.innerHTML = `{harvester_html}`;")

    def configure_harvester_style(self):
        styles = {
            'container': {
                'width': '305px',
                'margin-left': 'auto',
                'margin-right': 'auto',
                'margin-top': '242px'
            }
        }


    def configure_harvester_style(self):
        styles = {
                'container': {
                        'width': '305px',
                        'margin-left': 'auto',
                        'margin-right': 'auto',
                        'margin-top': '242px'
                }
        }

        for element, style in styles.items():
            style_str = '; '.join(f'{k}: {v}' for k, v in style.items())
            self.execute_script(f"document.getElementById('{element}').style = '{style_str}';")

        # Add positioning loop
        self.execute_script('''
            var tick = function(){
                var divs = document.querySelector("body").children;
                for(i=0; i<divs.length; i++){
                    divs[i].style.left = 0;
                    divs[i].style.top = 0;
                }
                setTimeout(tick, 100);
            };
            tick();
        ''')

    def inject_recaptcha_script(self):
        if self.download_js:
            try:
                response = requests.get('https://www.google.com/recaptcha/api.js', timeout=10)
                if response.ok:
                    captcha_js = response.text
                else:
                    captcha_js = self.get_fallback_recaptcha_script()
            except:
                captcha_js = self.get_fallback_recaptcha_script()
        else:
            captcha_js = self.get_fallback_recaptcha_script()

        self.execute_script(captcha_js)

    @staticmethod
    def get_fallback_recaptcha_script():
        return """
        (function(){
            var w=window,C='___grecaptcha_cfg';
            var cfg=w[C]=w[C]||{};
            var gr=w['grecaptcha']=w['grecaptcha']||{};
            gr.ready=gr.ready||function(f){(cfg['fns']=cfg['fns']||[]).push(f);};
            w['__recaptcha_api']='https://www.google.com/recaptcha/api2/';
            (cfg['render']=cfg['render']||[]).push('explicit');
            w['__google_recaptcha_client']=true;
            var d=document,po=d.createElement('script');
            po.type='text/javascript';
            po.async=true;
            po.src='https://www.google.com/recaptcha/api.js?onload=grecaptchaCallback';
            var e=d.querySelector('script[nonce]'),n=e&&(e['nonce']||e.getAttribute('nonce'));
            if(n){po.setAttribute('nonce',n);}
            var s=d.getElementsByTagName('script')[0];
            s.parentNode.insertBefore(po,s);
        })();
        """

    def get_response(self) -> dict:
        """Get the current captcha response if available"""
        if not self.is_open:
            return {}

        try:
            response = self.execute_script('return grecaptcha.getResponse();')
            if response:
                return {
                        'timestamp': datetime.datetime.now(),
                        'response': response
                }
        except Exception as e:
            logging.error(f"Failed to get response: {e}")

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
