from fastapi import APIRouter,HTTPException
from multiprocessing import Pool

from homeassistant_functions import (
    getEntities,getEntity,
    getServicesByEntity,
    getHistory,getAutomations,
    callService,getDevicesFast,getDevicesNameAndId,
    getSingleDeviceFast,getDeviceId,
    getDeviceInfo,initializeToken)
from database_functions import (
    initialize_database,
    get_all_configuration_values,get_configuration_value_by_key,add_configuration_values,delete_configuration_value,
    add_map_entities, get_all_map_entities,get_map_entity,delete_map_entry,delete_floor_map_configuration,
    get_all_service_logs,add_service_logs,get_service_logs_by_user,
    get_energy_slot_by_day,get_all_energy_slots,add_energy_slots,delete_energy_slots,
    get_total_consumption,get_appliance_usage_entry,
    get_all_user_preferences,add_user_preferences,get_user_preferences_by_user,delete_user_preferences_by_user,
    get_all_energy_slots_with_cost
    )
from schemas import (
    Service_In,Operation_Out,Map_Entity_List,
    Map_Entity,User_Log,User_Log_List,Configuration_Value,
    Configuration_Value_List,Energy_Plan_Calendar,
    User_Preference_List,Automation
    )

import datetime,json,configparser,logging
from dateutil import parser,tz
from dateutil.relativedelta import relativedelta
from collections import defaultdict

logger = logging.getLogger('uvicorn.error')

DAYS=["mon","tue","wed","thu","fri","sat","sun"]

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




