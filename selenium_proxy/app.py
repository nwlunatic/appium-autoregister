# coding: utf-8

import json
import sys
import traceback
import asyncio
import aiohttp
import logging
from configparser import ConfigParser

from aiohttp import web

from android.adb import adb_command, until_adb_output
from android.emulator import Emulator, avd_list
from android import find_device_by_uuid


log = logging.getLogger(__name__)


config = ConfigParser()
config.read('proxy.ini')
config.read('local.proxy.ini')

HOST = config.get('settings', 'host')
TIMEOUT = config.getint('settings', 'timeout')

log.info("Proxying requests to %s" % HOST)
log.info("Internal commands timeout %s" % TIMEOUT)


sessions = []


class Session(object):
    session_id = None
    remote_session_id = None
    emulator = None
    _timer = None

    @asyncio.coroutine
    def timer(self):
        yield from asyncio.sleep(TIMEOUT)
        self.close()

    @asyncio.coroutine
    def close(self):
        if self.emulator:
            yield from self.emulator.delete()


@asyncio.coroutine
def wait_for_device_ready(device_name):
    log.info("Waiting for %s become ready" % device_name)
    yield from asyncio.wait_for(until_adb_output(
        device_name, "shell getprop dev.bootcomplete", b"1"), TIMEOUT)
    yield from asyncio.wait_for(until_adb_output(
        device_name, "shell getprop sys.boot_completed", b"1"), TIMEOUT)
    yield from asyncio.wait_for(until_adb_output(
        device_name, "shell getprop init.svc.bootanim", b"stopped"), TIMEOUT)
    yield from asyncio.wait_for(until_adb_output(
        device_name, "shell getprop service.bootanim.exit", b"1"), TIMEOUT)
    log.info("%s is ready" % device_name)


@asyncio.coroutine
def error_reporter_factory(app, handler):
    @asyncio.coroutine
    def error_reporter(request):
        try:
            result = yield from handler(request)
        except:
            ex_type, ex, tb = sys.exc_info()
            stack_trace = []
            for filename, lno, method, string in reversed(traceback.extract_tb(tb)):
                stack_trace.append({
                    "fileName": filename,
                    "lineNumber": lno,
                    "methodName": method,
                    "className": ""
                })
            value = {
                "message": str(ex),
                "class": str(ex_type),
                "stackTrace": stack_trace,
            }
            response = {
                "sessionId": "",
                "status": 13,
                "value": value
            }
            encoding = request.charset or "utf-8"
            result = web.Response(
                status=500,
                body=json.dumps(response).encode(encoding)
            )
        return result
    return error_reporter


@asyncio.coroutine
def transparent(request: web.Request):
    response = yield from aiohttp.request(
        request.method,
        "%s://%s%s" % (request.scheme, HOST, request.path),
        headers=request.headers,
        data=(yield from request.read())
    )
    return web.Response(
        status=response.status,
        headers=response.headers,
        body=(yield from response.read_and_close())
    )


@asyncio.coroutine
def get_capabilities(session_id):
    response = yield from aiohttp.request(
        "GET", "http://%s/wd/hub/session/%s" % (HOST, session_id))
    return (yield from response.json())


@asyncio.coroutine
def delete_session(request: web.Request):
    session_id = request.match_info.get('session_id')
    s = [session for session in sessions if session.session_id == session_id]
    if s:
        yield from s[0].close()
    return web.Response(status=200)


@asyncio.coroutine
def create_session(request: web.Request):
    session = Session()
    sessions.append(session)
    body = yield from request.json()
    desired_capabilities = body.get("desiredCapabilities")
    avd_name = desired_capabilities.get("avdName")
    emulator = Emulator(avd_name)
    session.emulator = emulator
    yield from emulator.start()
    device = find_device_by_uuid(str(emulator.uuid))
    while device is None:
        device = find_device_by_uuid(str(emulator.uuid))
        yield from asyncio.sleep(0)
    log.info("device %s found" % device)
    yield from wait_for_device_ready(device.name)
    result = yield from transparent(request)
    body = json.loads(result.body.decode("utf-8"))
    session.session_id = session.remote_session_id = body.get('sessionId')
    return result


@asyncio.coroutine
def platforms(request: web.Request):
    avds = yield from avd_list()
    return web.Response(body=json.dumps(avds).encode())


app = web.Application(middlewares=[error_reporter_factory])
app.router.add_route('POST', '/wd/hub/session', create_session)
app.router.add_route('DELETE', '/wd/hub/session/{session_id}', delete_session)
app.router.add_route('GET', '/platforms', platforms)
app.router.add_route('*', '/{path:.*}', transparent)
