from fastapi import APIRouter,HTTPException
import json
def getVirtualRouter():
    virtual_router=APIRouter(tags=["Virtual"],prefix="/virtual")

    @virtual_router.get("/device")
    def Get_All_Devices(get_only_names:bool=False):
        file=open("./data/virtual_context.json")
        virtual_context=json.load(file)
        return virtual_context["device_context"] if not get_only_names else virtual_context["device_context_only_names"]

    @virtual_router.get("/entity")
    def Get_All_Virtual_Entities():
        file=open("./data/virtual_context.json")
        virtual_context=json.load(file)
        return virtual_context["entities_context"]
    
    @virtual_router.get("/entity/{entity_id}")
    def Get_Virtual_Entity(entity_id):
        file=open("./data/virtual_context.json")
        virtual_context=json.load(file)
        temp=[x for x in virtual_context["entities_context"] if x["entity_id"]==entity_id]
        return temp[0] if len(temp)>0 else {}
    
    @virtual_router.get("/home")
    def Get_Home_context():
        file=open("./data/virtual_context.json")
        virtual_context=json.load(file)
        return virtual_context["home_context"]
    
    @virtual_router.get("/history/total/daily")
    def Get_Daily_Consumption():
        file=open("./data/virtual_context.json")
        virtual_context=json.load(file)
        return virtual_context["daily_total_consumption"]
    
    @virtual_router.get("/history/total/hourly")
    def Get_Hourly_Consumption():
        file=open("./data/virtual_context.json")
        virtual_context=json.load(file)
        return virtual_context["hourly_total_consumption"]
    
    return virtual_router
