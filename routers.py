from fastapi import APIRouter,HTTPException
from multiprocessing import Pool

from homeassistant_functions import getEntities,getEntity,getServicesByEntity,getHistory,getAutomations,callService,getDevices
from database_functions import (
    initialize_database,
    get_all_configuration_values,get_configuration_value_by_key,add_configuration_values,delete_configuration_value,
    add_map_entities, get_all_map_entities,get_map_entity,delete_map_entry,delete_floor_map_configuration,
    get_all_service_logs,add_service_logs,get_service_logs_by_user,
    get_energy_slot_by_day,get_all_energy_slots,add_energy_slots,delete_energy_slots
    )
from schemas import (
    Service_In,Operation_Out,Map_Entity_List,
    Map_Entity,User_Log,User_Log_List,Configuration_Value,
    Configuration_Value_List,Energy_Plan_Calendar)

import datetime,json,configparser
from dateutil import parser,tz
from collections import defaultdict


def getEntityRouter():
    entity_router=APIRouter(tags=["Entity"],prefix="/entity")
    @entity_router.get("")
    def Get_All_Entities(skip_services:bool=False,only_main:bool=False):
        res=getEntities(skip_services,only_main)
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




def createStateArray(entity_id:str,list:list,start_timestamp:datetime,end_timestamp:datetime)->list:
        time_delta=5 #minuti 
        power_consumption_factor=time_delta/60 
        #supponendo che un dispositivo abbia potenza 1W => consumera' 1 Wh ogni ora 
        #se campiono con un valore piu' basso dell'ora (es 1 minuti) dovro' calcolare che il dispositivo
        #consuma minuti_campionamento/60 di Wh ogni minuti_campionamento
        res=[]
        temp_date=start_timestamp
        for i in range(len(list)-1):
            #temp_date=parser.parse(list[i]["last_changed"],)
            end_block = parser.parse(list[i+1]["last_changed"]).astimezone(tz.tzlocal())
            while temp_date<end_block:
                res.append({
                    "date":temp_date.strftime("%d/%m/%Y %H:%M:%S"),
                    "state":list[i]["state"],
                    "power_consumption":list[i]["power_consumption"]*power_consumption_factor})
                temp_date=temp_date+datetime.timedelta(minutes=time_delta)
        #estendo l'ultimo blocco fino alla fine dell'intervallo richiesto in quanto home assistant fornisce solo i blocchi con dei cambi
        #per cui se per esempio l'ultimo cambio è avvenuto alle 22 l'ultimo blocco riporterà quell'ora e non le 23:59 per cui devo io estendere
        #manualmente lo stato fino alla fine dell'intervallo richiesto
        while temp_date<end_timestamp:
            res.append({
                "date":temp_date.strftime("%d/%m/%Y %H:%M:%S"),
                "state":list[-1]["state"],
                "power_consumption":list[-1]["power_consumption"]*power_consumption_factor})
            temp_date=temp_date+datetime.timedelta(minutes=time_delta)
        return {entity_id:res}

def computeHourlyTotalConsumption(entity_id,states,start_timestamp,end_timestamp):
    state_array=createStateArray(entity_id,states,start_timestamp,end_timestamp)[entity_id]
    res=defaultdict(lambda: {"power_consumption":0,"power_consumption_unit":"Wh"})
    for state in state_array:
        date=datetime.datetime.strptime(state["date"],"%d/%m/%Y %H:%M:%S")
        key=date.strftime("%d/%m/%Y %H-")+(date+datetime.timedelta(hours=1)).strftime("%H") #es 10/07/2024 00-01
        res[key]["power_consumption"]+=state["power_consumption"]
    return {entity_id:dict(res)}

def computeDailyTotalConsumption(list:list,day:datetime.date)->list:
        sum=0
        use_time=0 
        time_delta=60
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
        return {"power_consumption":sum,"power_consumption_unit":"Wh","use_time":use_time,"use_time_unit":"min"}
        

        


def getHistoryRouter():
    history_router=APIRouter(tags=["History"],prefix="/history")

    @history_router.get("/daily")
    def Get_Entity_History(entities:str,start_timestamp:datetime.datetime=datetime.date.today()):
        start_timestamp=start_timestamp.astimezone(tz.tzlocal())
        end_timestamp=start_timestamp+datetime.timedelta(days=1)
        if end_timestamp>datetime.datetime.now(tz.tzlocal()):
            end_timestamp=datetime.datetime.now(tz.tzlocal())
            
        response=getHistory(entities_id=entities,start_timestamp=start_timestamp,end_timestamp=end_timestamp)
        if response["status_code"]!=200:
            raise HTTPException(status_code=response["status_code"],detail=response["data"])
        else:
            entities_states=response["data"]
            res_pool={}
            res={}
            with Pool(len(entities_states)) as pool:
                args=[(entity_id,entities_states[entity_id],start_timestamp,end_timestamp) for entity_id in entities_states]
                res_pool=pool.starmap(createStateArray,args)
            for el in res_pool:
                res.update(el)
            return res
            #return createStateArray(list,start_timestamp,end_timestamp)
        
    

    return history_router


