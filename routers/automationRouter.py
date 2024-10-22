from fastapi import APIRouter,HTTPException

from homeassistant_functions import (
    getEntity,
    getAutomations,createAutomationDirect,
    getDevicesFast,
    getDeviceId,
    getDeviceInfo)
from database_functions import (
    get_configuration_value_by_key,
    get_appliance_usage_entry,
    get_all_energy_slots_with_cost,get_minimum_cost_slot,get_minimum_energy_slots
    )
from schemas import (
    Automation
    )

import datetime,json,logging
from dateutil import parser,tz
from collections import defaultdict
from enum import Enum

class Conflict(Enum):
    def __new__(cls, *args, **kwds):
            value = len(cls.__members__) + 1
            obj = object.__new__(cls)
            obj._value_ = value
            return obj
    def __init__(self, a, b):
            self.type = a
            self.description = b

    EXCESSIVE_ENERGY="Excessive energy consumption","The power required by the system will exceed the maximum value of {treshold} W from {start} to {end}"
    NOT_FEASIBLE_AUTOMATION="Not feasible automation","The automation's required power ({automation_power} W) exceeds the maximum power available ({treshold} W)"

DAYS=["mon","tue","wed","thu","fri","sat","sun"]
POWER_TRESHOLD_DEFAULT=150 #TODO:change this value
MINIMUM_SAVED_VALUE=0.001 #TODO:think if you can extract this value from user preferences

logger = logging.getLogger('uvicorn.error')

def format_action(action):
    """Convert the type action into a more readable form."""
    return action.replace("_", " ").lower()

def format_duration(duration):
    """Format the duration to include only non-zero time components."""
    hours = duration.get('hours', 0)
    minutes = duration.get('minutes', 0)
    seconds = duration.get('seconds', 0)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    if seconds > 0:
        parts.append(f"{seconds} second{'s' if seconds > 1 else ''}")
    
    return ", ".join(parts)

def getTriggerDescription(trigger):
    # Switch statement based on the platform field
    platform = trigger.get('platform', 'unknown platform')

    if platform == "device":
        # Set device name based on device info, default to "Unknown device"
        device_name = "Unknown device"
        if trigger.get('device_id'):
            device_info = getDeviceInfo(trigger.get('device_id'))  # Assuming this function exists
            device_name = device_info["name_by_user"] if device_info["name_by_user"] != "None" else device_info["name"]

        domain = trigger.get('domain', 'unknown domain')
        description = ""

        if domain == 'sensor':
            # Special handling for sensor domain
            description = f'When "{device_name}" {trigger.get('type', 'unknown type')}'
            
            if 'above' in trigger and 'below' in trigger:
                description += f" is between {trigger['above']} and {trigger['below']}"
            elif 'above' in trigger:
                description += f" is above {trigger['above']}"
            elif 'below' in trigger:
                description += f" is below {trigger['below']}"
            else:
                description += " changes"

        elif domain == 'bthome':
            # Special handling for bthome domain
            description = f'When you {trigger.get('subtype', 'unknown action').replace("_"," ")} "{device_name}"'
        
        else:
            # Generic description for other domains
            description = f'When "{device_name}" is {format_action(trigger.get('type', 'unknown action'))}'
            
        # Check for time condition 'for'
        if 'for' in trigger:
            duration_description = format_duration(trigger['for'])
            if duration_description:
                description += f" for {duration_description}"

        return description

    elif platform == "time":
        # Placeholder for time platform logic
        time="unknown time"
        if trigger.get('at'):
            time=trigger.get('at')[:-3] #remoing the seconds part
        return f"Time is {time}"

    elif platform == "sun":
        event = trigger.get('event', 'unknown event')
        offset = trigger.get('offset', None)

        if offset:
            offset_parsed = int(offset)
            offset_minutes = abs(offset_parsed) // 60
            before_after = "after" if offset_parsed > 0 else "before"
            return f"{offset_minutes} minutes {before_after} {event}"
        else:
            return f"It is the {event}"

    elif platform == "time_pattern":
        # Placeholder for time pattern platform logic
        return "Time pattern-based trigger description"

    else:
        # Default case for unhandled platforms
        return "Unknown platform trigger"
    
