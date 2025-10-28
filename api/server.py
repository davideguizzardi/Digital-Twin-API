from fastapi import FastAPI,status,HTTPException,Depends
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
from routers.authenticationRouter import getAuthenticationRouter,get_current_user
from routers.healthCheckRouter import getHealthRouter

from homeassistant_functions import initializeToken,checkHomeAssistant
from database_functions import initialize_database,add_log,checkMongodb,checkConsumptionExtraction
from config_loader import HOST, PORT, ENABLE_DEMO, ENABLE_PREDICTION,ENABLE_AUTHENTICATION
import requests,logging,uvicorn,datetime,os


# Configure logging with Uvicorn-like format
logging.basicConfig(
    level=logging.INFO,
    format="%(levelprefix)s %(message)s",  # Matches Uvicorn's format
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Required for "levelprefix" to work (Uvicorn uses this)
logging.getLogger().handlers[0].setFormatter(uvicorn.logging.DefaultFormatter("%(levelprefix)s %(message)s"))



def create_api(enable_prediction:False,enable_demo:False):
    api=FastAPI(title="Digial Twin API",docs_url="/")

    open_routers=[
        getAuthenticationRouter(),
        getVirtualRouter(),
        getRulebotRouter(),
        getHealthRouter()
    ]

    protected_routers=[
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
    ]

    if enable_prediction:
        from routers.predictionRouter import getPredictionRouter
        protected_routers.append(getPredictionRouter()) 

    for router in open_routers:
        api.include_router(router)

    for router in protected_routers:
        api.include_router(router,dependencies=[Depends(get_current_user)]) if ENABLE_AUTHENTICATION else api.include_router(router)
        
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

    if ENABLE_DEMO:
        #initializeDemo()
        logger.info("Running server in demo mode.")
    else:
        logger.info("Initializing home assistant configuration and token...")
        initializeToken()

    api = create_api(ENABLE_PREDICTION,ENABLE_DEMO)
    add_log([("System","Startup","DTAPI","{}",datetime.datetime.now().replace(microsecond=0).timestamp())])
    uvicorn.run(api, host=HOST,port=PORT,log_level="debug")

if __name__ == "__main__":
    main()