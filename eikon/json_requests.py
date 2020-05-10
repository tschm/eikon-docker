# coding: utf-8

__all__ = ['send_json_request']

import requests_async
import json
import sys
import logging
import time
import eikon.Profile

try:
    from json.decoder import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError

from .tools import is_string_type
from .eikonError import EikonError

__internal_timer__ = 15000


def send_json_request(entity, payload, debug=False):
    """
    Returns the JSON response.
    This function can be used for advanced usage or early access to new features.

    Parameters
    ----------
    entity: string
        A string containing a service name

    payload: string
        A string containing a JSON request

    debug: boolean, optional
        When set to True, the json request and response are printed.
        Default: False

    Returns
    -------
    string
        The JSON response as a string

    Raises
    ------
        EikonError
            If daemon is disconnected

        requests.Timeout
            If request times out

        Exception
            If request fails (HTTP code other than 200)

        EikonError
            If daemon is disconnected
    """
    profile = eikon.Profile.get_profile()
    if profile:
        logger = profile.logger
        logger.trace('entity: {}'.format(entity))
        logger.trace('payload: {}'.format(payload))

        if not is_string_type(entity):
            error_msg = 'entity must be a string identifying an UDF endpoint'
            logger.error(error_msg)
            raise ValueError(error_msg)
        try:
            if is_string_type(payload):
                data = json.loads(payload)
            elif type(payload) is dict:
                data = payload
            else:
                error_msg = 'payload must be a string or a dictionary'
                logger.error(error_msg)
                raise ValueError(error_msg)
        except JSONDecodeError as e:
            error_msg = 'payload must be json well formed.\n'
            error_msg += str(e)
            logger.error(error_msg)
            raise e

        try:
            # build the request
            udf_request = {'Entity': {'E': entity, 'W': data} }
            logger.debug('Request:{}'.format(udf_request))
            response = profile._get_http_session().post(profile.get_url(),
                                                        json=udf_request,
                                                        headers={'Content-Type': 'application/json',
                                              'x-tr-applicationid': profile.get_app_key()},
                                                        timeout=profile.get_timeout())

            try:
                logger.debug('HTTP Response code: {}'.format(response.status_code))
                logger.debug('HTTP Response: {}'.format(response.text))
            except UnicodeEncodeError as unicode_error:
                _response = json.dumps(response.text, ensure_ascii=False).encode('utf8')
                logger.debug(f'HTTP Response unicode: {_response}')

            if response.status_code == 200:
                result = response.json()
                logger.trace('Response size: {}'.format(sys.getsizeof(json.dumps(result))))

                # Manage specifically DataGrid async mode
                if entity.startswith('DataGrid') and entity.endswith('Async'):
                    ticket = _check_ticket_async(result)
                    while ticket:
                        ticket_request = {'Entity': {
                                             'E': entity,
                                             'W': {'requests': [{'ticket': ticket}]}
                                         }}
                        logger.debug('Send ticket request:{}'.format(ticket_request))
                        response = profile._get_http_session().post(profile.get_url(),
                                                                    json=ticket_request,
                                                                    headers={'Content-Type': 'application/json',
                                                                       'x-tr-applicationid': profile.get_app_key()},
                                                                    timeout=profile.get_timeout())
                        try:
                            logger.debug(f'HTTP Response: {response.text}')
                        except UnicodeEncodeError:
                            _response = json.dumps(response.text, ensure_ascii=False).encode('utf8')
                            logger.debug(f'HTTP Response unicode: {_response}')
                        result = response.json()
                        ticket = _check_ticket_async(result)

                _check_server_error(result)
                return result
            else:
                _raise_for_status(response)

        except requests_async.exceptions.ConnectionError as connectionError:
             network_error = True
        if network_error:
            error_msg = 'Eikon Proxy not installed or not running. Please read the documentation to know how to install and run the proxy'
            logger.error(error_msg)
            raise EikonError(401, error_msg)


