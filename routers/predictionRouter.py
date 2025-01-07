from fastapi import APIRouter,HTTPException
import datetime,logging
from dateutil import parser,tz

from joblib import load as scalerload
import keras 
from datetime import datetime,timedelta
from dateutil import tz
import numpy as np
import pandas as pd
import sqlite3,json,os

from database_functions import fetch_multiple_elements,DbPathEnum,get_appliance_usage_entry
from homeassistant_functions import getSingleDeviceFast

FUTURE_STEPS_RECURSIVE=12
FUTURE_STEPS_SEQUENTIAL=6
PREVIOUS_STEPS=24
FILENAME_SEQUENTIAL="./prediction_models/15-11-2024-12-38_Prev48_Next6_minmaxscaling"
FILENAME_RECURSIVE="./prediction_models/16-12-2024-16-43_Prev24_Next1_noscalerscaling"

def predictSequence(model,x_to_predict,use_weighted_average=False,scaler_in=None,future_steps=FUTURE_STEPS_RECURSIVE):
    # Predict the values (assuming the model provides multiple overlapping predictions)
    y_predict_raw = model.predict(x_to_predict)  # shape: (samples, FUTURE_STEPS)

    y_predict = scaler_in.inverse_transform(y_predict_raw) if scaler_in else y_predict_raw


    final = [0] * len(y_predict)  # Initialize a list of zeros for the final predictions

    # Loop through each prediction sample
    for i in range(len(y_predict)):
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


