from pydantic import BaseModel
import json

class Service_In(BaseModel):
    entity_id:str
    service: str
    data:dict | None
    user:str | None

class History_In(BaseModel):
    entity_id:str
    start_timestamp:str | None
    end_timestamp:str | None


class Operation_Out(BaseModel):
    success:bool

class Map_Entity(BaseModel):
    entity_id:str
    x:int
    y:int
    floor:int

class Map_Entity_List(BaseModel):
    data:list[Map_Entity]

class User_Preference(BaseModel):
    user_id:str
    preferences:list[str]

class User_Preference_List(BaseModel):
    data: list[User_Preference]

class User_Privacy(BaseModel):
    user_id:str
    data_collection:bool
    data_disclosure:bool

class User_Privacy_List(BaseModel):
    data: list[User_Privacy]

class User_Log(BaseModel):
     user:str
     service:str
     target:str
     payload:str
     timestamp:int

class User_Log_List(BaseModel):
    data:list[User_Log]


class Automation(BaseModel):
    automation:object

class Home_Assistant_Configuration(BaseModel):
    token:str | None=None
    server_url:str | None=None

class Configuration_Value(BaseModel):
    key:str
    value:str
    unit:str | None =None

class Configuration_Value_List(BaseModel):
    data:list[Configuration_Value]

class Energy_Plan_Calendar(BaseModel):
    data:list[list[int]]


class Device_Configuration(BaseModel):
    device_id:str
    name:str
    category:str
    show:int = 1

class Device_Configuration_List(BaseModel):
    data:list[Device_Configuration]


class Room_Configuration(BaseModel):
    name:str
    floor:int
    points:str="[x,y,x,y...]"

class Room_Name_Update(BaseModel):
    new_name:str

class Room_Configuration_List(BaseModel):
    data:list[Room_Configuration]


class Group_Configuration(BaseModel):
    name: str

class Group_Name_Update(BaseModel):
    new_name: str

class Group_Configuration_List(BaseModel):
    data: list[Group_Configuration]

class DeviceGroupMapping(BaseModel):
    device_id: str
    group_id: int

class DeviceGroupMappingList(BaseModel):
    data: list[DeviceGroupMapping]


class Log(BaseModel):
    actor:str
    event:str
    target:str
    payload:str

class Log_List(BaseModel):
    data:list[Log]

class AutomationStateUpdate(BaseModel):
    automation_id: str
    state: str 



triggers={
    "device_trigger":{
        "platform":"device",#costante non cambiare
        "domain":"domain_name",
        "type":"type",
        "device_id":"guiddevice",
        "entity_id":"guidentity"
    },
    "time_trigger":{
        "platform":"time",
        "at":"hh:MM:ss"
    },
    "time_pattern_trigger":{
        "plaform":"time_pattern",
        "hours":"1",
        "minutes":"1",
        "seconds":"1"#es. l'automazione si attiverà al primo secondo della primo minuto della prima ora 
    },
    "sun_trigger":{
        "platform":"sun",
        "event":"sunset|sunrise",
        "offset":"0"#scostamento dall'alba o tramonto in secondi
    },
    "conversation_trigger":{
        "platform":"conversation",
        "command":"command to invoke automation"
    }
}

conditions={
    "time_conditions":{
			"condition": "time",
			"weekday": [
				"mon",
				"tue"
				"wed",
				"thu",
				"fri",
				"sat",
                "sun"
			]
		}
}


actions={
    "device_action":{
        "domain":"domain_name",
        "type":"type", #nome servizio da attivare
        "device_id":"guiddevice",
        "entity_id":"guidentity"
    },
    "service_action":{
				"service": "service",
				"metadata": {},
				"data": {},
				"target": { #può comparire anche solo uno dei tre
					"area_id": [
						"area_virtuale_1"
					],
					"device_id": [
						"d8e7d38f46840148b64b2c0c548a7c7f"
					],
					"entity_id": [
						"light.virtual_lights_1"
					]
				}
			}
}

CONFIGURATION_PATH="./data/configuration.txt"
def point_in_polygon(x, y, poly_points):
    """
    Ray casting algorithm to check if a point is inside a polygon.
    poly_points: list of flat coordinates [x1, y1, x2, y2, ..., xn, yn]
    """
    n = len(poly_points) // 2
    inside = False
    px, py = x, y
    for i in range(n):
        xi, yi = poly_points[2 * i], poly_points[2 * i + 1]
        xj, yj = poly_points[2 * ((i + 1) % n)], poly_points[2 * ((i + 1) % n) + 1]

        intersect = ((yi > py) != (yj > py)) and \
                    (px < (xj - xi) * (py - yi) / (yj - yi + 1e-10) + xi)
        if intersect:
            inside = not inside
    return inside

def find_room(x, y, rooms):
    """
    Identifies the room where the point (x, y) is located on the given floor.
    Returns the room dict or None if not found.
    """
    for room in rooms:
        try:
            points = json.loads(room['points'])  # Convert string to list
        except json.JSONDecodeError:
            continue
        if point_in_polygon(x, y, points):
            return room["name"]
    return None