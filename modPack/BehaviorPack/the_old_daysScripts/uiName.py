# -*- coding: utf-8 -*-
import mod.client.extraClientApi as clientApi
import common

Client = clientApi.GetSystem(common.ModName, "ClientSystem")
ScreenNode = clientApi.GetScreenNodeCls()
CompFactory = clientApi.GetEngineCompFactory()
Enum = clientApi.GetMinecraftEnum()
localPlayerId = clientApi.GetLocalPlayerId()
ViewBinder = clientApi.GetViewBinderCls()


class uiName(ScreenNode):
    def __init__(self, namespace, name, param):
        ScreenNode.__init__(self, namespace, name, param)

    def Create(self):
        pass

    def Destroy(self):
        pass

    def Update(self):
        pass
