from fastapi import APIRouter

from homeassistant_functions import getEntities,getEntity,getServicesByEntity,getHistory,getAutomations,callService,getDevices
from database_functions import initialize_database, add_map_entities, get_all_map_entities,get_map_entity
from schemas import Service_In,Operation_Out,Map_Entity_List,Map_Entity

import datetime,json


def getEntityRouter():
    entity_router=APIRouter(tags=["Entity"],prefix="/entity")
    @entity_router.get("")
    def Get_All_Entities(skip_services:bool=False):
        return getEntities(skip_services)
    
    @entity_router.get("/{entity_id}")
    def Get_Single_Entity(entity_id:str):
        return getEntity(entity_id=entity_id)
    
    @entity_router.get("/history/")
    def Get_Entity_History(entity_id:str,start_timestamp:datetime.datetime | None = None,end_timestamp:datetime.datetime| None = None):
        return getHistory(entity_id=entity_id,start_timestamp=start_timestamp,end_timestamp=end_timestamp)
    
    @entity_router.get("/services/{entity_id}")
    def Get_Entity_Serices(entity_id:str):
        return getServicesByEntity(entity_id=entity_id)
    
    return entity_router


def getDeviceRouter():
    device_router=APIRouter(tags=["Device"],prefix="/device")
    @device_router.get("")
    def Get_All_Devices(skip_services:bool):
        return getDevices(skip_services)
    
    @device_router.get("/{device_id}")
    def Get_Single_Device(device_id:str):
        return {"result":"not implemented!"}

    
    return device_router

def getAutomationRouter():
    automation_router=APIRouter(tags=["Automation"],prefix="/automation")

    @automation_router.get("")
    def Get_Automations():
        return getAutomations()
    
    return automation_router

def getServiceRouter():
    service_router=APIRouter(tags=["Service"],prefix="/service")
    @service_router.post("")
    def Call_Service(service:Service_In):
        return callService(service=service)
    return service_router

def getConfigurationRouter():
    configuration_router=APIRouter(tags=["Configuration"],prefix="/configuration")

    @configuration_router.get("/initialize",response_model=Operation_Out)
    def Initialize_Database():
        return {"success":initialize_database()}
    
    @configuration_router.get("/map",response_model=list[Map_Entity])
    def Get_Map_Entitites():
        return get_all_map_entities()
    
    @configuration_router.get("/map/{entity_id}",response_model=Map_Entity)
    def Get_Single_Map_Entity(entity_id:str):
        return get_map_entity(entity_id)
    
    @configuration_router.put("/map",response_model=Operation_Out)
    def Add_Map_Entity(entities_list:Map_Entity_List):
        return {"success":add_map_entities([tuple(d.__dict__.values()) for d in entities_list.data])}

    return configuration_router

def getVirtualRouter():
    virtual_router=APIRouter(tags=["Virtual"],prefix="/virtual")

    @virtual_router.get("/entity")
    def Get_All_Virtual_Entities():
        file=open("./data/virtual_context.json")
        return json.load(file)
    
    return virtual_router
