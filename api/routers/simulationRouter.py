from fastapi import APIRouter, HTTPException
import json,os

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
        
    @Simulation_router.get("/house/{house_id}")
    def Get_House_Simulation(house_id: str):
        folder_path = f"./data/devices_simulations/{house_id}"

        if not os.path.isdir(folder_path):
            raise HTTPException(status_code=404, detail="House not found")

        simulations = []

        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            with open(file_path, "r") as file:
                simulations.append(json.load(file))

        return simulations

    return Simulation_router