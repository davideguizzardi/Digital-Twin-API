from fastapi import APIRouter,HTTPException
from fastapi.responses import JSONResponse
import datetime
from dateutil import tz

from joblib import load as scalerload
import keras 
from datetime import datetime,timedelta
from dateutil import tz
import numpy as np
import pandas as pd
import json,os,time
from threading import Lock

from database_functions import fetch_multiple_elements,DbPathEnum,get_usage_entry_for_appliance_state
from homeassistant_functions import getSingleDeviceFast

FUTURE_STEPS_RECURSIVE=12
FUTURE_STEPS_SEQUENTIAL=6
PREVIOUS_STEPS=24
FILENAME_SEQUENTIAL="./prediction_models/15-11-2024-12-38_Prev48_Next6_minmaxscaling"
FILENAME_RECURSIVE="./prediction_models/16-12-2024-16-43_Prev24_Next1_noscalerscaling"
FILENAME_POWER="./prediction_models/power_11-03-2025-23-43_Prev120_Next60_noscalerscaling"
PREVIOUS_POWER_STEPS=120
FUTURE_POWER_STEPS=60
CACHE_TTL_SECONDS=60*10

prediction_cache = {
    "result": None,
    "timestamp": 0,
    "lock": Lock()
}


def load_model_and_scaler(model_path,scaler_path=None):
    model=keras.saving.load_model(model_path, custom_objects=None, compile=False, safe_mode=True)
    model.compile(optimizer="adam",loss="mse",metrics=["mse"])

    scaler=None
    if os.path.exists(scaler_path):
        scaler=scalerload(scaler_path)

    return model,scaler

def prepare_dataset(scaler, consumption_data):
    for item in consumption_data:
        weekday,is_weekend=getDayIndicator(item["end"])
        item["weekday"]=weekday
        #item["is_weekend"]=is_weekend
        item["time_session"]=getTimeSession(item["end"])

    dataset_complete=pd.DataFrame.from_dict(consumption_data)
    #dataset_complete=dataset_complete[["date","end","energy_consumption","weekday","is_weekend","time_session"]]
    dataset_complete=dataset_complete[["date","end","energy_consumption","weekday","time_session"]]


    if scaler:
        dataset_complete['energy_consumption_scaled'] = scaler.fit_transform(dataset_complete[['energy_consumption']])
    else:
        dataset_complete['energy_consumption_scaled'] = dataset_complete['energy_consumption']

    dataset_complete=dataset_complete[dataset_complete.columns[3:]]
    return dataset_complete

def predictSequence(model,x_to_predict,use_weighted_average=False,scaler_in=None,future_steps=FUTURE_STEPS_RECURSIVE):
    # Predict the values (assuming the model provides multiple overlapping predictions)
    y_predict_raw = model.predict(x_to_predict)  # shape: (samples, FUTURE_STEPS)

    y_predict = scaler_in.inverse_transform(y_predict_raw) if scaler_in else y_predict_raw


    final = [0] * len(y_predict)  # Initialize a list of zeros for the final predictions

    if len(y_predict) == 1:
        return y_predict
    # Loop through each prediction sample
    for i in range(len(final)):
        temp_list = []
        
        # Loop through the overlapping predictions
        max_j=min(future_steps,i+1)

        if use_weighted_average:
            # Generate weight array (exponentially decaying) based on number of overlapping predictions
            temp_weights = np.exp(np.linspace(-1, 0, num=max_j))  # Exponential decay pattern
            
            # Normalize the weights so they sum to 1
            temp_weights = temp_weights / np.sum(temp_weights)

        for j in range(max_j):
            if use_weighted_average:
                temp_list.append(y_predict[i - j][j]*temp_weights[j])  # Append the overlapping value
            else:
                temp_list.append(y_predict[i - j][j])
        
        # Compute the simple average of the overlapping values
        if use_weighted_average:
            final[i] = np.sum(temp_list)
        else:
            final[i] = np.mean(temp_list)
    return np.array(final)


