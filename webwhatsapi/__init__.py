"""
WhatsAPI module
"""

import datetime
import time
import os
import sys
import logging
import pickle
import tempfile

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException


class WhatsAPIDriverStatus(object):
    Unknown = 'Unknown'
    NoDriver = 'NoDriver'
    NotConnected = 'NotConnected'
    NotLoggedIn = 'NotLoggedIn'
    LoggedIn = 'LoggedIn'


class WhatsAPIDriver(object):
    _PROXY = None

    _URL = "https://web.whatsapp.com"

    _SELECTORS = {
        'firstrun': "#wrapper",
        'qrCode': "img[alt=\"Scan me!\"]",
        'mainPage': ".app.two",
        'chatList': ".infinite-list-viewport",
        'messageList': "#main > div > div:nth-child(1) > div > div.message-list",
        'unreadMessageBar': "#main > div > div:nth-child(1) > div > div.message-list > div.msg-unread",
        'searchBar': ".input",
        'searchCancel': ".icon-search-morph",
        'chats': ".infinite-list-item",
        'chatBar': 'div.input',
        'sendButton': 'button.icon:nth-child(3)',
        'LoadHistory': '.btn-more',
        'UnreadBadge': '.icon-meta',
        'UnreadChatBanner': '.message-list',
        'ReconnectLink': '.action',
        'WhatsappQrIcon': 'span.icon:nth-child(2)',
        'QRReloader': '.qr-wrapper-container'
    }

    _CLASSES = {
        'unreadBadge': 'icon-meta',
        'messageContent': "message-text",
        'messageList': "msg"
    }

    logger = logging.getLogger("whatsapi")
    driver = None

    # Profile points to the Firefox profile for firefox and Chrome cache for chrome
    # Do not alter this
    _profile = None

    def save_firefox_profile(self):
        "Function to save the firefox profile to the permanant one"
        self.logger.info("Saving profile from %s to %s" % (self._profile.path, self._profile_path))
        os.system("cp -R " + self._profile.path + " "+ self._profile_path)
        cookie_file = os.path.join(self._profile_path, "cookies.pkl")
        if self.driver:
            pickle.dump(self.driver.get_cookies() , open(cookie_file,"wb"))

    def set_proxy(self, proxy):
        self.logger.info("Setting proxy to %s" % proxy)
        proxy_address, proxy_port = proxy.split(":")
        self._profile.set_preference("network.proxy.type", 1)
        self._profile.set_preference("network.proxy.http", proxy_address)
        self._profile.set_preference("network.proxy.http_port", int(proxy_port))
        self._profile.set_preference("network.proxy.ssl", proxy_address)
        self._profile.set_preference("network.proxy.ssl_port", int(proxy_port))

    def __init__(self, client="firefox", username="API", proxy=None, command_executor = None):
        "Initialises the webdriver"

        # Get the name of the config folder
        self.config_dir = os.path.join(os.path.expanduser("~"), ".whatsapi")

        try:
            if not os.path.exists(self.config_dir):
                os.makedirs(self.config_dir)
        except OSError:
            print("Error: Could not create config dir")
            exit(-1)

        self.logger.setLevel(logging.DEBUG)

        # Setting the log message format and log file
        log_file_handler = logging.FileHandler(os.path.join(self.config_dir, "whatsapi.log"))
        log_file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.logger.addHandler(log_file_handler)

        self.client = client.lower()
        if self.client == "firefox":
            # TODO: Finish persistant sessions. As of now, persistant sessions do not work for Firefox. You will need to scan each time.
            self._profile_path = os.path.join(self.config_dir, "profile")
            self.logger.info("Checking for profile at %s" % self._profile_path)
            if not os.path.exists(self._profile_path):
                self.logger.info("Profile not found. Creating profile")
                self._profile = webdriver.FirefoxProfile()
                self.save_firefox_profile()
            else:
                self.logger.info("Profile found")
                self._profile = webdriver.FirefoxProfile(self._profile_path)
            if proxy is not None:
                self.set_proxy(proxy)
            self.logger.info("Starting webdriver")
            self.driver = webdriver.Firefox(self._profile)

        elif self.client == "chrome":
            self._profile = webdriver.chrome.options.Options()
            self._profile_path = os.path.join(self.config_dir, 'chrome_cache')
            self._profile.add_argument("user-data-dir=%s" % self._profile_path)
            if proxy is not None:
                profile.add_argument('--proxy-server=%s' % proxy)
            self.driver = webdriver.Chrome(chrome_options=self._profile)

        elif client == 'remote':
            capabilities = DesiredCapabilities.FIREFOX.copy()
            self.driver = webdriver.Remote(
                command_executor=command_executor,
                desired_capabilities=capabilities
            )

        else:
            self.logger.error("Invalid client: %s" % client)
            print("Enter a valid client name")
        self.username = username
        self.driver.get(self._URL)
        self.driver.implicitly_wait(10)

    def wait_till_login(self):
        """Waits for the QR to go away"""
        WebDriverWait(self.driver, 90).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, self._SELECTORS['mainPage']))
        )

    def get_qr(self):
        """Get pairing QR code from client"""
        if "Click to reload QR code" in self.driver.page_source:
            self.reload_qr()
        qr = self.driver.find_element_by_css_selector(self._SELECTORS['qrCode'])
        fd, fn_png = tempfile.mkstemp(prefix=self.username, suffix='.png')
        self.logger.debug("QRcode image saved at %s" % fn_png)
        print(fn_png)
        qr.screenshot(fn_png)
        os.close(fd)
        return fn_png

    def screenshot(self, filename):
        self.driver.get_screenshot_as_file(filename)

    def view_unread(self):
        return self.view_messages(unread_only=True)

    def view_messages(self, unread_only=False):
        try:
            script_path = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_path = os.getcwd()
        script = open(os.path.join(script_path, "js_scripts/get_messages.js"), "r").read()
        Store = self.driver.execute_script(script, unread_only)
        return Store

    def send_to_whatsapp_id(self, id, message):
        try:
            script_path = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_path = os.getcwd()
        script = open(os.path.join(script_path, "js_scripts/send_message_to_whatsapp_id.js"), "r").read()
        success = self.driver.execute_script(script, id, message)
        return success

    def get_id_from_number(self, name):
        try:
            script_path = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_path = os.getcwd()
        script = open(os.path.join(script_path, "js_scripts/id_from_name.js"), "r").read()
        id = self.driver.execute_script(script, name)
        return id

    def send_to_phone_number(self, pno, message):
        try:
            script_path = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_path = os.getcwd()
        script = open(os.path.join(script_path, "js_scripts/send_message_to_phone_number.js"), "r").read()
        success = self.driver.execute_script(script, pno, message)
        return success

    def get_groups(self):
        try:
            script_path = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_path = os.getcwd()
        script = open(os.path.join(script_path, "js_scripts/get_groups.js"), "r").read()
        success = self.driver.execute_script(script)
        return success

    def __unicode__(self):
        return self.username

    def __str__(self):
        return self.__unicode__()

    def reload_qr(self):
        self.driver.find_element_by_css_selector(self._SELECTORS['qrCode']).click()

    def create_callback(self, callback_function):
        try:
            while True:
                messages = self.view_unread()
                if messages != []:
                    callback_function(messages)
                time.sleep(5)
        except KeyboardInterrupt:
            self.logger.debug("Exited")

    def get_status(self):
        if self.driver is None:
            return WhatsAPIDriverStatus.NotConnected
        if self.driver.session_id is None:
            return WhatsAPIDriverStatus.NotConnected
        try:
            self.driver.find_element_by_css_selector(self._SELECTORS['mainPage'])
            return WhatsAPIDriverStatus.LoggedIn
        except NoSuchElementException:
            pass
        try:
            self.driver.find_element_by_css_selector(self._SELECTORS['qrCode'])
            return WhatsAPIDriverStatus.NotLoggedIn
        except NoSuchElementException:
            pass
        return WhatsAPIDriverStatus.Unknown
