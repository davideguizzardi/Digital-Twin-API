import sqlite3

DB_PATH="./data/digital_twin.db"

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
        'CREATE TABLE "Energy_Timeslot" ("day"	INTEGER,"hour"	INTEGER,"slot"	INTEGER);'
    ]
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    for query in query_list:
        res=cur.execute(query)
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
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    cur.execute("DELETE FROM Configuration WHERE key='"+key+"'")
    con.commit()
    success=True if cur.rowcount>0 else False
    con.close()
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


