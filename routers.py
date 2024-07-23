from fastapi import APIRouter,HTTPException

from homeassistant_functions import getEntities,getEntity,getServicesByEntity,getHistory,getAutomations,callService,getDevices
from database_functions import initialize_database, add_map_entities, get_all_map_entities,get_map_entity
from schemas import Service_In,Operation_Out,Map_Entity_List,Map_Entity

import datetime,json
from dateutil import parser,tz


def getEntityRouter():
    entity_router=APIRouter(tags=["Entity"],prefix="/entity")
    @entity_router.get("")
    def Get_All_Entities(skip_services:bool=False):
        res=getEntities(skip_services)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
    @entity_router.get("/{entity_id}")
    def Get_Single_Entity(entity_id:str):
        res=getEntity(entity_id=entity_id)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
    @entity_router.get("/services/{entity_id}")
    def Get_Entity_Serices(entity_id:str):
        res=getServicesByEntity(entity_id=entity_id)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
    return entity_router




def createStateArray(list:list,start_timestamp:datetime,end_timestamp:datetime)->list:
        res=[]
        temp_date=start_timestamp
        for i in range(len(list)-1):
            #temp_date=parser.parse(list[i]["last_changed"],)
            end_block = parser.parse(list[i+1]["last_changed"]).astimezone(tz.tzlocal())
            while temp_date<end_block:
                res.append({"date":temp_date.strftime("%d/%m/%Y-%H:%M:%S"),"state":list[i]["state"],"power_consumption":list[i]["power_consumption"]})
                temp_date=temp_date+datetime.timedelta(seconds=60)
        #estendo l'ultimo blocco fino alla fine dell'intervallo richiesto in quanto home assistant fornisce solo i blocchi con dei cambi
        #per cui se per esempio l'ultimo cambio è avvenuto alle 22 l'ultimo blocco riporterà quell'ora e non le 23:59 per cui devo io estendere
        #manualmente lo stato fino alla fine dell'intervallo richiesto
        while temp_date<end_timestamp:
            res.append({"date":temp_date.strftime("%d/%m/%Y-%H:%M:%S"),"state":list[-1]["state"],"power_consumption":list[-1]["power_consumption"]})
            temp_date=temp_date+datetime.timedelta(seconds=60)
        return res

def computeDailyTotalConsumption(list:list,day:datetime.date)->list:
        sum=0
        use_time=0
        active_modes=["on","playing"]
        for i in range(len(list)):
            start_block=parser.parse(list[i]["last_changed"]).astimezone(tz.tzlocal())
            if i+1==len(list):
                end_block=datetime.datetime.combine(day+datetime.timedelta(days=1), datetime.time.min).astimezone(tz.tzlocal())
            else:
                end_block=parser.parse(list[i+1]["last_changed"]).astimezone(tz.tzlocal())
            delta=(end_block-start_block).total_seconds() #calcolo la durata dell'intervallo
            if list[i]["state"] in active_modes:
                use_time=use_time+delta/60
            delta=delta/3600 #lo converto in ore
            sum=sum+list[i]["power_consumption"]*delta #calcolo il kWh spesi
        return {"date":day.strftime("%d/%m/%Y"),"total_consumption":sum,"total_consumption_unit":"Wh","use_time":use_time,"use_time_unit":"min"}
        

        


def getHistoryRouter():
    history_router=APIRouter(tags=["History"],prefix="/history")

    @history_router.get("/daily")
    def Get_Entity_History(entity_id:str,start_timestamp:datetime.datetime=datetime.date.today()):
        start_timestamp=start_timestamp.astimezone(tz.tzlocal())
        end_timestamp=start_timestamp+datetime.timedelta(days=1)
        res=getHistory(entity_id=entity_id,start_timestamp=start_timestamp,end_timestamp=end_timestamp)[0]
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        else:
            list=res["data"]
            return createStateArray(list,start_timestamp,end_timestamp)
    

    @history_router.get("/total")
    def Get_Total_Consumpiton(entity_id:str,start_timestamp:datetime.date,end_timestamp:datetime.date):
        start_timestamp=datetime.datetime.combine(start_timestamp, datetime.time.min).astimezone(tz.tzlocal())
        end_timestamp=datetime.datetime.combine(end_timestamp,  datetime.time(23, 59)).astimezone(tz.tzlocal())
        resp=getHistory(entity_id=entity_id,start_timestamp=start_timestamp,end_timestamp=end_timestamp)
        if resp["status_code"]!=200:
            raise HTTPException(status_code=resp["status_code"],detail=resp["data"])
        
        list=resp["data"]
        res=[]
        delta=(end_timestamp-start_timestamp).days
        temp_date=start_timestamp
        for i in range(delta+1):
            temp_list=[x for x in list if x["last_changed"].startswith(temp_date.strftime("%Y-%m-%d"))]
            res.append(computeDailyTotalConsumption(temp_list,temp_date))
            temp_date=temp_date+datetime.timedelta(days=1)
        return res
        
    
    return history_router



def getDeviceRouter():
    device_router=APIRouter(tags=["Device"],prefix="/device")
    @device_router.get("")
    def Get_All_Devices(skip_services:bool):
        res=getDevices(skip_services)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
    @device_router.get("/{device_id}")
    def Get_Single_Device(device_id:str):
        return {"result":"not implemented!"}

    
    return device_router

def getAutomationRouter():
    automation_router=APIRouter(tags=["Automation"],prefix="/automation")

    @automation_router.get("")
    def Get_Automations():
        res=getAutomations()
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
    return automation_router

def getServiceRouter():
    service_router=APIRouter(tags=["Service"],prefix="/service")
    @service_router.post("")
    def Call_Service(service:Service_In):
        res=callService(service=service)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
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
