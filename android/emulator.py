# coding: utf-8

import os
import asyncio
import logging
from uuid import uuid4

from utils import run_command
from config import config

from android import find_device_by_uuid
from android.adb import adb_command, until_adb_output


log = logging.getLogger(__name__)

TIMEOUT = config.getint('settings', 'timeout')
EMULATOR_ARGS = config.get("emulator", "args", fallback=[]).split(" ")
log.info("emulator args %s" % str(EMULATOR_ARGS))


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
def android_command(args, wait_end=True):
    android_home = os.environ.get("ANDROID_HOME", None)
    if android_home is not None:
        android = os.path.join(android_home, 'tools', 'android')
    else:
        # if we don't have ANDROID_HOME set, let's just hope adb is in PATH
        android = 'android'
    args = [android] + args
    p = yield from run_command(args, wait_end)
    return p


@asyncio.coroutine
def avd_list():
    args = ['list', 'avds', '-c']
    p = yield from android_command(args)
    stdout, stderr = yield from p.communicate()
    return stdout.decode().split()


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


class Emulator(object):
    data = None
    sdcard = None
    process = None
    device = None

    def __init__(self, avd):
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
                '-data', self.data, '-sdcard', self.sdcard] + EMULATOR_ARGS
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
        avds = yield from avd_list()
        if self.avd not in avds:
            raise Exception("No such avd: %s\n" % self.avd)
        log.info("starting %s" % self)
        yield from self._create_disks()
        self.process = yield from self._start_emulator_process()
        log.info("%s started" % self)
        self.device = find_device_by_uuid(self.uuid)
        while self.device is None:
            self.device = find_device_by_uuid(self.uuid)
            yield from asyncio.sleep(0)
        log.info("device %s found" % self.device)
        yield from wait_for_device_ready(self.device.name)

    @asyncio.coroutine
    def delete(self):
        log.info("deleting %s" % self)
        if self.process:
            try:
                self.process.kill()
            except ProcessLookupError as e:
                log.exception(e)
            yield from self.process.wait()
        yield from self._delete_disks()