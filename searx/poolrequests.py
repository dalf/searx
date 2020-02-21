from time import time
import threading
import concurrent.futures
import asyncio
import logging

import uvloop
import httpx
from searx import settings


threadLocal = threading.local()
pool_connections = settings['outgoing'].get('pool_connections', 100)  # Magic number kept from previous code
pool_maxsize = settings['outgoing'].get('pool_maxsize', 10)  # Picked from constructor


def set_timeout_for_thread(timeout, start_time=None):
    threadLocal.timeout = timeout
    threadLocal.start_time = start_time


def reset_time_for_thread():
    threadLocal.total_time = 0


def get_time_for_thread():
    return threadLocal.total_time


loop = None
clients = dict()


async def get_client(verify, proxies):
    global clients, pool_connections, pool_maxsize
    key = str(verify) + '|' + str(proxies)
    if key not in clients:
        user_pool_limits = httpx.PoolLimits(soft_limit=pool_maxsize, hard_limit=pool_connections)
        client = httpx.AsyncClient(http2=True, pool_limits=user_pool_limits, verify=verify, proxies=proxies)
        clients[key] = client
    else:
        client = clients[key]
    return client


async def send_request(method, url, kwargs):
    if isinstance(url, bytes):
        url = url.decode('utf-8')

    client = await get_client(kwargs.get('verify', True), kwargs.get('proxies', None))
    if 'verify' in kwargs:
        del kwargs['verify']
    if 'proxies' in kwargs:
        del kwargs['proxies']
    if 'stream' in kwargs:
        del kwargs['stream']
        raise NotImplementedError('stream not supported')
    
    response = await client.request(method.upper(), url, **kwargs)

    # requests compatibility
    try:
        response.raise_for_status()
        response.ok = True
    except httpx.HTTPError:
        response.ok = False

    return response


def request(method, url, **kwargs):
    global loop

    """same as requests/requests/api.py request(...)"""
    time_before_request = time()

    # proxies
    kwargs['proxies'] = settings['outgoing'].get('proxies') or None

    # timeout
    if 'timeout' in kwargs:
        timeout = kwargs['timeout']
    else:
        timeout = getattr(threadLocal, 'timeout', None)
        if timeout is not None:
            kwargs['timeout'] = timeout

    # do request
    future = asyncio.run_coroutine_threadsafe(send_request(method, url, kwargs), loop)
    response = future.result()

    time_after_request = time()

    # is there a timeout for this engine ?
    if timeout is not None:
        timeout_overhead = 0.2  # seconds
        # start_time = when the user request started
        start_time = getattr(threadLocal, 'start_time', time_before_request)
        search_duration = time_after_request - start_time
        if search_duration > timeout + timeout_overhead:
            raise httpx.exceptions.ReadTimeout(response=response)

    if hasattr(threadLocal, 'total_time'):
        threadLocal.total_time += time_after_request - time_before_request

    return response


def get(url, **kwargs):
    kwargs.setdefault('allow_redirects', True)
    return request('get', url, **kwargs)


def options(url, **kwargs):
    kwargs.setdefault('allow_redirects', True)
    return request('options', url, **kwargs)


def head(url, **kwargs):
    kwargs.setdefault('allow_redirects', False)
    return request('head', url, **kwargs)


def post(url, data=None, **kwargs):
    return request('post', url, data=data, **kwargs)


def put(url, data=None, **kwargs):
    return request('put', url, data=data, **kwargs)


def patch(url, data=None, **kwargs):
    return request('patch', url, data=data, **kwargs)


def delete(url, **kwargs):
    return request('delete', url, **kwargs)


def init():
    # log
    for logger_name in ('httpx.client', 'httpx.config', 'hpack.hpack', 'hpack.table',
                        'httpx.dispatch.connection_pool', 'httpx.dispatch.connection',
                        'httpx.dispatch.http2', 'httpx.dispatch.http11'):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    #

    # loop
    def loop_thread():
        global loop
        loop = uvloop.new_event_loop()
        loop.run_forever()

    th = threading.Thread(
        target=loop_thread,
        name='asyncio_loop',
        daemon=True,
    )
    th.start()

init()
