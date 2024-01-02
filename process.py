from ynetbox import *
from excel_2 import *
import yaml
import os
import logging
from cmk_nbox_push import *


DISCOVERY_TIMEOUT = 180
cur_dir = os.path.abspath(os.path.dirname(__file__))
conf = yaml.safe_load(open(os.path.join(cur_dir, "conf.yml")))
logging.basicConfig(filename=os.path.join(cur_dir, "cmk_nbox_push.log"), filemode='a+', level=logging.INFO,
                    format='[%(levelname)s] %(asctime)s - %(name)s: %(message)s')
logger = logging.getLogger()

nbox = YNetbox(**conf['netbox'])
raw_location = nbox.get_locations()

# Stampa la lista di oggetti contenenti le informazioni
device_info_list = extract_information(raw_location)

# OTTIENI LIST DI TUTTE LE LOCATION (COUNTY_CITY)
def obatain_all_locations_on_netbox(device_info_list):
    all_locations_actually_on_netbox=[]
    all_paths = []
    for device_info in device_info_list:
        tenant = device_info["tenants"]
        folder = device_info["names"]
        all_locations_actually_on_netbox.append(folder)
        split_result = split_string(folder)
            # nazione_path = get_nation(folder)
            # print(split_result)
        if split_result is not None and '/' in split_result:
            path = "/" + tenant + "/" + split_result
            all_paths.append(path)
    
    return all_locations_actually_on_netbox

# OTTIENI TUTTI I TENANTS
def obatain_tenants_on_netbox(device_info_list):
    all_tenants_actually_on_netbox = []
    snmp_loc = []
    for device_info in device_info_list:
        tenant = device_info["tenants"]
        if tenant not in all_tenants_actually_on_netbox:
            all_tenants_actually_on_netbox.append(tenant)
            snmp_loc = device_info["snmp_communities_location"]
                # print(snmp_loc)
    return all_tenants_actually_on_netbox

# FAI LE DIFFERENZE TRA I DATI ESTARTTI DA EXCEL E QUELLI GIA PRESENTI SU NETBOX
def differenza_liste(lista1, lista2): #Lista1 = Locations estartte da Excel , LIsta2 dati NetBox
    da_aggiungere = []

    for elemento in lista1:
        if elemento not in lista2:
            da_aggiungere.append(elemento)

    return da_aggiungere

# Ottieni locations Netbox
all_locations_netbox = obatain_all_locations_on_netbox(device_info_list)
print("Tutte le Locations presenti su Netbox sono: \n>",all_locations_netbox, "\n")

# Ottieni tenants Netbox
all_tenants_netbox = obatain_tenants_on_netbox(device_info_list)
print("Tutti i Tenants presenti su Netbox sono: \n>",all_tenants_netbox, "\n")

# CONTORLLO TENANTS MANCANTI SU NBOX
add_tenants=differenza_liste(tenant_excel,all_tenants_netbox)
print("I Tenants da aggiungere su Netbox sono:\n>",add_tenants, "\n")

# CONTORLLO LOCATIONS MANCANTI SU NBOX
add_locations=differenza_liste(locations_excel,all_locations_netbox)
print("Le Locations da aggiungere su Netbox sono:\n>",add_locations, "\n")


