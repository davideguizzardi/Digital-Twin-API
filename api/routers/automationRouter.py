#region Import
from fastapi import APIRouter,HTTPException
from homeassistant_functions import (
    getEntity,
    getAutomations,createAutomationDirect,
    getDevicesFast,
    getDeviceId,
    getDeviceInfo)
from database_functions import (
    get_configuration_item_by_key,
    get_usage_entry_for_appliance_state,
    get_all_energy_slots_with_cost,get_minimum_cost_slot,get_minimum_energy_slots,get_maximum_cost_slot
    )
from schemas import (
    Automation
    )
from classes import BetterActivationTimeSuggestion,ConflictResolutionActivationTimeSuggestion,ConflictResolutionSplitSuggestion,ConflictResolutionDeactivateAutomationsSuggestion
import datetime,json,logging
from dateutil import parser,tz
from collections import defaultdict
from enum import Enum
from datetime import timedelta
from demo_functions import get_demo_automations
#endregion 

#region Constants
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
MINIMUM_SAVED_VALUE=0.01 #TODO:think if you can extract this value from user preferences
MIN_AUTOMATION_POWER = 5  #TODO: decide a valid default value for the minimum power drawn

logger = logging.getLogger('uvicorn.error')

#endregion
#region Formatting Functions
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
    '''Given the trigger it returns its natural language description'''
    platform = trigger.get('platform', 'unknown platform') if "platform" in trigger else trigger.get('trigger', 'unknown platform')

    if platform == "device":
        device_name = "Unknown device"
        if trigger.get('device_id'):
            device_info = getDeviceInfo(trigger.get('device_id')) 
            device_name = device_info["name_by_user"] if device_info["name_by_user"] != "None" else device_info["name"]

        domain = trigger.get('domain', 'unknown domain')
        description = ""

        if domain == 'sensor':
            description = f'When "{device_name}" {trigger.get("type", "unknown type")}'
            
            if 'above' in trigger and 'below' in trigger:
                description += f" is between {trigger['above']} and {trigger['below']}"
            elif 'above' in trigger:
                description += f" is above {trigger['above']}"
            elif 'below' in trigger:
                description += f" is below {trigger['below']}"
            else:
                description += " changes"
        elif domain == 'binary_sensor':
            description = f'When "{device_name}" is {trigger.get("type", "unknown type")}'

        elif domain == 'bthome':
            description = f'When you {trigger.get("subtype", "unknown action").replace("_"," ")} "{device_name}"'
        
        else:
            description = f'When "{device_name}" is {format_action(trigger.get("type", "unknown action"))}'
            
        if 'for' in trigger:
            duration_description = format_duration(trigger['for'])
            if duration_description:
                description += f" for {duration_description}"

        return description

    elif platform == "time":
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
        return "Time pattern-based trigger description"

    else:
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
    '''Given a condition it returns a natural language description of it'''
    platform = condition.get('condition', 'unknown condition')

    if platform == "device":
        device_name = "Unknown device"
        if condition.get('device_id'):
            device_info = getDeviceInfo(condition.get('device_id'))  
            device_name = device_info["name_by_user"] if device_info["name_by_user"] != "None" else device_info["name"]

        domain = condition.get('domain', 'unknown domain')
        description = ""

        if domain == 'sensor':
            measured_value=condition.get("type","unknown measure").replace("is_","")
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
            description = f'"{device_name}" {format_action(condition.get("type", "in unknown state"))}'
            
        if 'for' in condition:
            duration_description = format_duration(condition['for'])
            if duration_description:
                description += f" for {duration_description}"

        return description

    elif platform == "time":
        description=""

        if 'before' in condition and 'after' in condition:
            description += f"Time is between {condition['after']} and {condition['before']}"
        elif 'before' in condition:
            description += f"Time is before {condition['before']}"
        elif 'after' in condition:
            description += f"Time is below {condition['after']}"

        if condition.get('weekday'):
            days_string=f"Day is {','.join(condition.get('weekday'))}"
            if description!="":
                description+=f"and {days_string}"
            else:
                description+=days_string
        return description

    elif platform == "sun":
        """Create a description string based on the sun conditions."""
        description_parts = []
        
        if 'before' in condition:
            before_offset = int(condition.get('before_offset', None))  
            if before_offset is not None:
                if before_offset > 0:
                    before_time = format_time_offset(before_offset)
                    description_parts.append(f"{before_time} before {condition['before']}")
                else:
                    description_parts.append(f"at {condition['before']}")
            else:
                description_parts.append(f"before {condition['before']}")
        if 'after' in condition:
            after_offset = int(condition.get('after_offset', None))
            if after_offset is not None:
                if after_offset > 0:
                    after_time = format_time_offset(after_offset)
                    description_parts.append(f"{after_time} after {condition['after']}")
                else:
                    description_parts.append(f"at {condition['after']}")
            else:
                description_parts.append(f"after {condition['after']}")

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

