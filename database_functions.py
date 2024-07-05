import sqlite3

DB_PATH="./data/digital_twin.db"

def row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict:
    data = {}
    for idx, col in enumerate(cursor.description):
        data[col[0]] = row[idx]
    return data

def initialize_database():
    return create_map_entities_table()

def create_map_entities_table():
    query='CREATE TABLE "Map_config" ("entity_id" TEXT NOT NULL,"x" INTEGER NOT NULL,"y" INTEGER NOT NULL,"floor" INTEGER NOT NULL,PRIMARY KEY("entity_id"));'
    con=sqlite3.connect(DB_PATH)
    cur=con.cursor()
    res=cur.execute(query)
    success=True if cur.rowcount>0 else False
    con.close()
    return success
    
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

