# coding: utf-8

import json
import sys
import traceback
import asyncio
import aiohttp
import logging

from aiohttp import web, hdrs

from config import config

from android.emulator import Emulator, avd_list
from appium import AppiumNode

from selenium_proxy.session import Sessions, Session
from selenium_proxy.endpoint import Endpoint

from utils import get_free_port


log = logging.getLogger(__name__)


HOST = config.get('settings', 'host')

log.info("Proxying requests to %s" % HOST)


@asyncio.coroutine
def error_reporter_factory(app, handler):
    @asyncio.coroutine
    def error_reporter(request):
        try:
            result = yield from handler(request)
        except:
            session_id = request.match_info.get("session_id")
            try:
                session = Sessions.find(session_id)
                session.close()
            except:
                pass
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
    session_id = request.match_info.get('session_id')
    session = Sessions.find(session_id)
    response = yield from aiohttp.request(
        request.method,
        "%s://%s%s" % (request.scheme, session.endpoint.address, request.path),
        headers=request.headers,
        data=(yield from request.read())
    )
    return web.Response(
        status=response.status,
        headers=response.headers,
        body=(yield from response.read_and_close())
    )


@asyncio.coroutine
def delete_session(request: web.Request):
    session_id = request.match_info.get('session_id')
    session = Sessions.find(session_id)
    if session:
        yield from session.close()
    return web.Response(status=200)


@asyncio.coroutine
def create_session(request: web.Request):
    session = Session()
    body = yield from request.json()
    desired_capabilities = body.get("desiredCapabilities")
    avd_name = desired_capabilities.get("avdName")
    emulator = Emulator(avd_name)
    try:
        yield from emulator.start()
        appium_node = AppiumNode(get_free_port(), emulator.device)
        yield from appium_node.start_coro()
        session.endpoint = Endpoint("localhost", appium_node.port, [
            appium_node, emulator
        ])
        yield from session.endpoint.wait_ready()
        headers = {k: v for k, v in request.headers.items() if k != hdrs.HOST}
        response = yield from aiohttp.request(
            request.method,
            "%s://%s%s" % (request.scheme, session.endpoint.address, request.path),
            headers=headers,
            data=(yield from request.read())
        )
        if response.status == 200:
            body = yield from response.json()
            session.session_id = session.remote_session_id = body.get('sessionId')
        else:
            yield from session.close()
    except:
        yield from session.close()
        raise
    return web.Response(
        status=response.status,
        headers=response.headers,
        body=(yield from response.read_and_close())
    )


@asyncio.coroutine
def platforms(request: web.Request):
    avds = yield from avd_list()
    return web.Response(body=json.dumps(avds).encode())


@asyncio.coroutine
def sessions(request: web.Request):
    session_ids = [session.session_id for session in Sessions.sessions]
    return web.Response(body=json.dumps(session_ids).encode())


app = web.Application(middlewares=[error_reporter_factory])
app.router.add_route('POST', '/wd/hub/session', create_session)
app.router.add_route('DELETE', '/wd/hub/session/{session_id}', delete_session)
app.router.add_route('*', '/wd/hub/session/{session_id}', transparent)
app.router.add_route('*', '/wd/hub/session/{session_id}/{path:.*}', transparent)
app.router.add_route('GET', '/platforms', platforms)
app.router.add_route('GET', '/sessions', sessions)