#endregion


#region Support functions
def getAutomationDetails(automation,state_map={}):
    '''Returns a json file representing all the details of an automation.'''
    automation_average_power_drawn=0
    automation_energy_consumption=0
    minimum_automation_cost=-1
    maximum_automation_cost=-1
    monthly_cost=-1
    temp=[]
    action_list=[]
    activation_days=[]
    
    #Section required for integration with CNR
    trigger_key="trigger" if "trigger" in automation else "triggers"
    condition_key="condition" if "condition" in automation else "conditions"
    action_key="action" if "action" in automation else "actions"

    activation_time=getAutomationTime(automation.get(trigger_key,{}))

    for trigger in automation.get(trigger_key,[]):
        if trigger.get("platform")=="device" or trigger.get("trigger")=="device":
            device_info = getDeviceInfo(trigger.get('device_id'))  
            trigger["device_name"] = device_info["name_by_user"] if device_info["name_by_user"] != "None" else device_info["name"]
        if "entity_id" in trigger:
            device_info = getDeviceInfo(getDeviceId(trigger.get('entity_id')))  
            trigger["device_name"] = device_info["name_by_user"] if device_info["name_by_user"] != "None" else device_info["name"]
        
        trigger["description"]=getTriggerDescription(trigger)

    for condition in automation.get(condition_key,[]):
        if condition["condition"]=="device":
            device_info = getDeviceInfo(condition.get('device_id'))  
            condition["device_name"] = device_info["name_by_user"] if device_info["name_by_user"] != "None" else device_info["name"]
        if "entity_id" in condition:
            device_info = getDeviceInfo(getDeviceId(condition.get('entity_id')))  
            condition["device_name"] = device_info["name_by_user"] if device_info["name_by_user"] != "None" else device_info["name"]
        condition["description"]=getConditionDescription(condition) 

    time_condition=[x for x in automation.get(condition_key,[]) if x["condition"]=="time"]
    if len(time_condition)>0:
        activation_days=time_condition[0].get("weekday", []) #we assume only one time trigger

    for action in automation.get(action_key,[]):
        temp.extend(extract_action_operations(action))

    if not state_map:
        with open("./data/devices_new_state_map.json") as file: #TODO:extract path
            state_map=json.load(file)
        
    for device_id,service,domain,action_data in temp:

        state=state_map[service]
        device_info=getDeviceInfo(device_id)
        device_name=device_info["name_by_user"] if device_info["name_by_user"]!="None" else device_info["name"]

        if state not in ["on|off","same"]:#TODO:manage also this cases
            usage_data=get_usage_entry_for_appliance_state(device_id,state)
            #TODO:if there are no data you should extract static data from somewhere
            if usage_data:
                usage_data.update({
                    "device_id":device_id,
                    "state":state,
                    "service":service,
                    "domain":domain,
                    "description":f"{formatServiceString(service)} {device_name}",
                    "device_name":device_name,
                    "data":action_data
                })
                automation_average_power_drawn+=usage_data["average_power"]
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
            

    automation_out={
        "id":automation.get("id",""),
        "entity_id":automation["entity_id"] if automation.get("entity_id") else "",
        "state":automation["state"]if automation.get("state") else "",
        "description":automation.get("description",""),
        "trigger":automation.get(trigger_key,""),
        "condition":automation.get(condition_key,[]),
        "name":automation.get("alias",""),
        "time":activation_time,
        "days":activation_days,
        "action":action_list,
        "average_power_drawn":automation_average_power_drawn,
        "energy_consumption":automation_energy_consumption
        }

    if activation_time!="":
        monthly_cost=getMonthlyAutomationCost(automation_out,None,activation_days if len(activation_days)>0 else DAYS)
    else:
        minimum_cost_slot=get_minimum_cost_slot()
        maximum_cost_slot=get_maximum_cost_slot()
        if len(minimum_cost_slot)>0:
            minimum_automation_cost=(automation_energy_consumption/1000)*float(minimum_cost_slot["cost"]) #FIXME: assumption consumption in Wh and cost in euro/kW
        
        if len(maximum_cost_slot)>0:
            maximum_automation_cost=(automation_energy_consumption/1000)*float(maximum_cost_slot["cost"]) #FIXME: assumption consumption in Wh and cost in euro/kW    
    

    automation_out.update({
        "monthly_cost":monthly_cost,
        "maximum_cost_per_run":maximum_automation_cost,
        "minimum_cost_per_run":minimum_automation_cost
    })
    
    return automation_out

