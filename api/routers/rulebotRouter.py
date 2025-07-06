from fastapi import APIRouter, HTTPException
from schemas import  Operation_Out, AutomationStateUpdate
from database_functions import add_log
from database_functions import set_automation_state 
from datetime import datetime

def getRulebotRouter():
    rulebot_router = APIRouter(tags=["Rulebot"], prefix="/rulebot")

    @rulebot_router.put("/automation/state")
    def update_automation_state(update: AutomationStateUpdate):
        try:
            set_automation_state(update.automation_id, update.state)
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return rulebot_router
