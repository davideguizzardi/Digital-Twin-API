from requests import get,post
from random import randint
from schemas import Service_In
from urllib.parse import urlencode
import json,datetime,time,configparser,os
from dateutil import tz,parser

from database_functions import get_configuration_value_by_key,add_configuration_values

from demo_functions import get_all_demo_devices,get_all_demo_entities,get_demo_automations,get_demo_entity,get_single_demo_device

base_url="http://homeassistant.local:8123/api"
headers = {}
demo=False
CONFIGURATION_PATH="./data/configuration.txt"

def buildError(response):
    return {"status_code":response.status_code,"data":response.text}

def initializeDemo():
    global demo
    dm=get_configuration_value_by_key("enable_demo")
    demo=dm["value"] or demo


def initializeToken():
    global headers
    global base_url
    url = get_configuration_value_by_key("server_url")
    base_url=url["value"]  or base_url
    tkn=get_configuration_value_by_key("token")
    token=tkn["value"] or ""

    headers = {
    "Authorization": "Bearer "+token,
    "content-type": "application/json",
    }


def setHomeAssistantConfiguration(token,server_url=None): #TODO:think it is better to move this elsewhere
    """
    Sets the Home Assistant configuration values (token and optionally server_url) in the database.

    :param token: The Home Assistant long-lived access token.
    :param server_url: Optional server address to override the default.
    :return: True if the values were updated, False otherwise.
    """
    values=[]
    if token:
        values.append(("token",token,""))
    if server_url:
        values.append(("server_url",server_url,""))
    updated = add_configuration_values(values)
    

    if updated:
        new_token = get_configuration_value_by_key("token")
        new_token=new_token["value"] or ""
        new_url = get_configuration_value_by_key("server_url")
        new_url=new_url["value"] or ""

        if token and new_token!=token:
            return False
        
        if server_url and new_url!=server_url:
            return False
        
        initializeToken()

    return updated
    
def getHomeAssistantConfiguration() -> dict:
    """
    Retrieves the Home Assistant configuration from the database.

    :return: A dictionary containing 'server_url' and 'token'.
    :raises Exception: If required configuration keys are missing.
    """
    server_url_entry = get_configuration_value_by_key("server_url")
    token_entry = get_configuration_value_by_key("token")

    if not server_url_entry or not token_entry:
        raise Exception("Missing Home Assistant configuration in the database.")

    return {
        "server_url": server_url_entry["value"],
        "token": token_entry["value"]
    }
    

def extractEntityData(entity,skip_services=False):
    device = getDeviceId(entity["entity_id"])
    entity["device_id"]=device

    if not skip_services:
        resp=getServicesByEntity(entity["entity_id"])
        if resp["status_code"]!=200:
            return buildError(resp)

        services=resp["data"]
        entity["services"]=services

    #Sposto i campi 
    entity["friendly_name"]=entity["attributes"].get("friendly_name")

    if entity["attributes"].get("unit_of_measurement"):
        entity["unit_of_measurement"]=entity["attributes"]["unit_of_measurement"]
        #entity["state"]+=entity["attributes"]["unit_of_measurement"]

    entity["entity_class"]=entity["attributes"].get("device_class") if entity["attributes"].get("device_class") else entity["entity_id"].split(".")[0]

    #Rimuovo i campi non necessari
    entity.pop("context",None)
    entity.pop("last_changed",None)
    entity.pop("last_reported",None)
    entity.pop("last_updated",None)
    #entity["attributes"].pop("supported_features",None)
    entity["attributes"].pop("friendly_name",None)
    entity["attributes"].pop("supported_color_modes",None)
    entity["attributes"].pop("device_class",None)
    entity["attributes"].pop("unit_of_measurement",None)
    return entity


def getEntities(skip_services=False):
    '''
    Ritorna la lista di tutte le entità di HA
    '''
    if demo:
        return {"status_code":200,"data":get_all_demo_entities()}
    start_time = time.time()
    response = get(base_url+"/states", headers=headers)
    if response.status_code!=200:
        return buildError(response)
    
    entity_list=response.json()
    res_list=[]
    for entity in entity_list:
        res_list.append(extractEntityData(entity,skip_services))
    #print("Time to get all entities:"+str((time.time()-start_time)*1000)+" ms") #TODO: add debug logs
    return {"status_code":200,"data":res_list}


