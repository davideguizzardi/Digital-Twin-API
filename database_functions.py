import sqlite3

DB_PATH="./data/digital_twin.db"

QUERIES={
    "hourly_consumption":
    ("select "
     "{device_id_field}" 
    "strftime('%d-%m-%Y %H',start,'unixepoch','localtime') ||'-'|| strftime('%H',end,'unixepoch','localtime') as 'date',"
    "sum(energy_consumption) as 'energy_consumption',energy_consumption_unit " 
    "from Hourly_Consumption "
    "where start>={from_time} and end<={to_time} {device_filter}"
    "GROUP by strftime('%d-%m-%Y %H',start,'unixepoch','localtime') ||'-'|| strftime('%H',end,'unixepoch','localtime') {device_id_grouping} order by start"
    ),
    "daily_consumption":
    ("select "
    "{device_id_field}" 
    "strftime('%d-%m-%Y',start,'unixepoch','localtime') as 'date',"
    "sum(energy_consumption) as 'energy_consumption',energy_consumption_unit " 
    "from Hourly_Consumption "
    "where start>={from_time} and end<={to_time} {device_filter}"
    "GROUP by strftime('%d-%m-%Y',start,'unixepoch','localtime') {device_id_grouping} order by start"
    ),
    "monthly_consumption":
    ("select "
     "{device_id_field}"  
    "strftime('%m-%Y',start,'unixepoch','localtime') as 'date',"
    "sum(energy_consumption) as 'energy_consumption',energy_consumption_unit " 
    "from Hourly_Consumption "
    "where start>={from_time} and end<={to_time} {device_filter}"
    "GROUP by strftime('%m-%Y',start,'unixepoch','localtime') {device_id_grouping} order by start"
    ),
}

def row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict:
    data = {}
    for idx, col in enumerate(cursor.description):
        data[col[0]] = row[idx]
    return data

def initialize_database():
    create_tables()


def create_tables():
    query_list=[
        'CREATE TABLE "Configuration" ("key" TEXT NOT NULL,"value" TEXT NOT NULL,"unit"	TEXT,PRIMARY KEY("key"));',
        'CREATE TABLE "Map_config" ("entity_id" TEXT NOT NULL,"x" INTEGER NOT NULL,"y" INTEGER NOT NULL,"floor" INTEGER NOT NULL,PRIMARY KEY("entity_id"));',
        'CREATE TABLE "Service_logs" ("user"	TEXT NOT NULL,"service"	TEXT NOT NULL,"target"	TEXT,"payload"	TEXT,"timestamp"	INTEGER NOT NULL);',
        'CREATE TABLE "Energy_Timeslot" ("day"	INTEGER,"hour"	INTEGER,"slot"	INTEGER);',
        'CREATE TABLE "Daily_Consumption" ("device_id" TEXT,"energy_consumption"	REAL,"energy_consumption_unit" TEXT,"use_time" REAL,"use_time_unit" TEXT,"date" INTEGER,PRIMARY KEY("device_id","date"))',
        'CREATE TABLE "Hourly_Consumption" ("device_id" TEXT,"energy_consumption" REAL,"energy_consumption_unit"	TEXT,"from"	INTEGER,"to" INTEGER,PRIMARY KEY("device_id","from"))',
        'CREATE TABLE "Appliances_Usage" ("device_id"	TEXT,"state"	TEXT,"average_duration"	REAL,"duration_unit"	TEXT,"duration_samples"	INTEGER,"average_power"	REAL,"average_power_unit"	TEXT,"power_samples"	INTEGER,"last_timestamp"	INTEGER,PRIMARY KEY("device_id","state"))',
        'CREATE TABLE "User_Preferences" ("user_id"	TEXT NOT NULL,"preferences"	TEXT,"data_collection"	INTEGER,"data_disclosure"	INTEGER,PRIMARY KEY("user_id"))'
    ]
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    for query in query_list:
        res=cur.execute(query)
        success=True if cur.rowcount>0 else False
    con.close()
    return success

def fetchOneElement(query:str):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute(query)
    res=res.fetchone()
    con.close()
    return res

def add_user_preferences(preferences_list:list):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.executemany("INSERT or REPLACE into User_Preferences(user_id,preferences,data_collection,data_disclosure) VALUES (?,?,?,?)",preferences_list)
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success

def get_all_user_preferences():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM User_Preferences")
    res=res.fetchall()
    con.close()
    return res

def get_user_preferences_by_user(user_id:str):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM User_Preferences WHERE user_id='"+user_id+"'")
    res=res.fetchone()
    con.close()
    return res

def delete_user_preferences_by_user(user_id:str):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("DELETE FROM User_Preferences WHERE user_id='"+user_id+"'")
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success

def add_user_consensus(consensus_list:list):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.executemany("INSERT or REPLACE into User_Consensus(user_id,data_collection,information_disclosure) VALUES (?,?,?)",consensus_list)
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success

