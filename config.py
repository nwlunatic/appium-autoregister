# coding: utf-8
from configparser import ConfigParser


config = ConfigParser()
config.read('proxy.ini')
config.read('local.proxy.ini')
