# coding: utf-8
import argparse
import logging
import tempfile
import signal
import time
from string import Template


from android import android_devices
from utils import get_free_port
from appium import AppiumNode


logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("autoregister")


class StopAutoregister(Exception):
    pass


class Autoregister(object):
    nodes = list()

    config_template = Template("""
    {
        "capabilities": [{
            "browserName": "$browserName",
            "version": "$version",
            "maxInstances": 1,
            "platformName": "$platform",
            "deviceName": "$device"
        }],
        "configuration": {
            "cleanUpCycle": 2000,
            "timeout": 30000,
            "proxy": "org.openqa.grid.selenium.proxy.DefaultRemoteProxy",
            "url": "http://$appium_host:$appium_port/wd/hub",
            "host": "$appium_host",
            "port": $appium_port,
            "maxSession": 1,
            "register": true,
            "registerCycle": 5000,
            "hubPort": $grid_port,
            "hubHost": "$grid_host"
        }
    }
    """)

    def __init__(self, grid_host, grid_port, appium_host, additional_args):
        self.grid_host = grid_host
        self.grid_port = grid_port
        self.appium_host = appium_host
        self.additional_args = additional_args
        signal.signal(signal.SIGTERM, self.stop_signal)

    @staticmethod
    def stop_signal(signum, frame):
        raise StopAutoregister()

    def register(self, device):
        config_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
        port = get_free_port()
        config = self.generate_config(device, port)
        config_file.write(config)
        config_file.flush()
        node = AppiumNode(port, device, config_file.name, self.additional_args)
        node.start()
        self.nodes.append(node)

    def unregister(self, node):
        node.stop()
        self.nodes.remove(node)

    def run(self, ):
        log.info("start registering devices...")
        try:
            while True:
                known_devices = {node.device.name: node for node in self.nodes}
                for device in android_devices():
                    if device.name in known_devices.keys():
                        del known_devices[device.name]
                        continue

                    self.register(device)

                for node in known_devices.values():
                    self.unregister(node)

                time.sleep(0.2)
        except (StopAutoregister, KeyboardInterrupt, SystemExit):
            self.stop()

    def generate_config(self, device, appium_port):
        return self.config_template.substitute({
            "browserName": device.model,
            "version": device.version,
            "platform": device.platform,
            "device": device.name,
            "appium_host": self.appium_host,
            "appium_port": appium_port,
            "grid_host": self.grid_host,
            "grid_port": self.grid_port,
        })

    def stop(self):
        log.info("stopping...")
        for node in self.nodes:
            node.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run appium autoregister')
    parser.add_argument('--grid-host', type=str, dest='grid_host', default="localhost",
                        help='Selenium grid host register to. Default localhost.')
    parser.add_argument('--grid-port', type=int, dest='grid_port', default=4444,
                        help='Selenium grid port register to. Default 4444.')
    parser.add_argument('--appium-host', type=str, dest='appium_host', default="localhost",
                        help='This machine host, to be discovered from grid. Default localhost.')
    parser.add_argument('--additional-args', type=str, dest='additional_args', default='',
                        help='Additional arguments to appium, when it starts.'
                             ' Arguments should be separated by ",".'
                             ' Default no additional arguments passing')
    args = parser.parse_args()
    additional_args = args.additional_args.split(',')
    autoregister = Autoregister(args.grid_host, args.grid_port, args.appium_host, additional_args)
    autoregister.run()
