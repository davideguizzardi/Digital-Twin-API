from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.entityRouter import getEntityRouter
from routers.automationRouter import getAutomationRouter
from routers.serviceRouter import getServiceRouter
from routers.configurationRouter import getConfigurationRouter
from routers.configurationRouter import getMapConfigurationRouter
from routers.configurationRouter import getEnergyCalendarConfigurationRouter
from routers.configurationRouter import getUserRouter
from routers.consumptionRouter import getConsumptionRouter
from routers.historyRouter import getHistoryRouter
from routers.deviceRouter import getDeviceRouter

from homeassistant_functions import initializeToken
from schemas import CONFIGURATION_PATH
import configparser

import uvicorn



def create_api(enable_prediction:False):
    api=FastAPI(title="Digial Twin API",docs_url="/")

    routers=[
        getEntityRouter(),
        getDeviceRouter(),
        #getHomeRouter(),
        getHistoryRouter(),
        getConsumptionRouter(),
        getAutomationRouter(),
        getServiceRouter(),
        getConfigurationRouter(),
        getUserRouter(),
        getMapConfigurationRouter(),
        getEnergyCalendarConfigurationRouter(),
        #getVirtualRouter(),
        #getTestRouter()
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
    initializeToken()
    parser=configparser.ConfigParser()
    parser.read(CONFIGURATION_PATH)
    
    host=parser["Network"]["host"] if 'host' in parser["Network"] else "0.0.0.0"
    port = int(parser["Network"]['port']) if 'port' in parser["Network"] else 8000

    enable_prediction=parser.getboolean("ApiConfiguration","enable_prediction")
    api = create_api(enable_prediction)
    uvicorn.run(api, host=host,port=port,log_level="debug")

if __name__ == "__main__":
    main()