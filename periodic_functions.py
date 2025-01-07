
import datetime,logging
from datetime import timedelta
from dateutil import tz,parser
from collections import defaultdict




from homeassistant_functions import initializeToken, getDevicesFast
from database_functions import (
    add_hourly_consumption_entry,
    get_all_appliances_usage_entries,add_appliances_usage_entry,
    fetch_one_element,add_device_history_entry,add_entity_history_entry,
    DbPathEnum
    )
from routers.historyRouter import extractSingleDeviceHistory,getEntitiesHistory

logger = logging.getLogger(__name__)


def entitiesHistoryExtractionProcedure(start_timestamp:datetime.datetime=datetime.date.today()):
    start_call=datetime.datetime.now() 
    end_timestamp=datetime.datetime.today().astimezone(tz.tzlocal())
    end_timestamp=end_timestamp.replace(minute=0,second=0)
    #Getting the list of devices
    res=getDevicesFast()
    if res["status_code"]!=200:
        logger.error("getDevicesFast returned "+res["status_code"]+", "+res["data"])
        return
    
    devicesToRemove=["device_tracker","weather","event"]

    entities_list=[]
    for device in res["data"]:
        if device["device_class"] not in devicesToRemove and device["name"]!="Sun":
            entities_list+=[x["entity_id"] for x in device["list_of_entities"]]
    
    history=getEntitiesHistory(entities_list,start_timestamp,end_timestamp)
    history_to_add=[]


    history_to_add = [(
        entity_id,
        parser.parse(history_row["date"],dayfirst=False).astimezone(tz.tzlocal()).timestamp(),
        *list(history_row.values())[1:]
        )
    for entity_id, entity_history in history.items()
    for history_row in entity_history
    ]

    res=add_entity_history_entry(history_to_add)
    if res:
        logger.info(f"Entity History data updated successfully! elapsed time:{(datetime.datetime.now()-start_call).total_seconds()}[s]\n")
    else:
        logger.error("Some error occurred while saving Entity History data, could't update...")


def historyExtractionProcedure(start_timestamp:datetime.datetime=datetime.date.today()): 
    end_timestamp=datetime.datetime.today().astimezone(tz.tzlocal())
    end_timestamp=end_timestamp.replace(minute=0,second=0)
    #Getting the list of devices
    res=getDevicesFast()
    if res["status_code"]!=200:
        logger.error("getDevicesFast returned "+res["status_code"]+", "+res["data"])
        return
    
    devicesToRemove=["sensor","device_tracker","weather","event"]
    devices_list=[x["device_id"] for x in res["data"] if x["device_class"] not in devicesToRemove and x["name"]!='Sun']

    device_history=[]
    for id in devices_list:
        history=extractSingleDeviceHistory(id,start_timestamp,end_timestamp)
        if len(history)==0: #if the device remains not available for long HA will not produce its history 
            continue

        for i in range(len(history)):
            timestamp=parser.parse(history[i]["date"],dayfirst=False).astimezone(tz.tzlocal()).timestamp()
            device_history.append((id,timestamp, *list(history[i].values())[1:]))

    res=add_device_history_entry(device_history)
    if res:
        logger.info("Device History data updated successfully!")
    else:
        logger.error("Some error occurred while saving Device History data, could't update...")