def extract_action_operations(action):
    pairs=[]
    action_data=action.get("data",None)
    if action.get("device_id")!=None:
        #if contains "device_id" then it is an action on device, the "type" field represent the service
        pairs.append((action["device_id"],action["type"],action["domain"],action_data))

    if action.get("service")!=None or action.get("action")!=None:
        #if contains "service" then is a service type of action, target->entity_id/device_id is the recipient 
        # while "service" is the service
        service=action["service"].split(".")[1] if "service" in action else action["action"].split(".")[1]
        domain=action["service"].split(".")[0] if "service" in action else action["action"].split(".")[0]
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
        elif "entity_id" in action:
            pairs.append((getDeviceId(action.get("entity_id")),service,domain,action_data))
    return pairs

def getAutomationTime(trigger):
    activation_time=""

    time_trigger=[x for x in trigger if x.get("platform","")=="time" or x.get("trigger","")=="time"]
    if len(time_trigger)>0:
        if len(time_trigger[0]["at"].split(":")) == 3:
            activation_time=time_trigger[0]["at"][:-3]
        else:
            activation_time=time_trigger[0]["at"] #we assume only one time trigger

    sun_trigger=[x for x in trigger if x.get("platform","")=="sun"]
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
    '''
    Returns the matrix expressing the cost of energy each minute of the week 
    '''
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
    '''
    It produces the weekly power matrix of the automation passed as input. It's main use is to compute automation cost
    '''
    power_matrix = {day: [0] * 1440 for day in DAYS} 
    power_array=[0]*(1440*7)
    if automation.get("time","")!="":
        activation_time=parser.parse(automation["time"])
        activation_days=automation["days"] if len(automation["days"])>0 else DAYS
        for act in automation["action"]:
            indexes=[]
            for day in activation_days:
                activation_index=(activation_time.hour*60+activation_time.minute)+1440*DAYS.index(day)
                end_index=activation_index+int(act.get("average_duration",0))
                if end_index>len(power_array): 
                    #an activation of sunday overflow into monday
                    offset=activation_index+int(act.get("average_duration",0))-len(power_array)
                    indexes+=list(range(activation_index,len(power_array)))
                    indexes+=list(range(0,offset))
                else:
                    indexes+=list(range(activation_index,end_index))
                    
            for i in indexes:
                power_array[i]+=act.get("average_power",0)

        for d in range(len(DAYS)):
            power_matrix[DAYS[d]]=power_array[1440*d:1440*(d+1)]

    return power_matrix