def predictSequenceReverse(model,x_to_predict,use_weighted_average=False,scaler_in=None,future_steps=FUTURE_STEPS_SEQUENTIAL):
    # Predict the values (assuming the model provides multiple overlapping predictions)
    y_predict_raw = model.predict(x_to_predict)  # shape: (samples, FUTURE_STEPS)

    y_predict = scaler_in.inverse_transform(y_predict_raw) if scaler_in else y_predict_raw


    final = [0] * len(y_predict)  # Initialize a list of zeros for the final predictions

    # Loop through each prediction sample backwards
    for i in range(len(y_predict) - 1, -1, -1):
        temp_list = []
        
        # Loop through the overlapping predictions in reverse
        max_j = min(future_steps, len(y_predict) - i)

        if use_weighted_average:
            # Generate weight array (exponentially decaying) based on number of overlapping predictions
            temp_weights = np.exp(np.linspace(-1,0, num=max_j)) # Exponential decay pattern
            
            # Normalize the weights so they sum to 1
            temp_weights = temp_weights / np.sum(temp_weights)

        for j in range(max_j):
            if use_weighted_average:
                temp_list.append(y_predict[i + j][future_steps - 1 - j] * temp_weights[j])  # Use reverse index
            else:
                temp_list.append(y_predict[i + j][future_steps - 1 - j])
        
        # Compute the simple average of the overlapping values
        if use_weighted_average:
            final[i] = np.sum(temp_list)
        else:
            final[i] = np.mean(temp_list)
    return np.array(final)


def predictSequenceRecursive(model,dataset_to_predict,scaler,last_date,consumption_delta=[],future_steps=FUTURE_STEPS_RECURSIVE):
    incremental_prediction=[]
    dataset_incremental=dataset_to_predict
    j=0
    temp_date=last_date+timedelta(hours=1)
    for i in range(future_steps):
        X_in=create_sequences(dataset_incremental)
        y = model.predict(X_in[-1].reshape(1, *X_in.shape[1:])) 
        pred_value=float(scaler.inverse_transform(y)[0][0]) if scaler else y[0][0]
        if j<len(consumption_delta):
            pred_value+=consumption_delta[j]
            j+=1
        incremental_prediction.append(max(pred_value,0))
        weekday,is_weekend=getDayIndicator(temp_date.timestamp())

        new_row = {
            "weekday": weekday,
            #"is_weekend": is_weekend,
            "time_session": getTimeSession(temp_date.timestamp()),
            "energy_consumption_scaled": scaler.transform([[pred_value]])[0][0] if scaler else y[0][0] 
        }
        dataset_incremental = pd.concat([dataset_incremental, pd.DataFrame([new_row])], ignore_index=True)
        temp_date=temp_date+timedelta(hours=1)
    return incremental_prediction

def predictSequenceRecursivePower(model,dataset_to_predict,scaler,last_date,consumption_delta=[],future_steps=FUTURE_STEPS_RECURSIVE):
    incremental_prediction=[]
    dataset_incremental=dataset_to_predict
    j=0
    temp_date=last_date+timedelta(hours=1)
    for i in range(future_steps):
        X_in=create_sequences(dataset_incremental,n_timesteps=PREVIOUS_POWER_STEPS)
        y = model.predict(X_in[-1].reshape(1, *X_in.shape[1:])) 
        pred_value=float(scaler.inverse_transform(y)[0][0]) if scaler else y[0][0]
        if j<len(consumption_delta):
            pred_value+=consumption_delta[j]
            j+=1
        incremental_prediction.append(max(pred_value,0))
        weekday,is_weekend=getDayIndicator(temp_date.timestamp())

        new_row = {
            "weekday": weekday,
            #"is_weekend": is_weekend,
            "time_session": getTimeSession(temp_date.timestamp()),
            "power_scaled": scaler.transform([[pred_value]])[0][0] if scaler else y[0][0] 
        }
        dataset_incremental = pd.concat([dataset_incremental, pd.DataFrame([new_row])], ignore_index=True)
        temp_date=temp_date+timedelta(hours=1)
    return incremental_prediction


