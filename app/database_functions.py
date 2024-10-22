import sqlite3
from contextlib import contextmanager

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
def get_db_connection(db_path=DB_PATH):
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

def initialize_database():
    create_tables()

    
def create_tables():
    table_creation_queries=[
        'CREATE TABLE "Configuration" ("key" TEXT NOT NULL,"value" TEXT NOT NULL,"unit"	TEXT,PRIMARY KEY("key"));',
        'CREATE TABLE "Map_config" ("entity_id" TEXT NOT NULL,"x" INTEGER NOT NULL,"y" INTEGER NOT NULL,"floor" INTEGER NOT NULL,PRIMARY KEY("entity_id"));',
        'CREATE TABLE "Service_logs" ("user"	TEXT NOT NULL,"service"	TEXT NOT NULL,"target"	TEXT,"payload"	TEXT,"timestamp"	INTEGER NOT NULL);',
        'CREATE TABLE "Energy_Timeslot" ("day"	INTEGER,"hour"	INTEGER,"slot"	INTEGER);',
        'CREATE TABLE "Daily_Consumption" ("device_id" TEXT,"energy_consumption"	REAL,"energy_consumption_unit" TEXT,"use_time" REAL,"use_time_unit" TEXT,"date" INTEGER,PRIMARY KEY("device_id","date"))',
        'CREATE TABLE "Hourly_Consumption" ("device_id" TEXT,"energy_consumption" REAL,"energy_consumption_unit"	TEXT,"from"	INTEGER,"to" INTEGER,PRIMARY KEY("device_id","from"))',
        'CREATE TABLE "Appliances_Usage" ("device_id"	TEXT,"state"	TEXT,"average_duration"	REAL,"duration_unit"	TEXT,"duration_samples"	INTEGER,"average_power"	REAL,"average_power_unit"	TEXT,"power_samples"	INTEGER,"last_timestamp"	INTEGER,PRIMARY KEY("device_id","state"))',
        'CREATE TABLE "User_Preferences" ("user_id"	TEXT NOT NULL,"preferences"	TEXT,"data_collection"	INTEGER,"data_disclosure"	INTEGER,PRIMARY KEY("user_id"))'
    ]
    success=True
    with get_db_connection() as con:
        try:
            cur = con.cursor()
            # Execute each table creation query
            for query in table_creation_queries:
                cur.execute(query)
                success=True if cur.rowcount>0 else False
            con.commit()  # Commit the changes after creating tables
        except sqlite3.Error as e:
            print(f"An error occurred while creating tables: {e}")
            con.rollback()  # Rollback if an error occurs
            success=False
    return success


#region General DB operations
def fetch_one_element(query:str, params=None):
    """
    Executes a query to fetch a single element from the database.
    
    :param query: The SQL query to execute.
    :param params: Parameters for the SQL query (optional).
    :return: The first row of the query result as a dictionary, or None if an error occurs.
    """
    with get_db_connection() as con:
        try:
            cur = con.cursor()
            cur.execute(query, params or ())
            result = cur.fetchone()  # Fetch a single result
            return result if result else None  # Return None if no result found
        except sqlite3.Error as e:
            print(f"An error occurred during fetch_one_element: {e}")
            return None  # Return None if there was an error
        
def fetch_multiple_elements(query:str, params=None):
    """
    Executes a query to fetch multiple elements from the database.
    
    :param query: The SQL query to execute.
    :param params: Parameters for the SQL query (optional).
    :return: The result as a dictionary, or an empty list if an error occurs.
    """
    with get_db_connection() as con:
        try:
            cur = con.cursor()
            cur.execute(query, params or ())
            result = cur.fetchall()  # Fetch multiple results
            return result if result else []  # Return empty list if no result found
        except sqlite3.Error as e:
            print(f"An error occurred during fetch_one_element: {e}")
            return []  # Return None if there was an error
        
def execute_one_query(query: str, params: tuple = None) -> bool:
    """
    Executes a single SQL query that modifies the database (INSERT, UPDATE, DELETE).

    :param query: The SQL query to execute.
    :param params: A tuple of parameters to substitute into the query.
    :return: True if the query affected any rows, otherwise False.
    """
    try:
        with get_db_connection() as con:
            cur = con.cursor()
            cur.execute(query, params or ())  # Execute the query with parameters
            con.commit()  # Commit changes
            return cur.rowcount > 0  # Return True if any rows were affected
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")  # Log the error message
        return False  # Return False to indicate failure
        
def add_multiple_elements(query, data):
    """
    Adds multiple elements to the database using the provided query.

    :param query: The SQL query to execute.
    :param data: A list of tuples containing the data to insert.
    :return: True if the elements were added successfully, False otherwise.
    """
    try:
        with get_db_connection() as con:
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
    query="INSERT or REPLACE into User_Preferences(user_id,preferences) VALUES (?,?)"
    return add_multiple_elements(query,preferences_list)

def add_user_privacy_settings(settings_list:list):
    query="INSERT or REPLACE into User_Preferences(user_id,data_collection,data_disclosure) VALUES (?,?,?)"
    return add_multiple_elements(query,settings_list)



def get_all_user_preferences():
    return fetch_multiple_elements("SELECT user_id,preferences FROM User_Preferences")


def get_all_user_privacy_settings():
    return fetch_multiple_elements("SELECT user_id,data_collection,data_disclosure FROM User_Preferences")

def get_user_preferences_by_user(user_id:str):
    query = "SELECT user_id,preferences FROM User_Preferences WHERE user_id = ?"
    params = (user_id,) 
    return fetch_one_element(query,params)

