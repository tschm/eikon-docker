# coding: utf-8
__version__ = '1.1.2'

"""
Eikon Data API for Python allows your Python applications to access Refinitiv data directly from Eikon.
It's usage requires:
    - An App Key (you can create it wit App Key Generator in Eikon Desktop)
    - Eikon Desktop application running on your local machine
"""

from .Profile import *
from .symbology import get_symbology
from .json_requests import send_json_request
from .news_request import get_news_headlines, get_news_story
from .time_series import get_timeseries
from .data_grid import get_data, TR_Field
from .eikonError import EikonError
from .streaming_session import *
