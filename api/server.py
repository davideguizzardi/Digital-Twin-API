from fastapi import FastAPI,status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from routers.entityRouter import getEntityRouter
from routers.automationRouter import getAutomationRouter
from routers.serviceRouter import getServiceRouter
from routers.configurationRouter import getConfigurationRouter
from routers.configurationRouter import getMapConfigurationRouter
from routers.configurationRouter import getEnergyCalendarConfigurationRouter
from routers.configurationRouter import getUserRouter
from routers.configurationRouter import getDeviceConfigurationRouter
from routers.configurationRouter import getRoomConfigurationRouter
from routers.configurationRouter import getGroupConfigurationRouter
from routers.configurationRouter import getDeviceGroupRouter
from routers.consumptionRouter import getConsumptionRouter
from routers.configurationRouter import getHomeAssistantConfigurationRouter
from routers.historyRouter import getHistoryRouter
from routers.deviceRouter import getDeviceRouter
from routers.logsRouter import getLogRouter
from routers.virtualRouter import getVirtualRouter
from routers.rulebotRouter import getRulebotRouter

from homeassistant_functions import initializeToken,initializeDemo,checkHomeAssistant
from database_functions import initialize_database,get_configuration_value_by_key,add_log,checkMongodb,checkConsumptionExtraction
from schemas import CONFIGURATION_PATH
import requests
import logging,uvicorn,datetime

# Configure logging with Uvicorn-like format
logging.basicConfig(
    level=logging.INFO,
    format="%(levelprefix)s %(message)s",  # Matches Uvicorn's format
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Required for "levelprefix" to work (Uvicorn uses this)
logging.getLogger().handlers[0].setFormatter(uvicorn.logging.DefaultFormatter("%(levelprefix)s %(message)s"))

def check_frontend(url: str):
    try:
        resp = requests.get(url, timeout=3, verify=False)  # ignore SSL validation
        return resp.status_code == 200
    except Exception as e:
        print(f"Frontend check failed for {url}: {e}")
        return False


def create_api(enable_prediction:False,enable_demo:False):
    api=FastAPI(title="Digial Twin API",docs_url="/")

    routers=[
        getEntityRouter(enable_demo),
        getDeviceRouter(enable_demo),
        getHistoryRouter(),
        getConsumptionRouter(),
        getAutomationRouter(enable_demo),
        getServiceRouter(),
        getConfigurationRouter(),
        getHomeAssistantConfigurationRouter(),
        getDeviceConfigurationRouter(),
        getRoomConfigurationRouter(),
        getGroupConfigurationRouter(),
        getDeviceGroupRouter(),
        getUserRouter(),
        getMapConfigurationRouter(),
        getEnergyCalendarConfigurationRouter(),
        getLogRouter(),
        getVirtualRouter(),
        getRulebotRouter()
    ]

    if enable_prediction:
        from routers.predictionRouter import getPredictionRouter
        routers.append(getPredictionRouter())

    for router in routers:
        api.include_router(router)

    @api.get("/health")
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
        
    @api.get("/health/consumption")
    def health_consumption():
        consumption_extraction=checkConsumptionExtraction()
        if consumption_extraction:
            return {"consumption_extraction":consumption_extraction}
        else:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "The system didn't poll the consumption for more than one hour"}
            )

        
    api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    )
    
    api.mount("/files", StaticFiles(directory="./data"), name="files")
    
    return api




def main():
    logger = logging.getLogger(__name__)

    initialize_database()

    host=get_configuration_value_by_key("host")
    host=host["value"] or "0.0.0.0"

    port=get_configuration_value_by_key("port")
    port=int(port["value"] or 8000)
    
    enable_prediction=get_configuration_value_by_key("enable_prediction")
    enable_prediction=enable_prediction["value"] =="1"

        
    enable_demo=get_configuration_value_by_key("enable_demo")
    enable_demo=enable_demo["value"]=="1"

    if enable_demo:
        initializeDemo()
        logger.info("Running server in demo mode.")
    else:
        logger.info("Initializing home assistant configuration and token...")
        initializeToken()

    api = create_api(enable_prediction,enable_demo)
    add_log([("System","Startup","DTAPI","{}",datetime.datetime.now().replace(microsecond=0).timestamp())])
    uvicorn.run(api, host=host,port=port,log_level="debug")

if __name__ == "__main__":
    main()