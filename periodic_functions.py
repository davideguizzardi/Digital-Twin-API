import logging
import datetime

from homeassistant_functions import getEntities,getHistory,initializeToken
from database_functions import add_daily_consumption_entry,add_hourly_consumption_entry,get_all_appliances_usage_entries,add_appliances_usage_entry
from routers import computeHourlyTotalConsumption,computeTotalConsumption
from dateutil import tz,parser
from collections import defaultdict

logger = logging.getLogger(__name__)


def Get_Total_Consumption(start_timestamp:datetime.date=datetime.date.today(),end_timestamp:datetime.date=datetime.date.today()):
        start_call=datetime.datetime.now() #used for debug purposes
        start_timestamp=datetime.datetime.combine(start_timestamp, datetime.time.min).astimezone(tz.tzlocal())
        end_timestamp=datetime.datetime.combine(end_timestamp,  datetime.time(23, 59)).astimezone(tz.tzlocal())

        ## Getting the list of all the entities of the house
        res=getEntities(True,False)
        if res["status_code"]!=200:
           logger.error("getEntities returned "+res["status_code"]+", "+res["data"])
           return 
        
        ## Filtering only those entities that could produce some consumption data
        domainsToFilter=["light","media_player","fan"] #domains of entities that could consume energy, sensors and buttons are supposed to consume 0
        entities_list=[x["entity_id"] for x in res["data"] if x["entity_id"].split(".")[0] in domainsToFilter]
        logger.info(f"Asking HA for history, from:{start_timestamp.strftime("%d/%m/%Y %H:%M")} to:{end_timestamp.strftime("%d/%m/%Y %H:%M")}, for {len(entities_list)-1} entities")
        entities_list=",".join(entities_list)

        response=getHistory(entities_id=entities_list,start_timestamp=start_timestamp,end_timestamp=end_timestamp)
        if response["status_code"]!=200:
            logger.error("getHistory returned "+res["status_code"]+", "+res["data"])
            return 
        
        if not response["data"]:
            logger.error("getHistory returned no data...")
            return
        
        entities_states=response["data"]
        res={}
   
        delta=(end_timestamp-start_timestamp).days
        hourly_grouping=[]
        daily_grouping=[]
        mode_use_dict={}
        for id in entities_states:
            logger.info(f"Computing Hourly consumption, Daily consumption and mean use for entity {id}")
            hourly_total=computeHourlyTotalConsumption(id,entities_states[id],start_timestamp,end_timestamp)[id]
            for element in hourly_total:
                 date_from=element["date"].split(" ")[0]+" "+element["date"].split(" ")[1].split("-")[0]
                 date_to=element["date"].split(" ")[0]+" "+element["date"].split(" ")[1].split("-")[1]
                 date_from=datetime.datetime.strptime(date_from,"%d/%m/%Y %H").replace(microsecond=0).timestamp()
                 date_to=datetime.datetime.strptime(date_to,"%d/%m/%Y %H").replace(microsecond=0).timestamp()
                 hourly_grouping.append((id,element["power_consumption"],element["power_consumption_unit"],date_from,date_to))

            temp_date=start_timestamp
            for i in range(delta+1):                   
                temp_list=[x for x in entities_states[id] if x["last_changed"].startswith(temp_date.strftime("%Y-%m-%d"))]
                daily_consumption=computeTotalConsumption(temp_list,temp_date,date_format="%d/%m/%Y")
                daily_grouping.append((
                    id,
                    daily_consumption["power_consumption"],daily_consumption["power_consumption_unit"],
                    daily_consumption["use_time"],daily_consumption["use_time_unit"],
                    datetime.datetime.strptime(daily_consumption["date"],"%d/%m/%Y").replace(microsecond=0).timestamp()
                    ))
                temp_date=temp_date+datetime.timedelta(days=1)

            mode_dict=defaultdict(lambda:{"sum":0,"samples":0,"unit":"s"})
            for i in range(len(entities_states[id])):
                start_block=parser.parse(entities_states[id][i]["last_changed"]).astimezone(tz.tzlocal())
                if i+1==len(entities_states[id]):
                    end_block=datetime.datetime.combine(start_block+datetime.timedelta(days=1), datetime.time.min).astimezone(tz.tzlocal())
                else:
                    end_block=parser.parse(entities_states[id][i+1]["last_changed"]).astimezone(tz.tzlocal())
                duration=(end_block-start_block).total_seconds() #calcolo la durata dell'intervallo
                mode_dict[entities_states[id][i]["state"]]["sum"]+=duration
                mode_dict[entities_states[id][i]["state"]]["samples"]+=1
            
            mode_use_dict[id]=dict(mode_dict)

        logger.info("Retrieving saved data on appliances usage...")
        temp=[]
        database_data=get_all_appliances_usage_entries()
        for id in mode_use_dict.keys():
            for mode in mode_use_dict[id]:
                index=[i for i in range(len(database_data)) if database_data[i]["entity_id"]==id and database_data[i]["state"]==mode]
                if len(index)>0: #the db already has some data about that mode
                    database_element=database_data[index[0]]
                    old_sum=database_element["average_duration"]*database_element["samples"]
                    samples=mode_use_dict[id][mode]["samples"]+database_element["samples"]
                    mean=(mode_use_dict[id][mode]["sum"]+old_sum)/(samples)
                    temp.append((id,mode,mean,samples,mode_use_dict[id][mode]["unit"]))
                else:
                    temp.append((id,mode,mode_use_dict[id][mode]["sum"]/mode_use_dict[id][mode]["samples"],mode_use_dict[id][mode]["samples"],mode_use_dict[id][mode]["unit"]))

        res=add_appliances_usage_entry(temp)
        if res:
            logger.info("Appliances usage data updated successfully!")
        else:
            logger.error("Some error occurred while saving appliaces usage data, could't update...")

        res=add_daily_consumption_entry(daily_grouping)
        if res:
            logger.info("Daily consumption data updated successfully!")
        else:
            logger.error("Some error occurred while saving daily consumption data, could't update...")
        
        res=add_hourly_consumption_entry(hourly_grouping)
        if res:
            logger.info("Hourly consumption data updated successfully!")
        else:
            logger.error("Some error occurred while saving hourly consumption data, could't update...")

        logger.info(f"Updating consumption and use data of {len(entities_list.split(","))-1} entities ended, elapsed time:{(datetime.datetime.now()-start_call).total_seconds()}[s]")
       



def main(): 
    logging.basicConfig(format='%(levelname)s-%(asctime)s: %(message)s',datefmt='%d/%m/%Y %H:%M:%S',filename='./logs/periodic_functions.log', encoding='utf-8', level=logging.INFO)
    logger.info("Running the script to get daily appliances consumption and usage time...")
    initializeToken()
    Get_Total_Consumption()

if __name__ == "__main__":
    main()