# -*- coding: utf-8 -*-
from mod.common.mod import Mod
import mod.server.extraServerApi as serverApi
import mod.client.extraClientApi as clientApi
import common


@Mod.Binding(name=common.ModName, version="1.0.0")
class Main(object):
    @Mod.InitServer()
    def ServerInit(self):
        serverApi.RegisterSystem(common.ModName, "ServerSystem", common.ModName + ".serverSystem.ServerSystem")

    @Mod.DestroyServer()
    def ServerDestroy(self):
        pass

    @Mod.InitClient()
    def ClientInit(self):
        clientApi.RegisterSystem(common.ModName, "ClientSystem", common.ModName + ".clientSystem.ClientSystem")

    @Mod.DestroyClient()
    def ClientDestroy(self):
        pass
