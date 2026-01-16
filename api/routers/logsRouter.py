from fastapi import APIRouter, HTTPException
from schemas import Log_List,Operation_Out
from database_functions import add_log,get_all_logs,get_logs_for_actor
from datetime import datetime

def getLogRouter():
    log_router = APIRouter(tags=["Log"], prefix="/log")

    @log_router.put("",response_model=Operation_Out)
    def Add_Log(logs_list:Log_List):
        tuple_list=[(x.actor,x.event,x.target,x.payload,datetime.now().replace(microsecond=0).timestamp()) for x in logs_list.data]
        return {"success":add_log(tuple_list)}
    
    @log_router.get("/sessions")
    def Get_Log_Sessions():
        # Fetch all logs ordered by actor and timestamp with formatted datetime
        logs = get_all_logs()
        
        sessions = []
        current_session = []
        current_actor = None

        for log in logs:
            actor = log['actor']

            # Reset session when actor changes
            if current_actor != actor:
                if current_session:
                    sessions.append(current_session)
                current_session = []
                current_actor = actor

            # Start a new session at each Login
            if log['event'] == 'Login' and current_session:
                sessions.append(current_session)
                current_session = []

            # Add log to current session
            current_session.append(log)

        if current_session:
            sessions.append(current_session)

        formatted_sessions = []
        for session in sessions:
            if len(session) <= 1:
                continue  # Skip sessions with only one event
            formatted_sessions.append({
                "actor": session[0]['actor'],
                "start_time": session[0]['datetime'],
                "end_time": session[-1]['datetime'],
                "events": [
                    {
                        "event": e['event'],
                        "target": e['target'],
                        "payload": e['payload'],
                        "timestamp": e['datetime'] 
                    }
                    for e in session
                ]
            })

        return {"sessions": formatted_sessions}
    
    @log_router.get("/sessions/{actor}")
    def Get_Sessions_For_Actor(actor: str):
        logs = get_logs_for_actor(actor)
        if not logs:
            raise HTTPException(status_code=404, detail="No logs found for this actor")

        sessions = []
        current_session = []

        for log in logs:
            # Start new session at each Login
            if log['event'] == 'Login' and current_session:
                sessions.append(current_session)
                current_session = []

            current_session.append(log)

        if current_session:
            sessions.append(current_session)

        # Filter out sessions with only one event and format output
        formatted_sessions = []
        for session in sessions:
            if len(session) <= 1:
                continue
            formatted_sessions.append({
                "actor": session[0]['actor'],
                "start_time": session[0]['datetime'],
                "end_time": session[-1]['datetime'],
                "events": [
                    {
                        "event": e['event'],
                        "target": e['target'],
                        "payload": e['payload'],
                        "timestamp": e['datetime']
                    }
                    for e in session
                ]
            })

        return {"sessions": formatted_sessions}


    return log_router