def _check_ticket_async(server_response):
    """
    Check server response.

    Check is the server response contains a ticket.

    :param server_response: request's response
    :type server_response: requests.Response
    :return: ticket value if response contains a ticket, None otherwise
    """
    logger = eikon.Profile.get_profile().logger
    # ticket response should contains only one key
    if len(server_response) == 1:
        for key, value in list(server_response.items()):
            ticket = value[0]
            if ticket and ticket.get('estimatedDuration'):
                ticket_duration = int(ticket['estimatedDuration'])
                ticket_duration = min(ticket_duration, __internal_timer__)
                ticket_value = ticket['ticket']
                message = 'Receive ticket from {}, wait for {} second'.format(key, ticket_duration / 1000.0)
                if ticket_duration > 1000:
                    message = message + 's'
                logger.info(message)
                time.sleep(ticket_duration / 1000.0)
                return ticket_value
    return None


def _check_server_error(server_response):
    """
    Check server response.

    Check is the server response contains an HTPP error or a server error.

    :param server_response: request's response
    :type server_response: requests.Response
    :return: nothing

    :raises: Exception('HTTP error : <error_message>) if response contains HTTP response
              ex: '<500 Server error>'
          or Exception('Server error (<error code>) : <server_response>') if UDF returns an error
              ex: {u'ErrorCode': 500, u'ErrorMessage': u'Requested datapoint was not found: News_Headlines', u'Id': u''}

    """
    logger = eikon.Profile.get_profile().logger
    str_response = str(server_response)

    # check HTTP response (server response is an object that can contain ErrorCode attribute)
    if hasattr(server_response, 'ErrorCode'):
        logger.error(getattr(server_response, 'ErrorMessage'))
        raise requests_async.HTTPError(response=server_response)

    # check HTTPError on proxy request
    if str_response.startswith('<') and str_response.endswith('>'):
        logger.error(str_response)
        raise requests_async.HTTPError(response=server_response)

    # check UDF response (server response is JSON and it can contain ErrorCode + ErrorMessage keys)
    if 'ErrorCode' in server_response and 'ErrorMessage' in server_response:
        error_message = server_response['ErrorMessage']
        if len(error_message.split(',')) > 4:
            status, reason_phrase, version, content, headers = error_message.split(',')[:5]
        logger.error(error_message)
        raise EikonError(int(server_response['ErrorCode']), error_message)

    # check DataGrid response (server response is JSON and it can contain error + transactionId keys)
    if 'error' in server_response and 'transactionId' in server_response:
        error_message = '{} (transactionId:{}'.format(server_response['error'],server_response['transactionId'])
        logger.error(error_message)
        raise EikonError(400, error_message)


def _raise_for_status(response):
    """Raises stored :class:`HTTPError`, if one occurred."""

    error_msg = ''
    if isinstance(response.reason, bytes):
        # We attempt to decode utf-8 first because some servers
        # choose to localize their reason strings. If the string
        # isn't utf-8, we fall back to iso-8859-1 for all other
        # encodings. (See PR #3538)
        try:
            reason = response.reason.decode('utf-8')
        except UnicodeDecodeError:
            reason = response.reason.decode('iso-8859-1')
    else:
        reason = response.reason

    logger = eikon.Profile.get_profile().logger

    # Check if retry-after is in headers
    retry_after = response.headers.get('retry-after', '0')

    if eikon.Profile.get_profile().get_log_level() < logging.INFO:
        rate_limit = response.headers.get('x-ratelimit-limit')
        rate_remaining = response.headers.get('x-ratelimit-remaining')
        volume_limit = response.headers.get('x-volumelimit-limit')
        volume_remaining = response.headers.get('x-volumelimit-remaining')

        logger.trace('Headers: x_ratelimit_limit={} / x_ratelimit_remaining={} '.format(rate_limit, rate_remaining))
        logger.trace('         x_volumelimit_limit={} / x_volumelimit_remaining={}'.format(volume_limit, volume_remaining))
        logger.trace('         retry_after {}'.format(retry_after))

    if 400 <= response.status_code < 500:
        error_msg = 'Client Error: %s' % response.text
    elif 500 <= response.status_code < 600:
        error_msg = 'Server Error: %s' % response.text

    if retry_after is not '0':
        error_msg += ' Wait for {} second{}'.format(retry_after, '.' if retry_after is '1' else 's.')

    if error_msg:
        logger.error('Error code {} | {}'.format(response.status_code, error_msg))
        raise EikonError(response.status_code, error_msg)
