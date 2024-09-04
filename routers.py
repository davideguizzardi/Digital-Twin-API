from fastapi import APIRouter,HTTPException
from multiprocessing import Pool

from homeassistant_functions import getEntities,getEntity,getServicesByEntity,getHistory,getAutomations,callService,getDevices,getDevicesFast,getSingleDeviceFast
from database_functions import (
    initialize_database,
    get_all_configuration_values,get_configuration_value_by_key,add_configuration_values,delete_configuration_value,
    add_map_entities, get_all_map_entities,get_map_entity,delete_map_entry,delete_floor_map_configuration,
    get_all_service_logs,add_service_logs,get_service_logs_by_user,
    get_energy_slot_by_day,get_all_energy_slots,add_energy_slots,delete_energy_slots,
    get_total_consumption
    )
from schemas import (
    Service_In,Operation_Out,Map_Entity_List,
    Map_Entity,User_Log,User_Log_List,Configuration_Value,
    Configuration_Value_List,Energy_Plan_Calendar)

import datetime,json,configparser,logging
from dateutil import parser,tz
from dateutil.relativedelta import relativedelta
from collections import defaultdict

logger = logging.getLogger('uvicorn.error')


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




def createStateArray(entity_id:str,list:list,start_timestamp:datetime,end_timestamp:datetime,time_delta_min=1)->list:
        power_consumption_factor=time_delta_min/60 
        #supponendo che un dispositivo abbia potenza 1W => consumera' 1 Wh ogni ora 
        #se campiono con un valore piu' basso dell'ora (es 1 minuti) dovro' calcolare che il dispositivo
        #consuma minuti_campionamento/60 di Wh ogni minuti_campionamento
        res=[]
        temp_date=start_timestamp
        temp_date=parser.parse(list[0]["last_changed"],)
        for i in range(len(list)-1):
            #temp_date=parser.parse(list[i]["last_changed"],)
            end_block = parser.parse(list[i+1]["last_changed"]).astimezone(tz.tzlocal())
            while temp_date<end_block:
                res.append({
                    "date":temp_date.strftime("%d/%m/%Y %H:%M:%S"),
                    "state":list[i]["state"],
                    "power":list[i]["power_consumption"],
                    "unit_of_measurement":list[i]["unit_of_measurement"],
                    "energy_consumption":list[i]["power_consumption"]*power_consumption_factor})
                temp_date=temp_date+datetime.timedelta(minutes=time_delta_min)
        #estendo l'ultimo blocco fino alla fine dell'intervallo richiesto in quanto home assistant fornisce solo i blocchi con dei cambi
        #per cui se per esempio l'ultimo cambio è avvenuto alle 22 l'ultimo blocco riporterà quell'ora e non le 23:59 per cui devo io estendere
        #manualmente lo stato fino alla fine dell'intervallo richiesto
        while temp_date<end_timestamp:
            res.append({
                "date":temp_date.strftime("%d/%m/%Y %H:%M:%S"),
                "state":list[-1]["state"],
                "power":list[-1]["power_consumption"],
                "unit_of_measurement":list[-1]["unit_of_measurement"],
                "energy_consumption":list[-1]["power_consumption"]*power_consumption_factor})
            temp_date=temp_date+datetime.timedelta(minutes=time_delta_min)
        return {entity_id:res}

def computeHourlyTotalConsumption(entity_id,states,start_timestamp,end_timestamp):
    #if the entity is of type energy i use a fast procedure 
    if states[0]["attributes"].get("device_class")=="energy":
        return energyClassHourlyPowerConsumption(entity_id,states,start_timestamp,end_timestamp)
    
    state_array=createStateArray(entity_id,states,start_timestamp,end_timestamp)[entity_id]
    res=defaultdict(lambda: {"energy_consumption":0,"energy_consumption_unit":"Wh"})
    for state in state_array:
        date=datetime.datetime.strptime(state["date"],"%d/%m/%Y %H:%M:%S")
        key=date.strftime("%d/%m/%Y %H-")+(date+datetime.timedelta(hours=1)).strftime("%H") #es 10/07/2024 00-01
        res[key]["energy_consumption"]+=state["energy_consumption"]
        res[key]["date"]=key
    return {entity_id:list(dict(res).values())}