def getSingleDeviceFast(device_id:str):
    if demo:
        return {"status_code":200,"data":get_single_demo_device(device_id)}
    start=datetime.datetime.now()
    templ="{%- set device = '"+device_id+"' %}"
    templ+="{%- set entities = device_entities(device) | list %}"
    templ+="{%- set var = namespace(entities = [],state = '',device_class = 'sensor',energy_entity_id='',power_entity_id='',state_entity_id='')%}"
    templ+="{%- for entity in entities %}"
    templ+="{%- if not entity.split('.')[0] in ['sensor','binary_sensor'] %}"
    templ+="{%- set var.state=states(entity)%}"
    templ+="{%- set var.state_entity_id=entity%}"
    templ+="{%- set var.device_class=entity.split('.')[0]%}"
    templ+="{%- if var.energy_entity_id== ''%}"
    templ+="{%- set var.energy_entity_id= entity %}"
    templ+="{%- endif %}"
    templ+="{%- endif %}"
    templ+="{%- if state_attr(entity,'device_class')== 'energy'%}"
    templ+="{%- set var.energy_entity_id= entity %}"
    templ+="{%- endif %}"
    templ+="{%- if state_attr(entity,'device_class')== 'power'%}"
    templ+="{%- set var.power_entity_id= entity %}"
    templ+="{%- endif %}"
    templ+="{%- set var.entities=var.entities+[{'entity_id':entity,'state':states(entity),'entity_class':state_attr(entity,'device_class'),'unit_of_measurement':state_attr(entity,'unit_of_measurement')}]%}"
    templ+="{%- endfor %}"
    templ+="{%- set dev = {'name':device_attr(device,'name'),'device_id':device,'name_by_user':device_attr(device,'name_by_user'),'model':device_attr(device,'model'),'manufacturer':device_attr(device,'manufacturer'),'state':var.state,'device_class':var.device_class,'energy_entity_id':var.energy_entity_id,'power_entity_id':var.power_entity_id,'state_entity_id':var.state_entity_id,'list_of_entities':var.entities}%}"
    templ+="{{ dev |to_json(sort_keys=True)}}"
    response = post(base_url+"/template", headers=headers, json={"template":templ})
    res= json.loads(response.text)
    
    #print("getSingleDevice:"+device_id+" elapsed time "+str((datetime.datetime.now()-start).total_seconds())) #TODO:add log in debug
    return {"status_code":200,"data":res}

def getDevicesNameAndId():
    if demo:
        return {"status_code":200,"data":get_all_demo_devices(get_only_names=True)}
    start=datetime.datetime.now()
    templ=(
        "{% set devices = states | map(attribute='entity_id') | map('device_id') | unique | reject('eq',None) | list %}"
        "{%- set ns = namespace(devices = []) %}"
        "{%- for device in devices %}"
        "{%- set name=device_attr(device,'name')%}"
        "{%- if device_attr(device,'name_by_user')%}"
        "{%- set name=device_attr(device,'name_by_user')%}"
        "{%- endif %}"
        "{%- set dev = {'name':name,'device_id':device}%}"
        "{%- if dev %}{%- set ns.devices = ns.devices + [ dev ] %}{%- endif %}{%- endfor %}"
        "{{ ns.devices |to_json(sort_keys=True)}}")
    response = post(base_url+"/template", headers=headers, json={"template":templ})
    res= json.loads(response.text)
    
    #print("getDevicesNameAndId: elapsed time "+str((datetime.datetime.now()-start).total_seconds())) #TODO: add logs in debug
    return {"status_code":200,"data":res}
    


