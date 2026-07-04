# -*- coding: utf-8 -*-
import mod.server.extraServerApi as serverApi
import common
import blockLogic as L

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
        self.seats = {}          # playerId -> 座位实体id
        self._pendingAc = {}     # (dim, x, y, z) -> mounted(0/1)，放置面暂存

    # ------------------------------------------------------------------ 通信
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

    # ------------------------------------------------------------------ 方块实体数据
    def _blockEntity(self, dim, pos):
        comp = self.CreateComponent(levelId, "Minecraft", "blockEntityData")
        return comp.GetBlockEntityData(dim, tuple(pos))

    def _getCount(self, dim, pos):
        be = self._blockEntity(dim, pos)
        if be and "count" in be:
            try:
                return int(be["count"])
            except (TypeError, ValueError):
                return 1
        return 1

    def _setCount(self, dim, pos, n):
        be = self._blockEntity(dim, pos)
        if be is not None:
            be["count"] = n

    def _syncMolang(self, dim, pos, var, val):
        self.CallAllClient("SetBlockMolang", dim, list(pos), var, float(val))

    def _consumeHeld(self, playerId):
        try:
            item = CompFactory.CreateItem(playerId)
            slot = item.GetSelectSlotId()
            held = item.GetPlayerItem(Enum.ItemPosType.CARRIED_ITEM, 0)
            cnt = int(held.get("count", 1)) if held else 1
            item.SetInvItemNum(slot, max(0, cnt - 1))
        except Exception as e:
            common.log("consumeHeld err:", e)

    # ------------------------------------------------------------------ 客户端请求方块状态
    def ReqBlockState(self, args):
        dim = args["dim"]
        pos = tuple(args["pos"])
        pid = args["__id__"]
        binfo = CompFactory.CreateBlockInfo(levelId).GetBlockNew(pos, dim)
        if not binfo:
            return
        name = binfo.get("name")
        be = self._blockEntity(dim, pos)
        if name == L.STOOL:
            cnt = int(be["count"]) if (be and "count" in be) else 1
            self.CallClient(pid, "SetBlockMolang", dim, list(pos), "variable.stool_count", float(cnt))
        elif name == L.AC:
            mounted = int(be["mounted"]) if (be and "mounted" in be) else 0
            self.CallClient(pid, "SetBlockMolang", dim, list(pos), "variable.ac_mounted", float(mounted))

    # ------------------------------------------------------------------ 放置：AC 记录朝向 / 红凳堆叠拦截
    @Listen("ServerEntityTryPlaceBlockEvent")
    def OnTryPlaceBlock(self, args):
        full = args["fullName"]
        dim = args["dimensionId"]
        pos = (args["x"], args["y"], args["z"])
        if full == L.AC:
            self._pendingAc[(dim,) + pos] = 0 if L.face_is_ground(args["face"]) else 1
            return
        if full == L.STOOL:
            below = (pos[0], pos[1] - 1, pos[2])
            binfo = CompFactory.CreateBlockInfo(levelId).GetBlockNew(below, dim)
            if binfo and binfo.get("name") == L.STOOL:
                cnt = self._getCount(dim, below)
                if cnt < L.STOOL_MAX:
                    args["cancel"] = True
                    self._setCount(dim, below, cnt + 1)
                    self._syncMolang(dim, below, "variable.stool_count", cnt + 1)
                    self._consumeHeld(args["entityId"])

    @Listen("ServerPlaceBlockEntityEvent")
    def OnPlaceBlockEntity(self, args):
        name = args["blockName"]
        dim = args["dimension"]
        pos = (args["posX"], args["posY"], args["posZ"])
        if name == L.AC:
            mounted = self._pendingAc.pop((dim,) + pos, None)
            if mounted is None:
                blk = CompFactory.CreateBlockInfo(levelId).GetBlockNew(pos, dim)
                aux = (blk or {}).get("aux", 0)
                mounted = 0 if (aux % 6) in (0, 1) else 1
            be = self._blockEntity(dim, pos)
            if be is not None:
                be["mounted"] = mounted
            self._syncMolang(dim, pos, "variable.ac_mounted", mounted)
        elif name == L.STOOL:
            be = self._blockEntity(dim, pos)
            if be is not None and "count" not in be:
                be["count"] = 1
            self._syncMolang(dim, pos, "variable.stool_count", 1)

    # ------------------------------------------------------------------ 红凳交互：坐 / 取回
    @Listen("ServerBlockUseEvent")
    def OnBlockUse(self, args):
        if args["blockName"] != L.STOOL:
            return
        pid = args["playerId"]
        dim = args["dimensionId"]
        pos = (args["x"], args["y"], args["z"])
        cnt = self._getCount(dim, pos)
        sneaking = CompFactory.CreatePlayer(pid).isSneaking()
        args["cancel"] = True
        if sneaking:
            CompFactory.CreateItem(pid).SpawnItemToPlayerInv(
                {"itemName": L.STOOL, "count": 1, "auxValue": 0}, pid)
            if cnt <= 1:
                CompFactory.CreateBlockInfo(levelId).SetBlockNew(
                    pos, {"name": "minecraft:air", "aux": 0}, 0, dim, True)
            else:
                self._setCount(dim, pos, cnt - 1)
                self._syncMolang(dim, pos, "variable.stool_count", cnt - 1)
        else:
            self._sit(pid, dim, pos, cnt)

    def _sit(self, pid, dim, pos, cnt):
        old = self.seats.pop(pid, None)
        if old:
            self.DestroyEntity(old)
        seatPos = (pos[0] + 0.5, pos[1] + L.seat_offset_y(cnt), pos[2] + 0.5)
        seatId = self.CreateEngineEntityByTypeStr(L.SEAT, seatPos, (0.0, 0.0), dim)
        if not seatId:
            return
        self.seats[pid] = seatId
        CompFactory.CreateRide(seatId).SetEntityRide(pid, seatId)

    @Listen("EntityStopRidingEvent")
    def OnStopRiding(self, args):
        rideId = args.get("rideId")
        for pid, sid in list(self.seats.items()):
            if sid == rideId:
                self.DestroyEntity(sid)
                del self.seats[pid]

    # ------------------------------------------------------------------ 破坏堆叠凳：按层数掉落
    @Listen("ServerPlayerTryDestroyBlockEvent")
    def OnTryDestroy(self, args):
        pid = args["playerId"]
        pos = (args["x"], args["y"], args["z"])
        dim = CompFactory.CreateDimension(pid).GetEntityDimensionId()
        binfo = CompFactory.CreateBlockInfo(levelId).GetBlockNew(pos, dim)
        if not binfo or binfo.get("name") != L.STOOL:
            return
        cnt = self._getCount(dim, pos)
        if cnt > 1:
            CompFactory.CreateItem(pid).SpawnItemToPlayerInv(
                {"itemName": L.STOOL, "count": cnt - 1, "auxValue": 0}, pid)
