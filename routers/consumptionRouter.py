from fastapi import APIRouter,HTTPException
from multiprocessing import Pool
import datetime,logging
from dateutil import parser,tz
from dateutil.relativedelta import relativedelta
from collections import defaultdict

from homeassistant_functions import (
    getHistory)
from database_functions import (
    get_total_consumption
    )

ACTIVE_MODES = ["on", "playing"]
DEFAULT_ENERGY_UNIT = "Wh"
STATE_ARRAY_DATE_FORMAT="%Y-%m-%dT%H:%M:%S"

logger = logging.getLogger('uvicorn.error')

def computeTotalConsumption(block_list:list,day:datetime.date,date_format:str,device_class="")->list:
        sum=0
        use_time=0
        energy_consumption_unit="Wh"

        if len(block_list)>0:
            energy_consumption_unit=block_list[0].get("unit_of_measurement", DEFAULT_ENERGY_UNIT)
            if device_class=="energy":
                try:
                    sum=float(block_list[-1]["state"])-float(block_list[0]["state"])
                except ValueError:
                    sum=0
            else:
                end_day=datetime.datetime.combine(day+datetime.timedelta(days=1), datetime.time.min).astimezone(tz.tzlocal())
                for i in range(len(block_list)-1):
                    start_block=parser.parse(block_list[i]["last_changed"]).astimezone(tz.tzlocal())
                    end_block=parser.parse(block_list[i+1]["last_changed"]).astimezone(tz.tzlocal())

                    if end_block> end_day: #se la fine del blocco supera la giornata odierna taglio il blocco ad day+1
                        end_block=end_day
                        
                    delta=(end_block-start_block).total_seconds() #calcolo la durata dell'intervallo
                    if block_list[i]["state"] in ACTIVE_MODES:
                        use_time=use_time+delta/60

                    delta=delta/3600 #lo converto in ore
                    sum=sum+block_list[i]["power_consumption"]*delta #calcolo il kWh spesi
        return {"energy_consumption":sum,"energy_consumption_unit":energy_consumption_unit,"use_time":use_time,"use_time_unit":"min","date":day.strftime(date_format)}
 

def createStateArray(entity_id:str,history_list:list,start_timestamp:datetime,end_timestamp:datetime,time_delta_min=1)->list:
        power_consumption_factor=time_delta_min/60 
        #supponendo che un dispositivo abbia potenza 1W => consumera' 1 Wh ogni ora 
        #se campiono con un valore piu' basso dell'ora (es 1 minuti) dovro' calcolare che il dispositivo
        #consuma minuti_campionamento/60 di Wh ogni minuti_campionamento
        res=[]
        temp_date=start_timestamp
        start_history=parser.parse(history_list[0]["last_changed"],)
        while temp_date<start_history:
                res.append({
                "date":temp_date.strftime(STATE_ARRAY_DATE_FORMAT),
                "state":"unavailable",
                "power":0,
                "unit_of_measurement":"",
                "energy_consumption":0})
                temp_date=temp_date+datetime.timedelta(minutes=time_delta_min)
                
        for i in range(len(history_list)-1):
            end_block = parser.parse(history_list[i+1]["last_changed"]).astimezone(tz.tzlocal())
            while temp_date<end_block:
                res.append(formatStateArrayBlock(temp_date,history_list[i],power_consumption_factor))
                temp_date=temp_date+datetime.timedelta(minutes=time_delta_min)
                
        #estendo l'ultimo blocco fino alla fine dell'intervallo richiesto in quanto home assistant fornisce solo i blocchi con dei cambi
        #per cui se per esempio l'ultimo cambio è avvenuto alle 22 l'ultimo blocco riporterà quell'ora e non le 23:59 per cui devo io estendere
        #manualmente lo stato fino alla fine dell'intervallo richiesto
        while temp_date<end_timestamp:
            res.append(formatStateArrayBlock(temp_date,history_list[-1],power_consumption_factor))
            temp_date=temp_date+datetime.timedelta(minutes=time_delta_min)

        return {entity_id:res}

def formatStateArrayBlock(block_date,block,power_consumption_factor):
    return {
            "date":block_date.strftime(STATE_ARRAY_DATE_FORMAT),
            "state":block["state"],
            "power":block["power_consumption"],
            "unit_of_measurement":block["unit_of_measurement"],
            "energy_consumption":block["power_consumption"]*power_consumption_factor
            }

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