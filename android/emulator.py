# coding: utf-8

import os
import asyncio
import logging
from uuid import uuid4

from utils import run_command


log = logging.getLogger(__name__)


@asyncio.coroutine
def delete_file(filename):
    try:
        os.remove(filename)
        log.debug("file %s deleted" % filename)
    except FileNotFoundError:
        pass


@asyncio.coroutine
def create_img(name, size):
    qemu_img = "qemu-img"
    args = [qemu_img, 'create', '-f', 'qcow2',
            '-o', 'preallocation=metadata',
            name, size]
    p = yield from run_command(args)
    return name if not p.returncode else None


@asyncio.coroutine
def mksdcard(name, size):
    android_home = os.environ.get("ANDROID_HOME", None)
    if android_home is not None:
        mksdcard = os.path.join(android_home, 'tools', 'mksdcard')
    else:
        # if we don't have ANDROID_HOME set, let's just hope adb is in PATH
        mksdcard = 'mksdcard'
    args = [mksdcard, size, name]
    p = yield from run_command(args)
    return name if not p.returncode else None


@asyncio.coroutine
def emulator_command(args, wait_end=True):
    android_home = os.environ.get("ANDROID_HOME", None)
    if android_home is not None:
        emulator = os.path.join(android_home, 'tools', 'emulator')
    else:
        # if we don't have ANDROID_HOME set, let's just hope adb is in PATH
        emulator = 'emulator'
    args = [emulator] + args
    p = yield from run_command(args, wait_end)
    return p


@asyncio.coroutine
def avd_list():
    args = ['-list-avds']
    p = yield from emulator_command(args)
    stdout, stderr = yield from p.communicate()
    return stdout.decode().split()


class Emulator(object):
    data = None
    sdcard = None
    process = None

    def __init__(self, avd):
        if avd not in avd_list:
            raise Exception("No such avd: %s\n" % avd)
        self.avd = avd
        self.uuid = str(uuid4())
        self.name = "%s-%s" % (avd, self.uuid)

    def __str__(self):
        pid = self.process.pid if self.process else "Not running"
        return "<%s %s pid=%s>" % (self.__class__.__name__, self.name, pid)

    def __del__(self):
        self.delete()

    def to_json(self):
        return self.__dict__

    @asyncio.coroutine
    def _start_emulator_process(self):
        assert self.avd is not None
        assert self.uuid is not None
        assert self.data is not None
        assert self.sdcard is not None

        args = ['-avd', self.avd, '-prop', 'emu.uuid=%s' % self.uuid,
                '-data', self.data, '-sdcard', self.sdcard]
        emulator_command(args)
        return (yield from emulator_command(args, wait_end=False))

    @asyncio.coroutine
    def _create_disks(self):
        self.data = yield from create_img("%s-data.qcow2" % self.name, "500M")
        self.sdcard = yield from mksdcard("%s-sdcard" % self.name, "500M")

    @asyncio.coroutine
    def _delete_disks(self):
        log.debug("deleting %s disks" % self.name)
        yield from delete_file(self.sdcard)
        yield from delete_file("%s.lock" % self.sdcard)
        yield from delete_file(self.data)
        yield from delete_file("%s.lock" % self.data)

    @asyncio.coroutine
    def start(self):
        log.debug("starting %s" % self)
        yield from self._create_disks()
        self.process = yield from self._start_emulator_process()
        log.debug("%s started" % self)

    @asyncio.coroutine
    def delete(self):
        log.debug("deleting %s" % self)
        if self.process:
            try:
                self.process.kill()
            except ProcessLookupError as e:
                log.exception(e)
            yield from self.process.wait()
        yield from self._delete_disks()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    e1 = Emulator(avd_list[0])
    loop.run_until_complete(e1.start())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(e1.delete())
    finally:
        loop.close()