def getAutomationStateMatrix(state_array,power_array, automation,day):
    if automation["time"]!="":
        activation_time=parser.parse(automation["time"])
        activation_days=automation["days"] if len(automation["days"])>0 else DAYS

        for act in automation["action"]:
            indexes_state=[]
            indexes_empty=[]
            dev_state_array=state_array[act["device_id"]]
            dev_power_array=power_array[act["device_id"]]

            activation_index=(activation_time.hour*60+activation_time.minute)+1440*DAYS.index(day)
            end_index=activation_index+int(act.get("average_duration",0))
            if end_index>len(dev_state_array): 
                #an activation of sunday overflow into monday
                offset=activation_index+int(act.get("average_duration",0))-len(dev_power_array)
                indexes_state+=list(range(activation_index,len(dev_power_array)))
                indexes_state+=list(range(0,offset))
            else:
                indexes_state+=list(range(activation_index,end_index))
                if end_index<1440*(DAYS.index(day)+1):
                    indexes_empty+=list(range(end_index,1440*(DAYS.index(day)+1)))#Added to fix a bug, could be removed if problems occurs
            
            for i in indexes_state:
                dev_state_array[i]=act.get("state","")
                dev_power_array[i]=act.get("maximum_power",0)
                #dev_power_array[i]=act["average_power"]
            
            for j in indexes_empty:
                dev_state_array[j]=""

def getAutomationCost(automation,energy_cost_matrix,day_list=DAYS):
    '''Returns the monthly cost of running an automation'''
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

def getMonthlyAutomationCost(automation,energy_cost_matrix,day_list=DAYS):
    '''Returns the monthly cost of running an automation'''
    if not energy_cost_matrix:
        energy_cost_matrix=getEnergyCostMatrix()
    power_matrix=getPowerMatrix(automation)
    cost=0
    for day in day_list:
        for i in range(1440):
            #power is in W so we need to divide by 1000 to get kW
            #energy_cost is in euro/kWh
            #we are computing the cost of 1 minute =>1/60 kWh each minute
            #TODO:remember that this formula works only for €/kWh unit, power_matrix is in W
            cost+=(power_matrix[day][i]/1000)*(energy_cost_matrix[day][i])*(1/60)

    return cost*4 #assumption, each month is composed of 4 weeks

def findBetterActivationTime(automation,device_list,saved_automations)->list[BetterActivationTimeSuggestion]:
    '''
    Return a list of suggestions. Each suggestion express a new activation time that could be set to the passed automation
    to reduce it's monthly cost.

    Args:
        automation: automation to optimize
        device_list: list of devices saved in home assistant
        saved_automations: list of saved automations

    Returns:
        list[BetterActivationTimeSuggestion]: list of suggestions or empty list
    '''
    temp_automation=automation.copy()
    automation_days=automation["days"] if len(automation["days"])>0 else DAYS

    energy_cost_matrix=getEnergyCostMatrix()
    cost=getAutomationCost(automation,energy_cost_matrix)
    monthlycost=getMonthlyAutomationCost(automation,energy_cost_matrix)
    minimum_cost_slot=get_minimum_cost_slot()

    ideal_cost=float(minimum_cost_slot["cost"])*(automation["energy_consumption"]/1000) if minimum_cost_slot else 0 # placeholder for ideal in the case in which the db is down

    less_cost_index=get_minimum_energy_slots() #for each day

    suggestions=defaultdict(lambda:{"suggestion_type":"better_activation","days":[],"new_activation_time":"","monthly_saved_money": 0})
    if automation["time"]!="":
        activation_hour=float(automation["time"].split(":")[0])
        for day in automation_days:
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
                    #temp_automation["days"]=[day]#used to check conflicts only on the current day TODO: change this

                    new_cost=getMonthlyAutomationCost(temp_automation,energy_cost_matrix,day_list=automation_days)
                    saved_money=monthlycost-new_cost #NOTICE ME

                    if saved_money>MINIMUM_SAVED_VALUE:
                        #Checking for conflicts with the new activation time
                        conflicts=getConflicts(
                            device_list=device_list,
                            automations_list=saved_automations+[temp_automation])
                        
                        if len(conflicts)<=0:
                            new_activation_found=True
                            suggestions[new_activation]["days"].append(day)
                            suggestions[new_activation]["new_activation_time"]=new_activation
                            suggestions[new_activation]["monthly_saved_money"]=saved_money    
                index+=1
    return list(suggestions.values())

