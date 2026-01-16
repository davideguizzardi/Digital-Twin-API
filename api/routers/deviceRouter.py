from fastapi import APIRouter,HTTPException
from homeassistant_functions import (
    getDevicesFast,getDevicesNameAndId,
    getSingleDeviceFast,getLastLogbookEntry)
from database_functions import (
    get_all_appliances_usage_entries,get_usage_entry_for_appliance,get_configuration_of_device,get_names_and_id_configuration,
    get_map_entity,get_all_rooms_of_floor,get_groups_for_device,get_configured_devices,get_last_event_for_target)
from collections import defaultdict
from demo_functions import get_all_demo_devices
from schemas import find_room
import json

from datetime import datetime, timezone, timedelta

def merge_last_event_and_logbook(last_event: dict, last_booklog: dict):
    """
    Merge Home Assistant last_event and last_booklog data into a unified entry.
    Rules:
      - Convert UTC datetime (from last_booklog) to local time.
      - If datetimes match (same moment), merge fields.
      - If different, newer wins.
      - If logbook is an automation trigger, build special entry.
    """
    event_timestamp= last_event.get("timestamp") if last_event else None
    # --- Parse last_booklog datetime (UTC) ---
    log_timestamp=None
    if last_booklog and "when" in last_booklog:
        log_timestamp = datetime.fromisoformat(last_booklog["when"].replace("Z", "+00:00")).timestamp()

    # --- If both exist, compare times ---
    if event_timestamp and log_timestamp:
        #same manual event
        if abs((event_timestamp - log_timestamp)) < 60:
            return {
                "actor": last_event.get("actor", last_booklog.get("context_domain")),
                "state": last_booklog.get("state"),
                "domain":"manual_command",
                "service": last_event.get("event", last_booklog.get("context_service")).replace("Service:",""),
                "datetime": datetime.fromtimestamp(event_timestamp).astimezone().strftime("%d/%m/%Y %H:%M")
            }
        # Rare occurency in which the DT get an event and HA didnt
        elif event_timestamp > log_timestamp:
            return {
                "actor": last_event.get("actor"),
                "state": None,
                "domain":"manual_command",
                "service": last_event.get("event").replace("Service:",""),
                "datetime": datetime.fromtimestamp(event_timestamp).astimezone().strftime("%d/%m/%Y %H:%M")
            }
        else:
            #A more recent automation activation changed device state (no local log can exist)
            return {
            "actor": last_booklog.get("context_name", "automation"),
            "state": last_booklog.get("state"),
            "domain": "automation_triggered",
            "service":"automation",
            "datetime": datetime.fromtimestamp(log_timestamp).astimezone().strftime("%d/%m/%Y %H:%M")
            }

    # --- If only one exists ---
    if last_event:
        return {
            "actor": last_event.get("actor"),
            "state": None,
            "domain":"manual_command",
            "service": last_event.get("event").replace("Service:",""),
            "datetime": datetime.fromtimestamp(event_timestamp).astimezone().strftime("%d/%m/%Y %H:%M")
        }

    if last_booklog:
        return {
            "actor": last_booklog.get("context_domain", "unknown"),
            "state": last_booklog.get("state"),
            "domain":last_booklog.get("context_event_type",""),
            "service": last_booklog.get("context_service", "unknown"),
            "datetime": datetime.fromtimestamp(log_timestamp).astimezone().strftime("%d/%m/%Y %H:%M")
        }

    return {}



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

                if len(dev["state_entity_id"])>0:
                    last_local_log = get_last_event_for_target(dev["state_entity_id"])
                    last_ha_log=getLastLogbookEntry(dev["state_entity_id"]) #TODO:unify functions notations
                    dev["last_event"]=merge_last_event_and_logbook(last_local_log,last_ha_log)
 

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