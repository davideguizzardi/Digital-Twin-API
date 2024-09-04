from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import (
    getEntityRouter,getAutomationRouter,getServiceRouter,
    getConfigurationRouter,getMapConfigurationRouter,getVirtualRouter,
    getConsumptionRouter,getHistoryRouter,getTestRouter,
    getDeviceRouter,getHomeRouter,getEnergyCalendarConfigurationRouter
    )
from homeassistant_functions import initializeToken

import uvicorn



def create_api():
    api=FastAPI(title="Digial Twin API",docs_url="/")

    routers=[
        getEntityRouter(),
        getDeviceRouter(),
        getHomeRouter(),
        getHistoryRouter(),
        getConsumptionRouter(),
        getAutomationRouter(),
        getServiceRouter(),
        getConfigurationRouter(),
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
    uvicorn.run(api, host="0.0.0.0",log_level="debug")

if __name__ == "__main__":
    main()