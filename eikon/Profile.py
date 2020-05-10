# coding: utf-8

__all__ = ['set_app_key', 'get_app_key',
           'set_timeout', 'get_timeout',
           'set_port_number', 'get_port_number',
           'set_log_level', 'set_log_path',
           #'set_app_id', 'get_app_id',
           'set_on_state_callback', 'set_on_event_callback',
           'Profile', 'get_desktop_session']

from appdirs import *
import socket
import deprecation
import platform
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from requests import Session
from requests.exceptions import ConnectTimeout
from .tools import is_string_type
from .eikonError import EikonError
from eikon import __version__
from .streaming_session import DesktopSession


def set_app_key(app_key):
    """
    Set the app key.

    Parameters
    ----------
    app_key : string
        the app key
    Notes
    -----
    The app key identifies your application on Refinitiv Platform.
    You can get an app key using the App Key Generator (this App is available in Eikon Desktop).
    """
    get_profile().set_app_key(app_key)


def get_app_key():
    """
    Returns the app key previously set

    Notes
    -----
    The app key identifies your application on Refinitiv Platform.
    You can get an application ID using the App Key Generator (this App is available in Eikon Desktop).
    """
    return get_profile().get_app_key()


def get_desktop_session():
    """
    Returns the desktop session for streaming access

    Notes
    -----
    The desktop session is use to initialize streaming subscription.
    """
    return get_profile()._get_desktop_session()


def set_on_state_callback(on_state):
    """
    Set the callback for desktop session state notification.

    Parameters
    ----------
    on_state : function that accepts session, state_ and state_msg as parameters.
    """
    get_profile().set_on_state_callback(on_state)


def set_on_event_callback(on_event):
    """
    Set the callback for desktop session event notification.

    Parameters
    ----------
    on_event : function that accepts session, event_code and event_msg as parameters.
    """
    get_profile().set_on_event_callback(on_event)


def set_timeout(timeout):
    """
    Set the timeout for each request.

    Parameters
    ----------
    timeout : int
        the request timeout in sec
        Default value: 30 sec
    """
    get_profile().set_timeout(timeout)


def get_timeout():
    """
    Returns the request timeout in sec
    """
    return get_profile().get_timeout()


def set_port_number(port_number):
    """
    Set the port number to communicate with the Eikon Data API proxy.
    This port number is detected automatically but you can call this function to force it manually for troubleshooting issues.

    Parameters
    ----------
    port_number : int
        the port number
    """
    get_profile().set_port_number(port_number)


def get_port_number():
    """
    Returns the port number used to communicate with the Eikon Data API Proxy
    """
    return get_profile().get_port_number()


def get_profile():
    """
    Returns the Profile singleton
    """
    return Profile.get_profile()


def set_log_level(level):
    """
    Set the log level.
    When logs are activated (log_level != logging.NOTSET), log files are created in the current directory.
    To change directory for log files, set log path with set_log_path() function.

    Parameters
    ----------
    level : int
        Possible values from logging module : [CRITICAL, FATAL, ERROR, WARNING, WARN, INFO, DEBUG, NOTSET]

    Example
    -------
        ek.set_log_level(logging.DEBUG)

    """
    get_profile().set_log_level(level)


def set_log_path(path):
    """
    Set the filepath of the log file.

    Parameters
    ----------
    path : string
        File path location for log files

    Example
    -------
        ek.set_log_path("c:\\my_directory")
    """
    get_profile().set_log_path(path)


