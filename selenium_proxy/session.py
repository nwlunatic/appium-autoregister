# coding: utf-8
import asyncio
import time
import logging
import copy

from config import config

log = logging.getLogger(__name__)

TIMEOUT = config.getint('settings', 'timeout')


class SessionStatus:
    timeouted = "timeouted"
    closed_by_user = "closed by user"
    connection_dropped = "connection dropped"


class SessionClosed(Exception):
    pass


class SessionError(Exception):
    pass


class Sessions(object):
    sessions = []

    @classmethod
    def find(cls, session_id):
        sessions = [session for session in cls.sessions
                    if session.session_id == session_id]
        if not sessions:
            raise SessionError("No such session [%s]" % session_id)

        if len(sessions) > 1:
            raise SessionError("Found more than one session for [%s]" % session_id)

        session = sessions[0]
        session.last_activity = time.time()
        return session

    @classmethod
    def add(cls, session):
        cls.sessions.append(session)

    @classmethod
    def remove(cls, session):
        return cls.sessions.remove(session)


class Session(object):
    desired_capabilities = None
    session_id = None
    remote_session_id = None
    endpoint = None
    last_activity = None

    def __init__(self, desired_capabilities):
        self.desired_capabilities = desired_capabilities
        self.start = self.last_activity = time.time()
        self.closed = asyncio.Future()
        asyncio.async(self.close_handler())
        self.watcher = asyncio.async(self.timeout_watcher())
        Sessions.add(self)

    @asyncio.coroutine
    def timeout_watcher(self):
        try:
            while time.time() - self.last_activity < TIMEOUT:
                yield from asyncio.sleep(1)
            self.close(SessionStatus.timeouted)
        except asyncio.CancelledError:
            pass

    # def to_json(self):
    #     _json = copy.copy(self.__dict__)
    #     del _json['watcher']
    #     _json['closed'] = self.closed.done()
    #     return _json

    @asyncio.coroutine
    def close_handler(self):
        try:
            reason = yield from self.closed
        except SessionClosed as e:
            reason, = e.args
        log.info("session [%s]: %s" % (self.session_id, reason))
        if self.endpoint:
            yield from self.endpoint.delete()
        if not self.watcher.done():
            self.watcher.cancel()
        Sessions.remove(self)
        log.info("session [%s] closed" % self.session_id)

    def close(self, reason=SessionStatus.closed_by_user):
        if self.closed.done():
            return

        self.closed.set_exception(SessionClosed(reason))