def energyClassHourlyPowerConsumption(entity_id,states,start_timestamp,end_timestamp):
    state_array=createStateArray(entity_id,states,start_timestamp,end_timestamp,time_delta_min=60)[entity_id]
    res=[]
    for i in range(len(state_array)-1):
        date=datetime.datetime.strptime(state_array[i]["date"],"%d/%m/%Y %H:%M:%S")
        key=date.strftime("%d/%m/%Y %H-")+(date+datetime.timedelta(hours=1)).strftime("%H")
        try:
            consumption=float(state_array[i+1]["state"])-float(state_array[i]["state"])
        except ValueError:
            consumption=0
        res.append({"date":key,"energy_consumption":consumption,"energy_consumption_unit":state_array[i]["unit_of_measurement"]})
    return {entity_id:res}

def computeTotalConsumption(list:list,day:datetime.date,date_format:str,device_class="")->list:
        sum=0
        use_time=0
        energy_consumption_unit="Wh"

        if len(list)>0:
            energy_consumption_unit=list[0]["unit_of_measurement"]
            if device_class=="energy":
                try:
                    sum=float(list[-1]["state"])-float(list[0]["state"])
                except ValueError:
                    sum=0
            else:
                end_day=datetime.datetime.combine(day+datetime.timedelta(days=1), datetime.time.min).astimezone(tz.tzlocal())
                active_modes=["on","playing"]
                for i in range(len(list)-1):
                    start_block=parser.parse(list[i]["last_changed"]).astimezone(tz.tzlocal())
                    end_block=parser.parse(list[i+1]["last_changed"]).astimezone(tz.tzlocal())
                    if end_block> end_day: #se la fine del blocco supera la giornata odierna taglio il blocco ad day+1
                        end_block=end_day
                    delta=(end_block-start_block).total_seconds() #calcolo la durata dell'intervallo
                    if list[i]["state"] in active_modes:
                        use_time=use_time+delta/60
                    delta=delta/3600 #lo converto in ore
                    sum=sum+list[i]["power_consumption"]*delta #calcolo il kWh spesi
        return {"energy_consumption":sum,"energy_consumption_unit":energy_consumption_unit,"use_time":use_time,"use_time_unit":"min","date":day.strftime(date_format)}
        

        


def getHistoryRouter():
    history_router=APIRouter(tags=["History"],prefix="/history")

    @history_router.get("/daily")
    def Get_Entity_History(entities:str,start_timestamp:datetime.datetime=datetime.date.today(),end_timestamp:datetime.datetime|None=None):
        if end_timestamp==None:
            end_timestamp=start_timestamp+datetime.timedelta(days=1)
        return getEntitiesHistory(entities, start_timestamp,end_timestamp)

    @history_router.get("/device/{device_id}")
    def Get_Device_History(device_id:str,start_timestamp:datetime.datetime=datetime.date.today(),end_timestamp:datetime.datetime|None=None):
        if end_timestamp==None:
            end_timestamp=start_timestamp+datetime.timedelta(days=1)
        return extractSingleDeviceHistory(device_id, start_timestamp,end_timestamp)
    
    @history_router.get("/test/{device_id}") #TODO:remove
    def Get_Hourly_stats(device_id:str,start_timestamp:datetime.datetime=datetime.date.today()):
        history=Get_Device_History(device_id,start_timestamp)
        use_map=defaultdict(lambda:{"average_duration":0,"average_duration_unit":"min","average_power":0,"average_power_unit":"W","power_samples":0,"duration_samples":0})
        prev_state=history[0]["state"]
        current_duration=1
        for i in range(len(history)):
            x=history[i]
            x["state"]="off" if x["power"]<2 else x["state"]
            key= x["state"]
            use_map[key]["average_power"]=((use_map[key]["average_power"]*use_map[key]["power_samples"])+x["power"])/(use_map[key]["power_samples"]+1)
            use_map[key]["power_samples"]+=1
            
            if x["state"]==prev_state:#current block is still going
                current_duration+=1
            if x["state"]!=prev_state or i==len(history)-1: #current block is over or we reached the end of the day
                use_map[prev_state]["average_duration"]=((use_map[prev_state]["average_duration"]*use_map[prev_state]["duration_samples"])+current_duration)/(use_map[prev_state]["duration_samples"]+1)
                use_map[prev_state]["duration_samples"]+=1
                current_duration=1
                prev_state=x["state"]

        return {device_id:use_map}
        
    return history_router