def getConsumptionRouter():
    consumption_router=APIRouter(tags=["Consumption"],prefix="/consumption")

    @consumption_router.get("/entity")
    def Get_Entities_Consumption(entities:str,start_timestamp:datetime.date,end_timestamp:datetime.date,group:str):

        start_timestamp=datetime.datetime.combine(start_timestamp, datetime.time.min).astimezone(tz.tzlocal())
        end_timestamp=datetime.datetime.combine(end_timestamp,  datetime.time(23, 59)).astimezone(tz.tzlocal())

        response=getHistory(entities_id=entities,start_timestamp=start_timestamp,end_timestamp=end_timestamp)
        if response["status_code"]!=200:
            raise HTTPException(status_code=response["status_code"],detail=response["data"])
        
        entities_states=response["data"]

        if group.lower()=="hourly":
            res_pool={}
            res={}
            with Pool(len(entities_states)) as pool:
                args=[(entity_id,entities_states[entity_id],start_timestamp,end_timestamp) for entity_id in entities_states]
                res_pool=pool.starmap(computeHourlyTotalConsumption,args)
            for el in res_pool:
                res.update(el)
            return res
        else:         
            res={}
            delta=(end_timestamp-start_timestamp).days
            for id in entities_states:
                temp_date=start_timestamp
                temp={}
                entity_id=id
                for i in range(delta+1):                   
                    temp_list=[x for x in entities_states[id] if x["last_changed"].startswith(temp_date.strftime("%Y-%m-%d"))]
                    temp[temp_date.strftime("%d/%m/%Y")]=computeDailyTotalConsumption(temp_list,temp_date)
                    temp_date=temp_date+datetime.timedelta(days=1)
                res[entity_id]=temp
            return res
        
    @consumption_router.get("/total")
    def Get_Total_Consumption(start_timestamp:datetime.date,end_timestamp:datetime.date,group:str):
        res=getEntities(True,False)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        
        domainsToFilter=["light","media_player","fan"] #domains of entities that could consume energy, sensors and buttons are supposed to consume 0
        entities_list=[x["entity_id"] for x in res["data"] if x["entity_id"].split(".")[0] in domainsToFilter]
        entities_list=",".join(entities_list)
        consumption_history=Get_Entities_Consumption(entities_list,start_timestamp,end_timestamp,group)
        result=defaultdict(lambda:{"power_consumption":0,"power_consumption_unit":"Wh"})
        for key1 in consumption_history.keys():
            for key2 in consumption_history[key1].keys():
                result[key2]["power_consumption"]+=consumption_history[key1][key2]["power_consumption"]
        return result
    
    return consumption_router




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
        add_service_logs([(service.user,service.service,service.entity_id,json.dumps(service.data),datetime.datetime.now().replace(microsecond=0).timestamp())])
        return res["data"]
    

    @service_router.get("/logs",response_model=list[User_Log])
    def Get_All_Service_Logs():
        return get_all_service_logs()
    
    @service_router.get("/logs/{user}",response_model=list[User_Log])
    def Get_Service_Logs_By_User(user:str):
        return get_service_logs_by_user(user)
    
    @service_router.put("/logs",response_model=Operation_Out)
    def Add_Service_logs(logs_list:User_Log_List):
        return {"success":add_service_logs([tuple(d.__dict__.values()) for d in logs_list.data])}
    
    return service_router

def getConfigurationRouter():
    configuration_router=APIRouter(tags=["Configuration"],prefix="/configuration")

    @configuration_router.get("/initialize",response_model=Operation_Out)
    def Initialize_Database():
        return {"success":initialize_database()}
    
    @configuration_router.get("",response_model=list[Configuration_Value])
    def Get_Configuration_Values():
        return get_all_configuration_values()
    
    @configuration_router.get("/{key}",response_model=Configuration_Value)
    def Get_Configuration_Value_By_Key(key):
        return get_configuration_value_by_key(key)
    
    @configuration_router.put("",response_model=Operation_Out)
    def Add_Configuration_Values(values_list:Configuration_Value_List):
        return {"success":add_configuration_values([tuple(d.__dict__.values()) for d in values_list.data])}
    
    @configuration_router.put("/energy/calendar",response_model=Operation_Out)
    def Add_Energy_Calendar(data:Energy_Plan_Calendar):
        print(data)
        return {"success":True}
    
    @configuration_router.delete("/{key}",response_model=Operation_Out)
    def Delete_Configuration_Value(key:str):
        return {"success":delete_configuration_value(key)}

    return configuration_router

