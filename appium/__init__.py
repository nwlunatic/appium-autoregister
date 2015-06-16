# coding: utf-8

import os
import logging
from subprocess import Popen, PIPE, STDOUT
from threading import Thread

from utils import get_free_port


log = logging.getLogger(__name__)


class AppiumNode(object):
    process = None
    process_reader = None

    appium_executable = os.environ.get("APPIUM_EXECUTABLE", None)
    if appium_executable is None:
        exit('set $APPIUM_EXECUTABLE to path of appium executable')

    def __init__(self, port, device, config_file):
        self.port = port
        self.device = device
        self.config_file = config_file
        self.log = logging.getLogger(self.device.name)

    def start(self):
        if self.process is not None:
            return self.process

        log.info("starting appium node for %s" % self.device)
        command = [
            self.appium_executable,
            "--nodeconfig", self.config_file,
            "--port", str(self.port),
            "--bootstrap-port", str(get_free_port()),
            "--udid", self.device.name]
        log.info("running command %s" % " ".join(command))
        self.process = Popen(command, stderr=STDOUT, stdout=PIPE)
        self.process_reader = Thread(target=self._log_process_stdout)
        self.process_reader.daemon = True
        self.process_reader.start()
        log.info("process started with pid %s" % self.process.pid)
        return self.process

    def stop(self):
        try:
            self.process.kill()
        except ProcessLookupError:
            # process killed from outside
            pass
        self.process_reader.join()
        try:
            os.remove(self.config_file)
        except FileNotFoundError:
            # file already deleted
            pass
        log.info("appium node for %s stopped" % self.device)

    def _log_process_stdout(self):
        while self.process.poll() is None:
            line = self.process.stdout.readline()
            if line:
                self.log.info("%s" % line.decode().strip("\n"))