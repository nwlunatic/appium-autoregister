# coding: utf-8

import socket
import asyncio
import os
import logging


log = logging.getLogger(__name__)


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def get_socket(host, port):
    s = None

    for res in socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        try:
            s = socket.socket(af, socktype, proto)
        except socket.error:
            s = None
            continue
        try:
            s = socket.create_connection((host, port), timeout=0.1)
        except socket.error:
            s.close()
            s = None
            continue
        break

    return s


def ping(ip, port):
    s = get_socket(ip, port)
    if s:
        s.close()
        return True

    return False


@asyncio.coroutine
def run_command(args, wait_end=True, env=os.environ.copy()):
    log.info("running command: %s" % " ".join(args))
    p = yield from asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=env)
    setattr(p, 'args', args)
    if wait_end:
        yield from p.wait()
        if p.returncode:
            out, err = yield from p.communicate()
            log.warning(err)
    return p