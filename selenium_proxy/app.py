# coding: utf-8

import json
import sys
import traceback
import asyncio
import aiohttp
import logging

from aiohttp import web, hdrs

from android.emulator import avd_list
from selenium_proxy.session import Sessions, Session, SessionStatus
from selenium_proxy.endpoint import AndroidEndpoint


log = logging.getLogger(__name__)


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        try:
            return super(JSONEncoder, self).default(o)
        except TypeError:
            return o.to_json()


def in_session(handler):
    @asyncio.coroutine
    def request_wrapper(request: web.Request):
        @asyncio.coroutine
        def connection_dropped():
            socket = request.transport.get_extra_info('socket')
            while socket._closed != True:
                yield from asyncio.sleep(0)
            request.session.close(SessionStatus.connection_dropped)

        drop_handler = asyncio.async(connection_dropped())
        req = asyncio.async(handler(request))
        done, pending = yield from asyncio.wait(
            [
                req,
                asyncio.async(request.session.closed)
            ],
            return_when=asyncio.FIRST_COMPLETED)
        if req.done():
            drop_handler.cancel()
            return req.result()
        else:
            req.cancel()
            for task in done:
               task.result()
    return request_wrapper


@asyncio.coroutine
def session_factory(app, handler):
    @asyncio.coroutine
    def session_extractor(request: web.Request):
        session_id = request.match_info.get("session_id")
        if session_id:
            session = Sessions.find(session_id)
        else:
            session = None

        request.session = session
        return (yield from handler(request))
    return session_extractor


@asyncio.coroutine
def error_reporter_factory(app, handler):
    @asyncio.coroutine
    def error_reporter(request):
        try:
            result = yield from handler(request)
        except:
            session_id = request.match_info.get("session_id")
            ex_type, ex, tb = sys.exc_info()
            if session_id:
                session = Sessions.find(session_id)
                session.close(ex)
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
                "sessionId": session_id,
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


@in_session
@asyncio.coroutine
def transparent(request: web.Request):
    response = yield from aiohttp.request(
        request.method,
        "%s://%s%s" % (request.scheme, request.session.endpoint.address, request.path),
        headers=request.headers,
        data=(yield from request.read())
    )
    return web.Response(
        status=response.status,
        headers=response.headers,
        body=(yield from response.read_and_close())
    )


@in_session
@asyncio.coroutine
def delete_session(request: web.Request):
    request.session.close()
    return web.Response(status=200)


@in_session
@asyncio.coroutine
def start_session(request: web.Request):
    session = request.session
    session.endpoint = AndroidEndpoint()
    yield from session.endpoint.start(session.desired_capabilities)
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
        session.close()
    return response


@asyncio.coroutine
def create_session(request: web.Request):
    body = yield from request.json()
    desired_capabilities = body.get("desiredCapabilities")
    request.session = Session(desired_capabilities)
    response = yield from start_session(request)
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
    return web.Response(body=json.dumps(
        Sessions.sessions, cls=JSONEncoder
    ).encode())


app = web.Application(middlewares=[error_reporter_factory, session_factory])

app.router.add_route('POST', '/wd/hub/session', create_session)
app.router.add_route('DELETE', '/wd/hub/session/{session_id}', delete_session)
app.router.add_route('*', '/wd/hub/session/{session_id}', transparent)
app.router.add_route('*', '/wd/hub/session/{session_id}/{path:.*}', transparent)
app.router.add_route('GET', '/platforms', platforms)
app.router.add_route('GET', '/sessions', sessions)
