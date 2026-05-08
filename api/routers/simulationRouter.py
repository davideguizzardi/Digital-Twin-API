from fastapi import APIRouter, HTTPException
import json,os
import numpy as np

def getSimulationRouter():
    Simulation_router = APIRouter(tags=["Simulation"], prefix="/Simulation")

    def load_Simulation_context():
        """Helper function to load Simulation context from JSON file."""
        with open("./data/Simulation_context.json", "r") as file:
            return json.load(file)
        

    def resample_sequence(seq, target_length):
        """
        Resample sequence to a new length using linear interpolation.
        """
        original_length = len(seq)
        
        x_old = np.linspace(0, 1, original_length)
        x_new = np.linspace(0, 1, target_length)
        
        return list(np.interp(x_new, x_old, np.array(seq)))

    @Simulation_router.get("/device/{device_id}")
    def Get_Device_Simulation(device_id: str):
        with open(f"./data/devices_simulations/{device_id}.json", "r") as file:
            return json.load(file)
        
    @Simulation_router.get("/resample/{device_id}/")
    def Get_Device_Simulation(device_id: str,mode:str,new_length:int):
        with open(f"./data/devices_simulations/{device_id}.json", "r") as file:
            modes= json.load(file)
            sequence=[x for x in modes["clusters"] if str(x["id"])==mode][0]
            return resample_sequence(sequence["medoid"],new_length)
        
        
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