class Profile(object):

    TRACE = 5
    MAX_LOG_SIZE = 10000000

    # singleton profile
    __profile = None

    @classmethod
    def get_profile(cls):
        """
        Returns the Profile singleton
        """
        if cls.__profile is None:
            cls.__profile = Profile()
        return cls.__profile

    def __init__(self):
        """
        Initialization of the __profile.
        """
        self.log_path = None
        self.log_level = logging.NOTSET

        logging.addLevelName(5, 'TRACE')
        self.logger = logging.getLogger('pyeikon')
        setattr(self.logger, 'trace', lambda *args: self.logger.log(5, *args))

        self.app_key = None
        self._desktop_session = None
        self._on_state_cb = None
        self._on_event_cb = None

        self._http_session = Session()
        self._http_session.trust_env = False
        self.port = None
        self.url = None
        self.streaming_url = None
        self.timeout = 30

    def __del__(self):
        print('Delete a Profile')

    def __delete__(self, instance):
        self.log(1, f'Delete the Profile instance {instance}')

    def set_app_key(self, app_key):
        """
        Set the application id.
        """
        if app_key is None:
            raise AttributeError('App key value is None')
        else:
            if not is_string_type(app_key):
                raise AttributeError('App key must be a string')

            self.logger.info('Set App Key: {}'.format(self.app_key))
            self.app_key = app_key
            port_number = identify_scripting_proxy_port(self._http_session, self.app_key)
            self.set_port_number(port_number)

            if self._desktop_session:
                self.log(1, 'Reinit a Desktop session with new app_key')
                self._desktop_session.close()
                self._desktop_session._app_key = app_key  # = DesktopSession(app_key, self._on_state, self._on_event)
            else:
                self._desktop_session = DesktopSession(app_key, self._on_state, self._on_event)

            self._desktop_session.open()

            self.check_profile()

    def set_on_state_callback(self, on_state):
        self._on_state_cb = on_state

    def set_on_event_callback(self, on_event):
        self._on_event_cb = on_event

    def _on_state(self, session, state_code, state_msg):
        if self._on_state_cb:
            self._on_state_cb(self, state_code, state_msg)

    def _on_event(self, session, event_code, event_msg):
        if self._on_event_cb:
            self._on_event_cb(self, event_code, event_msg)

    def _get_desktop_session(self):
        return self._desktop_session

    def get_app_key(self):
        """
        Returns the app key.
        """
        return self.app_key

    def get_url(self):
        """
        Returns the scripting proxy url.
        """
        return self.url

    def get_streaming_url(self):
        """
        Returns the streaming_session proxy url.
        """
        return self.streaming_url

    def _get_http_session(self):
        """
        Returns the scripting proxy _http_session for requests.
        """
        return self._http_session

    def set_timeout(self, timeout):
        """
        Set the timeout in seconds for each request.
        """
        self.timeout = timeout
        self.logger.info('Set timeout to {} seconds'.format(self.timeout))

    def get_timeout(self):
        """
        Returns the timeout for requests.
        """
        return self.timeout

    def set_port_number(self, port_number):
        """
        Set the port number to reach Eikon API proxy.
        """
        self.port = port_number
        if port_number is not None:
            self.url = "http://host.docker.internal:{}/api/v1/data".format(self.port)
        else:
            self.url = None

        self.logger.info('Set Proxy port number to {}'.format(self.port))

    def get_port_number(self):
        """
        Returns the port number
        """
        return self.port

    def set_log_path(self, log_path):
        """
        Set the path where log files will be created.

        Parameters
        ----------
        log_path : path directory
            Default: current directory (beside *.py running file)
        Return True if log_path exists and is writable
        """
        if os.access(log_path, os.W_OK):
            self.log_path = log_path
            return True
        else:
            return False

    def set_log_level(self, log_level):
        """
        Set the log level.
        By default, logs are disabled.

        Parameters
        ----------
        log_level : int
            Possible values from logging module : [CRITICAL, FATAL, ERROR, WARNING, WARN, INFO, DEBUG, NOTSET]
        """
        if log_level > logging.NOTSET:
            __formatter = logging.Formatter("%(asctime)s -- %(name)s -- %(levelname)s -- %(message)s \n")
            __filename = 'pyeikon.{}.log'.format(datetime.now().strftime('%Y%m%d.%H-%M-%S'))

            if self.log_path is not None:
                if not os.path.isdir(self.log_path):
                    os.makedirs(self.log_path)
                __filename = os.path.join(self.log_path, __filename)

            __handler = logging.handlers.RotatingFileHandler(__filename, mode='a', maxBytes=self.MAX_LOG_SIZE,
                                                        backupCount=10, encoding='utf-8')
            __handler.setFormatter(__formatter)
            self.logger.addHandler(__handler)

        self.logger.setLevel(log_level)
        self.log_level = log_level

    def get_log_level(self):
        """
        Returns the log level
        """
        return self.logger.level

    def log(self, log_level, message):
        self.logger.log(log_level, message)

    def check_profile(self):
        if self.port is not None:
            self.logger.info('Port {} on local proxy was detected'.format(self.get_port_number()))
        else:
            # port number wasn't identified => raise EikonError exception
            self.logger.error('Port number was not identified.\nCheck if Eikon Desktop or Eikon API Proxy is running.')
            raise EikonError(-1, 'Port number was not identified. Check if Eikon Desktop or Eikon API Proxy is running.')


