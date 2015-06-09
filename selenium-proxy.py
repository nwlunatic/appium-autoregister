import os
import json
import sys
import traceback
import asyncio
import aiohttp
import logging
from aiohttp import web
from configparser import ConfigParser

config = ConfigParser()
config.read('proxy.ini')
config.read('local.proxy.ini')

HOST = config.get('settings', 'host')
TIMEOUT = config.getint('settings', 'timeout')


log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
stream_log_handler = logging.StreamHandler()
stream_log_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s')
stream_log_handler.setFormatter(formatter)
log.addHandler(stream_log_handler)


@asyncio.coroutine
def adb_command(device, params, asynchronous=False):
    assert device is not None

    if isinstance(params, str):
        params = params.split(" ")

    android_home = os.environ.get("ANDROID_HOME", None)
    if android_home is not None:
        adb = os.path.join(android_home, 'platform-tools', 'adb')
    else:
        # if we don't have ANDROID_HOME set, let's just hope adb is in PATH
        adb = 'adb'
    command = [adb, '-s', device] + params
    p = yield from asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy())
    setattr(p, 'command', command)
    if not asynchronous:
        yield from p.wait()
    return p


@asyncio.coroutine
def soft_restart_device(device_name):
    yield from adb_command(device_name, "shell stop")
    yield from adb_command(device_name, "shell start")
    yield from asyncio.sleep(1)
    log.info("%s soft rebooted" % device_name)


@asyncio.coroutine
def until_adb_output(device_name, command, result):
    _result = None
    while _result != result:
        _process = yield from adb_command(device_name, command)
        _result = (yield from _process.stdout.read()).strip()

    _process = yield from adb_command(device_name, command)
    log.info("%s is %s" % (" ".join(_process.command), result))


@asyncio.coroutine
def wait_for_device_ready(device_name):
    log.info("waiting for %s become ready" % device_name)
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
            result = web.Response(
                status=500,
                body=json.dumps(response).encode(request.charset)
            )
        return result
    return error_reporter


@asyncio.coroutine
def wait_connections_done(handler):
    log.info("waiting for %s connections to over" % len(handler.connections))
    for connection in handler.connections:
        log.info(str(connection))
    while handler.connections:
        yield from asyncio.sleep(0)


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
    capabilities = yield from get_capabilities(session_id)
    device_name = capabilities["value"]["deviceName"]

    response = yield from aiohttp.request(
        request.method,
        "%s://%s%s" % (request.scheme, HOST, request.path),
        headers=request.headers,
        data=(yield from request.read())
    )
    yield from soft_restart_device(device_name)
    yield from wait_for_device_ready(device_name)
    return web.Response(
        status=response.status,
        headers=response.headers,
        body=(yield from response.read_and_close())
    )


app = web.Application(middlewares=[error_reporter_factory])
# app.router.add_route('POST', '/wd/hub/session', create_session)
app.router.add_route('DELETE', '/wd/hub/session/{session_id}', delete_session)
app.router.add_route('*', '/{path:.*}', transparent)
handler = app.make_handler()

loop = asyncio.get_event_loop()
server_coroutine = loop.create_server(handler, '0.0.0.0', 8080)
server = loop.run_until_complete(server_coroutine)

log.info('serving on %s' % str(server.sockets[0].getsockname()))
try:
    loop.run_forever()
except KeyboardInterrupt:
    log.info("shutting down...")
finally:
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.run_until_complete(wait_connections_done(handler))
    loop.run_until_complete(app.finish())
loop.close()