def getDevicesFast():
    if demo:
        return {"status_code":200,"data":get_all_demo_devices()}
    start=datetime.datetime.now()
    templ=(
    "{% set devices = states | map(attribute='entity_id') | map('device_id') | unique | reject('eq',None) | list %}"
    "{%- set ns = namespace(devices = []) %}{%- for device in devices %}"
    "{%- set entities = device_entities(device) | list %}"
    "{%- set var = namespace(entities = [],state = '',device_class = 'sensor',energy_entity_id='',power_entity_id='',state_entity_id='')%}"
    "{%- for entity in entities %}"
    "{%- if not entity.split('.')[0] in ['sensor','binary_sensor'] %}"
    "{%- set var.state=states(entity)%}"
    "{%- set var.state_entity_id=entity%}"
    "{%- set var.device_class=entity.split('.')[0]%}"
    "{%- if var.energy_entity_id== ''%}"
    "{%- set var.energy_entity_id= entity %}"
    "{%- endif %}"
    "{%- endif %}"
    "{%- if state_attr(entity,'device_class')== 'energy'%}"
    "{%- set var.energy_entity_id= entity %}"
    "{%- endif %}"
    "{%- if state_attr(entity,'device_class')== 'power'%}"
    "{%- set var.power_entity_id= entity %}"
    "{%- endif %}"
    #"{%- set var.entities=var.entities+[{'entity_id':entity,'state':states(entity),'entity_class':state_attr(entity,'device_class'),'unit_of_measurement':state_attr(entity,'unit_of_measurement'),'attributes': states[entity].attributes}]%}"
    "{%- set var.entities=var.entities+[{'entity_id':entity,'state':states(entity),'entity_class':state_attr(entity,'device_class'),'unit_of_measurement':state_attr(entity,'unit_of_measurement')}]%}"
    "{%- endfor %}"
    "{%- set dev = {'name':device_attr(device,'name'),'device_id':device,'name_by_user':device_attr(device,'name_by_user'),'model':device_attr(device,'model'),'manufacturer':device_attr(device,'manufacturer'),'state':var.state,'device_class':var.device_class,'energy_entity_id':var.energy_entity_id,'power_entity_id':var.power_entity_id,'state_entity_id':var.state_entity_id,'list_of_entities':var.entities}%}"
    "{%- if dev %}{%- set ns.devices = ns.devices + [ dev ] %}{%- endif %}{%- endfor %}"
    "{{ ns.devices |to_json(sort_keys=True)}}"
    )
    response = post(base_url+"/template", headers=headers, json={"template":templ})
    res= json.loads(response.text)
    
    #print("getDevicesFast: elapsed time "+str((datetime.datetime.now()-start).total_seconds())) #TODO:add debug logs
    return {"status_code":200,"data":res}

def getEntity(entity_id:str):
    '''Ritorna l'entità con l'entity_id passato'''
    if demo:
        return {"status_code":200,"data":get_demo_entity(entity_id)}
    response = get(base_url+"/states"+"/"+entity_id, headers=headers)
    if response.status_code!=200:
        return buildError(response)
    return {"status_code":200,"data":response.json()}


def getHistory(entities_id:str,start_timestamp:datetime.datetime |None, end_timestamp:datetime.datetime |None):
    '''Ritorna la storia dei valori assunti durante le ultime 24 ore dell'entità specificata '''
    params={"filter_entity_id":entities_id}
    if(end_timestamp):
        params.update({"end_time":end_timestamp.replace(microsecond=0).isoformat()})
    params=urlencode(params,doseq=True)+"&minimal_response"
    #params=urlencode(params,doseq=True)+"&minimal_response&no_attributes"
    url=base_url+"/history/period"+"/"+start_timestamp.replace(microsecond=0).isoformat() if start_timestamp else base_url+"/history/period"
    response=get(url=url,headers=headers,params=params)
    if response.status_code!=200:
        return buildError(response)
    
    state_list=response.json()
    file = open("./data/entities_consumption_map.json")
    consumption_map=json.load(file)
    res={}
    for entity_state in state_list:
        entity_id=entity_state[0]["entity_id"]
        unit=""
        if entity_state[0]["attributes"].get("unit_of_measurement"):
            unit=entity_state[0]["attributes"].get("unit_of_measurement")
        
        if entity_state[0]["attributes"].get("device_class")=="power":
           extract_power=True 
        else: 
            extract_power=False
            modes=consumption_map.get(entity_id.split(".")[0],[])

        for entity_data in entity_state:
            temp_date=parser.parse(entity_data["last_changed"]).astimezone(tz.tzlocal())
            entity_data["last_changed"]=temp_date.isoformat()
            if not extract_power:
                if entity_data["state"] in modes:
                    state_consumption=modes[entity_data["state"]]["power_consumption"]
                else:
                    state_consumption=0
            else:
                try:
                    state_consumption=float(entity_data["state"])
                except ValueError:
                    state_consumption=0
            entity_data.update({"unit_of_measurement":unit,"power_consumption":state_consumption})
        res[entity_id]=entity_state
    file.close()
    return {"status_code":200,"data":res}