def predictSequenceRecursive(model,dataset_to_predict,scaler,last_date,consumption_delta=[]):
    incremental_prediction=[]
    dataset_incremental=dataset_to_predict
    j=0
    temp_date=last_date+timedelta(hours=1)
    for i in range(FUTURE_STEPS_RECURSIVE):
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
            date_str=f"{last_date.strftime("%d-%m-%Y %H-")}{(last_date+timedelta(hours=1)).strftime("%H")}"
            energy_cons=y_predict[i]
            result.append({"date":date_str,"energy_consumption":energy_cons,"energy_consumption_unit":unit})
            last_date+=timedelta(hours=1)

        return result
    

    @prediction_router.get("/recursive")
    def Get_Recursive_Consumption_Prediction():
        model=keras.saving.load_model(f"{FILENAME_RECURSIVE}.keras", custom_objects=None, compile=False, safe_mode=True)
        model.compile(optimizer="adam",loss="mse",metrics=["mse"])

        scaler=None
        if os.path.exists(f"{FILENAME_RECURSIVE}.bin"):
            scaler=scalerload(f"{FILENAME_RECURSIVE}.bin")
        
        selected_date=datetime.now().astimezone(tz.tzlocal())
        query = (
            "SELECT date, end, energy_consumption,energy_consumption_unit FROM ("
            "    SELECT strftime('%d-%m-%Y %H', start, 'unixepoch', 'localtime') || '-' || strftime('%H', end, 'unixepoch', 'localtime') AS 'date',"
            "           end, SUM(energy_consumption) AS 'energy_consumption',energy_consumption_unit"
            "    FROM Hourly_Consumption"
            f"    WHERE end<={selected_date.timestamp()}"
            "    GROUP BY strftime('%d-%m-%Y %H', start, 'unixepoch', 'localtime')"
            "    ORDER BY start DESC"
            f"    LIMIT {PREVIOUS_STEPS}"
            ") AS recent_rows"
            " ORDER BY end ASC"
        )

        consumption_data=fetch_multiple_elements(DbPathEnum.CONSUMPTION,query)
        unit=consumption_data[-1]["energy_consumption_unit"]
        result=[{k:d[k] for k in ["date","energy_consumption","energy_consumption_unit"] if k in d} for d in consumption_data][-FUTURE_STEPS_RECURSIVE:]

        last_date=datetime.fromtimestamp(consumption_data[-1]["end"]).astimezone(tz.tzlocal())

        

        if len(consumption_data)<PREVIOUS_STEPS:
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
        y_predict=predictSequenceRecursive(model,dataset_complete,scaler,last_date)

        for i in range(FUTURE_STEPS_RECURSIVE):
            date_str=f"{last_date.strftime("%d-%m-%Y %H-")}{(last_date+timedelta(hours=1)).strftime("%H")}"
            energy_cons=y_predict[i]
            result.append({"date":date_str,"energy_consumption":float(energy_cons),"energy_consumption_unit":unit})
            last_date+=timedelta(hours=1)

        return result
    
    @prediction_router.get("/service/{device_id}/{state}")
    def Predict_With_Service_Activation(device_id,state):
        model=keras.saving.load_model(f"{FILENAME_RECURSIVE}.keras", custom_objects=None, compile=False, safe_mode=True)
        model.compile(optimizer="adam",loss="mse",metrics=["mse"])

        scaler=None
        if os.path.exists(f"{FILENAME_RECURSIVE}.bin"):
            scaler=scalerload(f"{FILENAME_RECURSIVE}.bin")
        
        selected_date=datetime.now().astimezone(tz.tzlocal())
        query = (
            "SELECT date, end, energy_consumption,energy_consumption_unit FROM ("
            "    SELECT strftime('%d-%m-%Y %H', start, 'unixepoch', 'localtime') || '-' || strftime('%H', end, 'unixepoch', 'localtime') AS 'date',"
            "           end, SUM(energy_consumption) AS 'energy_consumption',energy_consumption_unit"
            "    FROM Hourly_Consumption"
            f"    WHERE end<={selected_date.timestamp()}"
            "    GROUP BY strftime('%d-%m-%Y %H', start, 'unixepoch', 'localtime')"
            "    ORDER BY start DESC"
            f"    LIMIT {PREVIOUS_STEPS}"
            ") AS recent_rows"
            " ORDER BY end ASC"
        )

        consumption_data=fetch_multiple_elements(DbPathEnum.CONSUMPTION,query)
        unit=consumption_data[-1]["energy_consumption_unit"]
        result=[{k:d[k] for k in ["date","energy_consumption","energy_consumption_unit"] if k in d} for d in consumption_data][-FUTURE_STEPS_RECURSIVE:]

        last_date=datetime.fromtimestamp(consumption_data[-1]["end"]).astimezone(tz.tzlocal())


        if len(consumption_data)<PREVIOUS_STEPS:
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

        #Increasing the last element in the dataset with the activation value

        consumption_delta=[]
        if device_id.split(".")[0]=="virtual":
             with open("./data/appliances_consumption_map.json") as file:
                consumption_map=json.load(file)
                usage_map=consumption_map[device_id.split(".")[1]]
                state_data=[x for x in usage_map if x["name"]==state][0]
                power_delta=state_data.get("power_consumption",0)
                
                remaining_time=state_data.get("default_duration",0)/60
                time_delta=min(60-selected_date.minute,remaining_time)
                while remaining_time>0:
                    consumption_delta.append(power_delta*(time_delta/60)) #need to convert it into Wh
                    remaining_time-=time_delta
                    time_delta=min(60,remaining_time)


        else:
            device_info=getSingleDeviceFast(device_id)
            current_state=device_info["data"]["state"]
            if state!=current_state:
                old_state_data=get_appliance_usage_entry(device_id,current_state)
                new_state_data=get_appliance_usage_entry(device_id,state)

                remaining_time=new_state_data["average_duration"]
                time_delta=min(60-selected_date.minute,remaining_time)
                power_delta=new_state_data["average_power"]-old_state_data["average_power"]
                consumption_delta.append(power_delta*(time_delta/60)) #need to convert it into Wh

        y_predict=predictSequenceRecursive(model,dataset_complete,scaler,last_date,consumption_delta)

        for i in range(FUTURE_STEPS_RECURSIVE):
            date_str=f"{last_date.strftime("%d-%m-%Y %H-")}{(last_date+timedelta(hours=1)).strftime("%H")}"
            energy_cons=y_predict[i]
            result.append({"date":date_str,"energy_consumption":float(energy_cons),"energy_consumption_unit":unit})
            last_date+=timedelta(hours=1)

        return result
          
    return prediction_router