# coding: utf-8

__all__ = ['EikonError']


class EikonError(Exception):
    """
    Base class for exceptions specific to Eikon platform.
    """
    def __init__(self, code, message):
        """
        Parameters
        ----------
        code: int

        message: string
            Indicate the sort direction. Possible values are 'asc' or 'desc'. The default value is 'asc'
        """
        self.code = code
        self.message = message

    def __str__(self):
        return 'Error code {} | {}'.format(self.code, self.message)
