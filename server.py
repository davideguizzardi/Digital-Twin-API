from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import (
    getEntityRouter,getAutomationRouter,getServiceRouter,
    getConfigurationRouter,getMapConfigurationRouter,getVirtualRouter,
    getDeviceRouter,getHistoryRouter,getHomeRouter,getEnergyCalendarConfigurationRouter
    )
from homeassistant_functions import initializeToken

import uvicorn



def create_api():
    api=FastAPI(title="Digial Twin API",docs_url="/")

    entity_router=getEntityRouter()
    device_route=getDeviceRouter()
    home_router=getHomeRouter()
    history_router=getHistoryRouter()
    automation_router=getAutomationRouter()
    service_router=getServiceRouter()
    configuration_router=getConfigurationRouter()
    map_configuration_router=getMapConfigurationRouter()
    energy_calendar_router=getEnergyCalendarConfigurationRouter()
    virtual_router=getVirtualRouter()
    
    api.include_router(entity_router)
    api.include_router(device_route)
    api.include_router(home_router)
    api.include_router(history_router)
    api.include_router(automation_router)
    api.include_router(service_router)
    api.include_router(configuration_router)
    api.include_router(map_configuration_router)
    api.include_router(energy_calendar_router)
    api.include_router(virtual_router)

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
    uvicorn.run(api, host="0.0.0.0")

if __name__ == "__main__":
    main()