from pydantic import BaseModel


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

class User_Log(BaseModel):
     user:str
     service:str
     target:str
     payload:str
     timestamp:int

class User_Log_List(BaseModel):
    data:list[User_Log]

class Configuration_Value(BaseModel):
    key:str
    value:str
    unit:str | None =None

class Configuration_Value_List(BaseModel):
    data:list[Configuration_Value]

class Energy_Plan_Calendar(BaseModel):
    data:list[list[int]]

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
				"target": {
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