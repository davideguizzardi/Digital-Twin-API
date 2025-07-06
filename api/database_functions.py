import sqlite3
from contextlib import contextmanager

from enum import StrEnum
import os.path,logging
from pymongo import MongoClient
import datetime
#DB_PATH="./data/digital_twin.db"

class DbPathEnum(StrEnum):
    CONFIGURATION="./data/digital_twin_configuration.db"
    CONSUMPTION="./data/digital_twin_consumption.db"
    LOGS="./data/digital_twin_logs.db"
    ENTITY_HISTORY="./data/digital_twin_entity_history.db"


default_configuration_values = {
    "energy_slots_number":("1",""),
    "cost_slot_0":("0.1","€/kWh"),
    "cost_slot_1":("0.1","€/kWh"),
    "cost_slot_2":("0.1","€/kWh"),
    "power_threshold":("3000","W"),
    "server_url": ("http://homeassistant.local:8123/api", ""),
    "token": ("token", ""),
    "w_to_gco2": ("0.431", "kgCO2/kWh"),
    "enable_prediction": ("1", ""),
    "enable_demo": ("0", ""),
    "host": ("0.0.0.0", ""),
    "port": ("8000", "")
}



QUERIES={
    "hourly_consumption":
        ("select "
        "{device_id_field}" 
        "strftime('%d-%m-%Y %H:', timestamp, 'unixepoch', 'localtime') || printf('%02d', (strftime('%M', timestamp, 'unixepoch', 'localtime') / {minutes}) * {minutes}) || '-' ||strftime('%H:', timestamp+(60*{minutes}), 'unixepoch', 'localtime') || printf('%02d', ((strftime('%M', timestamp+(60*{minutes}), 'unixepoch', 'localtime') / {minutes}) * {minutes}) % 60) AS 'date',"
        "sum(energy_consumption) as 'energy_consumption',energy_consumption_unit " 
        "from Device_History "
        "where timestamp>={from_time} and timestamp<={to_time} {device_filter}"
        "GROUP by \"date\" {device_id_grouping} order by \"date\""
        ),
    "daily_consumption":
        ("select "
        "{device_id_field}" 
        "strftime('%d-%m-%Y',timestamp,'unixepoch','localtime') as 'date',"
        "sum(energy_consumption) as 'energy_consumption',energy_consumption_unit " 
        "from Device_History "
        "where timestamp>={from_time} and timestamp<={to_time} {device_filter}"
        "GROUP by \"date\" {device_id_grouping} order by \"date\""
        ),
    "monthly_consumption":
        ("select "
        "{device_id_field}"  
        "strftime('%m-%Y',timestamp,'unixepoch','localtime') as 'date',"
        "sum(energy_consumption) as 'energy_consumption',energy_consumption_unit " 
        "from Device_History "
        "where timestamp>={from_time} and timestamp<={to_time} {device_filter}"
        "GROUP by \"date\" {device_id_grouping} order by \"date\""
        ),
    "total_consumption":
        ("select "
        "{device_id_field}"  
        "strftime('%d-%m-%Y',min(timestamp),'unixepoch','localtime') as 'date',"
        "sum(energy_consumption) as 'energy_consumption',energy_consumption_unit " 
        "from Device_History "
        "where timestamp>={from_time} {device_filter}"
        ),
    "energy_slots":'''
        SELECT 
            CASE et.day 
                WHEN 0 THEN 'mon' 
                WHEN 1 THEN 'tue' 
                WHEN 2 THEN 'wed' 
                WHEN 3 THEN 'thu' 
                WHEN 4 THEN 'fri' 
                WHEN 5 THEN 'sat' 
                WHEN 6 THEN 'sun' 
            END AS day, 
            et.hour, 
            c.value AS slot_value,
            c.unit
        FROM 
            Energy_Timeslot et 
        JOIN 
            Configuration c 
        ON 
            c.key = 'cost_slot_' || et.slot;
    ''',
    "minimum_energy_slots":'''
        SELECT 
            CASE et.day 
                WHEN 0 THEN 'mon' 
                WHEN 1 THEN 'tue' 
                WHEN 2 THEN 'wed' 
                WHEN 3 THEN 'thu' 
                WHEN 4 THEN 'fri' 
                WHEN 5 THEN 'sat' 
                WHEN 6 THEN 'sun' 
            END AS day_name, 
            et.hour, 
            c.value AS slot_value 
        FROM 
            Energy_Timeslot et 
        JOIN 
            Configuration c 
        ON 
            c.key = 'cost_slot_' || et.slot
        WHERE 
            c.value = (SELECT MIN(value) FROM Configuration WHERE key LIKE 'cost_slot_%');
    '''
}