def extractSingleDeviceHistory(device_id, start_timestamp,end_timestamp):
    start_program=datetime.datetime.now()

    device_data=getSingleDeviceFast(device_id)["data"]
    state_entity_id=device_data["state_entity_id"]
    power_entity_id=device_data["power_entity_id"]

    entities_list=state_entity_id
    if power_entity_id!="":
        entities_list=entities_list+","+power_entity_id


    response=getEntitiesHistory(entities_list,start_timestamp,end_timestamp)
    temp=[]
    for i in range(len(response[device_data["state_entity_id"]])):
        if power_entity_id!="":
            power=float(response[power_entity_id][i]["state"]) if response[power_entity_id][i]["state"]!="unavailable" else 0
            power_unit=response[power_entity_id][i]["unit_of_measurement"]
            energy_consumption=response[power_entity_id][i]["energy_consumption"]
            energy_consumption_unit=response[power_entity_id][i]["unit_of_measurement"]+"h"
        else:
            power=response[state_entity_id][i]["power"]
            power_unit="W"
            energy_consumption=response[state_entity_id][i]["energy_consumption"]
            energy_consumption_unit="Wh"

        temp.append({
            "date": response[state_entity_id][i]["date"],
            "state": response[state_entity_id][i]["state"], #preso dall'entita stato 
            "power": power,
            "power_unit":power_unit,
            "energy_consumption": energy_consumption,
            "energy_consumption_unit":energy_consumption_unit
        })
    logger.debug(f"Get_Device_History for device: {device_data["name"]} ({device_id}) elapsed_time={(datetime.datetime.now()-start_program).total_seconds()}[s]")
    return temp

def getEntitiesHistory(entities, start_timestamp,end_timestamp):
    start_program=datetime.datetime.now()
    start_timestamp=start_timestamp.astimezone(tz.tzlocal())
    end_timestamp=end_timestamp.astimezone(tz.tzlocal())
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
        logger.debug(f"Get_Entity_History for {len(entities.split(","))} entities, time_range={(end_timestamp-start_timestamp).days} days      elapsed_time={(datetime.datetime.now()-start_program).total_seconds()}[s]")
        return res


