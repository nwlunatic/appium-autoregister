# coding: utf-8

import asyncio
import os
import logging
import copy
from subprocess import Popen, PIPE, STDOUT
from threading import Thread

from utils import get_free_port, run_command


log = logging.getLogger(__name__)


class AppiumNode(object):
    process = None
    process_reader = None

    appium_executable = os.environ.get("APPIUM_EXECUTABLE", None)
    if appium_executable is None:
        exit('set $APPIUM_EXECUTABLE to path of appium executable')

    def __init__(self, port, device, config_file=None):
        self.port = port
        self.device = device
        self.config_file = config_file
        self.log = logging.getLogger(self.device.name)

    def to_json(self):
        _json = copy.copy(self.__dict__)
        del _json['process']
        del _json['log']
        return _json

    @property
    def _command(self):
        command = [
            self.appium_executable,
            "--port", str(self.port),
            "--bootstrap-port", str(get_free_port()),
            "--udid", self.device.name]
        if self.config_file:
            command += ["--nodeconfig", self.config_file]
        return command

    def start(self):
        if self.process is not None:
            return self.process

        log.info("starting appium node for %s" % self.device)
        log.info("running command %s" % " ".join(self._command))
        self.process = Popen(self._command, stderr=STDOUT, stdout=PIPE)
        self.process_reader = Thread(target=self._log_process_stdout)
        self.process_reader.daemon = True
        self.process_reader.start()
        log.info("process started with pid %s" % self.process.pid)
        return self.process

    @asyncio.coroutine
    def start_coro(self):
        if self.process is not None:
            return self.process

        log.info("starting appium node for %s" % self.device)
        self.process = yield from run_command(self._command, wait_end=False)
        yield from self.process.stdout.read(1)
        log.info("process started with pid %s" % self.process.pid)
        return self.process

    def stop(self):
        if hasattr(self.process, "poll"):
            self.process.poll()
        if self.process and not self.process.returncode:
            self.process.kill()
        if self.process_reader:
            self.process_reader.join()
        if self.config_file:
            os.remove(self.config_file)
        log.info("appium node for %s stopped" % self.device)

    @asyncio.coroutine
    def delete(self):
        self.stop()

    def _log_process_stdout(self):
        while self.process.poll() is None:
            line = self.process.stdout.readline()
            if line:
                self.log.info("%s" % line.decode().strip("\n"))