def create_sequences(X_train, n_timesteps=PREVIOUS_STEPS):
    """
    Converts X_train into sequences with n_timesteps for LSTM input.
    Each sequence is of length n_timesteps.

    Parameters:
        X_train (np.array): The input data for training.
        n_timesteps (int): The number of timesteps for each sequence.

    Returns:
        np.array: Sequences reshaped for LSTM input.
    """
    # Convert DataFrame to NumPy array if it's not already
    if isinstance(X_train, pd.DataFrame):
        X_train = X_train.values

    # Initialize list to hold sequences
    sequences = []

    # Loop through the data and create sequences
    for i in range(len(X_train) - n_timesteps + 1):
        # Get the sequence of n_timesteps
        seq = X_train[i: i + n_timesteps]
        sequences.append(seq)

    # Convert list of sequences to a NumPy array
    sequences = np.array(sequences)

    # Reshape if necessary to (samples, timesteps, features)
    return sequences.reshape(-1, n_timesteps, X_train.shape[1])


def getDayIndicator(timestamp):
    date_to_check=datetime.fromtimestamp(timestamp).astimezone(tz.tzlocal())
    return (date_to_check.weekday(),1 if date_to_check.weekday() in [5,6] else 0)

def getTimeSession(timestamp):
    date_to_check=datetime.fromtimestamp(timestamp).astimezone(tz.tzlocal())
    hour=date_to_check.hour

    if 0<=hour and hour<6:
        return 0
    
    if 6<=hour and hour<10:
        return 1
    
    if 10<= hour and hour<18:
        return 2
    
    if hour>=18 and hour<=23:
        return 3
    

