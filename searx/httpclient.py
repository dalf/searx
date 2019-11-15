# -*- coding: utf-8 -*-

import asyncio
import time
import logging
import aiohttp
import aiohttp.client_reqrep
import httpx
import httpx.models
import httpx.config

from searx import settings, logger
from httpx import (Request, Response)
from httpx.exceptions import (HTTPError, Timeout, ConnectTimeout, ReadTimeout, WriteTimeout, PoolTimeout, ProxyError,
                              ProtocolError, DecodingError, RedirectError, TooManyRedirects, RedirectBodyUnavailable,
                              RedirectLoop, NotRedirectResponse, StreamError, StreamConsumed, ResponseNotRead,
                              ResponseClosed, InvalidURL, CookieConflict)


logger = logger.getChild('httpclient')
SESSION = None


def clientresponse_ok(self):
    try:
        self.raise_for_status()
    except HTTPError:
        return False
    return True


async def initialize():
    global SESSION

    # monkey patch
    setattr(aiohttp.client_reqrep.ClientResponse, 'ok', clientresponse_ok)

    # FIXME: pool_maxsize, pool_connections names don't match soft and hard limits
    soft_limit = settings['outgoing'].get('pool_maxsize', 10)
    hard_limit = settings['outgoing'].get('pool_connections', 100)
    pool_limits = httpx.config.PoolLimits(soft_limit=soft_limit, hard_limit=hard_limit, pool_timeout=10.0)

    # proxies
    proxies = settings['outgoing'].get('proxies') or None

    conn = aiohttp.TCPConnector(limit_per_host=30, limit=100, use_dns_cache=True)
    SESSION = aiohttp.ClientSession(connector=conn)


async def close():
    await SESSION.close()


def _get_context():
    return asyncio.Task.current_task()


def set_timeout_for_thread(timeout, start_time=None):
    context = _get_context()
    context.timeout = timeout
    context.start_time = start_time
    context.total_time = 0


def get_time_for_thread():
    return _get_context().total_time


async def request(method, url, **kwargs):
    """same as requests/requests/api.py request(...)"""
    time_before_request = time.time()
    context = _get_context()

    # timeout
    if 'timeout' in kwargs:
        timeout = kwargs['timeout']
    else:
        timeout = getattr(context, 'timeout', None)
        if timeout is not None:
            kwargs['timeout'] = timeout

    if 'verify' in kwargs:
        del kwargs['verify']

    # do request
    response = await SESSION.request(method, url, **kwargs)
    time_after_request = time.time()

    # debug
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("\"{0} {1}\" {2}".format(method, response.url, response.status))

    # is there a timeout for this engine ?
    if timeout is not None:
        timeout_overhead = 0.2  # seconds
        # start_time = when the user request started
        start_time = getattr(context, 'start_time', time_before_request)
        search_duration = time_after_request - start_time
        if search_duration > timeout + timeout_overhead:
            raise httpx.exceptions.Timeout(response=response)

    if hasattr(context, 'total_time'):
        context.total_time += time_after_request - time_before_request

    return response


async def get(url, **kwargs):
    kwargs.setdefault('allow_redirects', True)
    return await request('get', url, **kwargs)


async def options(url, **kwargs):
    kwargs.setdefault('allow_redirects', True)
    return await request('options', url, **kwargs)


async def head(url, **kwargs):
    kwargs.setdefault('allow_redirects', False)
    return await request('head', url, **kwargs)


async def post(url, data=None, **kwargs):
    return await request('post', url, data=data, **kwargs)


async def put(url, data=None, **kwargs):
    return await request('put', url, data=data, **kwargs)


async def patch(url, data=None, **kwargs):
    return await request('patch', url, data=data, **kwargs)


async def delete(url, **kwargs):
    return await request('delete', url, **kwargs)
