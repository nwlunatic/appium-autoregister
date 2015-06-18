# coding: utf-8
import asyncio
import time
import logging

from config import config

log = logging.getLogger(__name__)

TIMEOUT = config.getint('settings', 'timeout')


class Sessions(object):
    sessions = []

    @classmethod
    def find(cls, session_id):
        sessions = [session for session in cls.sessions
                    if session.session_id == session_id]
        if not sessions:
            raise Exception("No such session [%s]" % session_id)

        if len(sessions) > 1:
            raise Exception("Found more than one session for [%s]" % session_id)

        session = sessions[0]
        session.last_activity = time.time()
        return session

    @classmethod
    def add(cls, session):
        cls.sessions.append(session)

    @classmethod
    def remove(cls, session):
        return cls.sessions.remove(session)

    @classmethod
    @asyncio.coroutine
    def watcher(cls):
        try:
            while True:
                for session in Sessions.sessions:
                    if time.time() - session.last_activity > TIMEOUT:
                        log.info("session [%s] timeouted" % session.session_id)
                        yield from session.close()
                    yield from asyncio.sleep(0)
                yield from asyncio.sleep(0)
        except asyncio.CancelledError:
            return


class Session(object):
    session_id = None
    remote_session_id = None
    endpoint = None
    last_activity = None

    def __init__(self):
        self.start = self.last_activity = time.time()
        Sessions.add(self)

    @asyncio.coroutine
    def close(self):
        if self.endpoint:
            yield from self.endpoint.delete()
        Sessions.remove(self)