def get_user_privacy_settings_by_user(user_id:str):
    query = "SELECT user_id,data_collection,data_disclosure FROM User_Preferences WHERE user_id = ?"
    params = (user_id,) 
    return fetch_one_element(query,params)

def delete_user_preferences_by_user(user_id:str):
    query = "DELETE FROM User_Preferences WHERE user_id = ?"
    params = (user_id,)
    return execute_one_query(query,params)

#endregion

#region Service logs

def add_service_logs(logs_list:list):
    query="INSERT into Service_logs(user,service,target,payload,timestamp) VALUES (?,?,?,?,?)"
    return add_multiple_elements(query,logs_list)

def get_all_service_logs():
    return fetch_multiple_elements("SELECT * FROM Service_logs")


def get_service_logs_by_user(user:str):
    query = "SELECT * FROM Service_logs WHERE user= ?"
    params = (user,) 
    return fetch_multiple_elements(query,params)

#endregion

#region Map entries configuration

    
def add_map_entities(entities_list:list):
    """
    Aggiunge al db tutte le entita' passate in input.

    Args:
    ----------
    entities_list:
    lista di tuple nella forma (entity_id,x,y,floor)

    """
    query="INSERT or REPLACE into Map_config VALUES (?,?,?,?)"
    return add_multiple_elements(query,entities_list)


def delete_map_entry(entity_id:str):
    query = "DELETE FROM Map_config WHERE entity_id= ?"
    params = (entity_id,)
    return execute_one_query(query,params)

def delete_floor_map_configuration(floor:int):
    query = "DELETE FROM Map_config WHERE floor=?"
    params = (floor,)
    return execute_one_query(query,params)

def get_all_map_entities():
    return fetch_multiple_elements("SELECT * FROM Map_config")


def get_map_entity(id):
    query = "SELECT * FROM Map_config WHERE entity_id = ?"
    params = (id,) 
    return fetch_one_element(query,params)

#endregion

#region General Configuration

def add_configuration_values(values_list:list):
    query="INSERT or REPLACE into Configuration(key,value,unit) VALUES (?,?,?)"
    return add_multiple_elements(query,values_list)

def get_all_configuration_values():
    return fetch_multiple_elements("SELECT * FROM Configuration")


def get_configuration_value_by_key(key:str):
    query = "SELECT * FROM Configuration WHERE key= ?"
    params = (key,) 
    return fetch_one_element(query,params)


def delete_configuration_value(key:int):
    query = "SELECT * FROM Configuration WHERE key= ?"
    params = (key,) 
    element=fetch_one_element(query,params)
    if element:
        query = "DELETE FROM Configuration WHERE key=?"
        success=execute_one_query(query,params)
    else:
        success=True
    return success

#endregion

#region Energy slots planning

def add_energy_slots(slots_list:list):
    query="INSERT or REPLACE into Energy_Timeslot(day,hour,slot) VALUES (?,?,?)"
    return add_multiple_elements(query,slots_list)


def get_all_energy_slots():
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    res=cur.execute("SELECT * FROM Energy_Timeslot ORDER by day ASC, hour ASC")
    res=res.fetchall()
    con.close()
    return res


def get_minimum_energy_slots():
    return fetch_multiple_elements(QUERIES["minimum_energy_slots"])


def get_energy_slot_by_day(day:int):
    query="SELECT * FROM Energy_Timeslot WHERE day= ? ORDER by day ASC, hour ASC"
    params=(day,)
    return fetch_multiple_elements(query,params)


def get_minimum_cost_slot():
    return fetch_one_element("SELECT MIN(value) as cost FROM Configuration WHERE key LIKE 'cost_slot_%'")

def get_energy_slot_by_slot(slot:int):
    query = "SELECT * FROM Energy_Timeslot WHERE slot= ?"
    params = (slot,) 
    return fetch_multiple_elements(query,params)

def get_all_energy_slots_with_cost():
    return fetch_multiple_elements(QUERIES["energy_slots"])


def delete_energy_slots():
    return execute_one_query("DELETE FROM Energy_Timeslot")

#endregion

#region Daily consumption and Total consumption
def add_daily_consumption_entry(entry_list:list):
    query="INSERT or REPLACE into Daily_Consumption(device_id,energy_consumption,energy_consumption_unit,use_time,use_time_unit,date) VALUES (?,?,?,?,?,?)"
    return add_multiple_elements(query,entry_list)


def get_all_daily_consumption_entries():
    return fetch_multiple_elements("SELECT * FROM Daily_Consumption")


def add_hourly_consumption_entry(entry_list:list):
    query="INSERT or REPLACE into Hourly_Consumption(device_id,energy_consumption,energy_consumption_unit,start,end) VALUES (?,?,?,?,?)"
    return add_multiple_elements(query,entry_list)


def get_all_hourly_consumption_entries():
    return fetch_multiple_elements("SELECT * FROM Hourly_Consumption")

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

#endregion

#region Appliances usage
def add_appliances_usage_entry(entry_list:list):
    query="""INSERT or REPLACE into Appliances_Usage
                    (device_id,state,average_duration,duration_unit,duration_samples,average_power,average_power_unit,power_samples,last_timestamp) 
                    VALUES (?,?,?,?,?,?,?,?,?)"""
    return add_multiple_elements(query,entry_list)

def get_all_appliances_usage_entries():
    return fetch_multiple_elements("SELECT * FROM Appliances_Usage")


def get_appliance_usage_entry(device_id:str, state:str):
    query='select average_power,average_power_unit,average_duration,duration_unit from Appliances_Usage where device_id=? and state=?'
    params=(device_id,state)
    return fetch_one_element(query,params)


