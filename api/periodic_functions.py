
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

logger = {}

#value over which a device is considered on even if the state is unavailable
UNAVAIABLE_TO_ON = 20
#value under which the device connected to a smart plug is considered standby
ACTIVATION_TRESHOLD = 3

STATE_CHANGE_TOLERANCE = 3 #a device state is perceived if it last at least STATE_CHANGE_TOLERANCE minutes


def initializeLogger():
    global logger
    # Create a logger
    logger = logging.getLogger(__name__)

    # Set the overall logging level
    logger.setLevel(logging.INFO)

    # Create a file handler to log messages to a file
    file_handler = logging.FileHandler('./logs/periodic_functions.log', encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # Create a console handler to log messages to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Create a formatter and set it for both handlers
    formatter = logging.Formatter('%(levelname)s-%(asctime)s: %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)



def entitiesHistoryExtractionProcedure(start_timestamp:datetime.datetime=datetime.date.today()):
    start_call=datetime.datetime.now()
    logger.info(f"Starting Entity History extraction. Required timestamp:{start_timestamp.print("%d/%m/%Y %H:%M")}")
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


def getDevicesHistory(start_timestamp:datetime.datetime=datetime.date.today()):
    start_call=datetime.datetime.now()
    logger.info(f"Starting Device History extraction. Required timestamp:{start_timestamp.print("%d/%m/%Y %H:%M")}")
    end_timestamp=datetime.datetime.today().astimezone(tz.tzlocal())
    end_timestamp=end_timestamp.replace(second=0)
    #Getting the list of devices
    res=getDevicesFast()
    if res["status_code"]!=200:
        logger.error("getDevicesFast returned "+res["status_code"]+", "+res["data"])
        return
    
    devicesToRemove=["sensor","device_tracker","weather","event","update"]
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
        logger.info(f"Device History data updated successfully! Elapsed time {(datetime.datetime.now()-start_call).total_seconds()}[s]")
    else:
        logger.error("Some error occurred while saving Device History data, could't update...")


def getAppliancesUsageData(start_timestamp:datetime.datetime=datetime.date.today()):
    start_call=datetime.datetime.now() 
    logger.info(f"Starting Appliance Usage extraction. Required timestamp:{start_timestamp.print("%d/%m/%Y %H:%M")}")
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
    for id in devices_list:
        history=extractSingleDeviceHistory(id,start_timestamp,end_timestamp)
        if len(history)==0: #if the device remains not available for long HA will not produce its history 
            continue

        #a buffer mechanism is used. The avoids cases in which a new duration is computed when the state of a device changes for a brief second
        #e.g. if the sequence is state1 state2 state1 the instance of state2 is ignored
        buffer_state = None  
        buffer_count = 0  

        use_map = defaultdict(lambda: {
            "average_duration": 0,
            "average_duration_unit": "min",
            "average_power": 0,
            "average_power_unit": "W",
            "power_samples": 0,
            "maximum_power":0,
            "duration_samples": 0
        })

        first_element=history[0]
        prev_state=first_element["state"]

        if first_element["power"]<=0 or first_element["power"]>0 and first_element["power"]<ACTIVATION_TRESHOLD and first_element["state"]!="off":
            prev_state = "off"

        current_duration = 1

        for i in range(len(history)):
            x = history[i]
            #States preprocessing
            #For smart plugs a device could be off but still having on as the plug is in the on state, in that case we use the power to understand each state
            if x["power"]<=0:
                x["state"]="off"
            if x["power"]>0 and x["power"]<ACTIVATION_TRESHOLD and x["state"]!="off":
                x["state"] = "off" 

            #If the state is unavailable but the power is high, we consider the device in the on state
            
            x["state"] = "on" if x["state"]=="unavailable" and x["power"] > UNAVAIABLE_TO_ON else x["state"]
            key = x["state"]

            # Update power statistics
            use_map[key]["average_power"] = (
                (use_map[key]["average_power"] * use_map[key]["power_samples"]) + x["power"]
            ) / (use_map[key]["power_samples"] + 1)
            use_map[key]["power_samples"] += 1

            if x["power"]>use_map[key]["maximum_power"]:
                use_map[key]["maximum_power"]=x["power"]


            if x["state"] != prev_state:
                if buffer_state is None:  
                    buffer_state = x["state"]
                    buffer_count = 1
                elif buffer_state == x["state"]:  
                    buffer_count += 1
                    if buffer_count >= STATE_CHANGE_TOLERANCE: 
                        use_map[prev_state]["average_duration"] = (
                            (use_map[prev_state]["average_duration"] * use_map[prev_state]["duration_samples"]) + current_duration
                        ) / (use_map[prev_state]["duration_samples"] + 1)
                        use_map[prev_state]["duration_samples"] += 1
                        current_duration = 1
                        prev_state = buffer_state
                        buffer_state = None
                        buffer_count = 0
                else:  # Reset buffer if inconsistent
                    buffer_state = x["state"]
                    buffer_count = 1
            else: 
                buffer_state = None
                buffer_count = 0
                current_duration += 1

            # Handling the last entry in history
            if i == len(history) - 1:
                use_map[prev_state]["average_duration"] = (
                    (use_map[prev_state]["average_duration"] * use_map[prev_state]["duration_samples"]) + current_duration
                ) / (use_map[prev_state]["duration_samples"] + 1)
                use_map[prev_state]["duration_samples"] += 1


        mode_use_dict[id]=dict(use_map)

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
                        max(database_element["maximum_power"],mode_use_dict[id][mode]["maximum_power"]),
                        end_timestamp.replace(microsecond=0).timestamp()
                        ))
            else:
                temp.append((
                    id,mode,
                    mode_use_dict[id][mode]["average_duration"],mode_use_dict[id][mode]["average_duration_unit"],mode_use_dict[id][mode]["duration_samples"],
                    mode_use_dict[id][mode]["average_power"],mode_use_dict[id][mode]["average_power_unit"],mode_use_dict[id][mode]["power_samples"],
                    mode_use_dict[id][mode]["maximum_power"],
                    end_timestamp.replace(microsecond=0).timestamp()
                    ))
    #endregion
    res=add_appliances_usage_entry(temp)
    if res:
        logger.info(f"Appliances usage data updated successfully! Elapsed time {(datetime.datetime.now()-start_call).total_seconds()}[s]")
    else:
        logger.error("Some error occurred while saving appliaces usage data, could't update...")