def add_service_logs(logs_list:list):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.executemany("INSERT into Service_logs(user,service,target,payload,timestamp) VALUES (?,?,?,?,?)",logs_list)
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success

def get_all_service_logs():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Service_logs")
    res=res.fetchall()
    con.close()
    return res

def get_service_logs_by_user(user:str):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Service_logs WHERE user='"+user+"'")
    res=res.fetchall()
    con.close()
    return res
    
def add_map_entities(entities_list:list):
    """
    Aggiunge al db tutte le entita' passate in input.

    Args:
    ----------
    entities_list:
    lista di tuple nella forma (entity_id,x,y,floor)

    """
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.executemany("INSERT or REPLACE into Map_config VALUES (?,?,?,?)",entities_list)
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success

def delete_map_entry(entity_id:str):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.execute("DELETE FROM Map_config WHERE entity_id='"+entity_id+"'")
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success

def delete_floor_map_configuration(floor:int):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.execute("DELETE FROM Map_config WHERE floor="+str(floor))
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success

def get_all_map_entities():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Map_config")
    res=res.fetchall()
    con.close()
    return res

def get_map_entity(id):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Map_config WHERE entity_id=\""+id+"\"")
    res=res.fetchone()
    con.close()
    return res



def add_configuration_values(values_list:list):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.executemany("INSERT or REPLACE into Configuration(key,value,unit) VALUES (?,?,?)",values_list)
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success

def get_all_configuration_values():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Configuration")
    res=res.fetchall()
    con.close()
    return res

def get_configuration_value_by_key(key:str):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Configuration WHERE key='"+key+"'")
    res=res.fetchone()
    con.close()
    return res

def delete_configuration_value(key:int):
    element=fetchOneElement("Select * from Configuration WHERE key='"+key+"'")
    if element:
        con=sqlite3.connect(DB_PATH)
        cur=con.cursor()
        cur.execute("DELETE FROM Configuration WHERE key='"+key+"'")
        con.commit()
        success=True if cur.rowcount>0 else False
        con.close()
    else:
        success=True
    return success


def add_energy_slots(slots_list:list):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.executemany("INSERT or REPLACE into Energy_Timeslot(day,hour,slot) VALUES (?,?,?)",slots_list)
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success

def get_all_energy_slots():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    res=cur.execute("SELECT * FROM Energy_Timeslot ORDER by day ASC, hour ASC")
    res=res.fetchall()
    con.close()
    return res

def get_energy_slot_by_day(day:int):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Energy_Timeslot WHERE day="+str(day)+" ORDER by day ASC, hour ASC")
    res=res.fetchall()
    con.close()
    return res

def get_energy_slot_by_slot(slot:int):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Energy_Timeslot WHERE slot="+str(slot))
    res=res.fetchall()
    con.close()
    return res

def delete_energy_slots():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.execute("DELETE FROM Energy_Timeslot")
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success


def add_daily_consumption_entry(entry_list:list):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.executemany("INSERT or REPLACE into Daily_Consumption(device_id,energy_consumption,energy_consumption_unit,use_time,use_time_unit,date) VALUES (?,?,?,?,?,?)",entry_list)
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success


def get_all_daily_consumption_entries():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Daily_Consumption")
    res=res.fetchall()
    con.close()
    return res


def add_hourly_consumption_entry(entry_list:list):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.executemany("INSERT or REPLACE into Hourly_Consumption(device_id,energy_consumption,energy_consumption_unit,start,end) VALUES (?,?,?,?,?)",entry_list)
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success


def get_all_hourly_consumption_entries():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Hourly_Consumption")
    res=res.fetchall()
    con.close()
    return res

def get_total_consumption(from_timestamp:int,to_timestamp:int,group:str="hourly",device_id:str=""):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    device_filter=""
    device_id_field=""
    device_id_grouping=""
    if device_id!="":
        device_id_field="device_id, "
        device_filter="and device_id="+"'"+device_id+"'"
    key=group+"_consumption"
    query=QUERIES[key].format(
        from_time=from_timestamp,
        to_time=to_timestamp,
        device_filter=device_filter,
        device_id_field=device_id_field,
        device_id_grouping=device_id_grouping)
    res=cur.execute(query)
    res=res.fetchall()
    con.close()
    return res

def add_appliances_usage_entry(entry_list:list):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.executemany("""INSERT or REPLACE into Appliances_Usage
                    (device_id,state,average_duration,duration_unit,duration_samples,average_power,average_power_unit,power_samples,last_timestamp) 
                    VALUES (?,?,?,?,?,?,?,?,?)""",entry_list)
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
    return success

def get_all_appliances_usage_entries():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute("SELECT * FROM Appliances_Usage")
    res=res.fetchall()
    con.close()
    return res

def get_appliance_usage_entry(device_id:str, state:str):
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    res=cur.execute('select average_power,average_power_unit,average_duration,duration_unit from Appliances_Usage where device_id="'+device_id+'" and state="'+state+'"')
    res=res.fetchone()
    con.close()
    return res


