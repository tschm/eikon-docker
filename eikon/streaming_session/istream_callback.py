# coding: utf8


# __all__ = ['ItemStreamCallback']


class ItemStreamCallback(object):
    """
    All callbacks for item stream.

    Parameters
    ----------
    on_refresh: callable object
        Called when the stream is opened or when the record is refreshed with a new image.
        This callback receives a full image
        Default: None

    on_update: callable object
        Called when an update is received.
        This callback receives an utf-8 string as argument.
        Default: None

    on_error: callable object
        Called when an error occurs.
        This callback receives Exception as argument
        Default: None

    on_status: callable object
        Called when subscription status changed.
        This callback receives an status as argument.
        Default: None

    on_complete: callable object
        Called when the stream received all expected data.

    Raises
    ------
    Exception
        If request fails or if Refinitiv Services return an error
    """

    def __init__(self):
        self._on_refresh_cb = None
        self._on_update_cb = None
        self._on_error_cb = None
        self._on_status_cb = None
        self._on_complete_cb = None

    @property
    def on_refresh(self):
        return self._on_refresh_cb

    @on_refresh.setter
    def on_refresh(self, on_refresh_cb):
        self._on_refresh_cb = on_refresh_cb

    @property
    def on_update(self):
        return self._on_update_cb

    @on_update.setter
    def on_update(self, on_update_cb):
        self._on_update_cb = on_update_cb

    @property
    def on_error(self):
        return self._on_error_cb

    @on_error.setter
    def on_error(self, on_error_cb):
        self._on_error_cb = on_error_cb

    @property
    def on_status(self):
        return self._on_status_cb

    @on_status.setter
    def on_status(self, on_status_cb):
        self._on_status_cb = on_status_cb

    @property
    def on_complete(self):
        return self._on_complete_cb

    @on_complete.setter
    def on_complete(self, on_complete_cb):
        self._on_complete_cb = on_complete_cb