def getPredictionRouter():
    prediction_router=APIRouter(tags=["Prediction"],prefix="/prediction")

    @prediction_router.get("/sequential")
    def Get_Sequential_Consumption_Prediction():
        model=keras.saving.load_model(f"{FILENAME_SEQUENTIAL}.keras", custom_objects=None, compile=False, safe_mode=True)
        model.compile(optimizer="adam",loss="mse",metrics=["mse"])

        scaler=scalerload(f"{FILENAME_SEQUENTIAL}.bin")
        selected_date=datetime.now().astimezone(tz.tzlocal())
        query = (
            "SELECT date, end, energy_consumption,energy_consumption_unit FROM ("
            "    SELECT strftime('%d-%m-%Y %H', start, 'unixepoch', 'localtime') || '-' || strftime('%H', end, 'unixepoch', 'localtime') AS 'date',"
            "           end, SUM(energy_consumption) AS 'energy_consumption',energy_consumption_unit"
            "    FROM Hourly_Consumption"
            f"    WHERE end<={selected_date.timestamp()}"
            "    GROUP BY strftime('%d-%m-%Y %H', start, 'unixepoch', 'localtime')"
            "    ORDER BY start DESC"
            f"    LIMIT {PREVIOUS_STEPS+FUTURE_STEPS_SEQUENTIAL}"#TODO:extract this value from model
            ") AS recent_rows"
            " ORDER BY end ASC"
        )

        consumption_data=fetch_multiple_elements(DbPathEnum.CONSUMPTION,query)

        last_date=datetime.fromtimestamp(consumption_data[-1]["end"]).astimezone(tz.tzlocal())

        unit=consumption_data[-1]["energy_consumption_unit"]
        result=[{k:d[k] for k in ["date","energy_consumption","energy_consumption_unit"] if k in d} for d in consumption_data][-FUTURE_STEPS_SEQUENTIAL:]
        

        if len(consumption_data)<48:
            raise HTTPException(404,"Non sai programmare!")

        for item in consumption_data:
            weekday,is_weekend=getDayIndicator(item["end"])
            item["weekday"]=weekday
            #item["is_weekend"]=is_weekend
            item["time_session"]=getTimeSession(item["end"])

        dataset_complete=pd.DataFrame.from_dict(consumption_data)
        #dataset_complete=dataset_complete[["date","end","energy_consumption","weekday","is_weekend","time_session"]]
        dataset_complete=dataset_complete[["date","end","energy_consumption","weekday","time_session"]]

        if scaler:
            dataset_complete['energy_consumption_scaled'] = scaler.fit_transform(dataset_complete[['energy_consumption']])
        else:
            dataset_complete['energy_consumption_scaled'] = dataset_complete['energy_consumption']

        dataset_complete=dataset_complete[dataset_complete.columns[3:]]
        X_in1=create_sequences(dataset_complete)
        #y_predict_raw = model.predict(X_in1)  # shape: (samples, FUTURE_STEPS)
        #y_predict = scaler.inverse_transform(y_predict_raw) if scaler else y_predict_raw
        y_predict=predictSequenceReverse(model,X_in1,use_weighted_average=False,scaler_in=scaler)
        y_predict=y_predict.tolist()

        for i in range(FUTURE_STEPS_SEQUENTIAL):
            date_str=f"{last_date.strftime('%d-%m-%Y %H-')}{(last_date+timedelta(hours=1)).strftime('%H')}"
            energy_cons=y_predict[i]
            result.append({"date":date_str,"energy_consumption":energy_cons,"energy_consumption_unit":unit})
            last_date+=timedelta(hours=1)

        return result
    


    @prediction_router.get("/power")#TODO: this is a copy of the previous one, pls refactor
    def Get_Power_Consumption_Prediction():
        model,scaler=load_model_and_scaler(f"{FILENAME_POWER}.keras",f"{FILENAME_POWER}.bin")
        
        selected_date=datetime.now().astimezone(tz.tzlocal())
        query = (
            "SELECT date, timestamp, power FROM ("
            "    SELECT strftime('%d-%m-%Y %H:%M', timestamp, 'unixepoch', 'localtime') as 'date',"
            "           timestamp, SUM(power) AS 'power'"
            "    FROM Device_History"
            f"    WHERE timestamp<={selected_date.timestamp()}"
            "    GROUP BY timestamp"
            "    ORDER BY timestamp DESC"
            f"    LIMIT {PREVIOUS_POWER_STEPS+FUTURE_POWER_STEPS}"#TODO:extract this value from model
            ") AS recent_rows"
            " ORDER BY timestamp ASC"
        )

        consumption_data=fetch_multiple_elements(DbPathEnum.CONSUMPTION,query)

        last_date=datetime.fromtimestamp(consumption_data[-1]["timestamp"]).astimezone(tz.tzlocal())

        unit="W"
        result=[{k:d[k] for k in ["date","power"] if k in d} for d in consumption_data][-FUTURE_POWER_STEPS:]
        

        for item in consumption_data:
            weekday,is_weekend=getDayIndicator(item["timestamp"])
            item["weekday"]=weekday
            #item["is_weekend"]=is_weekend
            item["time_session"]=getTimeSession(item["timestamp"])

        dataset_complete=pd.DataFrame.from_dict(consumption_data)
        #dataset_complete=dataset_complete[["date","end","energy_consumption","weekday","is_weekend","time_session"]]
        dataset_complete=dataset_complete[["date","timestamp","power","weekday","time_session"]]

        if scaler:
            dataset_complete['power_scaled'] = scaler.fit_transform(dataset_complete[['power']])
        else:
            dataset_complete['power_scaled'] = dataset_complete['power']

        dataset_complete=dataset_complete[dataset_complete.columns[3:]]
        X_in1=create_sequences(dataset_complete)
        #y_predict_raw = model.predict(X_in1)  # shape: (samples, FUTURE_STEPS)
        #y_predict = scaler.inverse_transform(y_predict_raw) if scaler else y_predict_raw
        y_predict=predictSequenceReverse(model,X_in1,use_weighted_average=False,scaler_in=scaler)
        y_predict=y_predict.tolist()

        for i in range(FUTURE_POWER_STEPS):
            date_str=f"{last_date.strftime('%d-%m-%Y %H:%M')}"
            energy_cons=y_predict[i]
            result.append({"date":date_str,"power":energy_cons,"power_unit":unit})
            last_date+=timedelta(minutes=1)

        return result

    @prediction_router.get("/power/{device_id}/{service}")#TODO: this is a copy of the previous one, pls refactor
    def Get_Power_Consumption_Prediction_For_Service(device_id,service):
        model,scaler=load_model_and_scaler(f"{FILENAME_POWER}.keras",f"{FILENAME_POWER}.bin")
    
        selected_date=datetime.now().astimezone(tz.tzlocal())
        query = (
            "SELECT date, timestamp, power FROM ("
            "    SELECT strftime('%d-%m-%Y %H:%M', timestamp, 'unixepoch', 'localtime') as 'date',"
            "           timestamp, SUM(power) AS 'power'"
            "    FROM Device_History"
            f"    WHERE timestamp<={selected_date.timestamp()}"
            "    GROUP BY timestamp"
            "    ORDER BY timestamp DESC"
            f"    LIMIT {PREVIOUS_POWER_STEPS}"#TODO:extract this value from model
            ") AS recent_rows"
            " ORDER BY timestamp ASC"
        )

        consumption_data=fetch_multiple_elements(DbPathEnum.CONSUMPTION,query)

        last_date=datetime.fromtimestamp(consumption_data[-1]["timestamp"]).astimezone(tz.tzlocal())

        unit="W"
        result=[{k:d[k] for k in ["date","power"] if k in d} for d in consumption_data][-FUTURE_POWER_STEPS:]
        

        for item in consumption_data:
            weekday,is_weekend=getDayIndicator(item["timestamp"])
            item["weekday"]=weekday
            item["time_session"]=getTimeSession(item["timestamp"])

        dataset_complete=pd.DataFrame.from_dict(consumption_data)
        dataset_complete=dataset_complete[["date","timestamp","power","weekday","time_session"]]

        #Increasing the last element in the dataset with the activation value
        with open("./data/devices_new_state_map.json") as file: #TODO:extract path
            state_map=json.load(file)

        state=state_map.get(service,"")
        power_delta=0
        device_info=getSingleDeviceFast(device_id)
        if device_info["status_code"]==200:
            device_info=device_info["data"]
            current_state=device_info["state"]
            power_entity=[x for x in device_info["list_of_entities"] if x["entity_id"]==device_info["power_entity_id"]]
            if len(power_entity)>0:
                current_state=current_state if float(power_entity[0]["state"])>2 else "off"

            if state!=current_state and state not in ["same","on|off"]:
                old_state_data=get_usage_entry_for_appliance_state(device_id,current_state)
                new_state_data=get_usage_entry_for_appliance_state(device_id,state)
                power_delta=new_state_data["average_power"]-old_state_data["average_power"]

                state_duration= min(new_state_data["average_duration"],240)
                time_delta=min(60-selected_date.minute,state_duration)

        last_date=last_date+timedelta(minutes=1)
        last_power=max(float(consumption_data[-1]["power"])+power_delta,0)

        for i in range(5):
            weekday,is_weekend=getDayIndicator(last_date.timestamp())

            new_row = {
                "date":last_date.strftime('%d-%m-%Y %H:%M'),
                "timestamp":last_date.timestamp(),
                "power": last_power,
                "weekday": weekday,
                "time_session": getTimeSession(last_date.timestamp()),
            }
            result.append({"date":last_date.strftime('%d-%m-%Y %H:%M'),"power":last_power,"power_unit":unit})
            dataset_complete = pd.concat([dataset_complete, pd.DataFrame([new_row])], ignore_index=True)
            last_date=last_date+timedelta(minutes=1)

        if scaler:
            dataset_complete['power_scaled'] = scaler.fit_transform(dataset_complete[['power']])
        else:
            dataset_complete['power_scaled'] = dataset_complete['power']

        dataset_complete=dataset_complete[dataset_complete.columns[3:]][5:]
        
        X_in1=create_sequences(dataset_complete,n_timesteps=PREVIOUS_POWER_STEPS)

        y_predict = predictSequence(model,X_in1,False,scaler,future_steps=FUTURE_POWER_STEPS)
        y_predict=y_predict.tolist()[0]

        #y_predict=predictSequenceRecursivePower(model,dataset_complete,scaler,last_date,[],FUTURE_POWER_STEPS)
        for i in range(FUTURE_POWER_STEPS):
            date_str=f"{last_date.strftime('%d-%m-%Y %H:%M')}"
            energy_cons=max(float(y_predict[i]),0)
            result.append({"date":date_str,"power":energy_cons,"power_unit":unit})
            last_date+=timedelta(minutes=1)

        return result
    

    
    
    def Get_Recursive_Consumption_Prediction():
        model,scaler=load_model_and_scaler(f"{FILENAME_RECURSIVE}.keras",f"{FILENAME_RECURSIVE}.bin")
        
        selected_date=datetime.now().replace(minute=0,second=0).astimezone(tz.tzlocal())
        query = (
            "SELECT date, end, energy_consumption,energy_consumption_unit FROM ("
            "    SELECT strftime('%d-%m-%Y %H', timestamp, 'unixepoch', 'localtime') || '-' || strftime('%H', timestamp+(60*60), 'unixepoch', 'localtime') AS 'date',"
            "           timestamp+(60*60) as end, SUM(energy_consumption) AS 'energy_consumption',energy_consumption_unit"
            "    FROM Device_History"
            f"    WHERE timestamp<{int(selected_date.timestamp())}"
            "    GROUP BY \"date\""
            "    ORDER BY end DESC"
            f"    LIMIT {PREVIOUS_STEPS}"
            ") AS recent_rows"
            " ORDER BY end ASC"
        )

        consumption_data=fetch_multiple_elements(DbPathEnum.CONSUMPTION,query)

        if len(consumption_data)<PREVIOUS_STEPS:
            raise HTTPException(404,"Not enough data for prediction.")
        

        unit=consumption_data[-1]["energy_consumption_unit"]
        result=[{k:d[k] for k in ["date","energy_consumption","energy_consumption_unit"] if k in d} for d in consumption_data][-FUTURE_STEPS_RECURSIVE:]
        last_date=datetime.fromtimestamp(consumption_data[-1]["end"]).astimezone(tz.tzlocal())

        

        dataset_complete = prepare_dataset(scaler, consumption_data)

        y_predict=predictSequenceRecursive(model,dataset_complete,scaler,last_date)

        for i in range(FUTURE_STEPS_RECURSIVE):
            date_str=f"{last_date.strftime('%d-%m-%Y %H-')}{(last_date+timedelta(hours=1)).strftime('%H')}"
            energy_cons=y_predict[i]
            result.append({"date":date_str,"energy_consumption":float(energy_cons),"energy_consumption_unit":unit})
            last_date+=timedelta(hours=1)

        return result
    
    @prediction_router.get("/recursive/cache")
    def get_cached_prediction():
        result = prediction_cache["result"]
        if result is None:
            return JSONResponse(
                content={"cached": False, "message": "No cached result yet."},
                status_code=404
            )
        return {"cached": True, "data": result}
    

    
    @prediction_router.get("/recursive")
    def update_and_get_recursive_prediction():
        now = time.time()
        with prediction_cache["lock"]:
            if prediction_cache["result"] is not None and prediction_cache["timestamp"] is not None:
                if now - prediction_cache["timestamp"] < CACHE_TTL_SECONDS:
                    return {
                        "cached": True,
                        "data": prediction_cache["result"],
                        "timestamp": prediction_cache["timestamp"]
                    }
            # Otherwise, recompute and update the cache
            result = Get_Recursive_Consumption_Prediction()
            prediction_cache["result"] = result
            prediction_cache["timestamp"] = now
            return {
                "cached": False,
                "data": result,
                "timestamp": now
            }


    
    return prediction_router