def createStateArray(entity_id:str,list:list,start_timestamp:datetime,end_timestamp:datetime,time_delta_min=1)->list:
        power_consumption_factor=time_delta_min/60 
        #supponendo che un dispositivo abbia potenza 1W => consumera' 1 Wh ogni ora 
        #se campiono con un valore piu' basso dell'ora (es 1 minuti) dovro' calcolare che il dispositivo
        #consuma minuti_campionamento/60 di Wh ogni minuti_campionamento
        res=[]
        temp_date=start_timestamp
        start_history=parser.parse(list[0]["last_changed"],)
        while temp_date<start_history:
                res.append({
                #"date":temp_date.strftime("%d/%m/%Y %H:%M:%S"),
                "date":temp_date.strftime("%Y-%m-%dT%H:%M:%S"),
                "state":"unavailable",
                "power":0,
                "unit_of_measurement":"",
                "energy_consumption":0})
                temp_date=temp_date+datetime.timedelta(minutes=time_delta_min)
        for i in range(len(list)-1):
            #temp_date=parser.parse(list[i]["last_changed"],)
            end_block = parser.parse(list[i+1]["last_changed"]).astimezone(tz.tzlocal())
            while temp_date<end_block:
                res.append({
                    #"date":temp_date.strftime("%d/%m/%Y %H:%M:%S"),
                    "date":temp_date.strftime("%Y-%m-%dT%H:%M:%S"),
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
                #"date":temp_date.strftime("%d/%m/%Y %H:%M:%S"),
                "date":temp_date.strftime("%Y-%m-%dT%H:%M:%S"),
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
    for i in range(len(response[device_data["state_entity_id"]]) if response else 0):
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
        if len(entities_states)==0:
            logger.info(f"Get_Entity_History for entities {",".join(entities)} didn't produced any results..skipping...")
            return {}
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
    
    @consumption_router.get("/device")
    def Get_Device_Consumption_Fast(device_id:str="81faa423066ee532f37f15f1897a699d",start_timestamp:datetime.date=datetime.date.today(),end_timestamp:datetime.date=datetime.date.today(),group:str="hourly"):
        start_timestamp=datetime.datetime.combine(start_timestamp, datetime.time.min).astimezone(tz.tzlocal())
        end_timestamp=datetime.datetime.combine(end_timestamp,  datetime.time(23, 59)).astimezone(tz.tzlocal())

        from_ts=int(start_timestamp.replace(microsecond=0).timestamp())
        to_ts=int(end_timestamp.replace(microsecond=0).timestamp())
        return get_total_consumption(from_ts,to_ts,group,device_id)
    
    @consumption_router.get("/total")
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
    def Get_All_Devices(get_only_names:bool=False):
        if get_only_names:
            res=getDevicesNameAndId()
        else:    
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

def getAutomationDetails(automation): #TODO:could be moved outside
    automation_power_drawn=0
    automation_energy_consumption=0
    temp=[]
    action_list=[]
    activation_time=getAutomationTime(automation["trigger"])

    activation_days=[]
    time_condition=[x for x in automation["condition"] if x["condition"]=="time"]
    if len(time_condition)>0:
        activation_days=time_condition[0]["weekday"] #we assume only one time trigger
    for action in automation["action"]:
        if action.get("device_id")!=None:
            #if contains "device_id" then it is an action on device, the "type" field represent the service
            service=action["type"]
            device_id=action["device_id"]
            temp.append((device_id,service))
        if action.get("service")!=None:
            #if contains "service" then is a service type of action, target->entity_id/device_id is the recipient 
            # while "service" is the service
            service=action["service"].split(".")[1]
            #some actions (like notify) don't have target in that case we assume no action
            if action.get("target"): 
                if action["target"].get("entity_id"):
                    #some cases the target is a list in others is a single value
                    if type(action["target"].get("entity_id")) is list:
                        for entity_id in action["target"]["entity_id"]:
                            device_id=getDeviceId(entity_id)
                            temp.append((device_id,service))
                    else:
                        temp.append((getDeviceId(action["target"].get("entity_id")),service))
                if action["target"].get("device_id"):
                    #some cases the target is a list in others is a single value
                    if type(action["target"].get("device_id")) is list:
                        for device in action["target"]["device_id"]:
                            temp.append((device,service))
                    else:
                        temp.append((action["target"].get("device_id"),service))

    with open("./data/devices_new_state_map.json") as file:
        state_map=json.load(file)
        for action in temp:
            device_id=action[0]
            service=action[1]
            state=state_map[service]
            device_info=getDeviceInfo(device_id)
            device_name=device_info["name_by_user"] if device_info["name_by_user"]!="None" else device_info["name"]
            if state not in ["on|off","same"]:#TODO:manage also this cases
                usage_data=get_appliance_usage_entry(device_id,state)
                usage_data.update({
                    "device_id":device_id,"state":state,"service":service,"device_name":device_name
                })
                automation_power_drawn+=usage_data["average_power"]
                automation_energy_consumption+=usage_data["average_power"]*(usage_data["average_duration"]/60) #Remember that use time is express in minutes
                action_list.append(usage_data)
            else:
                action_list.append({"device_id":device_id,"state":state,"service":service,"device_name":device_name})

    

    return {"id":automation["id"],
        "description":automation["description"],
        "trigger":automation["trigger"],
        "condition":automation["condition"],
        "name":automation["alias"],
        "time":activation_time,
        "days":activation_days,
        "action":action_list,
        "power_drawn":automation_power_drawn,
        "energy_consumption":automation_energy_consumption
        }

def getAutomationTime(trigger): #TODO:could be moved outside
    activation_time=""

    time_trigger=[x for x in trigger if x["platform"]=="time"]
    if len(time_trigger)>0:
        activation_time=time_trigger[0]["at"] #we assume only one time trigger

    sun_trigger=[x for x in trigger if x["platform"]=="sun"]
    if len(sun_trigger)>0:
        resp=getEntity("sun.sun")
        if resp["status_code"]==200:
            sun=resp["data"]
            event=sun_trigger[0]["event"]
            offset=sun_trigger[0].get("offset")

            if event=="sunset":
                time_attr=sun["attributes"]["next_setting"]

            if event=="sunrise":
                time_attr=sun["attributes"]["next_dawn"]
            
            sun_time=parser.parse(time_attr).astimezone(tz.tzlocal())

            sign=1
            if offset:
                if offset[0]=="-":
                    sign=-1
                    offset=offset[1:]

                if ":" in offset: #if contains : then it's in HH:MM:SS format
                    splits=offset.split(":")
                    hours=int(splits[0])
                    minutes=int(splits[1])
                    seconds=int(splits[2])
                    total_offset_sec=hours*3600+minutes*60+seconds
                    sun_time=sun_time+sign*datetime.timedelta(seconds=total_offset_sec)
                
                else: #else it's an offset in seconds
                    sun_time=sun_time+sign*datetime.timedelta(seconds=int(offset))
            activation_time=sun_time.strftime("%H:%M:%S")

    return activation_time

def getEnergyCostMatrix():#TODO:could be moved outside
    cost_array=get_all_energy_slots_with_cost() 
    cost_matrix={}
    for day in DAYS:
        slots=[x for x in cost_array if x["day"]==day]
        temp=[0.0]*1440
        for i in range(1440):
            index=i//60 #index in slots
            temp[i]=float(slots[index]["slot_value"])
        cost_matrix[day]=temp
    return cost_matrix

def getPowerMatrix(automation):#TODO:could be moved outside

    power_matrix = {day: [0] * 1440 for day in DAYS}  

    if automation["time"]!="":
        activation_time=parser.parse(automation["time"])
        activation_days=automation["days"] if len(automation["days"])>0 else DAYS
        activation_index=activation_time.hour*60+activation_time.minute
        for act in automation["action"]:
            end_index=min(activation_index+int(act["average_duration"]),1440)
            for day in activation_days:
                for i in range(activation_index, end_index):
                    power_matrix[day][i]+=act["average_power"]
    return power_matrix


def getAutomationCost(automation):
    automation=getAutomationDetails(automation)
    energy_cost_matrix=getEnergyCostMatrix()
    power_matrix=getPowerMatrix(automation)
    cost_matrix={day: 0.0 for day in DAYS}  
    for day in DAYS:
        for i in range(1440):
            #power is in W so we need to divide by 1000 to get kW
            #energy_cost is in euro/kWh
            #we are computing the cost of 1 minute =>1/60 kWh each minute
            cost_matrix[day]+=(power_matrix[day][i]/1000)*(energy_cost_matrix[day][i])*(1/60)

    return cost_matrix






def getAutomationRouter():
    automation_router=APIRouter(tags=["Automation"],prefix="/automation")

    @automation_router.get("")
    def Get_Automations():
        res=getAutomations()
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        else:
            automations_list=res["data"]
            file = open("./data/devices_new_state_map.json")
            state_map=json.load(file)
            ret=[]
            for automation in automations_list:
                automation_power_drawn=0
                automation_energy_consumption=0
                temp=[]
                action_list=[]
                activation_days=[]
                #time_trigger=[x for x in automation["trigger"] if x["platform"]=="time"]
                #if len(time_trigger)>0:
                #    activation_time=time_trigger[0]["at"] #we assume only one time trigger

                activation_time=getAutomationTime(automation["trigger"])
                time_condition=[x for x in automation["condition"] if x["condition"]=="time"]
                if len(time_condition)>0:
                    activation_days=time_condition[0]["weekday"] #we assume only one time trigger
                for action in automation["action"]:
                    if action.get("device_id")!=None:
                        #if contains "device_id" then it is an action on device, the "type" field represent the service
                        service=action["type"]
                        device_id=action["device_id"]
                        temp.append((device_id,service))
                    if action.get("service")!=None:
                        #if contains "service" then is a service type of action, target->entity_id/device_id is the recipient 
                        # while "service" is the service
                        service=action["service"].split(".")[1]
                        #some actions (like notify) don't have target in that case we assume no action
                        if action.get("target"): 
                            if action["target"].get("entity_id"):
                                #some cases the target is a list in others is a single value
                                if type(action["target"].get("entity_id")) is list:
                                    for entity_id in action["target"]["entity_id"]:
                                        device_id=getDeviceId(entity_id)
                                        temp.append((device_id,service))
                                else:
                                    temp.append((getDeviceId(action["target"].get("entity_id")),service))
                            if action["target"].get("device_id"):
                                #some cases the target is a list in others is a single value
                                if type(action["target"].get("device_id")) is list:
                                    for device in action["target"]["device_id"]:
                                        temp.append((device,service))
                                else:
                                    temp.append((action["target"].get("device_id"),service))
                for action in temp:
                    device_id=action[0]
                    service=action[1]
                    state=state_map[service]
                    device_info=getDeviceInfo(device_id)
                    device_name=device_info["name_by_user"] if device_info["name_by_user"]!="None" else device_info["name"]
                    if state not in ["on|off","same"]:#TODO:manage also this cases
                        usage_data=get_appliance_usage_entry(device_id,state)
                        usage_data.update({
                            "device_id":device_id,"state":state,"service":service,"device_name":device_name
                        })
                        automation_power_drawn+=usage_data["average_power"]
                        automation_energy_consumption+=usage_data["average_power"]*(usage_data["average_duration"]/60) #Remember that use time is express in minutes
                        action_list.append(usage_data)
                    else:
                        action_list.append({"device_id":device_id,"state":state,"service":service,"device_name":device_name})

                

                ret.append({
                    "id":automation["id"],
                    "description":automation["description"],
                    "trigger":automation["trigger"],
                    "condition":automation["condition"],
                    "name":automation["alias"],
                    "time":activation_time,
                    "days":activation_days,
                    "action":action_list,
                    "power_drawn":automation_power_drawn,
                    "energy_consumption":automation_energy_consumption
                    })
        return ret
    
    @automation_router.get("/matrix")
    def Get_State_Matrix():
        ret = Get_Automations()
        dev_list=getDevicesFast()
        state_matrix={}
        for dev in dev_list["data"]:
            if dev["device_class"] not in ["sensor","event","sun","weather","device_tracker"]:
                state_matrix[dev["device_id"]]={
                    "state_list":[""]*1440,
                    "power_list":[0]*1440,
                    "device_id":dev["device_id"],
                    "device_name":dev["name"]
                }
        ret=sorted(ret,key=lambda x:x["time"])
        for aut in ret:
            if aut["time"]!="":
                activation_time=parser.parse(aut["time"])
                activation_index=activation_time.hour*60+activation_time.minute
                for act in aut["action"]:
                    end_index=min(activation_index+int(act["average_duration"]),1440)
                    state_matrix[act["device_id"]]["state_list"][activation_index:end_index]=[act["state"]]*(end_index-activation_index)
                    state_matrix[act["device_id"]]["power_list"][activation_index:end_index]=[act["average_power"]]*(end_index-activation_index)
                    state_matrix[act["device_id"]]["device_id"]=act["device_id"]
                    state_matrix[act["device_id"]]["device_name"]=act["device_name"]

        return dict(state_matrix)
    
    
    @automation_router.post("/simulate")
    def Simulate_Automation_Addition(automation:Automation):
        #Get automations saved and details of the one we want to add
        automation=getAutomationDetails(automation.automation)
        ret = Get_Automations()
        ret.append(automation)

        dev_list=getDevicesFast()
        week_days=[
				"mon",
				"tue",
				"wed",
				"thu",
				"fri",
				"sat",
                "sun"
			]
        state_matrix = {day: {} for day in week_days}

        for day in week_days:
            for dev in dev_list["data"]:
                if dev["device_class"] not in ["sensor","event","sun","weather","device_tracker"]:
                    state_matrix[day][dev["device_id"]] = {
                            "state_list": [""] * 1440,
                            "power_list": [0] * 1440,
                            "device_id": dev["device_id"],
                            "device_name": dev["name"]
                        }


        ret=sorted(ret,key=lambda x:x["time"])

        for aut in ret:
            if aut["time"]!="":
                activation_time=parser.parse(aut["time"])
                activation_days=aut["days"] if len(aut["days"])>0 else week_days
                activation_index=activation_time.hour*60+activation_time.minute

                for act in aut["action"]:
                    end_index=min(activation_index+int(act["average_duration"]),1440)
                    for day in activation_days:
                        device = state_matrix[day][act["device_id"]]
                        device["state_list"][activation_index:end_index]=[act["state"]]*(end_index-activation_index)
                        device["state_list"][end_index:]=[""]*(1440-end_index) #Added to fix a bug, could be removed if problems occurs
                        device["power_list"][activation_index:end_index]=[act["average_power"]]*(end_index-activation_index)

                        device["device_id"]=act["device_id"]
                        device["device_name"]=act["device_name"]

        cumulative_power_matrix = {day: [0] * 1440 for day in week_days}  

        for day in week_days:
            for dev in state_matrix[day].values():
                for i in range(1440):
                    cumulative_power_matrix[day][i]+=dev["power_list"][i]

        conflicts_list = defaultdict(lambda: {"type": "Excessive energy demand", "days": []})
        threshold = get_configuration_value_by_key("power_threshold")  
        if threshold:
            threshold=float(threshold["value"])
        else:
            threshold=150 #TODO: remember to remove this default

        for day in week_days:
            conflict_is_occurring=False

            for i in range(1440):
                if cumulative_power_matrix[day][i] > threshold: 
                    if not conflict_is_occurring:
                        start=i
                        conflict_is_occurring=True
                    end=i
                else:
                    if conflict_is_occurring: #there was a conflict since last minute
                        key=f"{start//60:02}:{(start%60):02}-{end//60:02}:{(end%60):02}"
                        conflicts_list[key]["days"].append(day)
                        conflicts_list[key]["start"] = f"{start // 60:02}:{start % 60:02}"
                        conflicts_list[key]["end"] = f"{end // 60:02}:{end % 60:02}"
                        conflict_is_occurring=False

        


        return {
            "state_matrix":state_matrix,
            "cumulative_power_matrix":cumulative_power_matrix,
            "conflicts":list(conflicts_list.values())
            }
    
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

def getUserRouter():
    user_router=APIRouter(tags=["User"],prefix="/user")

    @user_router.get("/preferences")
    def Get_All_Preferences():
        preferences=get_all_user_preferences()
        res=[]
        for user in preferences:
            res.append({"user_id":user["user_id"],"preferences":user["preferences"].split(","),"data_collection":bool(user["data_collection"]),"data_disclosure":bool(user["data_disclosure"])})
        return res
    
    @user_router.get("/preferences/{user_id}")
    def Get_Preferences_Of_Single_User(user_id:str):
        user= get_user_preferences_by_user(user_id)
        return {"user_id":user["user_id"],"preferences":user["preferences"].split(","),"data_collection":bool(user["data_collection"]),"data_disclosure":bool(user["data_disclosure"])} if user else {}
    
    @user_router.put("/preferences",response_model=Operation_Out)
    def Add_User_Preferences(preferences_list:User_Preference_List):
        to_add=[]
        for user in preferences_list.data:
            to_add.append((user.user_id,','.join(user.preferences),user.data_collection,user.data_disclosure))
        return {"success":add_user_preferences(to_add)}
    
    @user_router.delete("/preference/{user_id}",response_model=Operation_Out)
    def Delete_User_Preferences(user_id:str):
        return {"success":delete_user_preferences_by_user(user_id)}

    
    return user_router


def main():
    initializeToken()
    list_auto=getAutomations()
    cost_matrix=getAutomationCost(list_auto["data"][1])

if __name__ == "__main__":
    main()