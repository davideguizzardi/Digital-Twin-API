from fastapi import APIRouter,HTTPException
from homeassistant_functions import (
    getDevicesFast,getDevicesNameAndId,
    getSingleDeviceFast)
from database_functions import (
    get_all_appliances_usage_entries,get_usage_entry_for_appliance,get_configuration_of_device,get_names_and_id_configuration,
    get_map_entity,get_all_rooms_of_floor,get_groups_for_device,get_configured_devices)
from collections import defaultdict
from demo_functions import get_all_demo_devices
from schemas import find_room
import json


def getDeviceRouter(enable_demo=False):
    device_router=APIRouter(tags=["Device"],prefix="/device")
    @device_router.get("")
    def Get_All_Devices(get_only_names:bool=False):
        if get_only_names:
            if enable_demo:
                return get_all_demo_devices(get_only_names)
            else:    
                return get_names_and_id_configuration()

        if enable_demo:
            res={"status_code":200,"data":get_all_demo_devices(False)} 
        else:    
            res=getDevicesFast()
        
        if res["status_code"]==200:
            entities_list=get_configured_devices()
            for dev in res['data']:
                if len(entities_list)>0:
                    dev["list_of_entities"] = [e for e in dev["list_of_entities"] if e["entity_id"] in entities_list]
                dev["name"]=dev["name_by_user"] if dev["name_by_user"] else dev["name"]
                dev["category"]=dev["device_class"]
                dev["show"]=True
                dev.pop("name_by_user",None)
                configuration_data=get_configuration_of_device(dev["device_id"])
                if configuration_data:
                    dev["name"]=configuration_data["name"]
                    dev["category"]=configuration_data["category"]
                    dev["show"]=configuration_data["show"]==1

                map_data=get_map_entity(dev["device_id"])
                if map_data:
                    floor_rooms=get_all_rooms_of_floor(map_data["floor"])
                    room_name=find_room(float(map_data["x"]),float(map_data["y"]),floor_rooms)
                    dev["map_data"]={
                        "x":map_data["x"],
                        "y":map_data["y"],
                        "floor":map_data["floor"],
                        "room":room_name
                    }
                group_data=get_groups_for_device(dev["device_id"])
                dev["groups"]=group_data or []

        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
    @device_router.get("/{device_id}")
    def Get_Single_Device(device_id:str):
        res=getSingleDeviceFast(device_id=device_id)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        dev=res["data"]
        dev["name"]=dev["name_by_user"] if dev["name_by_user"] else dev["name"]
        dev["category"]=dev["device_class"]
        dev["show"]=True
        dev.pop("name_by_user",None)
        configuration_data=get_configuration_of_device(dev["device_id"])
        if configuration_data:
            dev["name"]=configuration_data["name"]
            dev["category"]=configuration_data["category"]
            dev["show"]=configuration_data["show"]==1
        map_data=get_map_entity(dev["device_id"])
        if map_data:
            floor_rooms=get_all_rooms_of_floor(map_data["floor"])
            room_name=find_room(float(map_data["x"]),float(map_data["y"]),floor_rooms)
            dev["map_data"]={
                "x":map_data["x"],
                "y":map_data["y"],
                "floor":map_data["floor"],
                "room":room_name
            }
        return dev
    
    @device_router.get("/usage/single/{device_id}")
    def Get_Single_Device_Usage_Data(device_id:str):
        usage_data=get_usage_entry_for_appliance(device_id)
        device=getSingleDeviceFast(device_id)
        if device["status_code"]==200:
            device=device["data"]
        res=[]
        for data in usage_data:
            res.append({
                    "device_id":device_id,
                    "entity_id":device.get("state_entity_id",""),
                    "state":data["state"],
                    "average_duration":data["average_duration"],
                    "average_power":data["average_power"],
                    "max_power":data["maximum_power"]
            })
        return {device.get("name"):res}

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
        return dict(result)
        

    
    return device_router