def getConflicts(device_list, automations_list)->list:
    """
    Return the list of Excessive Energy consumption conflicts given the list of automations passed as input.

    Args:
        device_list (dict): Dictionary containing device information.
        automations_list (list): List of automation to test.

    Returns:
        list : Conflicts list or an empty list.
    """

    conflicts_list=[]
    
    _, cumulative_power_matrix = getStatePowerMatrix(device_list, automations_list)
    cumulative_power_array = [value for daily_values in cumulative_power_matrix.values() for value in daily_values]
    

    threshold = get_configuration_item_by_key("power_threshold")
    threshold = float(threshold["value"]) if threshold else POWER_TRESHOLD_DEFAULT
    conflicts_list = defaultdict(lambda: {"type": Conflict.EXCESSIVE_ENERGY.type, "days": [], "threshold": threshold})

    conflict_is_occurring = False
    for i in range(len(cumulative_power_array)):
        day_index = i // 1440
        minute_of_day = i % 1440
        day = DAYS[day_index]

        if cumulative_power_array[i] > threshold:
            if not conflict_is_occurring:
                start = minute_of_day
                conflict_is_occurring = True
            end = minute_of_day
        else:
            if conflict_is_occurring:
                start_conflict = f"{start // 60:02}:{start % 60:02}"
                end_conflict = f"{end // 60:02}:{end % 60:02}"
                key = f"{start_conflict}-{end_conflict}"

                if key not in conflicts_list:
                    conflicts_list[key].update({
                        "start": start_conflict,
                        "end": end_conflict,
                        "description": Conflict.EXCESSIVE_ENERGY.description.format(
                            treshold=threshold,
                            start=start_conflict,
                            end=end_conflict
                        )
                    })
                conflicts_list[key]["days"].append(day)
                conflict_is_occurring = False

    return list(conflicts_list.values())


def getStatePowerMatrix(device_list:dict, automations_list:list):
    """
    Creates the state matrix and cumulative power matrix based on the device list and automations list.

    Args:
        device_list (dict): Dictionary containing device information.
        automations_list (list): List of automation configurations.

    Returns:
        tuple: state_matrix, cumulative_power_matrix
    """
    state_matrix = {day: {} for day in DAYS}
    state_array = {}
    power_array = {}
    dev_info = {}

    # Initialize device information
    for dev in device_list["data"]:
        if dev["device_class"] not in ["sensor", "event", "sun", "weather", "device_tracker"]:
            state_array[dev["device_id"]] = [""] * (1440 * 7)
            power_array[dev["device_id"]] = [0] * (1440 * 7)
            dev_info[dev["device_id"]] = {"device_id": dev["device_id"], "device_name": dev["name"]}

    # Populate the state matrix
    for day in DAYS:
        days_automations = [x for x in automations_list if x["days"] == [] or (day in x["days"])]
        sorted_automations = sorted(days_automations, key=lambda x: x["time"])
        for aut in sorted_automations:
            getAutomationStateMatrix(state_array, power_array, aut, day)

    # Compute the cumulative power array
    cumulative_power_array = [0] * (1440 * 7)
    for i in range(len(cumulative_power_array)):
        for dev in power_array.values():
            cumulative_power_array[i] += dev[i]

    # Build the cumulative power matrix and update the state matrix
    cumulative_power_matrix = {}
    for d in range(len(DAYS)):
        for dev_id in state_array:
            dev_state = {
                "state_list": state_array[dev_id][1440 * d:1440 * (d + 1)],
                "power_list": power_array[dev_id][1440 * d:1440 * (d + 1)],
                "device_id": dev_id,
                "device_name": dev_info[dev_id]["device_name"]
            }
            state_matrix[DAYS[d]][dev_id] = dev_state
        cumulative_power_matrix[DAYS[d]] = cumulative_power_array[1440 * d:1440 * (d + 1)]

    return state_matrix, cumulative_power_matrix



