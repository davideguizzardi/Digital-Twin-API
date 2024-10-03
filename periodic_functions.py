import logging
import datetime

from homeassistant_functions import getEntities,getHistory,initializeToken
from homeassistant_functions import getDevicesFast
from database_functions import (
    add_daily_consumption_entry,add_hourly_consumption_entry,
    get_all_appliances_usage_entries,add_appliances_usage_entry,
    fetch_one_element)
from routers_old import computeHourlyTotalConsumption,computeTotalConsumption,extractSingleDeviceHistory
from dateutil import tz,parser
from collections import defaultdict

logger = logging.getLogger(__name__)

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
    daily_grouping=[]
    for id in devices_list:
        history=extractSingleDeviceHistory(id,start_timestamp,end_timestamp)
        if len(history)==0: #if the device remains not available for long HA will not produce its history 
            continue
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

        #Computing appliance use datas
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
        print("\nAppliance use data extraction: DONE!")

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
    
    
    res=add_appliances_usage_entry(temp)
    if res:
        logger.info("Appliances usage data updated successfully!")
    else:
        logger.error("Some error occurred while saving appliaces usage data, could't update...")
    
    res=add_hourly_consumption_entry(hourly_grouping)
    if res:
        logger.info("Hourly consumption data updated successfully!")
    else:
        logger.error("Some error occurred while saving hourly consumption data, could't update...")

    logger.info(f"Updating consumption and use data of {len(devices_list)-1} entities ended, elapsed time:{(datetime.datetime.now()-start_call).total_seconds()}[s]")







