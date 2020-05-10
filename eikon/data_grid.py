# coding: utf-8

__all__ = ['TR_Field', 'get_data']

import eikon.json_requests
import pandas as pd
from .tools import get_json_value,is_string_type, check_for_string_or_list_of_strings, \
    check_for_string, build_dictionary, build_list, build_list_with_params


DataGrid_UDF_endpoint = 'DataGrid'
DataGridAsync_UDF_endpoint = 'DataGrid_StandardAsync'


def TR_Field(field_name, params=None, sort_dir=None, sort_priority=None):
    """
    This is a helper function to build the field for the get_data function.

    Parameters
    ----------
    field_name: string
        Field name to request. You can find the list in Data Item Browser.

    params: dict
        Dictionary containing the parameters for the field passed in the argument field_name

    sort_dir: string
        Indicate the sort direction. Possible values are 'asc' or 'desc'. The default value is 'asc'

    sort_priority: integer
        Gives a priority to the field for the sorting. The highest priority is 0 (zero). the default value is None

    Return
    ------
    Returns a dictionary that can directly passed to get_data.

    Example
    -------
    TR_Field('tr.revenue')
    TR_Field('tr.open','asc',1)
    TR_Field('TR.GrossProfit',{'Scale': 6, 'Curn': 'EUR'},'asc',0)

    """
    logger = eikon.Profile.get_profile().logger

    if params is not None and type(params) != dict:
        logger.error('TR_Field error: The argument params must be a dictionary')
        raise ValueError('TR_Field error: The argument params must be a dictionary')
    
    if type(params) == dict and not bool(params):
        error_msg = 'TR_Field error: The argument params must be a non empty dictionary or set to None (default value if not set)'
        logger.error(error_msg)
        raise ValueError(error_msg)

    field = {field_name:{}}
    if params: field[field_name]['params'] = params

    if sort_dir is not None:
        if is_string_type(sort_dir) and sort_dir in ['asc','desc']:
            field[field_name]['sort_dir'] = sort_dir
        else:
            error_msg = 'TR_Field error: The argument sort_dir must be a string ("asc" or "desc")'
            logger.error(error_msg)
            raise ValueError(error_msg)

    if sort_priority is not None:
        if type(sort_priority)is not int:
            error_msg = 'TR_Field error: The argument sort_priority must be a integer'
            logger.error(error_msg)
            raise ValueError(error_msg)
        field[field_name]['sort_priority'] = sort_priority
    return field