def getEnergyCalendarConfigurationRouter():
    energy_calendar_router=APIRouter(tags=["Energy calendar"],prefix="/calendar")

    @energy_calendar_router.get("",response_model=Energy_Plan_Calendar)
    def Get_All_Slots():
        slots_list=get_all_energy_slots()
        if len(slots_list)<(24*7): #si suppone che il calendario o ci sia tutto o non ci sia. Per come e' scritta ora l'API i blocchi hanno senso solo se tutti
            return {"data":[]}
        res=[]
        i=0
        for day in range(7):
            day_list=[]
            for hour in range(24):
                day_list.append(slots_list[i][-1])
                i+=1
            res.append(day_list)
        return {"data":res}
    
    @energy_calendar_router.get("/{day}")
    def Get_Energy_Slots_By_Day(entity_id:str,response_model=Energy_Plan_Calendar):
        slots_list=get_energy_slot_by_day(entity_id)
        res=[]
        for hour in range(24):
            res.append(slots_list[hour])
        return {"data":res}
    
    @energy_calendar_router.put("",response_model=Operation_Out)
    def Add_calendar(slots_matrix:Energy_Plan_Calendar):
        tuple_list=[]
        for day in range(len(slots_matrix.data)):
            for hour in range(len(slots_matrix.data[day])):
                tuple_list.append((day,hour,slots_matrix.data[day][hour]))
        return {"success":add_energy_slots(tuple_list)}
    
    @energy_calendar_router.delete("",response_model=Operation_Out)
    def Delete_Energy_Slots():
        return {"success":delete_energy_slots()}

    
    return energy_calendar_router

def getMapConfigurationRouter():
    map_configuration_router=APIRouter(tags=["Map configuration"],prefix="/map")

    @map_configuration_router.get("")
    def Get_All_Entities():
        return get_all_map_entities()
    
    @map_configuration_router.get("/{entity_id}",response_model=Map_Entity)
    def Get_Single_Map_Entity(entity_id:str):
        return get_map_entity(entity_id)
    
    @map_configuration_router.put("",response_model=Operation_Out)
    def Add_Map_Entity(entities_list:Map_Entity_List):
        return {"success":add_map_entities([tuple(d.__dict__.values()) for d in entities_list.data])}
    
    @map_configuration_router.delete("/floor/{floor}",response_model=Operation_Out)
    def Delete_Floor_Map_Configuration(floor:int):
        return {"success":delete_floor_map_configuration(floor)}
    
    @map_configuration_router.delete("/entity/{entity_id}",response_model=Operation_Out)
    def Delete_Entity_Map_Configuration(entity_id:str):
        return {"success":delete_map_entry(entity_id)}
    
    return map_configuration_router

def getVirtualRouter():
    virtual_router=APIRouter(tags=["Virtual"],prefix="/virtual")

    @virtual_router.get("/entity")
    def Get_All_Virtual_Entities():
        file=open("./data/virtual_context.json")
        virtual_context=json.load(file)
        return virtual_context["entities_context"]
    
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


def getHomeRouter():
    home_router=APIRouter(tags=["Home"],prefix="/home")

    @home_router.get("")
    def Get_Home_Context():
        res=getEntities(skip_services=True,only_main=True)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        
        entity_list= res["data"]
        active_entities=0
        current_power_consumption=0

        file = open("./data/entities_consumption_map.json")
        consumption_map=json.load(file)

        for entity in entity_list:
            if entity["state"] in ["on","playing"]:
                active_entities+=1
            domain=entity["entity_id"].split(".")[0]
            if domain not in ["device_tracker"]: #FIXME:fix this patchwork
                current_power_consumption+=consumption_map[domain][entity["state"]]["power_consumption"]

        parser=configparser.ConfigParser()
        parser.read("./data/configuration.txt")
        emissions_factor=parser["ApiConfiguration"]["w_to_gco2"] if 'w_to_gco2' in parser["ApiConfiguration"] else 0
        current_emissions=current_power_consumption*float(emissions_factor)

        return {
            "active_devices":active_entities,
            "power_usage":current_power_consumption,
            "power_usage_unit":"W",
            "emissions":current_emissions,
            "emissions_unit":"gCO2/h"
            }
    
    return home_router
