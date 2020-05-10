# coding: utf-8

__all__ = ['StreamingConnectionConfiguration']


import socket


class StreamingConnectionConfiguration(object):

    def __init__(self):
        self.host = "host.docker.internal:15000"
        self.user = ""
        self.dacs_application_id = "256"
        self.dacs_username = ""
        self.auth_token = None
        self.connection_retry = 5
        self.secure = False
        self._header = []
        self.login_message = None

        try:
            position_host = socket.gethostname()
            self._dacs_position = f"{socket.gethostbyname(position_host)}/{position_host}"
        except socket.gaierror:
            self._dacs_position = "127.0.0.1"

    @property
    def url(self):
        if self.secure:
            secure_token = "wss"
        else:
            secure_token = "ws"
        _url = f"{secure_token}://{self.host}/WebSocket"
        return _url

