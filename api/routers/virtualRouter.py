from fastapi import APIRouter, HTTPException
import json

def getVirtualRouter():
    virtual_router = APIRouter(tags=["Virtual"], prefix="/virtual")

    def load_virtual_context():
        """Helper function to load virtual context from JSON file."""
        with open("./data/virtual_context.json", "r") as file:
            return json.load(file)

    @virtual_router.get("/device")
    def Get_All_Devices(get_only_names: bool = False):
        virtual_context = load_virtual_context()
        return (
            virtual_context["device_context"]
            if not get_only_names
            else virtual_context["device_context_only_names"]
        )

    @virtual_router.get("/entity")
    def Get_All_Virtual_Entities():
        virtual_context = load_virtual_context()
        return virtual_context["entities_context"]

    @virtual_router.get("/entity/{entity_id}")
    def Get_Virtual_Entity(entity_id: str):
        virtual_context = load_virtual_context()
        temp = [x for x in virtual_context["entities_context"] if x["entity_id"] == entity_id]
        return temp[0] if temp else {}

    @virtual_router.get("/automation")
    def Get_Automations_Context():
        virtual_context = load_virtual_context()
        return virtual_context["automation_context"]

    return virtual_router
