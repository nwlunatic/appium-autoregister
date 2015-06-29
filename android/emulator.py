# coding: utf-8

import os
import asyncio
import logging
import copy
import shutil
from uuid import uuid4
from configparser import ConfigParser

from utils import run_command
from config import config

from android import find_device_by_uuid
from android.adb import until_adb_output


log = logging.getLogger(__name__)

TIMEOUT = config.getint('settings', 'timeout')
EMULATOR_ARGS = config.get("emulator", "args", fallback=[]).split(" ")
AVD_HOME = os.sep.join([os.environ.get("HOME"), '.android', 'avd'])
log.info("emulator args %s" % str(EMULATOR_ARGS))


# http://stackoverflow.com/questions/2819696/parsing-properties-file-in-python/2819788#2819788
class FakeSecHead(object):
    dummy_section = '[dummy]\n'

    def __init__(self, fp):
        self.fp = fp

    def __iter__(self):
        yield self.dummy_section
        for line in self.fp:
            yield line

    def write(self, string):
        if string == self.dummy_section:
            return
        else:
            self.fp.write(string)


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
    system = None
    data = None
    sdcard = None
    cache = None
    process = None
    device = None
    config_file = None

    def copy_avd_info(self):
        avd_ini = ConfigParser()
        path = os.sep.join([AVD_HOME, "%s.ini" % self.avd])
        with open(path) as fd:
            avd_ini.read_file(FakeSecHead(fd))
        avd_ini.set("dummy", "path", os.sep.join([
            os.getcwd(), self.name]))
        avd_ini.set("dummy", "path.rel", self.name)
        self.config_file = os.sep.join([self.name, "%s.ini" % self.name])
        with open(self.config_file, 'w') as fd:
            avd_ini.write(FakeSecHead(fd))
        avd_dir = os.sep.join([AVD_HOME, "%s.avd" % self.avd])
        for file in os.listdir(avd_dir):
            if file.endswith(".ini"):
                shutil.copy(
                    os.sep.join([avd_dir, file]),
                    os.sep.join([self.name, file])
                )

    def __init__(self, avd):
        self.avd = avd
        self.uuid = str(uuid4())
        self.name = "%s-%s" % (avd, self.uuid)
        os.makedirs(self.name)
        self.copy_avd_info()

    def __repr__(self):
        pid = self.process.pid if self.process else "Not running"
        return "<%s %s pid=%s>" % (self.__class__.__name__, self.name, pid)

    def __del__(self):
        self.delete()

    def to_json(self):
        _json = copy.copy(self.__dict__)
        del _json['process']
        return _json

    @asyncio.coroutine
    def _start_emulator_process(self):
        assert self.avd is not None
        assert self.uuid is not None
        assert self.data is not None
        assert self.sdcard is not None

        android_home = os.environ.get("ANDROID_HOME", None)
        if android_home is not None:
            emulator = os.path.join(android_home, 'tools', 'emulator')
        else:
            # if we don't have ANDROID_HOME set, let's just hope adb is in PATH
            emulator = 'emulator'

        args = [
            '-avd', self.name, '-prop', 'emu.uuid=%s' % self.uuid,
            '-data', self.data,
            '-sdcard', self.sdcard,
            '-cache', self.cache
            # '-datadir', self.name
        ] + EMULATOR_ARGS

        args = [emulator] + args
        env = os.environ.copy()
        env['ANDROID_AVD_HOME'] = "%s" % self.name
        return (yield from run_command(args, False, env=env))

    @asyncio.coroutine
    def _create_disks(self):
        self.data = yield from create_img("%s/userdata-qemu.img" % self.name, "500M")
        self.cache = yield from create_img("%s/cache.img" % self.name, "500M")
        self.sdcard = yield from mksdcard("%s/sdcard.img" % self.name, "500M")

    @asyncio.coroutine
    def _delete_disks(self):
        log.debug("deleting %s disks" % self.name)
        yield from delete_file(self.sdcard)
        yield from delete_file("%s.lock" % self.sdcard)
        yield from delete_file(self.data)
        yield from delete_file("%s.lock" % self.data)
        yield from delete_file(self.cache)
        yield from delete_file("%s.lock" % self.cache)

    @asyncio.coroutine
    def start(self):
        avds = yield from avd_list()
        if self.avd not in avds:
            raise Exception("No such avd: %s\n" % self.avd)
        log.info("starting %s" % self)
        yield from self._create_disks()
        self.process = yield from self._start_emulator_process()
        # yield from self.process.stdout.read(1)
        # if self.process.returncode:
        #     log.warning((yield from self.process.communicate()))
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
        os.remove(self.config_file)
        if self.process and not self.process.returncode:
            try:
                self.process.kill()
            except ProcessLookupError as e:
                log.warning(e)
            yield from self.process.wait()
        yield from self._delete_disks()
        for file in os.listdir(self.name):
            os.remove(os.sep.join([self.name, file]))
        os.removedirs(self.name)