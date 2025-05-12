from fastapi import APIRouter, HTTPException
from schemas import Log_List,Operation_Out
from database_functions import add_log
from datetime import datetime

def getLogRouter():
    log_router = APIRouter(tags=["Log"], prefix="/log")

    @log_router.put("",response_model=Operation_Out)
    def Add_Log(logs_list:Log_List):
        tuple_list=[(x.actor,x.event,x.target,x.payload,datetime.now().replace(microsecond=0).timestamp()) for x in logs_list.data]
        return {"success":add_log(tuple_list)}


    return log_router