def read_firstline_in_file(filename):
    logger = get_profile().logger
    try:
        f = open(filename)
        first_line = f.readline()
        f.close()
        return first_line
    except IOError as e:
        logger.error('IO error({}): {1}'.format(e.errno, e.strerror))
        return ''


def identify_scripting_proxy_port(http_session, application_key):
    """
    Returns the port used by the Scripting Proxy stored in a configuration file.
    """

    port = None
    logger = get_profile().logger
    app_names = ['Eikon API proxy', 'Eikon Scripting Proxy']
    app_author = 'Thomson Reuters'

    if platform.system() == 'Linux':
        path = [user_config_dir(app_name, app_author, roaming=True)
                for app_name in app_names if os.path.isdir(user_config_dir(app_name, app_author, roaming=True))]
    else:
        path = [user_data_dir(app_name, app_author, roaming=True)
                for app_name in app_names if os.path.isdir(user_data_dir(app_name, app_author, roaming=True))]

    if len(path):
        port_in_use_file = os.path.join(path[0], '.portInUse')

        # Test if '.portInUse' file exists
        if os.path.exists(port_in_use_file):
            # First test to read .portInUse file
            firstline = read_firstline_in_file(port_in_use_file)
            if firstline != '':
                saved_port = firstline.strip()
                if check_port(http_session, application_key, saved_port):
                    port = saved_port
                    logger.info('Port {} was retrieved from .portInUse file'.format(port))

    if port is None:
        logger.info('Warning: file .portInUse was not found. Try to fallback to default port number.')
        port_list = ['9000', '36036']
        for port_number in port_list:
            logger.info('Try defaulting to port {}...'.format(port_number))
            if check_port(http_session, application_key, port_number):
                return port_number

    handshake(http_session, application_key, port)
    return port


def check_port(http_session, application_key, port, timeout=(10.0, 20.0)):
    logger = get_profile().logger
    url = "http://host.docker.internal:{}/api/v1/data".format(port)
    try:
        response = http_session.get(url,
                                    headers = {'x-tr-applicationid': application_key},
                                    timeout=timeout)

        logger.info('Response : {} - {}'.format(response.status_code, response.text))
        return True
    except (socket.timeout, ConnectTimeout):
        logger.error('Timeout on checking port {}'.format(port))
    except Exception as e:
        logger.error('Error on checking port {} : {}'.format(port, e.__str__()))
    return False


def handshake(http_session, application_key, port, timeout=(10.0, 20.0)):
    logger = get_profile().logger
    url = "http://host.docker.internal:{}/api/handshake".format(port)
    logger.info('Try to handshake on url {}...'.format(url))
    try:
        user_ident = 'Profile.py_handshake[]'.format(os.getpid())
        body = {'id': user_ident, 'client': {'id':'EikonPython', 'version': __version__, 'supportedApiVersion': '1'}}
        response = http_session.post(url,
                                     headers = {'x-tr-applicationid': application_key, 'Content-Type':'application/json'},
                                     json = body,
                                     timeout=timeout)

        logger.info('Response : {} - {}'.format(response.status_code, response.text))
        return True
    except (socket.timeout, ConnectTimeout):
        logger.error('Timeout on handshake port {}'.format(port))
    except Exception as e:
        logger.error('Error on handshake port {} : {}'.format(port, e.__str__()))
    return False