def getExcessivePowerConflicts(cumulative_power_array:list)->list:
    """
    Identifies conflicts based on the cumulative power matrix.

    Args:
        cumulative_power_array: A 1440x7 list containing the power demand of the entire week 

    Returns:
        list: A list of conflicts identified.
    """
    threshold = get_configuration_item_by_key("power_threshold")
    threshold = float(threshold["value"]) if threshold else POWER_TRESHOLD_DEFAULT
    conflicts_list = defaultdict(lambda: {"type": Conflict.EXCESSIVE_ENERGY.type, "days": [], "threshold": threshold})

    conflict_is_occurring = False
    for i in range(len(cumulative_power_array)):
        day_index = i // 1440
        minute_of_day = i % 1440
        day = DAYS[day_index]

        if cumulative_power_array[i] > threshold:
            if not conflict_is_occurring:
                start = minute_of_day
                conflict_is_occurring = True
            end = minute_of_day
        else:
            if conflict_is_occurring:
                start_conflict = f"{start // 60:02}:{start % 60:02}"
                end_conflict = f"{end // 60:02}:{end % 60:02}"
                key = f"{start_conflict}-{end_conflict}"

                if key not in conflicts_list:
                    conflicts_list[key].update({
                        "start": start_conflict,
                        "end": end_conflict,
                        "description": Conflict.EXCESSIVE_ENERGY.description.format(
                            treshold=threshold,
                            start=start_conflict,
                            end=end_conflict
                        )
                    })
                conflicts_list[key]["days"].append(day)
                conflict_is_occurring = False

    return list(conflicts_list.values())


def getFeasibilityConflicts(automation):
    '''
    Functions that checks if the given automation could be executed alone.
    The control evaluates the instantaneous power drawn by the automations and compare it to the maximum threshold possible. 
    If such treshold is exceeded, a corresponding conflict is produced
    '''
    threshold = get_configuration_item_by_key("power_threshold")  
    threshold=float(threshold["value"]) if threshold else POWER_TRESHOLD_DEFAULT

    automation_power=sum([x.get("maximum_power",0) for x in automation["action"]])
    if  automation_power>= threshold:
        return {
                "type":Conflict.NOT_FEASIBLE_AUTOMATION.type,
                "threshold":threshold,
                "description":Conflict.NOT_FEASIBLE_AUTOMATION.description.format(
                    treshold=threshold,automation_power=automation_power),
                "days":DAYS #FIXME: this is a patchwork to show something in the web app, remove in prod           
                }
    else:
        return None
    