def main():
    #logging.basicConfig(format='%(levelname)s-%(asctime)s: %(message)s',datefmt='%d/%m/%Y %H:%M:%S',filename='./logs/periodic_functions.log', encoding='utf-8', level=logging.INFO)
    initializeLogger()
    initializeToken()

    last_timestamp_device_history=fetch_one_element(DbPathEnum.CONSUMPTION,"select max(timestamp) from Device_History")
    last_timestamp_device_history=last_timestamp_device_history["max(timestamp)"]
    if last_timestamp_device_history !=None:
        starting_date=datetime.datetime.fromtimestamp(last_timestamp_device_history).astimezone(tz.tzlocal())
        starting_date=starting_date.replace(second=0)
    else:
        starting_date=datetime.datetime.combine(datetime.date.today(), datetime.time.min).astimezone(tz.tzlocal())
    
    getDevicesHistory(start_timestamp=starting_date)
    

    last_timestamp_usage=fetch_one_element(DbPathEnum.CONSUMPTION,"select max(last_timestamp) from Appliances_Usage")
    last_timestamp_usage=last_timestamp_usage["max(last_timestamp)"]
    if last_timestamp_usage!=None:
        starting_date=datetime.datetime.fromtimestamp(last_timestamp_usage).astimezone(tz.tzlocal())
        starting_date=starting_date.replace(minute=0,second=0)
    else:
        starting_date=datetime.datetime.combine(datetime.date.today(), datetime.time.min).astimezone(tz.tzlocal())
    
    if (datetime.datetime.now().astimezone(tz.tzlocal())-starting_date).total_seconds()>60*60:
        getAppliancesUsageData(start_timestamp=starting_date)


    last_timestamp_entity_history=fetch_one_element(DbPathEnum.ENTITY_HISTORY,"select max(timestamp) from Entity_History")
    last_timestamp_entity_history=last_timestamp_entity_history["max(timestamp)"]
    if last_timestamp_entity_history!=None:
        starting_date=datetime.datetime.fromtimestamp(last_timestamp_entity_history["max(timestamp)"]).astimezone(tz.tzlocal())
        starting_date=starting_date.replace(minute=0,second=0)
    else:
        starting_date=datetime.datetime.now()-timedelta(days=2)
        starting_date=starting_date.replace(hour=0,minute=0,second=0)
    entitiesHistoryExtractionProcedure(start_timestamp=starting_date)

if __name__ == "__main__":
    main()