def devicesExtractionProcedure(start_timestamp:datetime.datetime=datetime.date.today()):
    start_call=datetime.datetime.now() 

    end_timestamp=datetime.datetime.today().astimezone(tz.tzlocal())
    end_timestamp=end_timestamp.replace(minute=0,second=0)
    #Getting the list of devices
    res=getDevicesFast()
    if res["status_code"]!=200:
        logger.error("getDevicesFast returned "+res["status_code"]+", "+res["data"])
        return
    
    devicesToRemove=["sensor","device_tracker","weather","event"]
    devices_list=[x["device_id"] for x in res["data"] if x["device_class"] not in devicesToRemove]

    mode_use_dict={}
    hourly_grouping=[]
    device_history=[]

    for id in devices_list:
        history=extractSingleDeviceHistory(id,start_timestamp,end_timestamp)
        if len(history)==0: #if the device remains not available for long HA will not produce its history 
            continue

        #region Extraction of Device history
        for i in range(len(history)):
            timestamp=parser.parse(history[i]["date"],dayfirst=False).astimezone(tz.tzlocal()).timestamp()
            device_history.append((id,timestamp, *list(history[i].values())[1:]))
        #endregion

        #region Conversion of History in hourly consumption data
        starting_date=parser.parse(history[0]["date"],dayfirst=False).astimezone(tz.tzlocal())
        ending_date=parser.parse(history[-1]["date"],dayfirst=False).astimezone(tz.tzlocal())
        energy_unit = history[0]["energy_consumption_unit"]
        temp_date=starting_date
        i=0
        steps=int((ending_date-starting_date).total_seconds()/3600)

        while temp_date<ending_date:
            consumption=sum([x["energy_consumption"] for x in history if x["date"].startswith(temp_date.strftime("%Y-%m-%dT%H"))])
            hourly_grouping.append((
                id,
                consumption,
                energy_unit,
                temp_date.replace(microsecond=0).timestamp(),
                (temp_date+datetime.timedelta(hours=1)).replace(microsecond=0).timestamp()
                ))
            print(f"Consumption History extraction step:{i}/{steps}",end="\r",flush=True)
            i+=1
            temp_date=temp_date+datetime.timedelta(hours=1)
        
        print("\nConsumption History extraction: DONE!")

        #endregion

        #region Computing appliance use datas
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
            print(f"Appliance use data extraction step:{i}/{len(history)}",end="\r",flush=True)

        mode_use_dict[id]=dict(use_map)
        print("\nAppliance use data extraction: DONE!\n")

    temp=[]
    database_data=get_all_appliances_usage_entries()
    for id in mode_use_dict.keys():
        for mode in mode_use_dict[id]:
            index=[i for i in range(len(database_data)) if database_data[i]["device_id"]==id and database_data[i]["state"]==mode]
            if len(index)>0: #the db already has some data about that mode
                database_element=database_data[index[0]]

                if database_element["last_timestamp"]<end_timestamp.replace(microsecond=0).timestamp():
                    old_sum_of_duration=database_element["average_duration"]*database_element["duration_samples"]
                    new_sum_of_duration=mode_use_dict[id][mode]["average_duration"]*mode_use_dict[id][mode]["duration_samples"]
                    duration_samples=mode_use_dict[id][mode]["duration_samples"]+database_element["duration_samples"]
                    new_average_duration=(new_sum_of_duration+old_sum_of_duration)/(duration_samples)

                    old_sum_of_power=database_element["average_power"]*database_element["power_samples"]
                    new_sum_of_power=mode_use_dict[id][mode]["average_power"]*mode_use_dict[id][mode]["power_samples"]
                    power_samples=mode_use_dict[id][mode]["power_samples"]+database_element["power_samples"]
                    new_average_power=(new_sum_of_power+old_sum_of_power)/(power_samples) if power_samples>0 else 0


                    temp.append((
                        id,mode,
                        new_average_duration,mode_use_dict[id][mode]["average_duration_unit"],duration_samples,
                        new_average_power,mode_use_dict[id][mode]["average_power_unit"],power_samples,
                        end_timestamp.replace(microsecond=0).timestamp()
                        ))
            else:
                temp.append((
                    id,mode,
                    mode_use_dict[id][mode]["average_duration"],mode_use_dict[id][mode]["average_duration_unit"],mode_use_dict[id][mode]["duration_samples"],
                    mode_use_dict[id][mode]["average_power"],mode_use_dict[id][mode]["average_power_unit"],mode_use_dict[id][mode]["power_samples"],
                    end_timestamp.replace(microsecond=0).timestamp()
                    ))
    #endregion
    
    #region Updating the database
    res=add_appliances_usage_entry(temp)
    if res:
        logger.info("Appliances usage data updated successfully!")
    else:
        logger.error("Some error occurred while saving appliaces usage data, could't update...")

    res=add_device_history_entry(device_history)
    if res:
        logger.info("Device History data updated successfully!")
    else:
        logger.error("Some error occurred while saving Device History data, could't update...")
    
    res=add_hourly_consumption_entry(hourly_grouping)
    if res:
        logger.info("Hourly consumption data updated successfully!")
    else:
        logger.error("Some error occurred while saving hourly consumption data, could't update...")

    #endregion

    logger.info(f"Updating consumption and use data of {len(devices_list)-1} devices ended, elapsed time:{(datetime.datetime.now()-start_call).total_seconds()}[s]")



def main():
    logging.basicConfig(format='%(levelname)s-%(asctime)s: %(message)s',datefmt='%d/%m/%Y %H:%M:%S',filename='./logs/periodic_functions.log', encoding='utf-8', level=logging.INFO)
    logger.info("Running the script to get hourly appliances consumption and usage time...")

    initializeToken()
    last_timestamp_usage=fetch_one_element(DbPathEnum.CONSUMPTION,"select max(last_timestamp) from Appliances_Usage")
    last_timestamp_consumption=fetch_one_element(DbPathEnum.CONSUMPTION,"select max(start) from Hourly_Consumption")
    last_timestamp_consumption=last_timestamp_consumption["max(start)"]
    last_timestamp_usage=last_timestamp_usage["max(last_timestamp)"]


    if last_timestamp_usage!=None and last_timestamp_consumption!=None:
        starting_date=datetime.datetime.fromtimestamp(min(last_timestamp_usage,last_timestamp_consumption)).astimezone(tz.tzlocal())
        starting_date=starting_date.replace(minute=0,second=0)
    else:
        starting_date=datetime.datetime.combine(datetime.date.today(), datetime.time.min).astimezone(tz.tzlocal())
    devicesExtractionProcedure(start_timestamp=starting_date)

    logger.info("Running the script to get entity history...")
    last_timestamp_entity_history=fetch_one_element(DbPathEnum.ENTITY_HISTORY,"select max(timestamp) from Entity_History")
    if last_timestamp_entity_history["max(timestamp)"]!=None:
        starting_date=datetime.datetime.fromtimestamp(last_timestamp_entity_history["max(timestamp)"]).astimezone(tz.tzlocal())
        starting_date=starting_date.replace(minute=0,second=0)
    else:
        starting_date=datetime.datetime.now()-timedelta(days=10)
        starting_date=starting_date.replace(hour=0,minute=0,second=0)
    entitiesHistoryExtractionProcedure(start_timestamp=starting_date)

if __name__ == "__main__":
    main()