def row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict:
    data = {}
    for idx, col in enumerate(cursor.description):
        data[col[0]] = row[idx]
    return data

@contextmanager
def get_db_connection(db_path:DbPathEnum=DbPathEnum.CONFIGURATION):
    """
    Context manager for handling SQLite connections.
    Automatically manages connection opening and closing, and handles errors.

    :param db_path: Path to the SQLite database.
    :yield: SQLite connection object.
    """
    connection = None
    try:
        connection = sqlite3.connect(db_path)
        connection.row_factory = row_to_dict  
        yield connection  
    except sqlite3.Error as e:
        print(f"Error connecting to the database: {e}")
        if connection:
            connection.rollback()  # Roll back if an error occurs
    finally:
        if connection:
            connection.close()  # Ensure the connection is always closed

def table_exists(db_path, table_name):
    """Check if a table exists in the SQLite database."""
    with get_db_connection(db_path) as con:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
        return cur.fetchone() is not None  # True if table exists, False otherwise
    
def initialize_default_configuration_values(db_path: DbPathEnum, defaults: dict):
    from contextlib import suppress

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        for key, (value, unit) in defaults.items():
            with suppress(sqlite3.IntegrityError): #Could be removed
                cursor.execute('''
                INSERT OR IGNORE INTO Configuration (key, value, unit)
                VALUES (?, ?, ?)
                ''', (key, value, unit))
        conn.commit()


def initialize_database():
    logger = logging.getLogger(__name__)

    configuration_db_tables = {
        "Configuration": 'CREATE TABLE "Configuration" ("key" TEXT NOT NULL, "value" TEXT NOT NULL, "unit" TEXT, PRIMARY KEY("key"));',
        "Device": 'CREATE TABLE "Device" ("device_id" TEXT, "name" TEXT, "category" TEXT, "show" INTEGER, PRIMARY KEY("device_id"));',
        "Room":'CREATE TABLE "Room" ("name"	TEXT,"floor"	INTEGER,"points"	TEXT,PRIMARY KEY("name"))',
        "Group": 'CREATE TABLE "Group" ("id" INTEGER PRIMARY KEY AUTOINCREMENT, "name" TEXT NOT NULL)',
        "DeviceGroup": 'CREATE TABLE "DeviceGroup" ("device_id" TEXT NOT NULL, "group_id" INTEGER NOT NULL,FOREIGN KEY("group_id") REFERENCES "Group"("id") ON DELETE CASCADE, PRIMARY KEY("device_id", "group_id"))',
        "Energy_Timeslot": 'CREATE TABLE "Energy_Timeslot" ("day" INTEGER, "hour" INTEGER, "slot" INTEGER);',
        "Map_config": 'CREATE TABLE "Map_config" ("id" TEXT NOT NULL, "x" INTEGER NOT NULL, "y" INTEGER NOT NULL, "floor" INTEGER NOT NULL, PRIMARY KEY("id"));',
        "Service_logs": 'CREATE TABLE "Service_logs" ("user" TEXT NOT NULL, "service" TEXT NOT NULL, "target" TEXT, "payload" TEXT, "timestamp" INTEGER NOT NULL);',
        "User_Preferences": 'CREATE TABLE "User_Preferences" ("user_id" TEXT NOT NULL, "preferences" TEXT, "data_collection" INTEGER, "data_disclosure" INTEGER, PRIMARY KEY("user_id"));'
    }

    consumption_db_tables = {
        "Appliances_Usage": 'CREATE TABLE "Appliances_Usage" ("device_id" TEXT, "state" TEXT, "average_duration" REAL, "duration_unit" TEXT, "duration_samples" INTEGER, "average_power" REAL, "average_power_unit" TEXT, "power_samples" INTEGER, "maximum_power" REAL, "last_timestamp" INTEGER, PRIMARY KEY("device_id", "state"));',
        "Device_History": 'CREATE TABLE "Device_History" ("device_id" TEXT, "timestamp" INTEGER, "state" TEXT, "power" REAL, "power_unit" TEXT, "energy_consumption" REAL, "energy_consumption_unit" TEXT, PRIMARY KEY("device_id", "timestamp"));',
        "Hourly_Consumption": 'CREATE TABLE "Hourly_Consumption" ("device_id" TEXT, "energy_consumption" REAL, "energy_consumption_unit" TEXT, "from" INTEGER, "to" INTEGER, PRIMARY KEY("device_id", "from"));'
    }

    logs_db_tables = {
        "Logs": 'CREATE TABLE "Logs" ("actor" TEXT NOT NULL,"event" TEXT NOT NULL,"target" TEXT,"payload" TEXT,"timestamp" INTEGER NOT NULL)'
    }

    entity_history_db_tables = {
        "Entity_History": 'CREATE TABLE "Entity_History" ("entity_id" TEXT, "timestamp" INTEGER, "state" TEXT, "power" REAL, "unit_of_measurement" TEXT, "energy_consumption" REAL, PRIMARY KEY("entity_id", "timestamp"));'
    }

    databases = [
        (DbPathEnum.CONFIGURATION, configuration_db_tables, "Configuration"),
        (DbPathEnum.CONSUMPTION, consumption_db_tables, "Consumption"),
        (DbPathEnum.LOGS, logs_db_tables, "Logs"),
        (DbPathEnum.ENTITY_HISTORY, entity_history_db_tables, "Entity History"),
    ]

    for db_path, tables, db_name in databases:
        missing_tables = [query for table, query in tables.items() if not table_exists(db_path, table)]

        if missing_tables:
            logger.info(f"{db_name} database is missing {len(missing_tables)} tables, running migration...")
            create_tables(db_path, missing_tables)
            logger.info(f"{db_name} database migration completed.")
        else:
            logger.info(f"All tables are present in {db_name} database, no migration needed.")

        if db_path == DbPathEnum.CONFIGURATION:
            logger.info(f"Checking if Configuration table contains all the default entries..")
            initialize_default_configuration_values(db_path, default_configuration_values)


