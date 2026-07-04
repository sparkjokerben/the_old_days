# -*- coding: utf-8 -*-
import mod.client.extraClientApi as clientApi
import common
import blockLogic as L

CompFactory = clientApi.GetEngineCompFactory()
localPlayerId = clientApi.GetLocalPlayerId()
Enum = clientApi.GetMinecraftEnum()
levelId = clientApi.GetLevelId()
eventList = []


def Listen(funcOrStr=None, EN=clientApi.GetEngineNamespace(), ESN=clientApi.GetEngineSystemName(), priority=0):
    def binder(func):
        eventList.append((EN, ESN, funcOrStr if isinstance(funcOrStr, str) else func.__name__, func, priority))
        return func

    return binder(funcOrStr) if callable(funcOrStr) else binder


class ClientSystem(clientApi.GetClientSystemCls()):
    def __init__(self, namespace, systemName):
        super(ClientSystem, self).__init__(namespace, systemName)
        for EN, ESN, eventName, callback, priority in eventList:
            self.ListenForEvent(EN, ESN, eventName, self, callback, priority)

    @Listen
    def UiInitFinished(self, args):
        print("UI框架初始化完成")

    @Listen("ServerEvent", common.ModName, "ServerSystem")
    def OnGetServerEvent(self, args):
        getattr(self, args["funcName"])(*args.get("args", ()), **args.get("kwargs", {}))

    def CallServer(self, funcName, *args, **kwargs):
        self.NotifyToServer("ClientEvent", common.CreateEventData(funcName, args, kwargs))

    def CallClient(self, playerId, funcName, *args, **kwargs):
        if playerId == localPlayerId:
            return getattr(self, funcName)(*args, **kwargs)
        self.CallServer("CallClient", playerId, funcName, *args, **kwargs)

    def CallAllClient(self, funcName, *args, **kwargs):
        self.CallServer("CallAllClient", funcName, *args, **kwargs)

    # ------------------------------------------------------------------ 方块实体外观状态
    @Listen("ModBlockEntityLoadedClientEvent")
    def OnBlockEntityLoaded(self, args):
        name = args["blockName"]
        if name in (L.STOOL, L.AC):
            # 方块实体刚初始化，向服务端请求其存档状态以设置 molang（切几何体）
            self.CallServer("ReqBlockState", {
                "dim": args["dimensionId"],
                "pos": [args["posX"], args["posY"], args["posZ"]],
            })

    def SetBlockMolang(self, dim, pos, var, val):
        # 服务端下发：设置自定义方块实体的 molang，驱动渲染控制器切换几何体
        CompFactory.CreateBlockInfo(levelId).SetBlockEntityMolangValue(tuple(pos), var, float(val))
