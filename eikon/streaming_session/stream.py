# coding: utf8

__all__ = ['Stream', 'StreamState']

import json
import logging
from threading import Lock
from enum import Enum, unique
from threading import Event


@unique
class StreamState(Enum):
    """
    Define the state of the Stream.
        Closed : The Stream is closed and ready to be opened.
        Pending : the Stream is in a pending state.  Upon success, the Stream will move into an open state, otherwise will be closed.
        Open : The Stream is opened.
    """
    Closed = 1
    Pending = 2
    Open = 3


class Stream(object):

    def __init__(self, session=None):
        from ..Profile import get_profile

        self.__stream_lock = Lock()
        self._stream_id = None
        self._session = None

        self._name = None
        self._service = None
        self._fields = []
        self._streaming = True
        self._domain = None

        self._state = StreamState.Closed

        if session is None:
            self._session = get_profile()._get_desktop_session()
        else:
            self._session = session

        if self._session is None:
            raise AttributeError("Session is mandatory")

        self._response_event = Event()
        self._session._register_stream(self)

    def __del__(self):
        self._session._unregister_stream(self)
        pass

    @property
    def stream_id(self):
        return self._stream_id

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    async def _wait_for_response(self):
        if self.state is StreamState.Open:
            return True

        try:
            self._session.log(1, "Lock on wait for a response on stream {}".format(self._stream_id))
            self._response_event.wait()
            self._session.log(1, "Response was received on stream {}.".format(self._stream_id))
        except Exception as e:
            self._session.log(logging.ERROR, f'Error occurred on stream {self._stream_id}: {e!r}') #.format(self._stream_id, str(e)))
        self._response_event.clear()

    #######################################
    #  methods to open and close session  #
    #######################################
    def open(self):
        """
        Open synchronously the data stream
        """
        self._session._loop.run_until_complete(self.open_async())
        return self._state

    def close(self):
        """
        Close the data stream
        """
        if self._state is StreamState.Open:
            self._session.log(logging.DEBUG, 'Close Stream subscription {}'.format(self._stream_id))

            mp_req_json = {
                'ID': self._stream_id,
                'Type': 'Close'
            }
            self._session.log(1,
                              'Sent close subscription:\n{}'.format(json.dumps(mp_req_json,
                                                                    sort_keys=True,
                                                                    indent=2,
                                                                    separators=(',', ':'))))
            self._session._send(mp_req_json)
        self._state = StreamState.Closed
        # Unblock any wait for response
        self._response_event.set()
        self._response_event.clear()
        return self._state

    ################################################
    #  methods to open asynchronously item stream  #
    ################################################
    async def open_async(self):
        """
        Open asynchronously the data stream
        """
        from eikon.streaming_session.session import Session
        from eikon.eikonError import EikonError
        if self._session is None:
            raise AttributeError("Session is mandatory")

        if self._session.get_open_state() is Session.State.Closed:
            raise EikonError(-1, "Session must be opened")

        if self._state in [StreamState.Open, StreamState.Pending]:
            self._session.log(logging.DEBUG, 'Try to reopen asynchronously Stream {}'.format(self._stream_id))
            return self._state

        self._state = StreamState.Pending

        # Wait for login successful before sending the request
        result = await self._session.wait_for_streaming()

        if result:
            self._session.log(logging.DEBUG, 'Open asynchronously Stream {}'.format(self._stream_id))
            if self._service is None:
                message = "Subscribe to {}".format(self._name, self._fields)
            else:
                message = "Subscribe to {}:{}".format(self._service, self._name)
            if self._fields:
                message = "{} on {}".format(message, self._fields)
            self._session.log(logging.DEBUG, message)

            mp_req_json = {
                'ID': self._stream_id,
                'Domain': self._domain,
                'Key': {
                    'Name': self._name
                },
                'Streaming': self._streaming
            }
            if self._service:
                mp_req_json['Key']['Service'] = self._service
            if self._fields:
                mp_req_json['View'] = self._fields

            self._session._send(mp_req_json)
            self._session.log(1, 'Sent subscription request:\n{}'.format(
                json.dumps(mp_req_json, sort_keys=True, indent=2, separators=(',', ':'))))

            # wait for response message
            self._session.log(1, 'Wait for a response on Stream {}'.format(self._stream_id))
            await self._wait_for_response()

            if self.state is StreamState.Open:
                self._session.log(1, 'Just receive a response on Stream {} !!'.format(self._stream_id))
        else:
            self._state = StreamState.Closed
            self._session.log(1, 'Start streaming failed. Set stream {} as {}'.format(self._stream_id, self._state))


        return self._state

    ####################
    # Stream callbacks #
    ####################
    def _on_refresh(self, message):
        with self.__stream_lock:
            if self._state in [StreamState.Pending, StreamState.Open] :
                self._session.log(1, f'Receive message {message} on stream {self._stream_id} [{self._name}]')
                self._state = StreamState.Open
                self._session.log(1, 'Set stream {} as {}'.format(self._stream_id, self._state))
            if not self._response_event.is_set():
                self._response_event.set()

    def _on_update(self, update):
        with self.__stream_lock:
            if self._state is StreamState.Open:
                self._session.log(1, f'Stream {self._stream_id} [{self._name}] - Receive update {update}')

    def _on_status(self, status):
        with self.__stream_lock:
            self._session.log(1, f'Stream {self._stream_id} [{self._name}] - Receive status {status}')
            if not self._response_event.is_set():
                self._response_event.set()

    def _on_complete(self,):
        with self.__stream_lock:
            if self._state in [StreamState.Pending, StreamState.Open]:
                self._session.log(1, f'Stream {self._stream_id} [{self._name}] - Receive complete')

    async def _set_response_event(self):
        self._response_event.set()

    def _on_error(self, error):
        with self.__stream_lock:
            self._session.log(1, f'Stream {self._stream_id} [{self._name}] - Receive error {error}')

            if not self._response_event.is_set():
                self._response_event.set()

    def _on_stream_state(self, state):
        self._state = state
