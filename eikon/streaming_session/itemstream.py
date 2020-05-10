# coding: utf8


__all__ = ['ItemStream']


import sys
import logging
from threading import Lock
from .stream import Stream, StreamState
from .istream_callback import ItemStreamCallback


class ItemStream(Stream):
    """
    Open an item stream.

    Parameters
    ----------
    name: string
        RIC to retrieve item stream.

    domain: string
        Specify item stream domain (MarketPrice, MarketByPrice, ...)
        Default : "MarketPrice"

    service: string, optional
        Specify the service to subscribe on.
        Default: None

    fields: string or list, optional
        Specify the fields to retrieve.
        Default: None

    streaming: boolean, optional
        Specify if user request snapshot or streamed data..
        Default: True

    extended_params: dict, optional
        Specify optional params
        Default: None

    on_refresh: callable object, optional
        Called when the stream is opened or when the record is refreshed with a new image.
        This callback receives a full image
        Default: None

    on_update: callable object, optional
        Called when an update is received.
        This callback receives an utf-8 string as argument.
        Default: None

    on_error: callable object, optional
        Called when an error occurs.
        This callback receives Exception as argument
        Default: None

    on_complete: callable object, optional
        Called when item stream received all fields.
        This callback has no argument.
        Default: None

    Raises
    ------
    Exception
        If request fails or if Refinitiv Services return an error

    Examples
    --------
    >> import eikon as ek
    >> euro = ek.delivery.stream.ItemStream('EUR=')
    >> euro.open()
    >> bid = euro.get_field_value('BID')
    >> ask = euro.get_field_value('ASK')
    >>
    >> def on_update(msg):
            ... print(msg)
    >> stream = ek.delivery.stream.ItemStream(['VOD.L', 'EUR=', 'PEUP.PA', 'IBM.N'],
            ... ['DSPLY_NAME', 'BID', 'ASK'],
            ... on_update=on_update)
    >> stream.open()
    {"EUR=":{"DSPLY_NAME":"RBS          LON","BID":1.1221,"ASK":1.1224}}
    {"PEUP.PA":{"DSPLY_NAME":"PEUGEOT","BID":15.145,"ASK":15.155}}
    {"IBM.N":{"DSPLY_NAME":"INTL BUS MACHINE","BID":"","ASK":""}}
    ...
    """

    class Params(object):

        def __init__(self, *args, **kwargs):
            self._name = None
            self._session = None
            self._domain = "MarketPrice"
            self._service = None
            self._fields = None
            self._streaming = True
            self._extended_params = None
            self._on_refresh_cb = None
            self._on_status_cb = None
            self._on_update_cb = None
            self._on_error_cb = None
            self._on_complete_cb = None

            if len(args) > 0 and isinstance(args[0], ItemStream.Params):
                self.__init_from_params__(args[0])

            if kwargs:
                self._name = kwargs.get("name")
                self._session = kwargs.get("session")
                self._domain = kwargs.get("domain", "MarketPrice")
                self._service = kwargs.get("service")
                self._fields = kwargs.get("fields")
                self._streaming = kwargs.get("streaming", True)
                self._extended_params = kwargs.get("extended_params", None)
                self._on_refresh_cb = kwargs.get("on_refresh")
                self._on_status_cb = kwargs.get("on_status")
                self._on_update_cb = kwargs.get("on_update")
                self._on_error_cb = kwargs.get("on_error")
                self._on_complete_cb = kwargs.get("on_complete")

        def __init_from_params__(self, params):
            self._name = getattr(params, "name", None)
            self._session = getattr(params, "session", None)
            self._domain = getattr(params, "domain", "MarketPrice")
            self._service = getattr(params, "service", "IDN_RDF")
            self._fields = getattr(params, "fields", [])
            self._streaming = getattr(params, "streaming", True)
            self._extended_params = getattr(params, "extended_params", None)
            self._on_refresh_cb = getattr(params, "on_refresh", None)
            self._on_status_cb = getattr(params, "on_status", None)
            self._on_update_cb = getattr(params, "on_update", None)
            self._on_error_cb = getattr(params, "on_error", None)
            self._on_complete_cb = getattr(params, "on_complete", None)

        def name(self, name):
            self._name = name
            return self

        def session(self, session):
            if session is None:
                raise AttributeError("Session is mandatory")
            else:
                self._session = session
            return self

        def with_domain(self, domain):
            if domain is None:
                self._domain = "MarketPrice"
            else:
                self._domain = domain
            return self

        def with_fields(self, fields):
            from eikon.tools import build_list
            if fields:
                self._fields = build_list(fields, "fields")
            else:
                self._fields = None
            return self

        def with_service(self, service):
            if service:
                self._service = service
            return self

        def with_streaming(self, streaming):
            if streaming is not None:
                self._streaming = streaming
            return self

        def with_extended_params(self, extended_params):
            self._extended_params = extended_params
            return self

        def on_status(self, on_status):
            self._on_status_cb = on_status
            return self

        def on_refresh(self, on_refresh):
            self._on_refresh_cb = on_refresh
            return self

        def on_update(self, on_update):
            self._on_update_cb = on_update
            return self

        def on_error(self, on_error):
            self._on_error_cb = on_error
            return self

        def on_complete(self, on_complete):
            self._on_complete_cb = on_complete
            return self

    def __init__(self, session, name,
                 domain="MarketPrice",
                 service=None,
                 fields=None,
                 streaming=True,
                 extended_params=None,
                 on_refresh=None,
                 on_status=None,
                 on_update=None,
                 on_error=None,
                 on_complete=None):
        self.__item_stream_lock = Lock()
        self._callbacks = ItemStreamCallback()
        self._name = None
        self._domain = None
        self._service = None
        self._fields = None
        self._streaming = None
        self._extended_params = None
        self._callbacks.on_refresh = None
        self._callbacks.on_status = None
        self._callbacks.on_update = None
        self._callbacks.on_error = None
        self._callbacks.on_complete = None
        self._message = None
        self._code = None

        self.__init_from_args__(name=name,
                                session=session,
                                domain=domain,
                                service=service,
                                fields=fields,
                                streaming=streaming,
                                extended_params=extended_params,
                                on_refresh=on_refresh,
                                on_status=on_status,
                                on_update=on_update,
                                on_error=on_error,
                                on_complete=on_complete)
        if self._session is None:
            raise AttributeError("Session must be defined")
        if self._name is None:
            raise AttributeError("name must be defined.")
        if type(self._name) is list:
            raise ValueError("name can't be a list.")
        if self._fields is None:
            self._fields = []

    def __init_from_args__(self, session, name, domain, service, fields,
                           streaming, extended_params,
                           on_refresh, on_status, on_update, on_error, on_complete):
        super(ItemStream, self).__init__(session)
        self._name = name
        self._domain = domain
        self._service = service
        self._fields = fields
        self._streaming = streaming if streaming is not None else True
        self._extended_params = extended_params
        self._callbacks.on_refresh = on_refresh
        self._callbacks.on_status = on_status
        self._callbacks.on_update = on_update
        self._callbacks.on_error = on_error
        self._callbacks.on_complete = on_complete

    @property
    def status(self):
        _st = dict([("status", self.state), ("code", self._code), ("message", self._message)])
        return _st

    #######################################
    #  methods to open and close session  #
    #######################################
    def open(self):
        """
        Open the item stream
        """
        self._session.log(logging.DEBUG, f"Open synchronously ItemStream {self.stream_id} to {self._name}")
        return super(ItemStream, self).open()

    def close(self):
        """
        Close the data stream
        """
        self._session.log(logging.DEBUG, f"Close ItemStream subscription {self.stream_id}")
        super(ItemStream, self).close()
        self._code = "Closed"
        self._message = ""
        return self._state

    ################################################
    #  methods to open asynchronously item stream  #
    ################################################
    async def open_async(self):
        """
        Open the data stream
        """
        self._session.log(logging.DEBUG, f"Open asynchronously ItemStream {self.stream_id} to {self._name}")
        if self._name is None:
            raise AttributeError("name parameter is mandatory")

        return await super(ItemStream, self).open_async()

    ##########################
    # ItemStream properties  #
    ##########################
    def has_error(self):
        return self._message

    ###########################################
    # Process messages from stream connection #
    ###########################################
    def _on_refresh(self, message):
        with self.__item_stream_lock:
            self._status = message.get("State")
            stream_state = self._status.get("Stream")
            self._code = stream_state
            self._message = self._status.get("Text")

            if self.state == StreamState.Pending:
                self._on_stream_state(StreamState.Open)

            super()._on_refresh(message)
            if self.state is not StreamState.Closed:
                if self._callbacks.on_refresh:
                    try:
                        self._session.log(1, "ItemStream : call on_refresh callback")
                        self._callbacks.on_refresh(self, message)
                    except Exception as e:
                        self._session.log(logging.ERROR, f"ItemStream on_refresh callback raised exception: {e!r}")
                        self._session.log(1, "Traceback:\n {}".format(sys.exc_info()[2]))

    def _on_status(self, status):
        with self.__item_stream_lock:
            state = status.get("State")
            stream_state = state.get("Stream")
            self._code = stream_state
            self._message = state.get("Text")

            if stream_state in ["Closed", "ClosedRecover", "NonStreaming", "Redirect"]:
                self._state = StreamState.Closed
                self._code = state.get("Code")
                self._session.log(1, "Set stream {} as {}".format(self.stream_id, self._state))
            if self._callbacks.on_status:
                try:
                    self._session.log(1, "ItemStream : call on_status callback")
                    self._callbacks.on_status(self, self.status)
                except Exception as e:
                    self._session.log(logging.ERROR, f"ItemStream on_status callback raised exception: {e!r}")
                    self._session.log(1, "Traceback:\n {}".format(sys.exc_info()[2]))
            super(ItemStream, self)._on_status(status)

    def _on_update(self, update):
        with self.__item_stream_lock:
            super(ItemStream, self)._on_update(update)
            if self.state is not StreamState.Closed:
                if self._callbacks.on_update:
                    try:
                        self._session.log(1, "ItemStream : call on_update callback")
                        self._callbacks.on_update(self, update)
                    except Exception as e:
                        self._session.log(logging.ERROR, f"ItemStream on_update callback raised exception: {e!r}")
                        self._session.log(1, "Traceback:\n {}".format(sys.exc_info()[2]))

    def _on_complete(self):
        with self.__item_stream_lock:
            super(ItemStream, self)._on_complete()
            if self.state is not StreamState.Closed:
                if self._callbacks.on_complete:
                    try:
                        self._session.log(1, "ItemStream : call on_complete callback")
                        self._callbacks.on_complete(self)
                    except Exception as e:
                        self._session.log(logging.ERROR, f"ItemStream on_complete callback raised exception: {e!r}")
                        self._session.log(1, "Traceback:\n {}".format(sys.exc_info()[2]))

    def _on_error(self, error):
        with self.__item_stream_lock:
            super(ItemStream, self)._on_error(error)
            if self.state is not StreamState.Closed:
                self._message = error
                if self._callbacks.on_error:
                    try:
                        self._session.log(1, "ItemStream: call on_error callback")
                        self._callbacks.on_error(self, error)
                    except Exception as e:
                        self._session.log(logging.ERROR, f"ItemStream on_error callback raised an exception: {e!r}")
                        self._session.log(1, "Traceback:\n {}".format(sys.exc_info()[2]))

    def _on_stream_state(self, state):
        super()._on_stream_state(state)
        if self._callbacks.on_status:
            try:
                self._session.log(1, "ItemStream : call on_status callback")
                self._callbacks.on_status(self, self.status)
            except Exception as e:
                self._session.log(logging.ERROR, f"ItemStream on_status callback raised exception: {e!r}")
                self._session.log(1, "Traceback:\n {}".format(sys.exc_info()[2]))
