# coding: utf-8
import os
import asyncio
import logging


log = logging.getLogger(__name__)


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
def until_adb_output(device_name, command, result):
    _result = None
    while _result != result:
        _process = yield from adb_command(device_name, command)
        _result = (yield from _process.stdout.read()).strip()

    _process = yield from adb_command(device_name, command)
    log.info("%s is %s" % (" ".join(_process.command), result))