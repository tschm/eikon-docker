# coding: utf-8

__all__ = ['Session', 'DacsParams']

import os
import logging
import socket
import requests_async as requests
import asyncio
import nest_asyncio
import time
from logging.handlers import RotatingFileHandler
from enum import Enum, unique
from datetime import datetime
from threading import Lock, Event, current_thread
from .stream_connection import StreamConnection
from ..eikonError import EikonError


# Load nest_asyncio to allow multiple calls to run_until_complete available
nest_asyncio.apply()


class DacsParams(object):

    def __init__(self, *args, **kwargs):
        self.dacs_username = kwargs.get("dacs_user_name", "user")
        self.dacs_application_id = kwargs.get("dacs_application_id", "256")
        self.dacs_position = kwargs.get("dacs_position")
        if self.dacs_position in [None, '']:
            try:
                position_host = socket.gethostname()
                self.dacs_position = "{}/{}".format(socket.gethostbyname(position_host), position_host)
            except socket.gaierror:
                self.dacs_position = "127.0.0.1/net"
        self.authentication_token = kwargs.get("authentication_token")


class Session(object):

    @unique
    class State(Enum):
        """
        Define the state of the session.
            Closed : The session is closed and ready to be opened.
            Pending : the session is in a pending state.
                Upon success, the session will move into an open state, otherwise will be closed.
            Open : The session is opened and ready for use.
        """
        Closed = 1
        Pending = 2
        Open = 3

    @classmethod
    def _state_msg(cls, state):
        if isinstance(state, Session.State):
            if state == Session.State.Opened:
                return "Session is Opened"
            if state == Session.State.Closed:
                return "Session is Closed"
            if state == Session.State.Pending:
                return "Session is Pending"
        return "Session is in an unknown state"  # Should not process this code path

    @unique
    class EventCode(Enum):
        """
        Each session can report different status events during it's lifecycle.
            StreamPending : Denotes the connection to the stream service within the session is pending.
            StreamConnected : Denotes the connection to the stream service has been successfully established.
            StreamDisconnected : Denotes the connection to the stream service is not established.
            SessionAuthenticationSuccess : Denotes the session has successfully authenticated this client.
            SessionAuthenticationFailed : Denotes the session has failed to authenticate this client.
            StreamAuthenticationSuccess: Denotes the stream has successfully authenticated this client.
            StreamAuthenticationFailed: Denotes the stream has failed to authenticate this client.
            TokenRefreshFailed  : The request to refresh the access token for the session has failed.
            DataRequestOk : The request for content from the sessions data services has completed successfully.
            DataRequestFailed : The request for content from the sessions data services has failed.
        """
        StreamPending = 1
        StreamConnected = 2
        StreamDisconnected = 3
        SessionAuthenticationSuccess = 4
        SessionAuthenticationFailed = 5
        StreamAuthenticationSuccess = 6
        StreamAuthenticationFailed = 7
        TokenRefreshFailed = 8
        DataRequestOk = 9
        DataRequestFailed = 10

    LOGGER_NAME = "pyeikon"

    class Params(object):
        def __init__(self, app_key=None, on_event=None, on_state=None, **kwargs):
            self._app_key = app_key
            self._on_event_cb = on_event
            self._on_state_cb = on_state
            self._dacs_params = DacsParams()

        def app_key(self, app_key):
            if app_key is None:
                raise AttributeError("app_key value can't be None")
            self._app_key = app_key
            return self

        def with_dacs_user_name(self, user):
            if user:
                self._dacs_params.dacs_username = user
            return self

        def with_dacs_application_id(self, application_id):
            if application_id:
                self._dacs_params.dacs_application_id = application_id
            return self

        def with_dacs_position(self, position):
            if position:
                self._dacs_params.dacs_position = position
            return self

        def on_state(self, on_state):
            self._on_state_cb = on_state
            return self

        def on_event(self, on_event):
            self._on_event_cb = on_event
            return self

    __all_sessions = {}
    __register_session_lock = Lock()
    __session_id_counter = 0

    @classmethod
    def register_session(cls, session):
        with cls.__register_session_lock:
            if not session:
                raise EikonError('Error', 'Try to register unavailable session')
            session_id = session.session_id
            if session_id in cls.__all_sessions:
                return
            session._session_id = cls.__session_id_counter
            cls.__session_id_counter += 1
            cls.__all_sessions[session._session_id] = session

    @classmethod
    def unregister_session(cls, session):
        with cls.__register_session_lock:
            if not session:
                raise EikonError('Error', 'Try to unregister unavailable session')
            session_id = session.session_id
            if session_id is None:
                raise EikonError('Error', 'Try to unregister unavailable session')
            if session_id not in cls.__all_sessions:
                raise EikonError('Error',
                                    'Try to unregister unknown session id {}'.format(session_id))
            cls.__all_sessions.pop(session_id)

    @classmethod
    def get_session(cls, session_id):
        """
        Returns the stream session singleton
        """
        if session_id not in cls.__all_sessions:
            raise EikonError('Error', 'Try to get unknown session id {}'.format(session_id))
        return cls.__all_sessions.get(session_id)

    def __init__(self, app_key, on_state=None, on_event=None,
                 token=None, dacs_user_name=None, dacs_position=None, dacs_application_id=None):
        from eikon.streaming_session.streaming_connection_config import StreamingConnectionConfiguration

        self._session_id = None
        self._lock_log = Lock()

        self._state = Session.State.Closed
        self._status = Session.EventCode.StreamDisconnected
        self._last_event_code = None
        self._last_event_message = None

        self._app_key = app_key
        self._on_event_cb = on_event
        self._on_state_cb = on_state
        self._access_token = token
        self._dacs_params = DacsParams()

        if dacs_user_name:
            self._dacs_params.dacs_username = dacs_user_name
        if dacs_position:
            self._dacs_params.dacs_position = dacs_position
        if dacs_application_id:
            self._dacs_params.dacs_application_id = dacs_application_id

        self._streaming_config = StreamingConnectionConfiguration()
        self._log_path = None
        self._log_level = logging.NOTSET

        logging.basicConfig(format=Session.FORMAT)
        logging.addLevelName(5, 'TRACE')
        self._logger = logging.getLogger(self.LOGGER_NAME)
        setattr(self._logger, 'trace', lambda *args: self._logger.log(5, *args))

        try:
            self._loop = asyncio.get_event_loop()
            self.log(1, f'Session loop was set to current event loop {self._loop}')
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            self.log(1, f'Session loop was set with a new event loop {self._loop}')
        self._streaming_session = None
        self._is_closing = False
        self._login_event = Event()
        self._login_event.clear()

        self.__lock_callback = Lock()
        self._http_session = requests.sessions.Session()
        self._base_url = 'https://api.edp.thomsonreuters.com'

        self._start_streaming_event = Event()
        self._stop_streaming_event = Event()
        self._stream_register_lock = Lock()
        self._all_stream_subscriptions = {}
        self._id_request = 0

        Session.register_session(self)

        if app_key is None:
            raise AttributeError("app_key value can't be None")

    def __del__(self):
        self.log(1, f'Delete a Session')
        Session.unregister_session(self)
        handlers = self._logger.handlers[:]
        for handler in handlers:
            handler.close()
            self._logger.removeHandler(handler)

    def __delete__(self, instance):
        self.log(1, f'Delete the Session instance {instance}')

    def _set_proxy(self, http, https):
        self._http_session.proxies = {"http": http, "https": https}

    def get_open_state(self):
        """
        Returns the session state.
        """
        return self._state

    def get_last_event_code(self):
        """
        Returns the last session event code.
        """
        return self._last_event_code

    def get_last_event_message(self):
        """
        Returns the last event message.
        """
        return self._last_event_message

    @property
    def app_key(self):
        """
        Returns the application id.
        """
        return self._app_key

    @app_key.setter
    def app_key(self, app_key):
        """
        Set the application key.
        """
        from eikon.tools import is_string_type

        if app_key is None:
            return
        if not is_string_type(app_key):
            raise AttributeError('application key must be a string')

        self._app_key = app_key

    @property
    def session_id(self):
        return self._session_id

    def logger(self):
        return self._logger

    ######################################
    # methods to manage log              #
    ######################################
    TRACE = 5
    MAX_LOG_SIZE = 10000000
    FORMAT = '%(asctime)-15s P[%(process)d] [%(threadName)s %(thread)s] %(message)s'
    #FORMAT = '%(asctime) - %(message)s'
    #FORMAT = '%(asctime),%(msecs)d %(levelname)-8s] %(message)s'
    # datefmt = '%Y-%m-%d:%H:%M:%S'
    # FORMAT = '[%(asctime)s] %(levelname)s - %(message)s'

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
            self._log_path = log_path
            return True
        return False

    def set_log_level(self, log_level):
        """
        Set the log level.
        By default, logs are disabled.

        Parameters
        ----------
        level : int
            Possible values from logging module :
            [CRITICAL, FATAL, ERROR, WARNING, WARN, INFO, DEBUG, NOTSET]
        """
        if log_level > logging.NOTSET:
            _formatter = logging.Formatter("[%(asctime)s;s] - [%(levelname)s] - [%(funcName)s] - %(message)s")
            _filename = "pyeikon.{}.log".format(datetime.now().strftime('%Y%m%d.%H-%M-%S'))

            if self._log_path is not None:
                if not os.path.isdir(self._log_path):
                    os.makedirs(self._log_path)
                _filename = os.path.join(self._log_path, _filename)

            _handler = RotatingFileHandler(_filename, mode='a',
                                           maxBytes=Session.MAX_LOG_SIZE,
                                           backupCount=10, encoding='utf-8')
            _handler.setFormatter(_formatter)
            self._logger.addHandler(_handler)

        self._logger.setLevel(log_level)
        self._log_level = log_level

        # set log_level to asyncio module
        logging.getLogger('asyncio').setLevel(log_level)

    def get_log_level(self):
        """
        Returns the log level
        """
        return self._logger.level

    def log(self, log_level, message):
        with self._lock_log:
            self._print(log_level, message)
            self._logger.log(log_level, message)

    def trace(self, message):
        self._logger.log(Session.TRACE, message)

    def _print(self, log_level, message):
        if False:
            print(f"{datetime.now()} - Thread {current_thread().ident} | {current_thread().name}\n{message}")

    ######################################
    # methods to open and close session  #
    ######################################
    def open(self):
        if self._state in [Session.State.Pending, Session.State.Open]:
            # session is already opened or is opening
            return self._state
        self._loop.run_until_complete(self.open_async())
        return self._state

    def close(self):
        if self._state == Session.State.Closed:
            return self._state

        self._state = Session.State.Closed
        self._stop_streaming()
        # Session.unregister_session(self)

        return self._state

    async def open_async(self):
        #Session.register_session(self)
        return self._state

    async def wait_for_streaming(self):
        await self._start_streaming()
        if self._status is Session.EventCode.StreamConnected:
            return True
        else:
            self.log(logging.DEBUG, "Streaming failed to start")
            return False

    async def _start_streaming(self):
        if self._status not in [Session.EventCode.StreamConnected,
                                Session.EventCode.StreamPending]:
            self._status = Session.EventCode.StreamPending

            self._start_streaming_event.clear()
            self._stop_streaming_event.clear()
            self._start_streaming_event = Event()
            self._stop_streaming_event = Event()
            self._login_event = Event()

            self._is_closing = False

            if self._streaming_session is None:
                _ws_name = "WebSocket {}".format(self.session_id)
                self.log(1, "Create StreamConnection...")
                self._streaming_session = StreamConnection(_ws_name, self,
                                                           self._start_streaming_event,
                                                           self._stop_streaming_event)
                self._streaming_session.daemon = True
                # Init web socket to support an open
                self._streaming_session.start()
                self.log(logging.DEBUG, "Streaming is started")
                time.sleep(0.2)

        self._start_streaming_event.set()

        if not self._login_event.is_set():
            self.log(1, "WAIT FOR LOGIN EVENT")
            self._login_event.wait()
            self.log(1, "RECEIVE LOGIN EVENT")
        else:
            self.log(1, "Session is logged, ")

        self._start_streaming_event.clear()
        return self._status

    def _send(self, msg):
        if self._streaming_session is not None:
            self._streaming_session.send(msg)

    def is_closing(self):
        return self._is_closing

    def _stop_streaming(self):
        # unblock any wait on login event
        self._is_closing = True
        if self._streaming_session:
            self._streaming_session.is_closing = True
        self.log(logging.DEBUG, f"Unlock login_event for streaming session {self._session_id} due to stop streaming call")
        if self._login_event:
            self._login_event.set()
            self._login_event.clear()
        if self._start_streaming_event:
            # unlock web socket on start_streaming event
            self._start_streaming_event.set()

        # Close web socket
        if self._streaming_session is not None:
            self._streaming_session.close()
            self._stop_streaming_event.wait()
            self.log(logging.INFO, f"Streaming session {self._session_id} was closed")
            del self._streaming_session
            self._streaming_session = None
        self._status = Session.EventCode.StreamDisconnected

    ##########################################################
    # methods for stream register / unregister               #
    ##########################################################
    def _get_new_id(self):
        self._id_request += 1
        return self._id_request

    def _register_stream(self, stream):
        with self._stream_register_lock:
            if stream is None:
                raise EikonError('Error', 'Try to register None subscription')

            if stream._stream_id in self._all_stream_subscriptions:
                raise EikonError('Error', f"Subscription {stream._stream_id} is already registered")
            if stream._stream_id is not None:
                raise EikonError('Error', f"Try to register again subscription {stream._stream_id}")
            stream._stream_id = self._get_new_id()
            self._all_stream_subscriptions[stream._stream_id] = stream

    def _unregister_stream(self, stream):
        with self._stream_register_lock:
            if not stream or not stream._stream_id:
                raise EikonError(-1, 'Try to unregister unavailable stream')

            if stream._stream_id not in self._all_stream_subscriptions:
                raise EikonError('Error',
                                 f"Try to unregister unknown stream {stream._stream_id} from session {self.session_id}")

            self._all_stream_subscriptions.pop(stream._stream_id)
            stream._stream_id = None

    def _get_stream(self, stream_id):
        with self._stream_register_lock:
            if stream_id is None:
                raise EikonError('Error', 'Try to retrieve undefined stream')
            if stream_id in self._all_stream_subscriptions:
                return self._all_stream_subscriptions[stream_id]
            return None

    ##########################################################
    # methods for session callbacks from streaming session   #
    ##########################################################
    def _on_open(self):
        with self.__lock_callback:
            self._state = Session.State.Pending
            pass

    def _on_close(self):
        with self.__lock_callback:
            self._state = Session.State.Closed
            pass

    def _on_state(self, state_code, state_text):
        with self.__lock_callback:
            if isinstance(state_code, Session.State):
                self._state = state_code
                if self._on_state_cb is not None:
                    self._on_state_cb(self, state_code, state_text)

    def _on_event(self, streaming_session_id, event_code, event_msg):
        with self.__lock_callback:
            if self._streaming_session:
                if streaming_session_id == self._streaming_session.streaming_session_id:
                    if isinstance(event_code, Session.EventCode):
                        if self._status != event_code:
                            self._status = event_code
                            if self._on_event_cb:
                                self._on_event_cb(self, event_code, event_msg)
                            # Unlock wait for login event if stream is disconnected
                            if event_code == Session.EventCode.StreamDisconnected:
                                self.log(logging.DEBUG,
                                         f"Unlock login_event for streaming session {self._streaming_session.streaming_session_id} due to disconnect event")
                                self._login_event.set()
                else:
                    # notification from another streaming session than current one
                    self.log(1, f'Received notification from another streaming session ({streaming_session_id}) than current one ({self._streaming_session.streaming_session_id})')
            else:
                self.log(1, f'Received notification for closed streaming session {streaming_session_id}')

    def process_on_close_event(self):
        self.close()

    ##############################################
    # methods for status reporting               #
    ##############################################
    @staticmethod
    def _report_session_status(self, session, session_status, event_msg):
        _callback = self._get_status_delegate(session_status)
        if _callback is not None:
            json_msg = self._define_results(session_status)[Session.CONTENT] = event_msg
            _callback(session, json_msg)

    def report_session_status(self, session, event_code, event_msg):
        # Report the session status event defined with the eventMsg to the appropriate delegate
        self._last_event_code = event_code
        self._last_event_message = event_msg
        _callback = self._get_status_delegate(event_code)
        if _callback is not None:
            _callback(session, event_code, event_msg)

    def _get_status_delegate(self, event_code):
        _cb = None

        if event_code in [Session.EventCode.SessionAuthenticationSuccess,
                          Session.EventCode.SessionAuthenticationFailed,
                          Session.EventCode.TokenRefreshFailed]:
            _cb = self._on_state_cb
        elif event_code not in [self.EventCode.DataRequestOk,
                                self.EventCode.StreamPending,
                                self.EventCode.StreamConnected,
                                self.EventCode.StreamDisconnected]:
            _cb = self._on_event_cb
        return _cb

    ############################
    # methods for HTTP request #
    ############################
    async def http_request_async(self, url: str, method=None, headers={},
                                 data=None, params=None, json=None, closure=None,
                                 auth=None, loop=None, **kwargs):
        if method is None:
            method = 'GET'

        if self._access_token is not None:
            headers["Authorization"] = "Bearer {}".format(self._access_token)

        if closure is not None:
            headers["Closure"] = closure

        headers.update({'x-tr-applicationid': self.app_key})

        _http_request = requests.Request(method, url, headers=headers, data=data, params=params, json=json, auth=auth,
                                         **kwargs)
        _prepared_request = _http_request.prepare()

        self.log(logging.DEBUG,
                 f'Request to {_prepared_request.url}\n   headers = {_prepared_request.headers}\n   params = {kwargs.get("params")}')

        try:
            async with requests.sessions.Session() as _http_session:
                _request_response = await _http_session.send(_prepared_request, **kwargs)
                self.log(1, f'HTTP request response {_request_response.status_code}: {_request_response.text}')
                return _request_response
        except Exception as e:
            self.log(1, f'HTTP request failed: {e!r}')

        return None

    def http_request(self, url: str, method=None, headers={}, data=None, params=None,
                     json=None, auth=None, loop=None, **kwargs):
        # Multiple calls to run_until_complete were allowed with nest_asyncio.apply()
        if loop is None:
            loop = self._loop
        response = loop.run_until_complete(self.http_request_async(url, method, headers, data,
                                                                   params, json, auth, **kwargs))
        return response
