# -*- coding: utf-8 -*-
import mod.server.extraServerApi as serverApi
import common

CompFactory = serverApi.GetEngineCompFactory()
Enum = serverApi.GetMinecraftEnum()
levelId = serverApi.GetLevelId()
eventList = []


def Listen(funcOrStr=None, EN=serverApi.GetEngineNamespace(), ESN=serverApi.GetEngineSystemName(), priority=0):
    def binder(func):
        eventList.append((EN, ESN, funcOrStr if isinstance(funcOrStr, str) else func.__name__, func, priority))
        return func

    return binder(funcOrStr) if callable(funcOrStr) else binder


class ServerSystem(serverApi.GetServerSystemCls()):
    def __init__(self, namespace, systemName):
        super(ServerSystem, self).__init__(namespace, systemName)
        for EN, ESN, eventName, callback, priority in eventList:
            self.ListenForEvent(EN, ESN, eventName, self, callback, priority)

    @Listen("ClientEvent", common.ModName, "ClientSystem")
    def OnGetClientEvent(self, args):
        funcArgs = args.get("args", ({},))
        if len(funcArgs) == 1 and isinstance(funcArgs[0], dict):
            funcArgs[0]["__id__"] = args["__id__"]
        getattr(self, args["funcName"])(*funcArgs, **args.get("kwargs", {}))

    def CallClient(self, playerId, funcName, *args, **kwargs):
        self.NotifyToClient(playerId, "ServerEvent", common.CreateEventData(funcName, args, kwargs))

    def CallAllClient(self, funcName, *args, **kwargs):
        self.BroadcastToAllClient("ServerEvent", common.CreateEventData(funcName, args, kwargs))
