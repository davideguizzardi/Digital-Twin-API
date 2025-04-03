from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.entityRouter import getEntityRouter
from routers.automationRouter import getAutomationRouter
from routers.serviceRouter import getServiceRouter
from routers.configurationRouter import getConfigurationRouter
from routers.configurationRouter import getMapConfigurationRouter
from routers.configurationRouter import getEnergyCalendarConfigurationRouter
from routers.configurationRouter import getUserRouter
from routers.configurationRouter import getDeviceConfigurationRouter
from routers.consumptionRouter import getConsumptionRouter
from routers.configurationRouter import getHomeAssistantConfigurationRouter
from routers.historyRouter import getHistoryRouter
from routers.deviceRouter import getDeviceRouter
from routers.virtualRouter import getVirtualRouter

from homeassistant_functions import initializeToken
from database_functions import initialize_database
from schemas import CONFIGURATION_PATH
import configparser
import logging
import uvicorn

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
        getUserRouter(),
        getMapConfigurationRouter(),
        getEnergyCalendarConfigurationRouter(),
        getVirtualRouter(),
    ]

    if enable_prediction:
        from routers.predictionRouter import getPredictionRouter
        routers.append(getPredictionRouter())

    for router in routers:
        api.include_router(router)
        
    api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    )
    
    return api




def main():
    logger = logging.getLogger(__name__)

    initialize_database()
    
    parser=configparser.ConfigParser()
    parser.read(CONFIGURATION_PATH)
    
    host=parser["Network"]["host"] if 'host' in parser["Network"] else "0.0.0.0"
    port = int(parser["Network"]['port']) if 'port' in parser["Network"] else 8000

    enable_prediction=parser.getboolean("ApiConfiguration","enable_prediction")
    enable_demo=parser.getboolean("ApiConfiguration","enable_demo")
    

    if enable_demo:
        logger.info("Running server in demo mode.")
    else:
        logger.info("Initializing home assistant configuration and token...")
        initializeToken()

    api = create_api(enable_prediction,enable_demo)
    uvicorn.run(api, host=host,port=port,log_level="debug")

if __name__ == "__main__":
    main()