def create_tables(databasePath:DbPathEnum,queriesList:list):#TODO:refactor this code with new database structure
    logger = logging.getLogger(__name__)
    success=True
    with get_db_connection(databasePath) as con:
        try:
            cur = con.cursor()
            # Execute each table creation query
            for query in queriesList:
                cur.execute(query)
                success=True if cur.rowcount>0 else False
            con.commit()  # Commit the changes after creating tables
        except sqlite3.Error as e:
            logger.error(f"An error occurred while creating tables for database {databasePath}: {e}")
            con.rollback()  # Rollback if an error occurs
            success=False
    return success


#region General DB operations
def fetch_one_element(db_path:DbPathEnum,query:str, params=None):
    """
    Executes a query to fetch a single element from the database.
    
    :param query: The SQL query to execute.
    :param params: Parameters for the SQL query (optional).
    :return: The first row of the query result as a dictionary, or None if an error occurs.
    """
    with get_db_connection(db_path) as con:
        try:
            cur = con.cursor()
            cur.execute(query, params or ())
            result = cur.fetchone()  # Fetch a single result
            return result if result else None  # Return None if no result found
        except sqlite3.Error as e:
            print(f"An error occurred during fetch_one_element: {e}")
            return None  # Return None if there was an error
        
def fetch_multiple_elements(db_path:DbPathEnum,query:str, params=None):
    """
    Executes a query to fetch multiple elements from the database.
    
    :param query: The SQL query to execute.
    :param params: Parameters for the SQL query (optional).
    :return: The result as a dictionary, or an empty list if an error occurs.
    """
    with get_db_connection(db_path) as con:
        try:
            cur = con.cursor()
            cur.execute(query, params or ())
            result = cur.fetchall()  # Fetch multiple results
            return result if result else []  # Return empty list if no result found
        except sqlite3.Error as e:
            print(f"An error occurred during fetch_one_element: {e}")
            return []  # Return None if there was an error
        
