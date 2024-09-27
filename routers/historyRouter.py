from fastapi import APIRouter,HTTPException
import datetime,logging
from dateutil import parser,tz
from multiprocessing import Pool

from homeassistant_functions import(
    getSingleDeviceFast,getHistory
)

from routers.consumptionRouter import createStateArray


logger = logging.getLogger('uvicorn.error')




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