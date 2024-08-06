from requests import get,post
from random import randint
from schemas import Service_In
from urllib.parse import urlencode
import json,datetime,time,configparser
from dateutil import tz,parser

base_url="http://homeassistant.local:8123/api"
headers = {}

def buildError(response):
    return {"status_code":response.status_code,"data":response.text}

def initializeToken():
    global headers
    global base_url
    parser=configparser.ConfigParser()
    parser.read("./data/configuration.txt")
    base_url=parser["HomeAssistant"]["server_url"] if 'server_url' in parser["HomeAssistant"] else base_url

    token = parser["HomeAssistant"]['token'] if 'token' in parser["HomeAssistant"] else ""
    headers = {
    "Authorization": "Bearer "+token,
    "content-type": "application/json",
    }


def getEntities(skip_services=False,only_main=False):
        '''
        Ritorna la lista di tutte le entità di HA
        '''
        start_time = time.time()
        response = get(base_url+"/states", headers=headers)
        if response.status_code!=200:
            return buildError(response)
        
        entity_list=response.json()
        res_list=[]
        for entity in entity_list:
            if only_main:
                if not isMainEntity(entity["entity_id"],entity["attributes"].get("friendly_name")):
                    continue
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
                entity["state"]+=entity["attributes"]["unit_of_measurement"]

            #Rimuovo i campi non necessari
            entity.pop("context",None)
            entity.pop("last_changed",None)
            entity.pop("last_reported",None)
            entity.pop("last_updated",None)
            #entity["attributes"].pop("supported_features",None)
            entity["attributes"].pop("friendly_name",None)
            entity["attributes"].pop("supported_color_modes",None)
            res_list.append(entity)
        print("Time to get all entities:"+str((time.time()-start_time)*1000)+" ms")
        return {"status_code":200,"data":res_list}

def getDevices(skip_services=False):
        '''
        Ritorna la lista di tutte le entità di HA raggruppate per dispositivo
        '''
        dev_list = {}
        start_time = time.time()
        response = get(base_url+"/states", headers=headers)
        if response.status_code!=200:
            return buildError(response)
        
        entity_list=response.json()
        for entity in entity_list:
            device = getDeviceId(entity["entity_id"])
            entity["device_id"]=device
            if not skip_services:
                services=getServicesByEntity(entity["entity_id"])
                entity["services"]=services

            #Sposto i campi 
            entity["friendly_name"]=entity["attributes"].get("friendly_name")
            
            entity["is_main_entity"]=isMainEntity(entity["entity_id"],entity["friendly_name"])

            #Rimuovo i campi non necessari
            entity.pop("context",None)
            entity.pop("last_changed",None)
            entity.pop("last_reported",None)
            entity.pop("last_updated",None)
            #entity["attributes"].pop("supported_features",None)
            entity["attributes"].pop("friendly_name",None)
            entity["attributes"].pop("supported_color_modes",None)
            
            t = dev_list.setdefault(entity['device_id'], {"list_of_entities":[]})
            t["list_of_entities"].append(entity)
            device_info=getDeviceInfo(device)
            t.update(device_info)
        print("Time to get all entities:"+str((time.time()-start_time)*1000)+" ms")
        return {"status_code":200,"data":dev_list}

def getEntity(entity_id:str):
    '''Ritorna l'entità con l'entity_id passato'''
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
        
        modes=consumption_map.get(entity_id.split(".")[0],[])

        for entity_data in entity_state:
            temp_date=parser.parse(entity_data["last_changed"])
            temp_date=temp_date.astimezone(tz.tzlocal())
            entity_data["last_changed"]=temp_date.isoformat()
            if entity_data["state"] in modes:
                state_consumption=modes[entity_data["state"]]["power_consumption"]
            else:
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

    return {"status_code":200,"data":supported_services}


def getAutomations():
    '''Ritorna la lista dei dettagli delle automazioni salvate in HA.'''
    ids=[]
    automations=[]

    response = get(base_url+"/states", headers=headers)
    if response.status_code!=200:
        return buildError(response)
    x=json.loads(response.text)
    for state in x:
        if state["entity_id"].startswith("automation"):
            ids.append(state["attributes"]["id"])

    for id in ids:
        response = get(base_url+"/config/automation/config/"+id,headers=headers)
        automations.append(response.json())
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


def getDeviceId(entity_id:str):
    '''Dato l'id di un'entità ritorna l'id del dispositivo a cui tale entità è associata'''
    templ="{{device_id('"+entity_id+"')}}"
    response = post(base_url+"/template", headers=headers, json={"template":templ})
    return response.text

def isMainEntity(entity_id:str,entity_name:str)->bool:
    if entity_name==None:
        return False
    
    templ="{{device_attr(device_id('"+entity_id+"'),'name')}}"
    response = post(base_url+"/template", headers=headers, json={"template":templ})
    if response.status_code!=200:
        return False
    else:
        return response.text.replace(" ","")==entity_name.replace(" ","")

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


def getDeviceModel(device_id:str):
    '''Dato l'id di un'entità ritorna l'id del dispositivo a cui tale entità è associata'''
    templ="{{device_attr('"+device_id+"','model')}}"
    response = post(base_url+"/template", headers=headers, json={"template":templ})
    return response.text


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