def execute_one_query(db_path:DbPathEnum,query: str, params: tuple = None) -> bool:
    """
    Executes a single SQL query that modifies the database (INSERT, UPDATE, DELETE).

    :param query: The SQL query to execute.
    :param params: A tuple of parameters to substitute into the query.
    :return: True if the query affected any rows, otherwise False.
    """
    try:
        with get_db_connection(db_path) as con:
            cur = con.cursor()
            cur.execute(query, params or ())  # Execute the query with parameters
            con.commit()  # Commit changes
            return cur.rowcount > 0  # Return True if any rows were affected
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")  # Log the error message
        return False  # Return False to indicate failure
        
def add_multiple_elements(db_path:DbPathEnum,query, data):
    """
    Adds multiple elements to the database using the provided query.

    :param query: The SQL query to execute.
    :param data: A list of tuples containing the data to insert.
    :return: True if the elements were added successfully, False otherwise.
    """
    try:
        with get_db_connection(db_path) as con:
            cur = con.cursor()
            cur.executemany(query, data)  # Insert all elements at once
            con.commit()  # Commit changes after inserting
            return cur.rowcount>0  # Return True on success
    except sqlite3.Error as e:
        print(f"An error occurred while adding elements: {e}")
        return False  # Return False if there was an error

#endregion

#region User preferences and data    

def add_user_preferences(preferences_list:list):
    query = "INSERT INTO User_Preferences(user_id, preferences) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET preferences = excluded.preferences"
    return add_multiple_elements(DbPathEnum.CONFIGURATION,query,preferences_list)

def add_user_privacy_settings(settings_list:list):
    query = "INSERT INTO User_Preferences(user_id, data_collection, data_disclosure) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET data_collection=excluded.data_collection, data_disclosure=excluded.data_disclosure"
    return add_multiple_elements(DbPathEnum.CONFIGURATION,query,settings_list)



def get_all_user_preferences():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,"SELECT user_id,preferences FROM User_Preferences")


def get_all_user_privacy_settings():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,"SELECT user_id,data_collection,data_disclosure FROM User_Preferences")

def get_user_preferences_by_user(user_id:str):
    query = "SELECT user_id,preferences FROM User_Preferences WHERE user_id = ?"
    params = (user_id,) 
    return fetch_one_element(DbPathEnum.CONFIGURATION,query,params)

def get_user_privacy_settings_by_user(user_id:str):
    query = "SELECT user_id,data_collection,data_disclosure FROM User_Preferences WHERE user_id = ?"
    params = (user_id,) 
    return fetch_one_element(DbPathEnum.CONFIGURATION,query,params)

def delete_user_preferences_by_user(user_id:str):
    query = "DELETE FROM User_Preferences WHERE user_id = ?"
    params = (user_id,)
    return execute_one_query(DbPathEnum.CONFIGURATION,query,params)

#endregion

#region Service logs

def add_service_logs(logs_list:list):
    query="INSERT into Service_logs(user,service,target,payload,timestamp) VALUES (?,?,?,?,?)"
    return add_multiple_elements(DbPathEnum.CONFIGURATION,query,logs_list)

def get_all_service_logs():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,"SELECT * FROM Service_logs")


def get_service_logs_by_user(user:str):
    query = "SELECT * FROM Service_logs WHERE user= ?"
    params = (user,) 
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,query,params)

#endregion

#region Map entries configuration

    
def add_map_entities(entities_list:list):
    """
    Aggiunge al db tutte le entita' passate in input.

    Args:
    ----------
    entities_list:
    lista di tuple nella forma (id,x,y,floor)

    """
    query="INSERT or REPLACE into Map_config VALUES (?,?,?,?)"
    return add_multiple_elements(DbPathEnum.CONFIGURATION,query,entities_list)


def delete_map_entry(entity_id:str):
    query = "DELETE FROM Map_config WHERE id= ?"
    params = (entity_id,)
    return execute_one_query(DbPathEnum.CONFIGURATION,query,params)

def delete_floor_map_configuration(floor:int):
    query = "DELETE FROM Map_config WHERE floor=?"
    params = (floor,)
    return execute_one_query(DbPathEnum.CONFIGURATION,query,params)

def get_all_map_entities():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,"SELECT * FROM Map_config")