def format_time_offset(seconds):
    """Convert seconds into a human-readable format (hours and minutes)."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")

    return ", ".join(parts) if parts else "0 minutes"
    

def getConditionDescription(condition):
    # Switch statement based on the platform field
    platform = condition.get('condition', 'unknown condition')

    if platform == "device":
        # Set device name based on device info, default to "Unknown device"
        device_name = "Unknown device"
        if condition.get('device_id'):
            device_info = getDeviceInfo(condition.get('device_id'))  
            device_name = device_info["name_by_user"] if device_info["name_by_user"] != "None" else device_info["name"]

        domain = condition.get('domain', 'unknown domain')
        description = ""

        if domain == 'sensor':
            measured_value=condition.get("type","unknown measure").replace("is_","")
            # Special handling for sensor domain
            description = f'"{device_name}" {measured_value}'
            
            if 'above' in condition and 'below' in condition:
                description += f" is between {condition['above']} and {condition['below']}"
            elif 'above' in condition:
                description += f" is above {condition['above']}"
            elif 'below' in condition:
                description += f" is below {condition['below']}"
            else:
                description += " changes"
        else:
            # Generic description for other domains
            description = f'"{device_name}" {format_action(condition.get('type', 'in unknown state'))}'
            
        # Check for time condition 'for'
        if 'for' in condition:
            duration_description = format_duration(condition['for'])
            if duration_description:
                description += f" for {duration_description}"

        return description

    elif platform == "time":
        # Placeholder for time platform 
        description=""

        if 'before' in condition and 'after' in condition:
            description += f"Time is between {condition['after']} and {condition['before']}"
        elif 'before' in condition:
            description += f"Time is before {condition['before']}"
        elif 'after' in condition:
            description += f"Time is below {condition['after']}"

        if condition.get('weekday'):
            days_string=f"Day is {",".join(condition.get('weekday'))}"
            if description!="":
                description+=f"and {days_string}"
            else:
                description+=days_string
        return description

    elif platform == "sun":
        """Create a description string based on the sun conditions."""
        description_parts = []
        
        # Check for before condition
        if 'before' in condition:
            before_offset = int(condition.get('before_offset', None))  # None if not present
            if before_offset is not None:
                if before_offset > 0:
                    before_time = format_time_offset(before_offset)
                    description_parts.append(f"{before_time} before {condition['before']}")
                else:
                    description_parts.append(f"at {condition['before']}")
            else:
                description_parts.append(f"before {condition['before']}")

        # Check for after condition
        if 'after' in condition:
            after_offset = int(condition.get('after_offset', None))  # None if not present
            if after_offset is not None:
                if after_offset > 0:
                    after_time = format_time_offset(after_offset)
                    description_parts.append(f"{after_time} after {condition['after']}")
                else:
                    description_parts.append(f"at {condition['after']}")
            else:
                description_parts.append(f"after {condition['after']}")

        # Construct the final description
        if description_parts:
            description = f"Sun is {' and '.join(description_parts)}"
        else:
            description = "No sun conditions available."

        return description

    else:
        # Default case for unhandled platforms
        return "Unknown condition"
    

def formatServiceString(service):
    return service.replace("_"," ").capitalize()


def getAutomationDetails(automation,state_map={}):
    automation_power_drawn=0
    automation_energy_consumption=0
    temp=[]
    action_list=[]
    activation_days=[]

    activation_time=getAutomationTime(automation["trigger"])
    for trigger in automation["trigger"]:
        if trigger["platform"]=="device":
            device_info = getDeviceInfo(trigger.get('device_id'))  
            trigger["device_name"] = device_info["name_by_user"] if device_info["name_by_user"] != "None" else device_info["name"]
        trigger["description"]=getTriggerDescription(trigger)

    for condition in automation["condition"]:
        if condition["condition"]=="device":
            device_info = getDeviceInfo(condition.get('device_id'))  
            condition["device_name"] = device_info["name_by_user"] if device_info["name_by_user"] != "None" else device_info["name"]
        condition["description"]=getConditionDescription(condition) 

    time_condition=[x for x in automation["condition"] if x["condition"]=="time"]
    if len(time_condition)>0:
        activation_days=time_condition[0].get("weekday", []) #we assume only one time trigger

    for action in automation["action"]:
        temp.extend(extract_action_operations(action))

    if not state_map:
        with open("./data/devices_new_state_map.json") as file: #TODO:extract path
            state_map=json.load(file)
        
    for device_id,service,domain,action_data in temp:

        state=state_map[service]
        device_info=getDeviceInfo(device_id)
        device_name=device_info["name_by_user"] if device_info["name_by_user"]!="None" else device_info["name"]

        if state not in ["on|off","same"]:#TODO:manage also this cases
            usage_data=get_appliance_usage_entry(device_id,state)
            usage_data.update({
                "device_id":device_id,
                "state":state,
                "service":service,
                "domain":domain,
                "description":f"{formatServiceString(service)} {device_name}",
                "device_name":device_name,
                "data":action_data
            })
            automation_power_drawn+=usage_data["average_power"]
            automation_energy_consumption+=usage_data["average_power"]*(usage_data["average_duration"]/60) #Remember that use time is express in minutes
            action_list.append(usage_data)
        else:
            action_list.append({
                "device_id":device_id,
                "state":state,
                "service":service,
                "domain":domain,
                "description":f"{formatServiceString(service)} {device_name}",
                "device_name":device_name,
                "data":action_data
                })

    return {
        "id":automation["id"],
        "entity_id":automation["entity_id"] if automation.get("entity_id") else "",
        "state":automation["state"]if automation.get("state") else "",
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

def extract_action_operations(action):
    pairs=[]
    action_data=action.get("data",None)
    if action.get("device_id")!=None:
        #if contains "device_id" then it is an action on device, the "type" field represent the service
        pairs.append((action["device_id"],action["type"],action["domain"],action_data))

    if action.get("service")!=None:
        #if contains "service" then is a service type of action, target->entity_id/device_id is the recipient 
        # while "service" is the service
        service=action["service"].split(".")[1]
        domain=action["service"].split(".")[0]
        #some actions (like notify) don't have target in that case we assume no action
        target=action.get("target")
        if target: 
            entity_ids=target.get("entity_id")
            if entity_ids:
                #some cases the target is a list in others is a single value
                if isinstance(entity_ids, list):
                    pairs.extend([(getDeviceId(eid), service,domain,action_data) for eid in entity_ids])
                else:
                    pairs.append((getDeviceId(entity_ids), service,domain,action_data))

            devices_ids=action["target"].get("device_id")
            if devices_ids:
                    #some cases the target is a list in others is a single value
                if isinstance(devices_ids, list):
                    pairs.extend([(device, service,domain,action_data) for device in devices_ids])
                else:
                    pairs.append((devices_ids, service,domain,action_data))
    return pairs

def getAutomationTime(trigger):
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

def getEnergyCostMatrix():
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


def getPowerMatrix(automation):
    power_matrix = {day: [0] * 1440 for day in DAYS} 
    power_array=[0]*(1440*7)
    if automation["time"]!="":
        activation_time=parser.parse(automation["time"])
        activation_days=automation["days"] if len(automation["days"])>0 else DAYS
        for act in automation["action"]:
            indexes=[]
            for day in activation_days:
                activation_index=(activation_time.hour*60+activation_time.minute)+1440*DAYS.index(day)
                end_index=activation_index+int(act["average_duration"])
                if end_index>len(power_array): 
                    #an activation of sunday overflow into monday
                    offset=activation_index+int(act["average_duration"])-len(power_array)
                    indexes+=list(range(activation_index,len(power_array)))
                    indexes+=list(range(0,offset))
                else:
                    indexes+=list(range(activation_index,end_index))
                    
            for i in indexes:
                power_array[i]+=act["average_power"]

        for d in range(len(DAYS)):
            power_matrix[DAYS[d]]=power_array[1440*d:1440*(d+1)]

    return power_matrix


def getAutomationStateMatrix2(state_array,power_array, automation,day):
    if automation["time"]!="":
        activation_time=parser.parse(automation["time"])
        activation_days=automation["days"] if len(automation["days"])>0 else DAYS

        for act in automation["action"]:
            indexes_state=[]
            indexes_empty=[]
            dev_state_array=state_array[act["device_id"]]
            dev_power_array=power_array[act["device_id"]]

            activation_index=(activation_time.hour*60+activation_time.minute)+1440*DAYS.index(day)
            end_index=activation_index+int(act["average_duration"])
            if end_index>len(dev_state_array): 
                #an activation of sunday overflow into monday
                offset=activation_index+int(act["average_duration"])-len(dev_power_array)
                indexes_state+=list(range(activation_index,len(dev_power_array)))
                indexes_state+=list(range(0,offset))
            else:
                indexes_state+=list(range(activation_index,end_index))
                if end_index<1440*(DAYS.index(day)+1):
                    indexes_empty+=list(range(end_index,1440*(DAYS.index(day)+1)))#Added to fix a bug, could be removed if problems occurs
            
            for i in indexes_state:
                dev_state_array[i]=act["state"]
                dev_power_array[i]+=act["average_power"]
            
            for j in indexes_empty:
                dev_state_array[i]=""


def getAutomationStateMatrix(state_matrix, aut):
    if aut["time"]!="":
        activation_time=parser.parse(aut["time"])
        activation_days=aut["days"] if len(aut["days"])>0 else DAYS
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





def getAutomationCost(automation,energy_cost_matrix,day_list=DAYS):
    #energy_cost_matrix=getEnergyCostMatrix()
    power_matrix=getPowerMatrix(automation)
    cost_matrix={day: 0.0 for day in day_list}  
    for day in day_list:
        for i in range(1440):
            #power is in W so we need to divide by 1000 to get kW
            #energy_cost is in euro/kWh
            #we are computing the cost of 1 minute =>1/60 kWh each minute
            #TODO:remember that this formula works only for €/kWh unit, power_matrix is in W
            cost_matrix[day]+=(power_matrix[day][i]/1000)*(energy_cost_matrix[day][i])*(1/60)

    return cost_matrix

def findBetterActivationTime(automation,device_list,saved_automations):
    temp_automation=automation.copy()
    energy_cost_matrix=getEnergyCostMatrix()
    cost=getAutomationCost(automation,energy_cost_matrix)
    minimum_cost_slot=get_minimum_cost_slot()

    ideal_cost=float(minimum_cost_slot["cost"])*(automation["energy_consumption"]/1000) if minimum_cost_slot else 0 # placeholder for ideal in the case in which the db is down

    less_cost_index=get_minimum_energy_slots() #for each day

    suggestions=[]
    if automation["time"]!="":
        activation_hour=float(automation["time"].split(":")[0])
        for day in automation["days"] if len(automation["days"])>0 else DAYS:
            if cost[day]<=ideal_cost:
                continue

            index_list=[x for x in less_cost_index if x["day_name"]==day]
            index_list=sorted(index_list,key=lambda x: abs(x["hour"]-activation_hour))

            new_activation_found=False
            index=0
            while (not new_activation_found) and index<len(index_list):
                new_activation_hour=index_list[index]["hour"]
                #i try to get a value as close as possible to the activation hour
                #if im over i will check "clockwise"
                #if im before i will check "counterclockwise"
                if int(new_activation_hour)>activation_hour:
                    minute_list=["00","10","20","30","40","50"]
                else:
                    minute_list=["50","40","30","20","10","00"]
                for minute in minute_list:
                    if new_activation_found: break
                    
                    new_activation=f"{new_activation_hour:02d}:{minute}:00"
                    temp_automation["time"]=new_activation
                    temp_automation["days"]=[day]#used to check conflicts only on the current day TODO: change this

                    new_cost=getAutomationCost(temp_automation,energy_cost_matrix,day_list=[day])
                    saved_money=cost[day]-new_cost[day]

                    if saved_money>MINIMUM_SAVED_VALUE:
                        #Checking for conflicts with the new activation time
                        conflicts=getConflicts(
                            device_list=device_list,
                            automations_list=saved_automations+[temp_automation],
                            return_only_conflicts=True)
                        
                        if len(conflicts)<=0:
                            #new_cost=getAutomationCost(temp_automation,energy_cost_matrix,day_list=[day])
                            
                            #if new_cost[day]<cost[day]:
                            #if new_cost[day]<=ideal_cost:
                            new_activation_found=True
                            #saved_money=cost[day]-new_cost[day]
                            suggestions.append(
                                {
                                    "day":day,
                                    "new_activation_time":new_activation,
                                    "saved_money": saved_money
                                }
                            )
                
                index+=1

    return suggestions

def getConflicts2(device_list,automations_list,return_only_conflicts=True):
    #Initializing the state matrix
    state_matrix = {day: {} for day in DAYS}
    state_array={}
    power_array={}
    dev_info={}

    for dev in device_list["data"]:
        if dev["device_class"] not in ["sensor","event","sun","weather","device_tracker"]:
            state_array[dev["device_id"]]=[""]*(1440*7)
            power_array[dev["device_id"]]=[0]*(1440*7)
            dev_info[dev["device_id"]]={"device_id": dev["device_id"],"device_name": dev["name"]}

    #Populating state matrix with automation's actions
    for day in DAYS:
        days_automations=[x for x in automations_list if x["days"]==[] or (day in x["days"])]
        sorted_automations=sorted(days_automations,key=lambda x:x["time"]) #sort automations by activation time 
        for aut in sorted_automations:
            getAutomationStateMatrix2(state_array,power_array, aut,day)

    #Computing the cumulative power matrix for conflicts identification
    cumulative_power_array=[0]*(1440*7)
    for i in range(len(cumulative_power_array)):
        for dev in power_array.values():
            cumulative_power_array[i]+=dev[i]


    #Conflicts identification
    conflicts_list = defaultdict(lambda: {"type": Conflict.EXCESSIVE_ENERGY.type, "days": []})

    threshold = get_configuration_value_by_key("power_threshold")  
    threshold=float(threshold["value"]) if threshold else POWER_TRESHOLD_DEFAULT
    
    conflict_is_occurring = False
    for i in range(len(cumulative_power_array)):  # Loop through all the minutes in the week (10080 minutes)
        day_index = i // 1440  # Determine the current day index (0 for Monday, 1 for Tuesday, etc.)
        minute_of_day = i % 1440  # Determine the minute of the current day (0-1439)
        day = DAYS[day_index]  # Get the actual day (e.g., "Monday", "Tuesday", etc.)
        
        if cumulative_power_array[i] > threshold:  # Check if the power exceeds the threshold
            if not conflict_is_occurring:
                start = minute_of_day
                conflict_is_occurring = True
            end = minute_of_day  # Update the end time of the conflict
        else:
            if conflict_is_occurring:  # A conflict has just ended
                start_conflict = f"{start // 60:02}:{start % 60:02}"
                end_conflict = f"{end // 60:02}:{end % 60:02}"
                key = f"{start_conflict}-{end_conflict}"

                # If conflict already exists, append the current day; otherwise, initialize a new conflict
                if key not in conflicts_list:
                    conflicts_list[key] = {
                        "days": [],
                        "start": start_conflict,
                        "end": end_conflict,
                        "description": Conflict.EXCESSIVE_ENERGY.description.format(
                            treshold=threshold,
                            start=start_conflict,
                            end=end_conflict
                        )
                    }
                conflicts_list[key]["days"].append(day)
                conflict_is_occurring = False  # Reset the flag after recording the conflict

    # Convert conflicts dictionary to a list
    conflicts_list = list(conflicts_list.values())

    if return_only_conflicts:
        return conflicts_list 
    else:
        cumulative_power_matrix={}
        for d in range(len(DAYS)):
            for dev_id in state_array:
                dev_state={}
                dev_state["state_list"]=state_array[dev_id][1440*d:1440*(d+1)]
                dev_state["power_list"]=power_array[dev_id][1440*d:1440*(d+1)]
                dev_state["device_id"]=dev_id
                dev_state["device_name"]=dev_info[dev_id]["device_name"]
                state_matrix[DAYS[d]][dev_id]=dev_state
            cumulative_power_matrix[DAYS[d]]=cumulative_power_array[1440*d:1440*(d+1)]
        return {
        "state_matrix":state_matrix,
        "cumulative_power_matrix":cumulative_power_matrix,
        "conflicts":conflicts_list
        }


def getConflicts(device_list,automations_list,return_only_conflicts=True):
    #Initializing the state matrix
    state_matrix = {day: {} for day in DAYS}
    for day in DAYS:
        for dev in device_list["data"]:
            if dev["device_class"] not in ["sensor","event","sun","weather","device_tracker"]:
                state_matrix[day][dev["device_id"]] = {
                        "state_list": [""] * 1440,
                        "power_list": [0] * 1440,
                        "device_id": dev["device_id"],
                        "device_name": dev["name"]
                    }

    #Populating state matrix with automation's actions
    sorted_automations=sorted(automations_list,key=lambda x:x["time"]) #sort automations by activation time 
    for aut in sorted_automations:
        getAutomationStateMatrix(state_matrix, aut)

    #Computing the cumulative power matrix for conflicts identification
    cumulative_power_matrix = {day: [0] * 1440 for day in DAYS}  
    for day in DAYS:
        for dev in state_matrix[day].values():
            for i in range(1440):
                cumulative_power_matrix[day][i]+=dev["power_list"][i]

    #Conflicts identification
    conflicts_list = defaultdict(lambda: {"type": Conflict.EXCESSIVE_ENERGY.type, "days": []})

    threshold = get_configuration_value_by_key("power_threshold")  
    threshold=float(threshold["value"]) if threshold else POWER_TRESHOLD_DEFAULT
    
    for day in DAYS:
        conflict_is_occurring=False
        for i in range(1440):
            if cumulative_power_matrix[day][i] > threshold: 
                if not conflict_is_occurring:
                    start=i
                    conflict_is_occurring=True
                end=i
            else:
                if conflict_is_occurring: #there was a conflict since last minute
                    start_conflict=f"{start // 60:02}:{start % 60:02}"
                    end_conflict=f"{end // 60:02}:{end % 60:02}"
                    key=f"{start_conflict}-{end_conflict}"
                    conflicts_list[key]["days"].append(day)
                    conflicts_list[key]["start"] = start_conflict
                    conflicts_list[key]["end"] = end_conflict
                    conflicts_list[key]["description"]=Conflict.EXCESSIVE_ENERGY.description.format(
                        treshold=threshold,
                        start=start_conflict,
                        end=end_conflict)
                    conflict_is_occurring=False

    conflicts_list=list(conflicts_list.values())

    if return_only_conflicts:
        return conflicts_list 
    else:
        return {
        "state_matrix":state_matrix,
        "cumulative_power_matrix":cumulative_power_matrix,
        "conflicts":conflicts_list
        }


    
def getFeasibilityConflicts(automation):
    '''
    Functions that checks if the given automation could be executed alone.
    The control evaluates the instantaneous power drawn by the automations and compare it to the maximum threshold possible. 
    If such treshold is exceeded, a corresponding "conflict" is produced
    '''
    threshold = get_configuration_value_by_key("power_threshold")  
    threshold=float(threshold["value"]) if threshold else POWER_TRESHOLD_DEFAULT

    automation_power=automation.get("power_drawn",0)
    if  automation_power>= threshold:
        return {
                "type":Conflict.NOT_FEASIBLE_AUTOMATION.type,
                "description":Conflict.NOT_FEASIBLE_AUTOMATION.description.format(
                    treshold=threshold,automation_power=automation_power),
                    "days":DAYS #FIXME: this is a patchwork to show something in the web app, remove in prod           
                }
    else:
        return None


def getAutomationRouter():
    automation_router=APIRouter(tags=["Automation"],prefix="/automation")

    @automation_router.get("")
    def Get_Automations(get_suggestions:bool=False):
        res=getAutomations()
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        else:
            automations_list = res["data"]
            with open("./data/devices_new_state_map.json") as file:  # TODO: Extract path to config
                state_map = json.load(file)

                

            automations_details = [getAutomationDetails(automation, state_map) for automation in automations_list]
            dev_list=getDevicesFast()
            ret=[]
            for automation in automations_details:
                if get_suggestions:
                    automation["suggestions"]=findBetterActivationTime(automation,dev_list,automations_details)
                ret.append(automation)
            return ret
        
    @automation_router.post("")
    def Automation_Addition(automation_in:Automation):
        return createAutomationDirect(automation_in.automation)
    
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
    def Simulate_Automation_Addition(automation_in:Automation):
        start_call=datetime.datetime.now()

        #Get automations saved and details of the one we want to add
        automation=getAutomationDetails(automation_in.automation)

        #TODO: when writing the final version, do the feasibility check first
        # conflicts=checkAutomationFeasibility(automation)
        # if not conflicts:

        saved_automations = Get_Automations()
        new_automation_list=saved_automations+[automation]

        #Getting the list of devices
        dev_list=getDevicesFast()
    
        #Getting conflicts
        simulation=getConflicts2(device_list=dev_list,automations_list=new_automation_list,return_only_conflicts=False)

        #TODO:remove this part in the final version
        feasibilty_conflicts=getFeasibilityConflicts(automation)
        if feasibilty_conflicts:
            simulation["conflicts"]=[feasibilty_conflicts]

        #Suggestions identification if no conflict occurs
        suggestions=[]
        if len(simulation["conflicts"])<=0 and automation["power_drawn"]>5: #TODO: decide a valid default value for the minimum power drawn
            suggestions=findBetterActivationTime(automation,dev_list,saved_automations)
        



        
        logger.debug(f"Simulate_Automation_Addition required {(datetime.datetime.now()-start_call).total_seconds()} [s]")

        return {
            "state_matrix":simulation["state_matrix"],
            "cumulative_power_matrix":simulation["cumulative_power_matrix"],
            "conflicts":simulation["conflicts"],
            "suggestions":suggestions
            }
    
    return automation_router