def searchFutureActivationTime(device_list,automation_to_add,saved_automations):
    '''
    Looks for a new activation time in the future that could solve conflicts.
    '''
    # Get the list of conflicts
    conflicts = getConflicts(device_list,[automation_to_add]+saved_automations)
    
    # Base case: If there are no conflicts, return the current time
    if len(conflicts)<=0:
        return automation_to_add["time"]
    
    # Recursive case: Adjust the time to one unit after the end of the first conflict
    first_conflict_end = conflicts[0]["end"]
    if first_conflict_end>=automation_to_add["time"] and first_conflict_end<="23>59":
        automation_to_add["time"] = (datetime.datetime.strptime(first_conflict_end, "%H:%M") + timedelta(minutes=1)).strftime("%H:%M")
        # Recurse to resolve further conflicts
        return searchFutureActivationTime(device_list,automation_to_add,saved_automations)
    else:
        return ""

def searchPastActivationTime(device_list,automation_to_add,saved_automations):
    '''
    Looks for a new activation time in the past that could solve conflicts.
    '''
    # Get the list of conflicts
    conflicts = getConflicts(device_list,[automation_to_add]+saved_automations)
    
    # Base case: If there are no conflicts, return the current time
    if len(conflicts)<=0:
        return automation_to_add["time"]
    
    start_time = datetime.datetime.strptime(conflicts[0]["start"], "%H:%M")
    end_time = datetime.datetime.strptime(conflicts[0]["end"], "%H:%M")
    
    conflict_duration = (end_time - start_time).seconds // 60  
    automation_time = datetime.datetime.strptime(automation_to_add["time"], "%H:%M")

    new_automation_time = automation_time - timedelta(minutes=(conflict_duration +1))
    new_automation_time=new_automation_time.strftime("%H:%M")
    if new_automation_time<=automation_to_add["time"] and new_automation_time>="00:00":
        automation_to_add["time"] = new_automation_time
        return searchPastActivationTime(device_list,automation_to_add,saved_automations)
    else:
        return ""
    


def getChangeTimeSuggestions(first_conflict:dict, automation:dict, dev_list:list, saved_automations:list)->list[ConflictResolutionActivationTimeSuggestion]:
    """
    Search for possible suggestions that could solve excessive power demand conflicts.

    Args:
        first_conflict (dict): data of the first conflict that occurs. Use primarly for start and end of conflict.
        automation (dict): A dictionary containing automation configuration, including the "time" key.
        dev_list (list): A list of devices involved in automation.
        saved_automations (list): A list of saved automations for reference.

    Returns:
        list: A list of conflict resolution suggestions.
    """
    new_time_list=[]
    
    # Resolve past conflict
    automation_in_past = automation.copy()
    start_time = datetime.datetime.strptime(first_conflict["start"], "%H:%M")
    end_time = datetime.datetime.strptime(first_conflict["end"], "%H:%M")

    conflict_duration = (end_time - start_time).seconds // 60
    automation_in_past["time"] = (
        datetime.datetime.strptime(automation_in_past["time"], "%H:%M") - timedelta(minutes=(conflict_duration + 1))
    ).strftime("%H:%M")

    new_activation_time_past = searchPastActivationTime(dev_list, automation_in_past, saved_automations)
    if new_activation_time_past!="":
        new_time_list.append(new_activation_time_past)

    # Resolve future conflict
    automation_in_future = automation.copy()
    first_conflict_end = first_conflict["end"]
    automation_in_future["time"] = (
        datetime.datetime.strptime(first_conflict_end, "%H:%M") + timedelta(minutes=1)
    ).strftime("%H:%M")

    new_activation_time_future = searchFutureActivationTime(dev_list, automation_in_future, saved_automations)
    if new_activation_time_future!="":
        new_time_list.append(new_activation_time_future)


    return [ConflictResolutionActivationTimeSuggestion(new_activation_time=new_time_list)] if new_time_list else []


