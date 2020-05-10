# coding: utf-8

__all__ = ['get_symbology']


import eikon.json_requests
from .tools import is_string_type, check_for_string_or_list_of_strings, check_for_string
import pandas as pd


Symbology_UDF_endpoint = 'SymbologySearch'
symbol_types = {"ric": "RIC", "isin": "ISIN", "cusip": "CUSIP", "sedol": "SEDOL",
                "ticker": "ticker", "lipperid": "lipperID", "imo": "IMO", "oapermid": "OAPermID"}


def get_symbology(symbol, from_symbol_type='RIC', to_symbol_type=None, raw_output=False, debug=False, bestMatch=True):
    """
    Returns a list of instrument names converted into another instrument code.
    For example: convert SEDOL instrument names to RIC names

    Parameters
    ----------
    symbol: string or list of strings
        Single instrument or list of instruments to convert.

    from_symbol_type: string
        Instrument code to convert from.
        Possible values: 'CUSIP', 'ISIN', 'SEDOL', 'RIC', 'ticker', 'lipperID', 'IMO'
        Default: 'RIC'

    to_symbol_type: string or list
        Instrument code to convert to.
        Possible values: 'CUSIP', 'ISIN', 'SEDOL', 'RIC', 'ticker', 'lipperID', 'IMO', 'OAPermID'
        Default: None  (means all symbol types are requested)

    raw_output: boolean, optional
        Set this parameter to True to get the data in json format
        if set to False, the function will return a data frame
        Default: False

    debug: boolean, optional
        When set to True, the json request and response are printed.
        Default: False

    bestMatch: boolean, optional
        When set to True, only primary symbol is requested.
        When set to false, all symbols are requested
        Default: True

    Returns
    -------
        If raw_output is set to True, the data will be returned in the json format.
        If raw_output is False (default value) the data will be returned as a pandas.DataFrame

        pandas.DataFrame content:
            - columns : Symbol types
            - rows : Symbol requested
            - cells : the symbols (None if not found)
            - symbol : The requested symbol

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
    >>> ISIN_codes = ek.get_symbology(["MSFT.O", "GOOG.O", "IBM.N"], from_symbol_type="RIC", to_symbol_type="ISIN")
    >>> ISIN_codes
                    ISIN
    MSFT.O  US5949181045
    GOOG.O  US02079K1079
    IBM.N   US4592001014
    """
    logger = eikon.Profile.get_profile().logger

    # check if symbol type is string or list of strings
    check_for_string_or_list_of_strings(symbol, 'symbol')
    if is_string_type(symbol): symbol = [symbol]

    # check if from_symbol type is string
    check_for_string(from_symbol_type, 'from_symbol_type')
    try:
        from_symbol_type = symbol_types[from_symbol_type.lower()]
    except:
        error_msg = 'from_symbol_type "' + from_symbol_type + '" should be in ' + [symbol_types[key] for key in symbol_types].__str__()
        logger.error(error_msg)
        raise ValueError(error_msg)

    # if from_symbol_type is RIC, apply rics = [ric.upper() if ric.islower() else ric for ric in rics ] transformation
    if from_symbol_type is 'RIC':
        symbol = [ric.upper() if ric.islower() else ric for ric in symbol]

    # to_symbol_type to None means request all symbol types
    if to_symbol_type is not None:
        # otherwise check if to_symbol type is string or list of strings
        check_for_string_or_list_of_strings(to_symbol_type, 'to_symbol_type')
        if is_string_type(to_symbol_type):
            to_symbol_type = [to_symbol_type.strip()]
        try:
            to_symbol_type = [symbol_types[_.lower()] for _ in to_symbol_type]
        except:
            error_msg = 'All items in the parameter to_symbol should be in ' + [symbol_types[key] for key in symbol_types].__str__()
            logger.error(error_msg)
            raise ValueError(error_msg)

    payload = {'symbols': symbol, 'from': from_symbol_type, 'to': to_symbol_type, 'bestMatchOnly': bestMatch}
    result = eikon.json_requests.send_json_request(Symbology_UDF_endpoint, payload, debug=debug)
   
    if raw_output:
        return result
    else:
        if bestMatch:
            results_dict = dict([(_['symbol'], _['bestMatch']) for _ in result['mappedSymbols']])
        else:
            results_dict = dict([(_['symbol'], _) for _ in result['mappedSymbols']])
        if len(results_dict):
            return pd.DataFrame(results_dict).transpose()
        else:
            return pd.DataFrame([])