def getConsumptionRouter():
    consumption_router=APIRouter(tags=["Consumption"],prefix="/consumption")

    @consumption_router.get("/entity")
    def Get_Entities_Consumption(entities:str,start_timestamp:datetime.date=datetime.date.today(),end_timestamp:datetime.date=datetime.date.today(),group:str="hourly"):
        start_call=datetime.datetime.now()
        start_timestamp=datetime.datetime.combine(start_timestamp, datetime.time.min).astimezone(tz.tzlocal())
        end_timestamp=datetime.datetime.combine(end_timestamp,  datetime.time(23, 59)).astimezone(tz.tzlocal())

        if end_timestamp>datetime.datetime.now(tz.tzlocal()):
            end_timestamp=datetime.datetime.now(tz.tzlocal())

        response=getHistory(entities_id=entities,start_timestamp=start_timestamp,end_timestamp=end_timestamp)
        if response["status_code"]!=200:
            raise HTTPException(status_code=response["status_code"],detail=response["data"])
        
        if not response["data"]:
            raise HTTPException(status_code=404,detail="Data not found")
        
        entities_states=response["data"]
        res={}

        if group.lower()=="hourly":
            res_pool={}
            with Pool(len(entities_states)) as pool:
                args=[(entity_id,entities_states[entity_id],start_timestamp,end_timestamp) for entity_id in entities_states]
                res_pool=pool.starmap(computeHourlyTotalConsumption,args)
            for el in res_pool:
                res.update(el)

        elif group.lower()=="daily":         
            delta=(end_timestamp-start_timestamp).days
            for id in entities_states:
                device_class=entities_states[id][0]["attributes"].get("device_class")
                temp_date=start_timestamp
                temp=[]
                for i in range(delta+1):                   
                    temp_list=[x for x in entities_states[id] if x["last_changed"].startswith(temp_date.strftime("%Y-%m-%d"))]
                    temp.append(computeTotalConsumption(temp_list,temp_date,date_format="%d/%m/%Y",device_class=device_class))
                    temp_date=temp_date+datetime.timedelta(days=1)
                res[id]=temp

        elif group.lower()=="monthly":
            delta =(end_timestamp.year - start_timestamp.year) * 12 + end_timestamp.month - start_timestamp.month
            for id in entities_states:
                device_class=entities_states[id][0]["attributes"].get("device_class")
                temp_date=start_timestamp
                temp=[]
                for i in range(delta+1):                
                    temp_list=[x for x in entities_states[id] if x["last_changed"].startswith(temp_date.strftime("%Y-%m"))]
                    temp.append(computeTotalConsumption(temp_list,temp_date,date_format="%m/%Y",device_class=device_class))
                    temp_date=temp_date+relativedelta(months=+1)
                res[id]=temp
        
        elif group.lower()=="entity":
            temp_date=start_timestamp
            temp=[]
            for id in entities_states:
                element=computeTotalConsumption(entities_states[id],end_timestamp,date_format="%d/%m/%Y")
                element["entity"]=id
                temp.append(element)
            return temp
        
        logger.debug(f"Get_Entities_Consumption for {len(entities.split(","))} entities, time_range={(end_timestamp-start_timestamp).days} days, split={group}      elapsed_time={(datetime.datetime.now()-start_call).total_seconds()}[s]")
        return res
        
    @consumption_router.get("/total") #TODO:remove
    def Get_Total_Consumption(start_timestamp:datetime.date=datetime.date.today(),end_timestamp:datetime.date=datetime.date.today(),group:str="hourly"):
        start_call=datetime.datetime.now() #used for debug purposes

        ## Getting the list of all the entities of the house
        res=getDevicesFast()
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        
        ## Filtering only those entities that could produce some consumption data
        domainsToRemove=["sensor","device_tracker","event","button","weather","forecast"] #domains of entities that could not consume energy
        entities_list=[x["energy_entity_id"] for x in res["data"] if x["device_class"]not in domainsToRemove]
        entities_list=",".join(entities_list)

        ## Producing consumption of each entitiy grouped by the value of group 
        consumption_history=Get_Entities_Consumption(entities_list,start_timestamp,end_timestamp,group)
        if group=="entity":
            return sorted(consumption_history,key=lambda x: x['energy_consumption'],reverse=True)
        
        result=defaultdict(lambda:{"energy_consumption":0,"energy_consumption_unit":"Wh"})

        ## Merging all the values together
        for key1 in consumption_history.keys():
            for element in consumption_history[key1]:
                result[element["date"]]["energy_consumption"]+=element["energy_consumption"]
                result[element["date"]]["date"]=element["date"]

        logger.debug(f"Get_Total_Consumption for {len(entities_list.split(","))} entities, time_range={(end_timestamp-start_timestamp).days} days, split={group}      elapsed_time={(datetime.datetime.now()-start_call).total_seconds()}[s]")
        return sorted(list(dict(result).values()),key=lambda x: x["date"])
    
    @consumption_router.get("/device/fast")
    def Get_Device_Consumption_Fast(device_id:str,start_timestamp:datetime.date=datetime.date.today(),end_timestamp:datetime.date=datetime.date.today(),group:str="hourly"):
        start_timestamp=datetime.datetime.combine(start_timestamp, datetime.time.min).astimezone(tz.tzlocal())
        end_timestamp=datetime.datetime.combine(end_timestamp,  datetime.time(23, 59)).astimezone(tz.tzlocal())

        from_ts=int(start_timestamp.replace(microsecond=0).timestamp())
        to_ts=int(end_timestamp.replace(microsecond=0).timestamp())
        return get_total_consumption(from_ts,to_ts,group,device_id)
    
    @consumption_router.get("/total/fast")
    def Get_Total_Consumption_Fast(start_timestamp:datetime.date=datetime.date.today(),end_timestamp:datetime.date=datetime.date.today(),group:str="hourly"):
        start_timestamp=datetime.datetime.combine(start_timestamp, datetime.time.min).astimezone(tz.tzlocal())
        end_timestamp=datetime.datetime.combine(end_timestamp,  datetime.time(23, 59)).astimezone(tz.tzlocal())

        from_ts=int(start_timestamp.replace(microsecond=0).timestamp())
        to_ts=int(end_timestamp.replace(microsecond=0).timestamp())
        return get_total_consumption(from_ts,to_ts,group)
    return consumption_router




def getDeviceRouter():
    device_router=APIRouter(tags=["Device"],prefix="/device")
    @device_router.get("")
    def Get_All_Devices(skip_services:bool):
        res=getDevicesFast()
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]
    
    @device_router.get("/{device_id}")
    def Get_Single_Device(device_id:str):
        res=getSingleDeviceFast(device_id=device_id)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        return res["data"]

    
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
        res=getEntities(skip_services=True)
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

def getTestRouter():
    test_router=APIRouter(tags=["Test"],prefix="/test")


    @test_router.post("/simulate")
    def Simulate_Automation(automation_in:str):
        automation=json.loads(automation_in)
        power_increase=0
        for action in automation['action']:
            if action["type"]:#device action
                service=action["domain"]+"."+action["type"]
                device_data=getSingleDeviceFast(action["device_id"])

                if action["type"]=="turn_on":
                    return False
    
    return test_router