def get_map_entity(id):
    query = "SELECT * FROM Map_config WHERE id = ?"
    params = (id,) 
    return fetch_one_element(DbPathEnum.CONFIGURATION,query,params)

#endregion

#region General Configuration

def add_configuration_values(values_list:list):
    query="INSERT or REPLACE into Configuration(key,value,unit) VALUES (?,?,?)"
    return add_multiple_elements(DbPathEnum.CONFIGURATION,query,values_list)

def get_all_configuration_values():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,"SELECT * FROM Configuration")


def get_configuration_item_by_key(key:str):
    query = "SELECT * FROM Configuration WHERE key= ?"
    params = (key,) 
    return fetch_one_element(DbPathEnum.CONFIGURATION,query,params)

def get_configuration_value_by_key(key:str):
    query = "SELECT value FROM Configuration WHERE key= ?"
    params = (key,) 
    return fetch_one_element(DbPathEnum.CONFIGURATION,query,params)


def delete_configuration_value(key:int):
    query = "SELECT * FROM Configuration WHERE key= ?"
    params = (key,) 
    element=fetch_one_element(DbPathEnum.CONFIGURATION,query,params)
    if element:
        query = "DELETE FROM Configuration WHERE key=?"
        success=execute_one_query(DbPathEnum.CONFIGURATION,query,params)
    else:
        success=True
    return success

#endregion

#region Energy slots planning

def add_energy_slots(slots_list:list):
    query="INSERT or REPLACE into Energy_Timeslot(day,hour,slot) VALUES (?,?,?)"
    return add_multiple_elements(DbPathEnum.CONFIGURATION,query,slots_list)


def get_all_energy_slots():
    con=sqlite3.connect(DbPathEnum.CONFIGURATION)
    cur=con.cursor()
    res=cur.execute("SELECT * FROM Energy_Timeslot ORDER by day ASC, hour ASC")
    res=res.fetchall()
    con.close()
    return res


def get_minimum_energy_slots():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,QUERIES["minimum_energy_slots"])


def get_energy_slot_by_day(day:int):
    query="SELECT * FROM Energy_Timeslot WHERE day= ? ORDER by day ASC, hour ASC"
    params=(day,)
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,query,params)


def get_minimum_cost_slot():
    return fetch_one_element(DbPathEnum.CONFIGURATION,"SELECT MIN(value) as cost FROM Configuration WHERE key LIKE 'cost_slot_%'")

def get_maximum_cost_slot():
    return fetch_one_element(DbPathEnum.CONFIGURATION,"SELECT MAX(value) as cost FROM Configuration WHERE key LIKE 'cost_slot_%'")

def get_energy_slot_by_slot(slot:int):
    query = "SELECT * FROM Energy_Timeslot WHERE slot= ?"
    params = (slot,) 
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,query,params)

def get_all_energy_slots_with_cost():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,QUERIES["energy_slots"])


def delete_energy_slots():
    return execute_one_query(DbPathEnum.CONFIGURATION,"DELETE FROM Energy_Timeslot")

#endregion

#region Total consumption
def add_hourly_consumption_entry(entry_list:list):
    query="INSERT or REPLACE into Hourly_Consumption(device_id,energy_consumption,energy_consumption_unit,start,end) VALUES (?,?,?,?,?)"
    return add_multiple_elements(DbPathEnum.CONSUMPTION,query,entry_list)


def get_all_hourly_consumption_entries():
    return fetch_multiple_elements(DbPathEnum.CONSUMPTION,"SELECT * FROM Hourly_Consumption")

def get_total_consumption(from_timestamp:int,to_timestamp:int,group:str="hourly",device_id:str="",minutes:int=60):
    con=sqlite3.connect(DbPathEnum.CONSUMPTION,)
    cur=con.cursor()
    cur.row_factory=row_to_dict
    device_filter=""
    device_id_field=""
    device_id_grouping=""
    if device_id!="":
        device_id_field="device_id, "
        device_filter="and device_id="+"'"+device_id+"'"
    key=group+"_consumption"
    if group=="total":
        query=QUERIES[key].format(
            from_time=from_timestamp,
            device_filter=device_filter,
            device_id_field=device_id_field)
    else:
        query=QUERIES[key].format(
            from_time=from_timestamp,
            to_time=to_timestamp,
            device_filter=device_filter,
            device_id_field=device_id_field,
            device_id_grouping=device_id_grouping,minutes=minutes)
    res=cur.execute(query)
    res=res.fetchall()
    con.close()
    return res

