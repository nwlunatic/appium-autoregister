# coding: utf-8
import asyncio
import aiohttp
import logging

from utils import ping


log = logging.getLogger(__name__)


class Endpoint(object):
    ip = None
    port = None
    resources = None
    ready = False

    def __init__(self, ip, port, resources: list):
        self.ip = ip
        self.port = port
        self.resources = resources

    def __repr__(self):
        return "<%s address=%s ready=%s>" % (
            self.__class__.__name__, self.address, self.ready
        )

    @asyncio.coroutine
    def delete(self):
        for resource in self.resources:
            yield from resource.delete()

    @property
    def address(self):
        return "%s:%s" % (self.ip, self.port)

    @asyncio.coroutine
    def _wait_open_port(self, port):
        log.info("wait for %s %s port is open" % (self, port))
        is_opened = ping(self.ip, port)
        while not is_opened:
            is_opened = ping(self.ip, port)
            yield from asyncio.sleep(0)
        loop = asyncio.get_event_loop()
        transport = None
        while not transport:
            try:
                transport, proto = yield from loop.create_connection(
                    lambda: asyncio.BaseProtocol(), host=self.ip, port=port)
            except OSError:
                pass
        transport.close()
        log.info("%s %s port is open" % (self, port))

    @asyncio.coroutine
    def _wait_selenium_status(self, reties=3):
        log.info("wait for %s selenium status" % self)
        status = None
        retry = 0
        while not status == 200 and retry < reties:
            response = yield from aiohttp.request(
                'GET', 'http://%s/wd/hub/status' % self.address)
            status = response.status
            retry += 1
            yield from asyncio.sleep(0)
        log.info("got selenium status for %s" % self)

    @asyncio.coroutine
    def wait_ready(self):
        log.info("waiting for %s become ready" % self)
        yield from self._wait_open_port(self.port)
        yield from self._wait_selenium_status()
        self.ready = True
        log.info("%s ready" % self)