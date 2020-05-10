# coding: utf-8

__all__ = ['StreamConnection', 'StreamConnectionState']

import json
import websocket
import threading
import logging
from enum import Enum
from .stream import StreamState

import datetime


class StreamConnectionState(Enum):
    CLOSED = 0
    PENDING = 1
    OPEN = 2


class StreamConnection(threading.Thread):

    __all_streaming_session = {}
    __register_lock = threading.Lock()
    __streaming_session_id_counter = 0

    @classmethod
    def _get_new_streaming_session_id(cls):
        cls.__streaming_session_id_counter += 1
        return cls.__streaming_session_id_counter

    @classmethod
    def register_streaming_session(cls, streaming_session):
        with cls.__register_lock:
            if not streaming_session:
                raise EikonError('Error', 'Try to register unavailable streaming session')
            streaming_session_id = streaming_session.streaming_session_id
            if streaming_session_id in cls.__all_streaming_session:
                raise EikonError('Error',
                                 f'Try to register again existing streaming session id {streaming_session_id}')

            streaming_session._streaming_session_id = cls._get_new_streaming_session_id()
            cls.log(streaming_session, 1,
                    "Register streaming session {}".format(streaming_session._streaming_session_id))
            cls.__all_streaming_session[streaming_session._streaming_session_id] = streaming_session

    @classmethod
    def unregister_streaming_session(cls, streaming_session):
        with cls.__register_lock:
            if not streaming_session:
                raise EikonError('Error', 'Try to unregister unavailable streaming session')
            if streaming_session.streaming_session_id is None:
                raise EikonError('Error', 'Try to unregister unavailable streaming session id')
            if streaming_session.streaming_session_id not in cls.__all_streaming_session:
                raise EikonError('Error',
                                    'Try to unregister unknown streaming session id {}'
                                    .format(streaming_session.streaming_session_id))
            cls.log(streaming_session, 1,
                    f'Unregister streaming session {streaming_session._streaming_session_id}')
            cls.__all_streaming_session.pop(streaming_session.streaming_session_id)

    __all_subscriptions = {}
    __id_request = 1

    ###############################################################################################

    def __init__(self, thread_name, session, start_event, stop_event, *args, **kwargs):
        from eikon.streaming_session.session import Session

        if session is None:
            raise ValueError("StreamConnection is passed a null session")
        if session._streaming_config is None:
            raise ValueError("StreamConnection must have a WebsocketEndpoint")
        if session._streaming_config.url is None:
            raise ValueError("StreamConnection must have a WebsocketEndpoint")

        self._streaming_session_id = None
        self._streaming_config = session._streaming_config
        self._session = session
        self._on_state_cb = session._on_state
        self._on_event_cb = session._on_event
        self._start_streaming_event = start_event
        self._stop_streaming_event = stop_event
        self._is_closing = False

        self._ws_login_id = None
        self._websocket = None
        self._ws_connected = False
        self._ws_is_logged = False
        self._ws_lock = threading.Lock()

        self._logger = logging.getLogger(Session.LOGGER_NAME)
        self._state = StreamConnectionState.CLOSED

        threading.Thread.__init__(self, target=self.run, name=thread_name)
        StreamConnection.register_streaming_session(self)

    def __del__(self):
        self.log(1, 'StreamConnection {} is releasing'.format(self._streaming_session_id))
        if self._websocket:
            try:
                if self._websocket.keep_running:
                    # Close web socket
                    self.log(1, "Close websocket client {}".format(self._streaming_session_id))
                    self._websocket.close()
                    self._websocket.keep_running = False

            except Exception as e:
                self.log(1, f'Exception on close websocket attempt for main stream {self._streaming_session_id}: {e!r}')
                pass
        if self._streaming_session_id in StreamConnection.__all_streaming_session:
            self.log(1, "Unregister streaming session {}".format(self._streaming_session_id))
            StreamConnection.unregister_streaming_session(self)

    def username(self, user):
        self._streaming_config.username = user
        return self

    def position(self, position):
        self._streaming_config.position = position

    def application_id(self, app_id):
        self._streaming_config.application_id = app_id

    def auth_token(self, token):
        self._streaming_config.auth_token = token

    def connection_retry(self, retry_in_seconds):
        self._streaming_config.connection_retry = retry_in_seconds

    def log(self, log_level, message):
        if self._logger:
            self._logger.log(log_level, message)

    @property
    def streaming_session_id(self):
        return self._streaming_session_id

    @property
    def is_connected(self):
        return self._ws_connected

    @property
    def is_closing(self):
        return self._is_closing

    @is_closing.setter
    def is_closing(self, value):
        self._is_closing = value

    #############################################
    #  methods to open and close the websocket  #
    #############################################
    def run(self):

        while not self.is_closing:
            self.log(1, f"Streaming session {self._streaming_session_id} waits for start event")
            self._start_streaming_event.wait()
            if not self.is_closing:
                self.log(1, f"Streaming session {self._streaming_session_id} received start event, then open websocket.")

                self._websocket = websocket.WebSocketApp(self._streaming_config.url,
                                                         header=["User-Agent: Python"]+self._streaming_config._header,
                                                         on_message=self._ws_message,
                                                         on_error=self._ws_error,
                                                         on_close=self._ws_close,
                                                         subprotocols=["tr_json2"])
                self._websocket.on_open = self._ws_open
                self._websocket.id = self._streaming_session_id
                self._state = StreamConnectionState.PENDING
                self._websocket.run_forever()
                self._websocket = None
                self.log(1, "Websocket for streaming session {} was closed".format(self._streaming_session_id))
        self.log(1, "Streaming session {} will be closed".format(self._streaming_session_id))


    def close(self):
        if not self._is_stopped:

            # set notify flag to Flase to avoid any more on_event

            # Send Close message for the web socket
            close_json = {'Type': 'Close'}
            close_json['ID'] = self._ws_login_id
            close_json['Domain'] = 'Login'
            self.log(1, "Send Close message for main stream {} (login id {})".format(self._streaming_session_id,
                                                                                     self._ws_login_id))
            self.send(close_json)
            StreamConnection.unregister_streaming_session(self)
            if self._websocket and self._websocket.keep_running:
                # Close web socket
                self.log(1, "Close websocket client {}".format(self._streaming_session_id))
                self._websocket.close()
                # self._websocket.keep_running = False


    #############################################
    #  methods to send request to the websocket #
    #############################################
    def send(self, request):
        if self._websocket:
            self.log(1, "Send request: {}".format(request))
            self._send(request)

    ############################################
    # Methods for web socket callbacks         #
    ############################################
    def _ws_open(self, *args):
        from eikon.streaming_session.session import Session
        with self._ws_lock:
            result = "WebSocket for streaming session {} was opened to server: {}".format(self._streaming_session_id,
                                                                    self._streaming_config.url)
            self.log(1, result)
            if self._on_event_cb:
                self._on_event_cb(self._streaming_session_id,
                                  Session.EventCode.StreamConnected,
                                  result)
            self._ws_connected = True
            _login_json = self._streaming_config.login_message
            self._ws_login_id = self._session._get_new_id()
            _login_json['ID'] = self._ws_login_id
            self.send(_login_json)
        pass

    def _ws_error(self, error):
        from eikon.streaming_session.session import Session
        with self._ws_lock:
            err = "WebSocket error occurred for web socket client {} (login id {}) : {}".format(self._streaming_session_id,
                                                                                                self._ws_login_id,
                                                                                                error)
            self.log(1, err)
            self._ws_is_logged = False
            self._ws_connected = False
            self._ws_login_id = None
            if self._on_event_cb:
                self._on_event_cb(self._streaming_session_id,
                                  Session.EventCode.StreamDisconnected,
                                  err)
            self._state = StreamConnectionState.CLOSED
            self._stop_streaming_event.set()
            # Stop iteration on web socket connexion attempt in run() function
            self.is_closing = True
        pass

    def _ws_message(self, *args):
        with self._ws_lock:
            if self._on_event_cb:
                self._on_message(args[0])

    def _ws_close(self, *args):
        from eikon.streaming_session.session import Session
        with self._ws_lock:
            self._state = StreamConnectionState.CLOSED
            self.log(1, "Close notification from main stream {} (login id {})".format(self._streaming_session_id,
                                                                                      self._ws_login_id))
            self._ws_is_logged = False
            self._ws_connected = False
            self._ws_login_id = None
            if self._on_event_cb:
                self._on_event_cb(self._streaming_session_id,
                                  Session.EventCode.StreamDisconnected,
                                  "Connection to the WebSocket server [{}] is down".format(self._streaming_config.url))
            self._state = StreamConnectionState.CLOSED
            self._stop_streaming_event.set()

    ############################################
    # Send request method                      #
    ############################################
    def _send(self, msg):
        try:
            if self._ws_connected:
                self._websocket.send(json.dumps(msg))
            pass
        except websocket.WebSocketConnectionClosedException as e:
            self._logger.log(logging.ERROR, "WebSocketConnectionClosedException: {}".format(e))

    ###############################################
    # Parse methods for _on_message notifications #
    ###############################################
    def _on_message(self, message):
        """ Called when message is received from websocket"""
        message_json = json.loads(message)
        self.log(logging.DEBUG, 'Receive message from Web Socket')
        for singleMsg in message_json:
            self._process_message(singleMsg)

    def _process_message(self, message_json):
        """ Parse at high level and output JSON of message """
        from eikon.streaming_session.session import Session

        if self._session.is_closing():
            return

        message_type = message_json['Type']
        _id = message_json.get("ID")
        if _id == self._ws_login_id:
            self.log(Session.TRACE, f"Receive message for login {_id}: {message_json}")
        else:
            self.log(Session.TRACE, f"Receive message for stream {_id}: {message_json}")

        if message_type == "Refresh":
            if 'Domain' in message_json:
                message_domain = message_json['Domain']
                if message_domain == "Login":
                    self._process_login_response(message_json)
                    return
            self._process_refresh_message(message_json)
        elif message_type == 'Update':
            self._process_update_message(message_json)
        elif message_type == 'Status':
            if 'Domain' in message_json:
                message_domain = message_json['Domain']
                if message_domain == "Login":
                    self._process_login_response(message_json)
                    return
            self._process_status_message(message_json)
        elif message_type == 'Error':
            self._process_error_message(message_json)
        elif message_type == "Ping":
            self.log(logging.INFO, 'Receive ping from server ...')
            pong_json = {'Type': 'Pong'}
            self.send(pong_json)
            self.log(logging.INFO, '    ... send pong response')

    def _process_login_response(self, response):
        """ Parse login response message """
        from eikon.streaming_session.session import Session
        id = response.get("ID")
        if id != self._ws_login_id:
            self.log(logging.DEBUG, f'Received login response for id {id} different than login id {self._ws_login_id}')
        else:
            self.log(logging.DEBUG, f'Received login response for login id {id}')
        state = response.get("State")
        stream_status = state.get("Stream")
        data_status = state.get("Data")
        if stream_status == "Open" and data_status == "Ok":
            self._state = StreamConnectionState.OPEN
            self._ws_is_logged = True
            self.log(logging.INFO, "Login to websocket successful")
            self._on_event_cb(self._streaming_session_id,
                              Session.EventCode.StreamConnected,
                              state.get("Text"))
        else:
            self._state = StreamConnectionState.CLOSED
            self._on_event_cb(self._streaming_session_id,
                              Session.EventCode.StreamDisconnected,
                              "Login to websocket failed: {}".format(response))
        # Unblock all tasks that are waiting for Login response
        self._set_login_event()
        pass

    def _set_login_event(self):
        self.log(logging.DEBUG, f"Unlock login event due to login response")
        self._session._login_event.set()

    def _process_status_message(self, status):
        """ Parse status message """
        self.log(logging.INFO, 'Received status message:\n   {}'.format(status['State']))

        # EventCode value determines further interest
        _stream = str(status["State"]["Stream"]) if "State" in status and "Stream" in status["State"] else None
        # noInterest = (_stream == "Closed") or (_stream == "ClosedRecover");

        _id = status['ID']
        mp_subscription = self._session._get_stream(_id)
        if mp_subscription:
            mp_subscription._on_status(status)
            # _name = str(status["Key"]["Name"]) if "Key" in status and "Name" in status["Key"] else ""
            # if noInterest:
            #    mp_subscription._on_stream_state(StreamConnectionState.CLOSED)
        else:
            self.log(logging.WARNING, "Receive status message for unknown subscription id {}".format(_id))

    def _process_refresh_message(self, refresh):
        _id = refresh['ID']
        mp_subscription = self._session._get_stream(_id)

        # A completion occurs when "Complete" == true or the "Complete" field is absent
        _complete = str(refresh["Complete"]).lower() == "true" if refresh.get("Complete") else True

        # EventCode value determines further interest
        _stream = str(refresh["State"]["Stream"]) if refresh.get("State") and refresh["State"].get("Stream") else None
        _no_interest = _stream == "Closed" or _stream == "NonStreaming"

        if mp_subscription:
            mp_subscription._on_refresh(refresh)

            # A completion occurs when "Complete" == true or the "Complete" field is absent
            complete = True if refresh.get("Complete") is None else bool(refresh["Complete"]);
            if complete:
                mp_subscription._on_complete()
        else:
            self.log(logging.WARNING, "Receive refresh message for unknown subscription {}".format(_id))

    def _process_update_message(self, update):
        _id = update['ID']
        mp_subscription = self._session._get_stream(_id)
        if mp_subscription:
            mp_subscription._on_update(update)
        else:
            self.log(logging.WARNING, "Receive update message for unknown subscription {}".format(_id))

    def _process_error_message(self, error):
        _id = error['ID']
        mp_subscription = self._session._get_stream(_id)
        if mp_subscription:
            mp_subscription._on_error(error)
        elif _id == self._ws_login_id:
            self.log(logging.WARNING, "Receive error message for session {} : {}".format(_id, error))
            self._on_event_cb(self._streaming_session_id,
                              Session.EventCode.StreamDisconnected,
                              error)
        else:
            self.log(logging.WARNING, "Receive error message for unknown subscription {} : {}".format(_id, error))

    ##############################################
    # methods for refresh token                  #
    ##############################################
    def refresh_token(self, refresh_token):
        if self._ws_connected and self._ws_is_logged:
            refresh = {"ID": self._ws_login_id,
                       "Domain": "Login",
                       "Key": {
                            "NameType": "AuthnToken",
                            "Elements": {
                                "AuthenticationToken": refresh_token,
                                "ApplicationId": self._streaming_config.application_id,
                                "Position": self._streaming_config.position
                            }
                       },
                       "Refresh": False}
            self.send(refresh)

