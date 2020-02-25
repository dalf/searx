from time import time
import threading
import asyncio
import logging
import ssl

import uvloop
import httpx
from searx import settings


threadLocal = threading.local()
pool_connections = settings['outgoing'].get('pool_connections', 100)  # Magic number kept from previous code
pool_maxsize = settings['outgoing'].get('pool_maxsize', 10)  # Picked from constructor

# Firefox cipher list
# https://clienttest.ssllabs.com:8443/ssltest/viewMyClient.html
# openssl ciphers -V ALL@SECLEVEL=0
FIREFOX_CIPHERS = ":".join([
    'TLS_AES_128_GCM_SHA256',  # (0x1301)
    'TLS_CHACHA20_POLY1305_SHA256',  # (0x1303)
    'TLS_AES_256_GCM_SHA384',  # (0x1302)
    'ECDHE-ECDSA-AES128-GCM-SHA256',  # (0xc02b)
    'ECDHE-RSA-AES128-GCM-SHA256',  # (0xc02f)
    'ECDHE-ECDSA-CHACHA20-POLY1305',  # (0xcca9)
    'ECDHE-RSA-CHACHA20-POLY1305',  # (0xcca8)
    'ECDHE-ECDSA-AES256-GCM-SHA384',  # (0xc02c)
    'ECDHE-RSA-AES256-GCM-SHA384',  # (0xc030)
    'ECDHE-ECDSA-AES256-SHA',  # (0xc00a) WEAK
    'ECDHE-ECDSA-AES128-SHA',  # (0xc009) WEAK
    'ECDHE-RSA-AES128-SHA',  # (0xc013) WEAK
    'ECDHE-RSA-AES256-SHA',  # (0xc014) WEAK
    'DHE-RSA-AES128-SHA',  # (0x33) WEAK
    'DHE-RSA-AES256-SHA',  # (0x39) WEAK
    'AES128-SHA',  # (0x2f) WEAK
    'AES256-SHA',  # (0x35) WEAK
    # 'RSA_WITH_3DES_EDE_CBC_SHA', # (0xa), WEAK not supported by OpenSSL 1.1.1
])


def set_timeout_for_thread(timeout, start_time=None):
    threadLocal.timeout = timeout
    threadLocal.start_time = start_time


def reset_time_for_thread():
    threadLocal.total_time = 0


def get_time_for_thread():
    return threadLocal.total_time


loop = None
clients = dict()


def _get_ssl_context(http2=True) -> ssl.SSLContext:
    """
    Creates the default SSLContext object that's used for both verified
    and unverified connections.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    context.options |= ssl.OP_NO_SSLv2
    context.options |= ssl.OP_NO_SSLv3
    context.options |= ssl.OP_NO_COMPRESSION
    context.set_ciphers(FIREFOX_CIPHERS)
    # Nothing to select a subset of supported curves
    # https://crypto.stackexchange.com/questions/11311/with-tls-and-ecdhe-how-does-curve-selection-work
    # openssl ecparam -list_curves
    # firefox: 'x25519', 'secp256r1', 'secp384r1', 'secp521r1', 'ffdhe2048', 'ffdhe3072'

    if ssl.HAS_ALPN:
        alpn_idents = ["http/1.1", "h2"] if http2 else ["http/1.1"]
        context.set_alpn_protocols(alpn_idents)

    return context


async def get_client(verify, proxies):
    global clients, pool_connections, pool_maxsize
    key = str(verify) + '|' + str(proxies)
    if key not in clients:
        user_pool_limits = httpx.PoolLimits(soft_limit=pool_maxsize, hard_limit=pool_connections)
        if verify:
            verify = _get_ssl_context(http2=True)
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
    for logger_name in ('hpack.hpack', 'hpack.table'):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

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