def getServicesByEntity(entity_id:str):
    '''
    Ritorna la lista dei servizi supportati dell'entità specificata.
    Per le lampadine viene fatto un controllo delle modalità supportate e inseriti solo i campi adeguati
    '''
    start_function=datetime.datetime.now()
    #estraggo i dati dell'entita per avere le supported_features
    response = get(base_url+"/states"+"/"+entity_id, headers=headers)
    if response.status_code!=200:
        return buildError(response)
    
    entity=response.json()
    entity_supported_features=entity["attributes"].get("supported_features")

    #il valore supported_features è un numero binario in cui un bit è 1 se la rispettiva feature è supportata
    #con la riga qui sotto ottengo una lista con la rappresentazione decimale di tutti i bit a 1.
    #la lista viene usata per estrarre soltanto i servizi che sono compatibili con l'entità.
    #Alucune entità non hanno in valore supported_features quindi è necessario controllare prima
    
    entity_supported_features=getListOfSupported(entity_supported_features) if entity_supported_features else []

    #Estraggo tutti i servizi del dominio dell'entità richiesta
    domain=entity_id.split('.')[0]
    response = get(base_url+"/services", headers=headers)
    if response.status_code!=200:
        return buildError(response)
    
    supported_services={}
    if domain!="":
        x=json.loads(response.text)
        for obj in x:
            if obj["domain"]==domain:
                services=obj["services"]
                #Se sono stato in grado di estrarre le supported features dell'entità allora vado alla ricerca
                #dei soli servizi supportati, se così non fosse li aggiungo tutti
                if len(entity_supported_features)>0:
                    #per ogni servizio controllo che il suo valore "supported_features" sia presente nella lista estratta all'inizio
                    #se è presente allora lo aggiungo al risultato
                    for key in services:
                        service_supported_features=None
                        if services[key].get("target",None):
                            service_supported_features=services[key]["target"]["entity"][0].get("supported_features")
                        #alcuni servizi non dispongono del campo supported features,in quel caso il servizio è ritenuto
                        #supportato di default
                        if service_supported_features:
                            if len(intersection(service_supported_features,entity_supported_features))>0:
                            #if service_supported_features[0] in entity_supported_features:
                                supported_services.update({key:obj["services"][key]})
                        else:
                            supported_services.update({key:obj["services"][key]})
                else:
                    supported_services=services

    #Per alcune entità (luci,ventilatori) è interessante capire quali sono i campi supportati dai servizi.
    #Es. una luce potrebbe avere la luminosità regolabile ma non il colore e viceversa.
    if domain in ["light","fan"]:
        for service_key in supported_services:
            fields=supported_services[service_key]['fields']
            supported_fields={}
            for field_key in fields:
                #alcuni campi all'interno dello stesso servizio potrebbero non avere il campo 'filter' (es. turn_on nei ventilatori)
                #nel caso in cui tale campo manca si suppone che esso sia supportato di default
                if fields[field_key].get('filter'):
                    field_supported_features= fields[field_key].get('filter').get('supported_features')
                    if field_supported_features:
                        if len(intersection(field_supported_features,entity_supported_features))>0:
                            supported_fields.update({field_key:fields[field_key]})
                    else:        
                        field_supported_color_modes=fields[field_key]['filter'].get('attribute').get("supported_color_modes")
                        if field_supported_color_modes:
                            if len(intersection(field_supported_color_modes,entity["attributes"].get("supported_color_modes")))>0:
                                supported_fields.update({field_key:fields[field_key]})
                else:
                    supported_fields.update({field_key:fields[field_key]})
            supported_services[service_key]["fields"]=supported_fields

    #Alla fine di tutto ripulisco i dati dai campi non necessari.
    #TODO:ottimizzare la cosa evitando di fare un ciclo aggiuntivo
    for service_key in supported_services:
        supported_services[service_key].pop("target",None)
    #print("getServicesByEntity required "+str((datetime.datetime.now()-start_function).total_seconds())+"[s]") TODO: add debug logs
    return {"status_code":200,"data":supported_services}


