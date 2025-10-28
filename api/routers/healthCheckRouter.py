import requests
from fastapi import status,HTTPException,APIRouter
from fastapi.responses import JSONResponse

from database_functions import checkMongodb,checkConsumptionExtraction
from homeassistant_functions import checkHomeAssistant

def check_frontend(url: str):
    try:
        resp = requests.get(url, timeout=3, verify=False)  # ignore SSL validation
        return resp.status_code == 200
    except Exception as e:
        print(f"Frontend check failed for {url}: {e}")
        return False

def getHealthRouter():
    router=APIRouter(tags=["Healthcheck"],prefix="/health")

    @router.get("/")
    def health():
        results= {
            "fastapi": True,  # if this runs, FastAPI is alive
            "mongodb": checkMongodb(),
            "home_assistant": checkHomeAssistant(),
            "digital_twin": check_frontend("https://192.168.1.118/login"),
            "rulebot": check_frontend("https://192.168.1.118:8888")
        }
        all_ok = all(results.values())
        if all_ok:
            return results
        else:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "One or more services are down", "details": results}
            )
        
    @router.get("/consumption")
    def health_consumption():
        consumption_extraction=checkConsumptionExtraction()
        if consumption_extraction:
            return {"consumption_extraction":consumption_extraction}
        else:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "The system didn't poll the consumption for more than one hour"}
            )
        
    return router