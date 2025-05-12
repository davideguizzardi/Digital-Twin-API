import ipaddress
from fastapi import APIRouter,HTTPException

from database_functions import (
    initialize_database,
    get_all_configuration_values,get_configuration_item_by_key,add_configuration_values,delete_configuration_value,
    add_map_entities, get_all_map_entities,get_map_entity,delete_map_entry,delete_floor_map_configuration,
    get_energy_slot_by_day,get_all_energy_slots,add_energy_slots,delete_energy_slots,
    get_all_user_preferences,add_user_preferences,get_user_preferences_by_user,delete_user_preferences_by_user,
    get_all_user_privacy_settings,add_user_privacy_settings,get_user_privacy_settings_by_user,
    add_devices_configuration,get_all_devices_configuration,get_configuration_of_device,
    get_all_rooms_configuration,add_rooms_configuration,delete_rooms_in_floor,delete_single_room,get_all_rooms_of_floor,get_single_room_by_name,update_single_room
    )
from schemas import (
    Operation_Out,Map_Entity_List,
    Map_Entity,Configuration_Value,
    Configuration_Value_List,Energy_Plan_Calendar,
    User_Preference_List,User_Privacy_List,
    Home_Assistant_Configuration,
    Device_Configuration_List,
    Room_Configuration_List,Room_Name_Update
    )

from homeassistant_functions import setHomeAssistantConfiguration,getHomeAssistantConfiguration


#region ConfigurationRouter
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
        return get_configuration_item_by_key(key)
       
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
#endregion

#region HomeAssistantConfiguration

def getHomeAssistantConfigurationRouter():
    router=APIRouter(tags=["HomeAssistant Configuration"],prefix="/homeassistant")

    @router.get("")
    def Get_Home_Assistant_Configuraiton():
        try:
            return getHomeAssistantConfiguration()
        except Exception as e:
            raise HTTPException(status_code=404,detail=e)
        
    @router.put("",response_model=Operation_Out)
    def Add_Home_Assistant_Configuration(configuration:Home_Assistant_Configuration):
        if configuration.token and len(configuration.token)!=183:
            raise HTTPException(status_code=400,detail="Format of the token not correct")
        return {"success":setHomeAssistantConfiguration(configuration.token,configuration.server_url)}
    
    return router

#endregion

#region EnergyCalendar

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

#endregion

#region Map

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
#endregion

#region User
def getUserRouter():
    user_router=APIRouter(tags=["User"],prefix="/user")

    @user_router.get("/preferences")
    def Get_All_Preferences():
        preferences=get_all_user_preferences()
        res=[]
        for user in preferences:
            res.append({"user_id":user["user_id"],"preferences":user["preferences"].split(",")})
        return res
    
    @user_router.get("/preferences/{user_id}")
    def Get_Preferences_Of_Single_User(user_id:str):
        user= get_user_preferences_by_user(user_id)
        return {"user_id":user["user_id"],"preferences":user["preferences"].split(",")} if user else {}
    
    @user_router.put("/preferences",response_model=Operation_Out)
    def Add_User_Preferences(preferences_list:User_Preference_List):
        to_add=[]
        for user in preferences_list.data:
            to_add.append((user.user_id,','.join(user.preferences)))
        return {"success":add_user_preferences(to_add)}
    
    @user_router.get("/privacy")
    def Get_All_Privacy_settings():
        preferences=get_all_user_privacy_settings()
        res=[]
        for user in preferences:
            res.append({"user_id":user["user_id"],"data_collection":bool(user["data_collection"]),"data_disclosure":bool(user["data_disclosure"])})
        return res
    
    @user_router.get("/privacy/{user_id}")
    def Get_Privacy_Setting_Of_Single_User(user_id:str):
        user= get_user_privacy_settings_by_user(user_id)
        return {"user_id":user["user_id"],"data_collection":bool(user["data_collection"]),"data_disclosure":bool(user["data_disclosure"])} if user else {}
    
    @user_router.put("/privacy",response_model=Operation_Out)
    def Add_User_Privacy_Settings(privacy_list:User_Privacy_List):
        to_add=[]
        for user in privacy_list.data:
            to_add.append((user.user_id,user.data_collection,user.data_disclosure))
        return {"success":add_user_privacy_settings(to_add)}
    
    @user_router.delete("/{user_id}",response_model=Operation_Out)
    def Delete_All_User_Preferences(user_id:str):
        return {"success":delete_user_preferences_by_user(user_id)}

    
    return user_router
#endregion

#region Device_Configuration

def getDeviceConfigurationRouter():
    device_configuration_router=APIRouter(tags=["Device configuration"],prefix="/device_configuration")

    @device_configuration_router.get("")
    def Get_All_Entities():
        return get_all_devices_configuration()
    
    @device_configuration_router.get("/{device_id}")
    def Get_Single_Device_Configuration(device_id:str):
        return get_configuration_of_device(device_id)
    
    @device_configuration_router.put("",response_model=Operation_Out)
    def Add_Devices_Configuration(entities_list:Device_Configuration_List):
        return {"success":add_devices_configuration([tuple(d.__dict__.values()) for d in entities_list.data])}
    
    return device_configuration_router
#endregion


#region Room_Configuration

def getRoomConfigurationRouter():
    room_configuration_router=APIRouter(tags=["Room configuration"],prefix="/room")

    @room_configuration_router.get("")
    def Get_All_Rooms():
        return get_all_rooms_configuration()
    
    @room_configuration_router.get("/{floor}")
    def Get_Room_On_Floor(floor:int):
        return get_all_rooms_of_floor(floor)
    
    @room_configuration_router.put("",response_model=Operation_Out)
    def Add_Devices_Configuration(entities_list:Room_Configuration_List):
        return {"success":add_rooms_configuration([tuple(d.__dict__.values()) for d in entities_list.data])}
    
    @room_configuration_router.patch("/{room_name}",response_model=Operation_Out)
    def Update_Single_Device_Configuration(room_name,new_configuration:Room_Name_Update):
        return {"success":update_single_room(room_name,new_configuration.new_name)}
    

    @room_configuration_router.delete("/{name}",response_model=Operation_Out)
    def Delete_Room(name:str):
        return {"success":delete_single_room(name)}
    
    return room_configuration_router
#endregion