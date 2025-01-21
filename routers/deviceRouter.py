from fastapi import APIRouter,HTTPException
from homeassistant_functions import (
    getDevicesFast,getDevicesNameAndId,
    getSingleDeviceFast)
from database_functions import (get_all_appliances_usage_entries)
from collections import defaultdict
import json


def getDeviceRouter():
    device_router=APIRouter(tags=["Device"],prefix="/device")
    @device_router.get("")
    def Get_All_Devices(get_only_names:bool=False):
        if get_only_names:
            res=getDevicesNameAndId()
        else:    
            res=getDevicesFast()
            if res["status_code"]==200:
                for dev in res['data']:
                    dev["name"]=dev["name_by_user"] if dev["name_by_user"] else dev["name"]
                    dev.pop("name_by_user",None)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
    @device_router.get("/{device_id}")
    def Get_Single_Device(device_id:str):
        res=getSingleDeviceFast(device_id=device_id)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    

    @device_router.get("/usage/all")
    def Get_All_Device_Usage_Data():
        usage_data=get_all_appliances_usage_entries()
        devices_list=getDevicesNameAndId()["data"]
        result=defaultdict(lambda:[])
        for data in usage_data:
            device_name=[x for x in devices_list if x["device_id"]==data["device_id"]]
            if len(device_name)>0:
                device_name=device_name[0]["name"]
            else:
                continue
            result[device_name].append(
                {
                    "device_id":data["device_id"],
                    "state":data["state"],
                    "average_duration":data["average_duration"],
                    "average_power":data["average_power"],
                    "max_power":data["maximum_power"]
                }
            )

        #TODO: remove this part in the future, it is used only to test purposed
        virtual_devices=["washing_machine","microwave"]
        with open("./data/appliances_consumption_map.json") as file:
            consumption_map=json.load(file)
            for device in virtual_devices:
                for state in consumption_map[device]:
                    result[device].append(
                    {
                        "device_id":f"virtual.{device}",
                        "state":state["name"],
                        "average_duration":state.get("default_duration",0)/60,
                        "average_power":state["power_consumption"]
                    }
            )

        return dict(result)
        

    
    return device_router