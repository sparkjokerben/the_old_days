# -*- coding: utf-8 -*-
import time

ModName = __file__.rsplit("/" if "/" in __file__ else ".", 2)[-2]


def CreateEventData(funcName, args, kwargs):
    data = {"funcName": funcName}
    if args:
        data["args"] = args
    if kwargs:
        data["kwargs"] = kwargs
    return data


def log(*msg):
    print("[{}] [\033[32m{}\033[0m] {}".format(time.strftime("%Y-%m-%d %H:%M:%S"), ModName, " ".join(map(str, msg))))