def getAutomations():
    '''Ritorna la lista dei dettagli delle automazioni salvate in HA.'''
    if demo:
        return get_demo_automations()
    
    ids=[]
    automations=[]

    response = get(base_url+"/states", headers=headers)
    if response.status_code!=200:
        return buildError(response)
    x=json.loads(response.text)
    for state in x:
        if state["entity_id"].startswith("automation"):
            ids.append((state["attributes"]["id"],state["entity_id"],state["state"]))

    for automation_id,entity_id,automation_state in ids:
        response = get(base_url+"/config/automation/config/"+automation_id,headers=headers)
        to_add=response.json()
        to_add.update({"entity_id":entity_id,"state":automation_state})
        automations.append(to_add)
    return {"status_code":200,"data":automations}


def callService(service:Service_In):
    '''Esegue il servizio specificato, sull'entità specificata e con i parametri specificati'''
    domain=service.entity_id.split('.')[0]
    url = base_url+"/services"+"/"+domain+"/"+service.service
    data = {"entity_id": service.entity_id}
    data.update(service.data) #fondo i due dizionari 
    response = post(url, headers=headers, json=data)
    if response.status_code!=200:
        return buildError(response)
    return {"status_code":200,"data":response.json()}


def getServicesByDomain(domain="",keys_only=False):
    '''Ritorna tutti i servizi disponibili per uno specifico dominio.'''
    response = get(base_url+"/services", headers=headers)

    if response.status_code!=200:
        return buildError(response)
    if domain!="":
        x=json.loads(response.text)
        for obj in x:
            if obj["domain"]==domain:
                return obj["services"].keys() if keys_only else json.dumps(obj)
    return {"status_code":200,"data":response.text}


    
def intersection(list1,list2)->list:
    '''Ritorna l'intersezione di due liste. Metodo di supporto utilizzato per individuare i servizi supportati delle entità'''
    return list(set(list1) & set(list2))


def createAutomation(name:str,description:str,triggers:list,conditions:list,actions:list):
    '''Crea una nuova automazione in HA'''
    id=randint(1,100)
    data={
    "id": str(id),
    "alias": name,
    "description": description,
    "trigger": triggers,
    "condition": conditions,
    "action": actions,
    "mode": "single"
    }
    response = post(base_url+"/config/automation/config/"+str(id), headers=headers, json=data)
    return (id,response.text)

def createAutomationDirect(automation):
    automation["id"]=str(automation["id"])
    body=automation
    response = post(base_url+"/config/automation/config/"+str(automation["id"]), headers=headers, json=body)
    return (automation["id"],response.text)


def getDeviceId(entity_id:str):
    '''Dato l'id di un'entità ritorna l'id del dispositivo a cui tale entità è associata'''
    templ="{{device_id('"+entity_id+"')}}"
    response = post(base_url+"/template", headers=headers, json={"template":templ})
    return response.text


def getDeviceInfo(device_id:str):
    '''Dato l'id di un'entità ritorna l'id del dispositivo a cui tale entità è associata'''
    data=['manufacturer','model','name','name_by_user']
    templ='{'
    for value in data:
        templ=templ+'"'+value+'":"{{device_attr("'+device_id+'","'+value+'")}}"'
        if data.index(value) !=len(data)-1:
            templ=templ+','
    templ=templ+'}'
    response = post(base_url+"/template", headers=headers, json={"template":templ})
    obj=json.loads(response.text)
    return obj

def getTriggerForDevice(entity_id:str,type:str)->dict:
    domain=str.split(entity_id,'.')[0]
    device_id=getDeviceId(entity_id)
    return{
        "platform":"device",
        "type":type,
        "domain":domain,
        "entity_id":entity_id,
        "device_id":device_id
    }

def getListOfSupported(supported_features:int)->list[int]:
    '''
    Converte il valore 'supported_features' in una lista di valori che rappresentano singole features.
    'supported_features' è la rappresentazione decimale di un numero binario dove un bit è a 1 se l'entità supporta la relativa funzione.
    '''
    binary=bin(supported_features)
    res=[]
    i=0
    binary=binary[2:]
    for bit in binary[::-1]:
        if bit=='1':
            res.append(pow(2,i))
        i=i+1
    return res

from collections import defaultdict
from database_functions import add_multiple_elements

def main():
    initializeToken()
    new_list=[]
    devices=defaultdict(lambda:[])
    res=getDevicesFast()
    if res["status_code"]==200:
        with open("devices.json", "w") as json_file:
            json.dump({"list":res["data"]}, json_file, indent=4) 


if __name__ == "__main__":
    main()