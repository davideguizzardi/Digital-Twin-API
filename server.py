from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers_old import (
    getTestRouter
    ,getHomeRouter
    )
from routers.entityRouter import getEntityRouter
from routers.automationRouter import getAutomationRouter
from routers.serviceRouter import getServiceRouter
from routers.configurationRouter import getConfigurationRouter
from routers.configurationRouter import getMapConfigurationRouter
from routers.configurationRouter import getEnergyCalendarConfigurationRouter
from routers.configurationRouter import getUserRouter
from routers.virtualRouter import getVirtualRouter
from routers.consumptionRouter import getConsumptionRouter
from routers.historyRouter import getHistoryRouter
from routers.deviceRouter import getDeviceRouter
from routers.predictionRouter import getPredictionRouter
from homeassistant_functions import initializeToken

import uvicorn



def create_api():
    api=FastAPI(title="Digial Twin API",docs_url="/")

    routers=[
        getPredictionRouter(),
        getEntityRouter(),
        getDeviceRouter(),
        getHomeRouter(),
        getHistoryRouter(),
        getConsumptionRouter(),
        getAutomationRouter(),
        getServiceRouter(),
        getConfigurationRouter(),
        getUserRouter(),
        getMapConfigurationRouter(),
        getEnergyCalendarConfigurationRouter(),
        getVirtualRouter(),
        getTestRouter()
    ]

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
    api = create_api()
    uvicorn.run(api, host="0.0.0.0",port=8000,log_level="debug")

if __name__ == "__main__":
    main()