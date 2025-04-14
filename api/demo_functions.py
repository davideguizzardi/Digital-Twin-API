
import json
def load_virtual_context():
    with open("./data/virtual_context.json", "r") as file:
        return json.load(file)


def get_all_demo_devices(get_only_names: bool = False):
    virtual_context = load_virtual_context()
    return (
        virtual_context["device_context"]
        if not get_only_names
        else virtual_context["device_context_only_names"]
    )

def get_single_demo_device(device_id):
    virtual_context = load_virtual_context()
    device_context=virtual_context["device_context"]
    device=[x for x in device_context if x["device_id"]==device_id]
    return device[0] if len(device)==1 else {}



def get_all_demo_entities():
    virtual_context = load_virtual_context()
    return virtual_context["entities_context"]

def get_demo_entity(entity_id: str):
    virtual_context = load_virtual_context()
    temp = [x for x in virtual_context["entities_context"] if x["entity_id"] == entity_id]
    return temp[0] if temp else {}


def get_demo_automations():
    virtual_context = load_virtual_context()
    return virtual_context["automation_context"]

