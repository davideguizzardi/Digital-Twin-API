from requests import get,post
from random import randint
from schemas import Service_In
from urllib.parse import urlencode
import json,datetime,time

base_url="http://homeassistant.local:8123/api"
url_entities=base_url+"/states"
url_template=base_url+"/template"
url_events=base_url+"/events"
url_history=base_url+"/history/period"
url_services=base_url+"/services"
url_automation_config = base_url+"/config/automation/config/"
url_device_config = base_url+"/config/device/config/"
headers = {}

def initializeToken():
    global headers
    file=open("./data/token.txt")
    token=file.read()
    headers = {
    "Authorization": "Bearer "+token,
    "content-type": "application/json",
    }


def getEntities(skip_services=False):
        '''
        Ritorna la lista di tutte le entità di HA
        '''
        start_time = time.time()
        response = get(url_entities, headers=headers)
        entity_list=response.json()
        for entity in entity_list:
            device = getDeviceId(entity["entity_id"])
            entity["device_id"]=device
            if not skip_services:
                services=getServicesByEntity(entity["entity_id"])
                entity["services"]=services

            #Sposto i campi 
            entity["friendly_name"]=entity["attributes"].get("friendly_name")

            #Rimuovo i campi non necessari
            entity.pop("context",None)
            entity.pop("last_changed",None)
            entity.pop("last_reported",None)
            entity.pop("last_updated",None)
            #entity["attributes"].pop("supported_features",None)
            entity["attributes"].pop("friendly_name",None)
            entity["attributes"].pop("supported_color_modes",None)
        print("Time to get all entities:"+str((time.time()-start_time)*1000)+" ms")
        return entity_list

def getDevices(skip_services=False):
        '''
        Ritorna la lista di tutte le entità di HA
        '''
        dev_list = {}
        start_time = time.time()
        response = get(url_entities, headers=headers)
        entity_list=response.json()
        for entity in entity_list:
            device = getDeviceId(entity["entity_id"])
            entity["device_id"]=device
            if not skip_services:
                services=getServicesByEntity(entity["entity_id"])
                entity["services"]=services

            #Sposto i campi 
            entity["friendly_name"]=entity["attributes"].get("friendly_name")

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
        return dev_list

def getEntity(entity_id:str):
    '''Ritorna l'entità con l'entity_id passato'''
    response = get(url_entities+"/"+entity_id, headers=headers)
    return response.json()


def getHistory(entity_id:str,start_timestamp:datetime.datetime |None, end_timestamp:datetime.datetime |None):
    '''Ritorna la storia dei valori assunti durante le ultime 24 ore dell'entità specificata '''
    params={"filter_entity_id":entity_id}
    if(end_timestamp):
        params.update({"end_time":end_timestamp.astimezone().replace(microsecond=0).isoformat()})
    params=urlencode(params,doseq=True)+"&minimal_response&no_attributes"
    url=url_history+"/"+start_timestamp.astimezone().replace(microsecond=0).isoformat() if start_timestamp else url_history
    response=get(url=url,headers=headers,params=params)
    state_list=response.json()
    if(response.status_code==200):
        file = open("./data/entities_consumption_map.json")
        consumption_map=json.load(file)
        modes=consumption_map[entity_id.split(".")[0]]
        for state_data in state_list[0]:
            state_consumption=modes[state_data["state"]]["power_consumption"]
            state_data.update({"power_consumption":state_consumption})
    return state_list


def getServicesByEntity(entity_id:str):
    '''
    Ritorna la lista dei servizi supportati dell'entità specificata.
    Per le lampadine viene fatto un controllo delle modalità supportate e inseriti solo i campi adeguati
    '''

    #estraggo i dati dell'entita per avere le supported_features
    response = get(url_entities+"/"+entity_id, headers=headers) 
    entity=response.json()
    entity_supported_features=entity["attributes"].get("supported_features")

    #il valore supported_features è un numero binario in cui un bit è 1 se la rispettiva feature è supportata
    #con la riga qui sotto ottengo una lista con la rappresentazione decimale di tutti i bit a 1.
    #la lista viene usata per estrarre soltanto i servizi che sono compatibili con l'entità.
    #Alucune entità non hanno in valore supported_features quindi è necessario controllare prima
    
    entity_supported_features=getListOfSupported(entity_supported_features) if entity_supported_features else []

    #Estraggo tutti i servizi del dominio dell'entità richiesta
    domain=entity_id.split('.')[0]
    response = get(url_services, headers=headers)
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

    return supported_services


def getAutomations():
    '''Ritorna la lista dei dettagli delle automazioni salvate in HA.'''
    ids=[]
    automations=[]

    response = get(url_entities, headers=headers)
    x=json.loads(response.text)
    for state in x:
        if state["entity_id"].startswith("automation"):
            ids.append(state["attributes"]["id"])

    for id in ids:
        response = get(url_automation_config+id,headers=headers)
        automations.append(response.json())
    return automations


def callService(service:Service_In):
    '''Esegue il servizio specificato, sull'entità specificata e con i parametri specificati'''
    domain=service.entity_id.split('.')[0]
    url = url_services+"/"+domain+"/"+service.service
    data = {"entity_id": service.entity_id}
    data.update(service.data) #fondo i due dizionari 
    response = post(url, headers=headers, json=data)
    return response.json() if response.status_code==200 else response.text


def getServicesByDomain(domain="",keys_only=False):
    '''Ritorna tutti i servizi disponibili per uno specifico dominio.'''
    response = get(url_services, headers=headers)
    if domain!="":
        x=json.loads(response.text)
        for obj in x:
            if obj["domain"]==domain:
                return obj["services"].keys() if keys_only else json.dumps(obj)
    return response.text


    
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
    response = post(url_automation_config+str(id), headers=headers, json=data)
    return (id,response.text)


def getDeviceId(entity_id:str):
    '''Dato l'id di un'entità ritorna l'id del dispositivo a cui tale entità è associata'''
    templ="{{device_id('"+entity_id+"')}}"
    response = post(url_template, headers=headers, json={"template":templ})
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
    response = post(url_template, headers=headers, json={"template":templ})
    obj=json.loads(response.text)
    return obj


def getDeviceModel(device_id:str):
    '''Dato l'id di un'entità ritorna l'id del dispositivo a cui tale entità è associata'''
    templ="{{device_attr('"+device_id+"','model')}}"
    response = post(url_template, headers=headers, json={"template":templ})
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