#endregion

#region Device History
def add_device_history_entry(entry_list):
    query="INSERT or REPLACE into Device_History(device_id,timestamp,state,power,power_unit,energy_consumption,energy_consumption_unit) VALUES (?,?,?,?,?,?,?)"
    return add_multiple_elements(DbPathEnum.CONSUMPTION,query,entry_list)

def get_all_device_history_entries():
    return fetch_multiple_elements(DbPathEnum.CONSUMPTION,"SELECT * FROM Device_History")
#endregion

#region Entity History
def add_entity_history_entry(entry_list):
    query='INSERT OR REPLACE INTO Entity_History(entity_id, timestamp,state,power,unit_of_measurement,energy_consumption) VALUES (?, ?, ?, ?, ?, ?);'
    return add_multiple_elements(DbPathEnum.ENTITY_HISTORY,query,entry_list)

def get_entity_history_entries(entities_list,start_timestamp,end_timestamp):
    entities_list=[f'"{x}"' for x in entities_list]
    query=f"SELECT * FROM Entity_History where timestamp>={start_timestamp} and timestamp<={end_timestamp} and entity_id in ({','.join(entities_list)})"
    return fetch_multiple_elements(DbPathEnum.ENTITY_HISTORY,query)

def get_all_entity_history_entries():
    return fetch_multiple_elements(DbPathEnum.ENTITY_HISTORY,"SELECT * FROM Entity_History")
#endregion

#region Appliances usage
def add_appliances_usage_entry(entry_list:list):
    query="""INSERT or REPLACE into Appliances_Usage
                    (device_id,state,average_duration,duration_unit,duration_samples,average_power,average_power_unit,power_samples,maximum_power,last_timestamp) 
                    VALUES (?,?,?,?,?,?,?,?,?,?)"""
    return add_multiple_elements(DbPathEnum.CONSUMPTION,query,entry_list)

def get_all_appliances_usage_entries():
    return fetch_multiple_elements(DbPathEnum.CONSUMPTION,"SELECT * FROM Appliances_Usage")

def get_usage_entry_for_appliance(device_id:str):
    query='select state,average_power,average_power_unit,average_duration,duration_unit,maximum_power from Appliances_Usage where device_id=?'
    params=(device_id,)
    return fetch_multiple_elements(DbPathEnum.CONSUMPTION,query,params)


def get_usage_entry_for_appliance_state(device_id:str, state:str):
    query='select average_power,average_power_unit,average_duration,duration_unit,maximum_power from Appliances_Usage where device_id=? and state=?'
    params=(device_id,state)
    return fetch_one_element(DbPathEnum.CONSUMPTION,query,params)
#endregion


#region Devices configuration
def add_devices_configuration(entry_list:list):
    query="""INSERT or REPLACE into Device
                    (device_id,name,category,show) 
                    VALUES (?,?,?,?)"""
    return add_multiple_elements(DbPathEnum.CONFIGURATION,query,entry_list)


def get_all_devices_configuration():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,"SELECT * FROM Device")

def get_names_and_id_configuration():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,"SELECT device_id,name FROM Device where show=1")

def get_configuration_of_device(device_id:str):
    query='select name,category,show from Device where device_id=?'
    params=(device_id,)
    return fetch_one_element(DbPathEnum.CONFIGURATION,query,params)
#endregion


#region Room configuration
def add_rooms_configuration(entry_list:list):
    query="""INSERT or REPLACE into Room
                    (name,floor,points) 
                    VALUES (?,?,?)"""
    return add_multiple_elements(DbPathEnum.CONFIGURATION,query,entry_list)

def get_all_rooms_configuration():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,"SELECT * FROM Room")

def get_all_rooms_of_floor(floor:int):
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION,f"SELECT * FROM Room where floor={floor}")

def get_single_room_by_name(name:str):
    return fetch_one_element(DbPathEnum.CONFIGURATION,f"SELECT * FROM Room where name=\"{name}\"")