def getAutomationsToDeactivateSuggestions(conflict_list,saved_automations):
    suggestions=[]
    conflicting_automations = []

    for conflict in conflict_list:
        conflicting_automations = []
        #Deactivate overlapping automations
        conflict_time=datetime.datetime.strptime(conflict["start"], "%H:%M")
        #i need to find automations whose time is before conflict_time and time+maximum_duration after conflict time 
        for auto in [x for x in saved_automations if x["time"]!="" and x.get("average_power_drawn",0)>=2]:
            # Convert the automation time to a datetime object
            auto_time = datetime.datetime.strptime(auto["time"], "%H:%M:%S" if len(auto["time"].split(":")) == 3 else "%H:%M")
            duration=max(act["average_duration"] for act in auto["action"] if auto.get("action"))
            # Calculate the end time (automation_time + duration)
            auto_end_time = auto_time + timedelta(minutes=duration)
            
            # Check the conditions
            if auto_time <= conflict_time <= auto_end_time:
                conflicting_automations.append({"name":auto["name"],"id":auto["id"]})

        if len(conflicting_automations)>0:
            conflict["conflicting_automations"]=conflicting_automations
            suggestions.append(ConflictResolutionDeactivateAutomationsSuggestion(automations_list=conflicting_automations))

    return suggestions

#endregion

    
#region GetRouterFunction
def getAutomationRouter(enable_demo=False):
    automation_router=APIRouter(tags=["Automation"],prefix="/automation")

    @automation_router.get("")
    def Get_Automations(get_suggestions:bool=False):
        if enable_demo:
            return get_demo_automations() 
        else:
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
    def Simulate_Automation_Addition(automation_in:Automation,return_state_matrix:bool=True):
        start_call=datetime.datetime.now()
        conflicts=[]
        suggestions=[]

        #Get automations saved and details of the one we want to add
        automation=getAutomationDetails(automation_in.automation)
        saved_automations = Get_Automations()
        #TODO:de-comment this part in the final release
        #saved_automations=[a for a in saved_automations if a["state"]=="on"]
        new_automation_list=saved_automations+[automation]

        #Getting the list of devices
        dev_list=getDevicesFast()

        feasibilty_conflicts=getFeasibilityConflicts(automation)
        if feasibilty_conflicts:
            conflicts=[feasibilty_conflicts]

            sorted_actions=sorted(automation["action"], key=lambda x: x["average_power"])

            threshold = get_configuration_item_by_key("power_threshold")  
            threshold=float(threshold["value"]) if threshold else POWER_TRESHOLD_DEFAULT

            split_actions=[[]]
            current_total=0
            for action in sorted_actions:
                if current_total+action["average_power"]<threshold:
                    split_actions[-1].append(action)
                    current_total+=action["average_power"]
                else:
                    split_actions.append([action])
                    current_total=action["average_power"]

            suggestions.append(ConflictResolutionSplitSuggestion(actions_split=split_actions).to_dict())
        else:
        
            #Getting conflicts
            excessive_energy_conflicts=getConflicts(device_list=dev_list,automations_list=new_automation_list)

            #If there are conflicts i look for suggestions on how to solve them
            if len(excessive_energy_conflicts)>0:
                conflicts+=excessive_energy_conflicts
                suggestions+=getChangeTimeSuggestions(excessive_energy_conflicts[0],automation,dev_list,saved_automations)
                getAutomationsToDeactivateSuggestions(excessive_energy_conflicts,saved_automations)

                
                
    
        #Suggestions identification if no conflict occurs
        if len(conflicts)<=0 and automation["average_power_drawn"]>MIN_AUTOMATION_POWER:
            suggestions+=findBetterActivationTime(automation,dev_list,saved_automations)
        



        
        logger.debug(f"Simulate_Automation_Addition required {(datetime.datetime.now()-start_call).total_seconds()} [s]")

        ret={
            "automation":automation,
            "conflicts":conflicts,
            "suggestions":suggestions,
        }

        if return_state_matrix:
            state_matrix,cumulative_power_matrix=getStatePowerMatrix(device_list=dev_list,automations_list=new_automation_list)
            ret.update({
            "state_matrix":state_matrix,
            "cumulative_power_matrix":cumulative_power_matrix})
        return ret
    
    return automation_router

#endregion