def Get_Total_Consumption(start_timestamp:datetime.date=datetime.date.today(),end_timestamp:datetime.date=datetime.date.today()):
        start_call=datetime.datetime.now() #used for debug purposes
        start_timestamp=datetime.datetime.combine(start_timestamp, datetime.time.min).astimezone(tz.tzlocal())
        end_timestamp=datetime.datetime.combine(end_timestamp,  datetime.time(23, 59)).astimezone(tz.tzlocal())

        ## Getting the list of all the entities of the house
        res=getEntities(True,False)
        if res["status_code"]!=200:
           logger.error("getEntities returned "+res["status_code"]+", "+res["data"])
           return 
        
        ## Filtering only those entities that could produce some consumption data
        domainsToFilter=["light","media_player","fan"] #domains of entities that could consume energy, sensors and buttons are supposed to consume 0
        entities_list=[x["entity_id"] for x in res["data"] if x["entity_id"].split(".")[0] in domainsToFilter]
        logger.info(f"Asking HA for history, from:{start_timestamp.strftime("%d/%m/%Y %H:%M")} to:{end_timestamp.strftime("%d/%m/%Y %H:%M")}, for {len(entities_list)-1} entities")
        entities_list=",".join(entities_list)

        response=getHistory(entities_id=entities_list,start_timestamp=start_timestamp,end_timestamp=end_timestamp)
        if response["status_code"]!=200:
            logger.error("getHistory returned "+res["status_code"]+", "+res["data"])
            return 
        
        if not response["data"]:
            logger.error("getHistory returned no data...")
            return
        
        entities_states=response["data"]
        res={}
   
        delta=(end_timestamp-start_timestamp).days
        hourly_grouping=[]
        daily_grouping=[]
        mode_use_dict={}
        for id in entities_states:
            logger.info(f"Computing Hourly consumption, Daily consumption and mean use for entity {id}")
            hourly_total=computeHourlyTotalConsumption(id,entities_states[id],start_timestamp,end_timestamp)[id]
            for element in hourly_total:
                 date_from=element["date"].split(" ")[0]+" "+element["date"].split(" ")[1].split("-")[0]
                 date_to=element["date"].split(" ")[0]+" "+element["date"].split(" ")[1].split("-")[1]
                 date_from=datetime.datetime.strptime(date_from,"%d/%m/%Y %H").replace(microsecond=0).timestamp()
                 date_to=datetime.datetime.strptime(date_to,"%d/%m/%Y %H").replace(microsecond=0).timestamp()
                 hourly_grouping.append((id,element["power_consumption"],element["power_consumption_unit"],date_from,date_to))

            temp_date=start_timestamp
            for i in range(delta+1):                   
                temp_list=[x for x in entities_states[id] if x["last_changed"].startswith(temp_date.strftime("%Y-%m-%d"))]
                daily_consumption=computeTotalConsumption(temp_list,temp_date,date_format="%d/%m/%Y")
                daily_grouping.append((
                    id,
                    daily_consumption["power_consumption"],daily_consumption["power_consumption_unit"],
                    daily_consumption["use_time"],daily_consumption["use_time_unit"],
                    datetime.datetime.strptime(daily_consumption["date"],"%d/%m/%Y").replace(microsecond=0).timestamp()
                    ))
                temp_date=temp_date+datetime.timedelta(days=1)

            mode_dict=defaultdict(lambda:{"sum":0,"samples":0,"unit":"s"})
            for i in range(len(entities_states[id])):
                start_block=parser.parse(entities_states[id][i]["last_changed"]).astimezone(tz.tzlocal())
                if i+1==len(entities_states[id]):
                    end_block=datetime.datetime.combine(start_block+datetime.timedelta(days=1), datetime.time.min).astimezone(tz.tzlocal())
                else:
                    end_block=parser.parse(entities_states[id][i+1]["last_changed"]).astimezone(tz.tzlocal())
                duration=(end_block-start_block).total_seconds() #calcolo la durata dell'intervallo
                mode_dict[entities_states[id][i]["state"]]["sum"]+=duration
                mode_dict[entities_states[id][i]["state"]]["samples"]+=1
            
            mode_use_dict[id]=dict(mode_dict)

        logger.info("Retrieving saved data on appliances usage...")
        temp=[]
        database_data=get_all_appliances_usage_entries()
        for id in mode_use_dict.keys():
            for mode in mode_use_dict[id]:
                index=[i for i in range(len(database_data)) if database_data[i]["entity_id"]==id and database_data[i]["state"]==mode]
                if len(index)>0: #the db already has some data about that mode
                    database_element=database_data[index[0]]
                    old_sum=database_element["average_duration"]*database_element["samples"]
                    samples=mode_use_dict[id][mode]["samples"]+database_element["samples"]
                    mean=(mode_use_dict[id][mode]["sum"]+old_sum)/(samples)
                    temp.append((id,mode,mean,samples,mode_use_dict[id][mode]["unit"]))
                else:
                    temp.append((id,mode,mode_use_dict[id][mode]["sum"]/mode_use_dict[id][mode]["samples"],mode_use_dict[id][mode]["samples"],mode_use_dict[id][mode]["unit"]))

        res=add_appliances_usage_entry(temp)
        if res:
            logger.info("Appliances usage data updated successfully!")
        else:
            logger.error("Some error occurred while saving appliaces usage data, could't update...")

        res=add_daily_consumption_entry(daily_grouping)
        if res:
            logger.info("Daily consumption data updated successfully!")
        else:
            logger.error("Some error occurred while saving daily consumption data, could't update...")
        
        res=add_hourly_consumption_entry(hourly_grouping)
        if res:
            logger.info("Hourly consumption data updated successfully!")
        else:
            logger.error("Some error occurred while saving hourly consumption data, could't update...")

        logger.info(f"Updating consumption and use data of {len(entities_list.split(","))-1} entities ended, elapsed time:{(datetime.datetime.now()-start_call).total_seconds()}[s]")
       



def main():
    logging.basicConfig(format='%(levelname)s-%(asctime)s: %(message)s',datefmt='%d/%m/%Y %H:%M:%S',filename='./logs/periodic_functions.log', encoding='utf-8', level=logging.INFO)
    logger.info("Running the script to get hourly appliances consumption and usage time...")
    initializeToken()
    last_timestamp_usage=fetch_one_element("select max(last_timestamp) from Appliances_Usage")
    last_timestamp_consumption=fetch_one_element("select max(start) from Hourly_Consumption")
    last_timestamp_consumption=last_timestamp_consumption["max(start)"]
    last_timestamp_usage=last_timestamp_usage["max(last_timestamp)"]


    if last_timestamp_usage!=None and last_timestamp_consumption!=None:
        starting_date=datetime.datetime.fromtimestamp(min(last_timestamp_usage,last_timestamp_consumption)).astimezone(tz.tzlocal())
        starting_date=starting_date.replace(minute=0,second=0)
    else:
        starting_date=datetime.datetime.combine(datetime.date.today(), datetime.time.min).astimezone(tz.tzlocal())
    devicesExtractionProcedure(start_timestamp=starting_date)

if __name__ == "__main__":
    main()