from fastapi import APIRouter,HTTPException


from homeassistant_functions import (
    getEntities,getEntity,
    getServicesByEntity
)
from demo_functions import (get_all_demo_entities,get_demo_entity)


def getEntityRouter(enable_demo=False):
    entity_router=APIRouter(tags=["Entity"],prefix="/entity")
    @entity_router.get("")
    def Get_All_Entities(skip_services:bool=False):
        res=getEntities(skip_services)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
    @entity_router.get("/{entity_id}")
    def Get_Single_Entity(entity_id:str):
        if enable_demo:
            return get_demo_entity(entity_id)
        res=getEntity(entity_id=entity_id)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        entity=res["data"]
        res=getServicesByEntity(entity_id=entity_id)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        entity["services"]=res["data"]
        return entity
    
    @entity_router.get("/services/{entity_id}")
    def Get_Entity_Services(entity_id:str):
        res=getServicesByEntity(entity_id=entity_id)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
    return entity_router