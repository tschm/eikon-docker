# coding: utf-8

__all__ = ['DesktopSession']

from appdirs import *
import os
import logging
import platform
import socket
from requests_async import codes as requests_async_codes
from requests_async import ConnectTimeout

from .. import __version__
from .session import Session


class DesktopSession(Session):

    class Params(Session.Params):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

    def __init__(self, app_key, on_state=None, on_event=None, **kwargs):
        super().__init__(app_key=app_key,
                         on_state=on_state,
                         on_event=on_event,
                         token=kwargs.get("token"),
                         dacs_user_name=kwargs.get('dacs_user_name'),
                         dacs_position=kwargs.get("dacs_position"),
                         dacs_application_id=kwargs.get("dacs_application_id"))
        self._http_session.trust_env = False
        self._port = None
        self._udf_url = None
        self._timeout = 30
        self._user = "root"
        self._check_port_result = False

    def _get_udf_url(self):
        """
        Returns the scripting proxy url.
        """
        return self._udf_url

    def _get_http_session(self):
        """
        Returns the scripting proxy http session for requests.
        """
        return self._http_session

    def set_timeout(self, timeout):
        """
        Set the timeout for requests.
        """
        self._timeout = timeout

    def get_timeout(self):
        """
        Returns the timeout for requests.
        """
        return self._timeout

    def set_port_number(self, port_number, logger=None):
        """
        Set the port number to reach Eikon API proxy.
        """
        self._port = port_number
        if port_number:
            self._udf_url = f"http://host.docker.internal:{self._port}/api/v1/data"
            self._streaming_config.host = f"host.docker.internal:{self._port}/api/v1/data/streaming/pricing"
            #self._streaming_config.host = "host.docker.internal:{}/api/rdp/streaming/pricing".format(self._port)
            self.close()
        else:
            self._udf_url = None

        if logger:
            logger.info(f"Set Proxy port number to {self._port}")

    def get_port_number(self):
        """
        Returns the port number
        """
        return self._port

    def is_session_logged(self):
        return self._streaming_session._ws_is_logged

    def _init_streaming_config(self):
        self._streaming_config.application_id = self._dacs_params.dacs_application_id
        self._streaming_config.position = self._dacs_params.dacs_position

        self._streaming_config.login_message = {
            "ID": "",
            "Domain": "Login",
            "Key": {
                "Name": "john doe",
                "Elements": {
                    "AppKey": self.app_key,
                    "ApplicationId": self._dacs_params.dacs_application_id,
                    "Position": self._dacs_params.dacs_position
                }
            }
        }
        # provide app_key to Eikon API Proxy through x_tr_applicationid header when starting websocket
        self._streaming_config._header = [f"x-tr-applicationid: {self.app_key}"]

    #######################################
    #  methods to open and close session  #
    #######################################
    def open(self):
        if self._state in [Session.State.Pending, Session.State.Open]:
            # session is already opened or is opening
            return self._state

        # call Session.open() based on open_async() => _init_streaming_config will be called later
        return super(DesktopSession, self).open()

    def close(self):
        return super(DesktopSession, self).close()

    ############################################
    #  methods to open asynchronously session  #
    ############################################
    async def open_async(self):
        if self._state in [Session.State.Pending, Session.State.Open]:
            # session is already opened or is opening
            return self._state

        await super(DesktopSession, self).open_async()

        port_number = await self.identify_scripting_proxy_port()
        if port_number:
            self.set_port_number(port_number)
            self.log(logging.INFO, f"Application ID: {self.app_key}")
            self._state = Session.State.Open
            self._on_state(Session.State.Open, "Session is opened.")
            self._init_streaming_config()
        else:
            # port number wasn't identified => do nothing ?
            self.log(logging.ERROR, "Port number was not identified, cannot send any request")

        # await super(DesktopSession, self).open_async()

        return self._state

    @staticmethod
    def read_firstline_in_file(filename, logger=None):
        try:
            f = open(filename)
            first_line = f.readline()
            f.close()
            return first_line
        except IOError as e:
            if logger:
                logger.error(f"I/O error({e.errno}): {e.strerror}")
            return ""

    async def identify_scripting_proxy_port(self):
        """
        Returns the port used by the Scripting Proxy stored in a configuration file.
        """

        port = None
        app_names = ["Eikon API proxy", "Eikon Scripting Proxy"]
        app_author = "Thomson Reuters"

        if platform.system() == "Linux":
            path = [user_config_dir(app_name, app_author, roaming=True)
                    for app_name in app_names if os.path.isdir(user_config_dir(app_name, app_author, roaming=True))]
        else:
            path = [user_data_dir(app_name, app_author, roaming=True)
                    for app_name in app_names if os.path.isdir(user_data_dir(app_name, app_author, roaming=True))]

        if len(path):
            port_in_use_file = os.path.join(path[0], ".portInUse")

            # Test if ".portInUse" file exists
            if os.path.exists(port_in_use_file):
                # First test to read .portInUse file
                firstline = self.read_firstline_in_file(port_in_use_file)
                if firstline != "":
                    saved_port = firstline.strip()
                    await self.check_port(saved_port)
                    if self._check_port_result:
                        port = saved_port
                        self.log(logging.INFO, f"Port {port} was retrieved from .portInUse file")

        if port is None:
            self.log(logging.INFO, "Warning: file .portInUse was not found. Try to fallback to default port number.")
            port_list = ["9000", "36036"]
            for port_number in port_list:
                self.log(logging.INFO, f"Try defaulting to port {port_number}...")
                await self.check_port(port_number)
                if self._check_port_result:
                    return port_number

        if port is None:
            self.log(logging.ERROR,
                     "Error: no proxy address identified.\nCheck if Eikon Desktop or Eikon API Proxy is running.")
            return None

        await self.handshake(port)

        return port

    async def check_port(self, port, timeout=(10.0, 15.0)):
        url = f"http://host.docker.internal:{port}/api/v1/data"
        try:
            response = await self._http_session.get(url,
                                   headers={"x-tr-applicationid": self.app_key},
                                   timeout=timeout)

            self.log(logging.INFO, f"Checking port {port} response : {response.status_code} - {response.text}")
            self._check_port_result = True
            return
        except (socket.timeout, ConnectTimeout):
            self.log(logging.ERROR, f"Timeout on checking port {port}")
        except ConnectionError as e:
            self.log(logging.CRITICAL, f"Connexion Error on checking port {port} : {e!r}")
        except Exception as e:
            self.log(logging.DEBUG, f"Error on checking port {port} : {e!r}")
        self._check_port_result = False

    async def handshake(self, port, timeout=(1.0, 2.0)):
        url = f"http://host.docker.internal:{port}/api/handshake"
        self.log(logging.INFO, f"Try to handshake on url {url}...")
        try:
            # DAPI for E4 - API Proxy - Handshake
            _body = {
                    "AppKey": self.app_key,
                    "AppScope": "rapi",
                    "ApiVersion": "1",
                    "LibraryName": "Eikon Python Library",
                    "LibraryVersion": __version__
            }

            _headers = {"Content-Type": "application/json"}
            # _headers['x-app-key'] = self.app_key
            # _headers['x-api-version'] = '1.0.0'
            # _headers['x-library-name'] = 'RDP Python Library'
            # _headers['x-library-version'] = __version__

            response = await self._http_session.post(url,
                                                     headers=_headers,
                                                     json=_body,
                                                     timeout=timeout)
            self.log(logging.INFO, f"Response : {response.status_code} - {response.text}")

            if response.status_code is requests_async_codes.ok:
                result = response.json()
                self._access_token = result.get("access_token")
            else:
                self.log(logging.DEBUG, f"Response {response.status_code} on handshake port {port} : {response.text}")

            return True
        except (socket.timeout, ConnectTimeout):
            self.log(logging.ERROR, f"Timeout on handshake port {port}")
        except Exception as e:
            self.log(logging.ERROR, f"Error on handshake port {port} : {e!r}")
        return False