def update_single_room(old_name:str,new_name:str):
    return execute_one_query(DbPathEnum.CONFIGURATION,f"UPDATE Room SET name=\"{new_name}\" where name=\"{old_name}\"")

def delete_single_room(name:str):
    return execute_one_query(DbPathEnum.CONFIGURATION,f"DELETE FROM Room where name=\"{name}\"")

def delete_rooms_in_floor(floor:int):
    return execute_one_query(DbPathEnum.CONFIGURATION,f"DELETE FROM Room where floor=\"{floor}\"")
#endregion

#region Logs

def add_log(logs_list:list):
    query="""INSERT or REPLACE into Logs
                (actor,event,target,payload,timestamp) 
                VALUES (?,?,?,?,?)"""
    return add_multiple_elements(DbPathEnum.LOGS,query,logs_list)
#endregion

#region Group configuration
def add_groups_configuration(entry_list: list):
    query = "INSERT OR REPLACE INTO \"Group\" (name) VALUES (?)"
    return add_multiple_elements(DbPathEnum.CONFIGURATION, query, entry_list)

def get_all_groups_configuration():
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION, "SELECT * FROM \"Group\"")

def get_single_group_by_id(group_id: int):
    return fetch_one_element(DbPathEnum.CONFIGURATION, f"SELECT * FROM Gro\"Group\"up WHERE id={group_id}")

def update_single_group(group_id: int, new_name: str):
    return execute_one_query(DbPathEnum.CONFIGURATION, f"UPDATE \"Group\" SET name=\"{new_name}\" WHERE id={group_id}")

def delete_single_group(group_id: int):
    return execute_one_query(DbPathEnum.CONFIGURATION, f"DELETE FROM \"Group\" WHERE id={group_id}")
#endregion

#region Device-Group mapping

def add_device_group_mapping(mapping_list: list[tuple[str, int]]):
    """
    Adds multiple (device_id, group_id) mappings to DeviceGroup table.
    Each entry in mapping_list should be a tuple: (device_id, group_id)
    """
    query = 'INSERT OR REPLACE INTO "DeviceGroup" (device_id, group_id) VALUES (?, ?)'
    return add_multiple_elements(DbPathEnum.CONFIGURATION, query, mapping_list)

def get_groups_for_device(device_id: str):
    """
    Returns list of groups (id and name) linked to the given device_id.
    """
    query = '''
    SELECT g.id as group_id, g.name as name
    FROM "DeviceGroup" dg
    JOIN "Group" g ON dg.group_id = g.id
    WHERE dg.device_id = ?
    '''
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION, query, (device_id,))

def get_devices_for_group(group_id: int):
    """
    Returns list of devices (device_id and name) linked to the given group_id.
    """
    query = '''
    SELECT d.device_id as device_id, d.name as name
    FROM "DeviceGroup" dg
    JOIN "Device" d ON dg.device_id = d.device_id
    WHERE dg.group_id = ?
    '''
    return fetch_multiple_elements(DbPathEnum.CONFIGURATION, query, (group_id,))

def remove_device_group_mapping(device_id: str, group_id: int):
    """
    Removes a specific device-to-group link.
    """
    query = 'DELETE FROM "DeviceGroup" WHERE device_id = ? AND group_id = ?'
    return execute_one_query(DbPathEnum.CONFIGURATION, query, (device_id, group_id))

def clear_groups_for_device(device_id: str):
    """
    Removes all group links for a given device.
    """
    query = 'DELETE FROM "DeviceGroup" WHERE device_id = ?'
    return execute_one_query(DbPathEnum.CONFIGURATION, query, (device_id,))

#endregion



#region Rulebot Mongodb database functions


def set_automation_state(automation_id, state):
    client = MongoClient("mongodb://localhost:27017/")
    db = client["Rulebot"]
    automations = db["automations"]

    result = automations.update_many(
        {"automation_data.id": automation_id},
        {
            "$set": {
                "automation_data.$[elem].state": state,
                "last_update": datetime.utcnow()
            }
        },
        array_filters=[{"elem.id": automation_id}]
    )

    if result.modified_count > 0:
        print(f"Updated {result.modified_count} automation(s) with id: {automation_id}")
    else:
        print(f"No automation found with id: {automation_id}")
#endregion