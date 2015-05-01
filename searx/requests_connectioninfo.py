# monkey patch of the monkey patch to records certificates
# important : import requests which guarantie that pyopenssl hook has been done
import requests
import requests.packages.urllib3.contrib.pyopenssl
import requests.packages.urllib3.connection as connection
import requests.packages.urllib3.poolmanager
import json
from requests.packages.urllib3.connection import HTTPConnection, HTTPSConnection
from requests.packages.urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool


db = {
}


class ConnectionInfo:

    def __init__(self):
        self.peers = set()
        self.certificates = set()
        self.ciphers = set()

    def add_peer(self, ip, port):
        self.peers.add((ip, port))

    def add_certificate(self, certificate):
        # print certificate.get_issuer()
        # print certificate.get_subject()
        # print certificate.digest("sha256")
        self.certificates.add(certificate.digest("sha256"))

    def add_cipher(self, name, version):
        self.ciphers.add((name, version))


class SetEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, ConnectionInfo):
            return {
                'peers': list(obj.peers),
                'certificates': list(obj.certificates),
                'ciphers': list(obj.ciphers)
            }
        return json.JSONEncoder.default(self, obj)


def get_json_db():
    return json.dumps(db, cls=SetEncoder)


def get_connectioninfo(hostname):
    global db

    r = db.get(hostname, None)
    if r is None:
        db[hostname] = r = ConnectionInfo()
    return r


class MonitoredHTTPConnection(HTTPConnection):

    def connect(self):
        retval = super(MonitoredHTTPConnection, self).connect()
        peer = self.sock.getpeername()
        get_connectioninfo(self.host).add_peer(peer[0], peer[1])
        return retval


class MonitoredHTTPSConnection(HTTPSConnection):

    def connect(self):
        retval = super(MonitoredHTTPSConnection, self).connect()
        if type(self.sock) is requests.packages.urllib3.contrib.pyopenssl.WrappedSocket:
            # see https://github.com/kennethreitz/requests/blob/3880cf1255c70e7a13a491cd07d282d41d871649/requests/packages/urllib3/contrib/pyopenssl.py#L158 # noqa
            peer = self.sock.socket.getpeername()
        else:
            peer = self.sock.getpeername()
        get_connectioninfo(self.host).add_peer(peer[0], peer[1])
        return retval


class MonitoredHTTPConnectionPool(HTTPConnectionPool):

    def _new_conn(self):
        self.ConnectionCls = MonitoredHTTPConnection
        return super(MonitoredHTTPConnectionPool, self)._new_conn()


class MonitoredHTTPSConnectionPool(HTTPSConnectionPool):

    def _new_conn(self):
        self.ConnectionCls = MonitoredHTTPSConnection
        return super(MonitoredHTTPSConnectionPool, self)._new_conn()


orig_connection_ssl_wrap_socket = connection.ssl_wrap_socket


def ssl_wrap_socket(*args, **kwargs):
    s = orig_connection_ssl_wrap_socket(*args, **kwargs)
    if type(s) is requests.packages.urllib3.contrib.pyopenssl.WrappedSocket:
        connectioninfo = get_connectioninfo(kwargs['server_hostname'])
        # print s.socket.getpeername()
        connectioninfo.add_cipher(s.connection.get_cipher_name(), s.connection.get_cipher_version())
        connectioninfo.add_certificate(s.connection.get_peer_certificate())
    return s


connection.ssl_wrap_socket = ssl_wrap_socket
requests.packages.urllib3.poolmanager.pool_classes_by_scheme['http'] = MonitoredHTTPConnectionPool
requests.packages.urllib3.poolmanager.pool_classes_by_scheme['https'] = MonitoredHTTPSConnectionPool
