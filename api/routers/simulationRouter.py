from fastapi import APIRouter, HTTPException
import json

def getSimulationRouter():
    Simulation_router = APIRouter(tags=["Simulation"], prefix="/Simulation")

    def load_Simulation_context():
        """Helper function to load Simulation context from JSON file."""
        with open("./data/Simulation_context.json", "r") as file:
            return json.load(file)

    @Simulation_router.get("/device/{device_id}")
    def Get_Device_Simulation(device_id: str):
        with open(f"./data/devices_simulations/{device_id}.json", "r") as file:
            return json.load(file)

    return Simulation_router