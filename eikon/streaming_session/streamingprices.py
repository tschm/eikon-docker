# coding: utf8


__all__ = ["StreamingPrices"]


import sys
import logging
import asyncio

from pandas import DataFrame
from pandas import to_numeric
from .streamingprice import StreamingPrice
from .stream import StreamState


class StreamingPrices:
    """
    Open a streaming price subscription.

    Parameters
    ----------
    instruments: list[string]
        List of RICs to subscribe.

    service: string
        Specified the service to subscribe on.
        Default: None

    fields: string or list[string]
        Specified the fields to retrieve.
        Default: None

    on_refresh: callable object (streaming_prices, instrument_name, message)
        Called when a stream on instrument_name was opened successfully or when the stream is refreshed by the server.
        This callback is called with the reference to the streaming_prices object, the instrument name and the instrument full image.
        Default: None

    on_update: callable object (streaming_prices, instrument_name, message)
        Called when an update is received for a instrument_name.
        This callback is called with the reference to the streaming_prices object, the instrument name and the instrument update.
        Default: None

    on_status: callable object (streaming_prices, instrument_name, status)
        Called when a status is received for a instrument_name.
        This callback is called with the reference to the streaming_prices object, the instrument name and the instrument status.
        Default: None

    on_complete: callable object  (streaming_prices, instrument_name)
        Called when all subscriptions are completed.
        This callback is called with the reference to the streaming_prices object.
        Default: None

    Raises
    ------
    Exception
        If request fails.

    Examples
    --------
    >> import eikon as ek
    >> fx = ek.StreamingPrices(['EUR=', 'GBP='])
    >> fx.open()
    >> bid_eur = fx['EUR']['BID']
    >> ask_eur = fx['EUR']['ASK']
    >>
    >> def on_update(streams, instrument, msg):
            ... print(msg)
    >> subscription = ek.StreamingPrices(['VOD.L', 'EUR=', 'PEUP.PA', 'IBM.N'],
            ... ['DSPLY_NAME', 'BID', 'ASK'],
            ... on_update=on_update)
    >> subscription.open()
    {"EUR=":{"DSPLY_NAME":"RBS          LON","BID":1.1221,"ASK":1.1224}}
    {"PEUP.PA":{"DSPLY_NAME":"PEUGEOT","BID":15.145,"ASK":15.155}}
    {"IBM.N":{"DSPLY_NAME":"INTL BUS MACHINE","BID":"","ASK":""}}
    ...
    """

    class Params(object):
        def __init__(self, instruments, fields):
            self._universe = instruments
            self._fields = fields

        @property
        def instruments(self):
            return self._universe

        @property
        def fields(self):
            return self._fields

    class StreamingPricesIterator:
        """ StreamingPrices Iterator class """
        def __init__(self, streaming_prices):
            self._streaming_prices = streaming_prices
            self._index = 0

        def __next__(self):
            """" Return the next streaming item from streaming price list """
            if self._index < len(self._streaming_prices.params.instruments):
                result = self._streaming_prices[self._streaming_prices.params.instruments[self._index]]
                self._index += 1
                return result
            raise StopIteration()

    def __init__(self,
                 instruments,
                 session=None,
                 fields=[],
                 service=None,
                 on_refresh=None,
                 on_status=None,
                 on_update=None,
                 on_complete=None):
        from eikon.Profile import get_desktop_session
        if session is None:
            self._session = get_desktop_session()
        else:
            self._session = session
        if isinstance(instruments, str):
            instruments = [instruments]
        elif isinstance(instruments, list) and all(isinstance(item, str) for item in instruments):
            pass
        else:
            raise EikonError(-1, "StreamingPrices: instruments must be a list of strings")
        self._fields = fields

        self.params = StreamingPrices.Params(instruments=instruments, fields=fields)

        self._service = service
        self._streaming_prices = {}
        for name in instruments:
            self._streaming_prices[name] = StreamingPrice(session=self._session,
                                                          name=name,
                                                          fields=self._fields,
                                                          service=self._service,
                                                          on_refresh=self._on_refresh,
                                                          on_update=self._on_update,
                                                          on_status=self._on_status,
                                                          on_complete=self._on_complete)
        self._on_refresh_cb = on_refresh
        self._on_status_cb = on_status
        self._on_update_cb = on_update
        self._on_complete_cb = on_complete

        self._state = StreamState.Closed
        self._complete_event_nb = 0

    @property
    def state(self):
        return self._state

    ###################################################
    #  Access to StreamingPrices as a dict            #
    ###################################################

    def keys(self):
        if self._streaming_prices:
            return list(self._streaming_prices.keys())
        return list({}.keys())

    def values(self):
        if self._streaming_prices:
            return list(self._streaming_prices.values())
        return list({}.values())

    def items(self):
        if self._streaming_prices:
            return list(self._streaming_prices.items())
        return list({}.items())

    ###################################################
    #  Make StreamingPrices iterable                  #
    ###################################################

    def __iter__(self):
        return StreamingPrices.StreamingPricesIterator(self)

    def __getitem__(self, item):
        if item in self.params.instruments:
            return self._streaming_prices[item]
        else:
            raise KeyError(f"{item} not in StreamingPrices universe")

    def __len__(self):
        return len(self.params.instruments)

    ###################################################
    #  methods to open synchronously item stream      #
    ###################################################
    def open(self):
        """
        Open synchronously the streaming price
        """
        return self._session._loop.run_until_complete(self.open_async())

    ################################################
    #  methods to open asynchronously item stream  #
    ################################################
    async def open_async(self):
        """
        Open asynchronously the streaming price
        """
        self._session.log(1, f'StreamingPrices : open streaming on {self.params.instruments}')
        if self._state == StreamState.Open:
            return

        self._state = StreamState.Pending
        self._complete_event_nb = 0
        task_list = [stream.open_async() for stream in list(self._streaming_prices.values())]
        await asyncio.wait(task_list, return_when=asyncio.ALL_COMPLETED)
        self._state = StreamState.Open
        self._session.log(1, f'StreamingPrices : start asynchrously streaming on {self.params.instruments} done')
        return self._state

    def close(self):
        if self._state is StreamState.Open:
            self._session.log(1, f'StreamingPrices : close streaming on {self.params.instruments}')
            for stream in list(self._streaming_prices.values()):
                stream.close()
        self._state = StreamState.Closed
        return self._state

    def get_snapshot(self, instruments=None, fields=None, convert=True):
        """
        Returns a Dataframe filled with snapshot values for a list of instrument names and a list of fields.

        Parameters
        ----------
        instruments: list of strings
            List of instruments to request snapshot data on.

        fields: list of strings
            List of fields to request.

        convert: boolean
            If True, force numeric conversion for all values.

        Returns
        -------
            pandas.DataFrame

            pandas.DataFrame content:
                - columns : instrument and fieled names
                - rows : instrument name and field values

        Raises
        ------
            Exception
                If request fails or if server returns an error

            ValueError
                If a parameter type or value is wrong

        Examples
        --------
        >>> import eikon as ek
        >>> ek.set_app_key('set your app key here')
        >>> streaming_prices = ek.StreamingPrices(instruments=["MSFT.O", "GOOG.O", "IBM.N"], fields=["BID", "ASK", "OPEN_PRC"])
        >>> data = streaming_prices.get_snapshot(["MSFT.O", "GOOG.O"], ["BID", "ASK"])
        >>> data
              Instrument    BID        ASK
        0     MSFT.O        150.9000   150.9500
        1     GOOG.O        1323.9000  1327.7900
        2     IBM.N         NaN        NaN
        """
        from eikon.eikonError import EikonError

        if instruments:
            for name in instruments:
                if name not in self.params.instruments:
                    raise ElektronError(-1, f'Instrument {name} was not requested : {self.params.instruments}')

        if fields:
            for field in fields:
                if field not in self.params.fields:
                    raise EikonError(-1, f'Field {field} was not requested : {self.params.fields}')

        _universe = instruments if instruments else self.params.instruments
        _all_fields_value = {name: self._streaming_prices[name].get_fields(fields)
        if name in self._streaming_prices else None
                             for name in _universe}
        _fields = []

        if not fields:
            fields = []
            for field_values in list(_all_fields_value.values()):
                if field_values:
                    _fields.extend(field for field in list(field_values.keys()) if field not in _fields)
        else:
            _fields = fields

        _df_source = {f: [_all_fields_value[name][f] if _all_fields_value[name].get(f) else None
                          for name in _universe] for f in _fields}
        _price_dataframe = DataFrame(_df_source, columns=_fields)
        if convert:
            _price_dataframe = _price_dataframe.apply(to_numeric, errors='ignore')
        _price_dataframe.insert(0, 'Instrument', _universe)

        return _price_dataframe

    #########################################
    # Messages from stream_cache connection #
    #########################################
    def _on_refresh(self, stream, message):
        if self._on_refresh_cb:
            try:
                self._session.log(1, 'StreamingPrices : call on_refresh callback')
                self._session._loop.call_soon_threadsafe(self._on_refresh_cb, self, stream.name, message)
                # self._on_refresh_cb(self, name, message)
            except Exception as e:
                self._session.log(logging.ERROR, f'StreamingPrices on_refresh callback raised exception: {e!r}')
                self._session.log(1, f'Traceback : {sys.exc_info()[2]}')

    def _on_status(self, stream, status):
        if self._on_status_cb:
            try:
                self._session.log(1, 'StreamingPrices : call on_status callback')
                self._session._loop.call_soon_threadsafe(self._on_status_cb, self, stream.name, status)
            except Exception as e:
                self._session.log(logging.ERROR, f'StreamingPrices on_status callback raised exception: {e!r}')
                self._session.log(1, f'Traceback : {sys.exc_info()[2]}')

    def _on_update(self, stream, update):
        if self._on_update_cb:
            try:
                self._session.log(1, 'StreamingPrices : call on_update callback')
                self._session._loop.call_soon_threadsafe(self._on_update_cb, self, stream.name, update)
            except Exception as e:
                self._session.log(logging.ERROR, f'StreamingPrices on_update callback raised exception: {e!r}')
                self._session.log(1, f'Traceback : {sys.exc_info()[2]}')

    def _on_complete(self, stream):
        self._complete_event_nb += 1
        if self._complete_event_nb == len(self.params.instruments):
            if self._on_complete_cb:
                try:
                    self._session.log(1, 'StreamingPrices : call on_complete callback')
                    self._session._loop.call_soon_threadsafe(self._on_complete_cb, self)
                except Exception as e:
                    self._session.log(logging.ERROR, f'StreamingPrices on_complete callback raised exception: {e!r}')
                    self._session.log(1, f'Traceback : {sys.exc_info()[2]}')