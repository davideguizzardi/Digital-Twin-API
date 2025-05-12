from fastapi import APIRouter,HTTPException
from multiprocessing import Pool

from homeassistant_functions import (
    callService)
from database_functions import (
    get_all_service_logs,add_service_logs,get_service_logs_by_user)
from schemas import (
    Service_In,Operation_Out,
    User_Log,User_Log_List

    )

from database_functions import add_log

import json,datetime


def getServiceRouter():
    service_router=APIRouter(tags=["Service"],prefix="/service")
    @service_router.post("")
    def Call_Service(service:Service_In):
        res=callService(service=service)
        if res["status_code"]!=200:
            raise HTTPException(status_code=res["status_code"],detail=res["data"])
        add_log([(service.user,f"Service:{service.service}",service.entity_id,json.dumps(service.data),datetime.datetime.now().replace(microsecond=0).timestamp())])
        #add_service_logs([(service.user,service.service,service.entity_id,json.dumps(service.data),datetime.datetime.now().replace(microsecond=0).timestamp())])
        return res["data"]
    

    @service_router.get("/logs",response_model=list[User_Log])
    def Get_All_Service_Logs():
        return get_all_service_logs()
    
    @service_router.get("/logs/{user}",response_model=list[User_Log])
    def Get_Service_Logs_By_User(user:str):
        return get_service_logs_by_user(user)
    
    @service_router.put("/logs",response_model=Operation_Out)
    def Add_Service_logs(logs_list:User_Log_List):
        return {"success":add_service_logs([tuple(d.__dict__.values()) for d in logs_list.data])}
    
    return service_router