def get_data(instruments, fields, parameters=None, field_name=False, raw_output=False, debug=False):
    """
    Returns a pandas.DataFrame with fields in columns and instruments as row index

    Parameters
    ----------
    instruments: string or list
        Single instrument or list of instruments to request.

    fields: string, dictionary or list of strings and/or dictionaries.
        List of fields to request.

        Examples:

        - 'TR.PriceClose'
        - {'TR.GrossProfit': { 'params':{ 'Scale': 6, 'Curn': 'EUR' }}
        - {'TR.GrossProfit': { 'params':{ 'Scale': 6, 'Curn': 'EUR' },sort_dir:'desc'}
        - ['TR.PriceClose','TR.PriceOpen']
        - [{'TR.PriceClose':  {'sort_dir':asc,sort_priority:1}},{'TR.PriceOpen':  {'sort_dir':asc,sort_priority:0}}
        
        You can use the function TR_Field to build the fields:

        >>> fields = [ek.TR_Field('tr.revenue'),ek.TR_Field('tr.open','asc',1),ek.TR_Field('TR.GrossProfit',{'Scale': 6, 'Curn': 'EUR'},'asc',0)]
        >>> data, err = ek.get_data(["IBM","MSFT.O"],fields)
       
        Tips:
        You can launch the Data Item Browser to discover fields and parameters,
        or copy field names and parameters from TR Eikon - MS Office formulas

    parameters: string or dictionary, optional
        Single global parameter key=value or dictionary of global parameters to request.

        Default: None

    field_name: boolean, optional
        Define if column headers are filled with field name or display names.

        If True value, field names will ube used as column headers. Otherwise, the full display name will be used.

        Default: False

    raw_output: boolean, optional
        By default the output is a pandas.DataFrame.

        Set raw_output=True to get data in Json format.

        Default: False

    debug: boolean, optional
        When set to True, the json request and response are printed. Default value is False

    Returns
    -------
        pandas.DataFrame
            Returns pandas.DataFrame with fields in columns and instruments as row index

        errors
            Returns a list of errors

    Raises
    ----------
        Exception
            If http request fails or if server returns an error.

        ValueError
            If a parameter type or value is wrong.

    Examples
    --------
    >>> import eikon as ek
    >>> ek.set_app_key('set your app key here')
    >>> data, err = ek.get_data(["IBM", "GOOG.O", "MSFT.O"], ["TR.PriceClose", "TR.Volume", "TR.PriceLow"])
    >>> data, err = ek.get_data("IBM", ['TR.Employees', {'TR.GrossProfit':{'params':{'Scale': 6, 'Curn': 'EUR'},'sort_dir':'asc'}}])
    >>> fields = [ek.TR_Field('tr.revenue'),ek.TR_Field('tr.open',None,'asc',1),ek.TR_Field('TR.GrossProfit',{'Scale': 6, 'Curn': 'EUR'},'asc',0)]
    >>> data, err = ek.get_data(["IBM","MSFT.O"],fields)
    """
    logger = eikon.Profile.get_profile().logger

    check_for_string_or_list_of_strings(instruments, 'instruments')
    instruments = build_list(instruments, 'instruments')
    instruments = [value.upper() if value.islower() else value for value in instruments]

    if parameters:
        parameters = build_dictionary(parameters, 'parameters')

    fields = parse_fields(fields)
    fields_for_request = []
    for f in fields:
        keys =  list(f.keys())
        if len(keys) != 1:
            with 'get_data error: The field dictionary should contain a single key which is the field name' as msg:
                logger.error(msg)
                raise ValueError(msg)
        name = list(f.keys())[0]
        field_info = f[name]
        if type(field_info) != dict:
            with 'get_data error: The parameters for the file {} should be passed in a dict'.format(name) as error_msg:
                logger.error(error_msg)
                raise ValueError(error_msg)

        field = {'name':name}
        if 'sort_dir' in list(field_info.keys()): field['sort'] = field_info['sort_dir']
        if 'sort_priority' in list(field_info.keys()): field['sortPriority'] = field_info['sort_priority']
        if 'params' in list(field_info.keys()): field['parameters'] = field_info['params']
        fields_for_request.append (field)
     
    payload = {'instruments': instruments,'fields': fields_for_request}
    if parameters: payload.update({'parameters': parameters})

    _endpoint = DataGridAsync_UDF_endpoint

    if _endpoint == DataGridAsync_UDF_endpoint:
        payload = {'requests': [payload]}

    result = eikon.json_requests.send_json_request(_endpoint, payload, debug=debug)

    if result.get('responses'):
        result = result['responses'][0]

    if raw_output:
        return result

    return get_data_frame(result, field_name)


def parse_fields(fields):
    if is_string_type(fields):
        return [{fields: {}}]

    logger = eikon.Profile.get_profile().logger
    if type(fields) == dict:
        if len(fields) is 0:
            with 'get_data error: fields list must not be empty' as error_msg:
                logger.error(error_msg)
                raise ValueError(error_msg)
        return [fields]
    field_list = []
    if type(fields) == list:
        if len(fields) is 0:
            with 'get_data error: fields list must not be empty' as error_msg:
                logger.error(error_msg)
                raise ValueError(error_msg)
        for f in fields:
             if is_string_type(f):
                 field_list.append({f:{}})
             elif type(f) == dict:
                 field_list.append(f)
             else:
                 error_msg = 'get_data error: the fields should be of type string or dictionary'
                 eikon.Profile.get_profile().logger.error(error_msg)
                 raise ValueError(error_msg)
        return field_list

    error_msg = 'get_data error: the field parameter should be a string, a dictionary , or a list of strings|dictionaries'
    eikon.Profile.get_profile().logger.error(error_msg)
    raise ValueError(error_msg)


def get_data_value(value):
    if is_string_type(value):
        return value
    elif value is dict:
        return value['value']
    else:
        return value


def get_data_frame(data_dict, field_name=False):
    if field_name:
        headers = [header.get('field', header.get('displayName')) for header in data_dict['headers'][0]]
    else:
        headers = [header['displayName'] for header in data_dict['headers'][0]]
    data = pd.np.array([[get_data_value(value) for value in row] for row in data_dict['data']])
    if len(data):
        df = pd.DataFrame(data, columns=headers)
    else:
        df = pd.DataFrame([], columns=headers)
    df = df.apply(pd.to_numeric, errors='ignore')
    errors = get_json_value(data_dict, 'error')
    return df, errors
