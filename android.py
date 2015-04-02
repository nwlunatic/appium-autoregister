# coding: utf-8

from os import environ, path
from subprocess import Popen, PIPE
import logging

import sys

ENCODING = sys.getdefaultencoding()


class Device(object):
    def __init__(self, name, platform):
        self.name = name
        self.platform = platform
        self.properties = self._getprop()
        self.version = self.properties.get("ro.build.version.sdk")
        self.model = self.properties.get("ro.product.model")

    def _getprop(self):
        p = adb_popen(["-s", self.name, "shell", "getprop"])
        properties = dict()
        for line in p.stdout.readlines():
            key, value = line.decode(ENCODING).split("]: ")
            properties[key.strip('[]')] = value.strip('[]\r\n')

        return properties

    def __str__(self):
        return "<%s %s %s>" % (self.name, self.platform, self.version)


def adb_popen(params):
    android_home = environ.get("ANDROID_HOME", None)
    if android_home is None:
        exit("set $ANDROID_HOME to path of your android sdk root")

    params = [param if isinstance(param, str) else param.decode(ENCODING) for param in params]
    command = [path.join(android_home, "platform-tools/adb")] + params
    p = Popen(command, stdout=PIPE, stderr=PIPE)
    p.wait()
    if p.returncode != 0:
        logging.warning("failed to run command %s" % " ".join(command))
    return p


def android_devices():
    p = adb_popen(["devices"])

    for line in p.stdout.readlines():
        string_parts = line.decode(ENCODING).split()
        if len(string_parts) == 2 and string_parts[1] == "device":
            yield Device(string_parts[0], "ANDROID")