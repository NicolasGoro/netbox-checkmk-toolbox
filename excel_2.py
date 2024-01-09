import pandas as pd
import json
import warnings
import os
from datetime import datetime
import ipaddress
import csv
import yaml
from ycheckmk import YCheckMK
from ynetbox import YNetbox
import logging
import numpy as np
import math
import requests

warnings.filterwarnings("ignore")

# Leggi il file Excel o CSV
path = 'C:/Users/y.francesco.amori/Kali_Share/Gencom/Excel/files/file3.xlsx'
#path = 'C:/Users/y.francesco.amori/Kali_Share/Gencom/Excel/files/file.csv'

#---------------------------------------------------------------------------------------------------
# EXCEL
# Estrazione riga per riga elmenti
def extract_all_objects_row(file_path):
    # Read the Excel file
    df = pd.read_excel(file_path, engine='openpyxl')

    # Inizializza una lista vuota per immagazzinare gli oggetti JSON
    json_list = []
    device_name_count = {}
    # Itera attraverso ogni riga nel dataframe
    for index, row in df.iterrows():
        # Crea un dizionario per ogni riga
        device_name = row["Device Name"]
        if device_name in device_name_count:
            device_name_count[device_name] += 1
            device_name = f"{device_name}/{row['Serial Number']}"
        else:
            device_name_count[device_name] = 1
    # Itera attraverso ogni riga nel dataframe
    #for index, row in df.iterrows():
        # Crea un dizionario per ogni riga
        json_data = {
            "Device Name": device_name,
            "Device Role": row["Device Role"],
            "Device Type": row["Device Type"],
            "Serial Number": row["Serial Number"],
            "Istance Number": "NON_PRESENTE" if pd.isna(row["Istance Number"]) else row["Istance Number"],
            "Country": row["Country"].replace("à", "a").replace("è", "e").replace("é","e").replace("ù", "u").replace("ì", "i").replace("ò", "o"),
            "City": row["City"].replace("à", "a").replace("è", "e").replace("é","e").replace("ù", "u").replace("ì", "i").replace("ò", "o"),
            "Site": row["Site"],
            "Status": row["Status"],
            "Tenant": row["Tenant"].replace("à", "a").replace("è", "e").replace("é","e").replace("ù", "u").replace("ì", "i").replace("ò", "o"),
            "Management IP Address": "NON_PRESENTE" if pd.isna(row["Management IP Address"]) else format_ip(row["Management IP Address"]),
            "SLA": row["SLA"],
            "On site": "No" if pd.isna(row["On site"]) else row["On site"],
            "Fornitore": "NON_PRESENTE" if pd.isna(row["Fornitore"]) else row["Fornitore"],
            "SNMP": "NON_PRESENTE" if pd.isna(row["SNMP"]) else row["SNMP"],
            "snmp_community_device": "NON_PRESENTE" if pd.isna(row["snmp_community_device"]) else row["snmp_community_device"],
            "snmp_community_city": "NON_PRESENTE" if pd.isna(row["snmp_community_city"]) else row["snmp_community_city"],
            "Data inizio contratto": datetime.strftime(row["Data inizio contratto"], "%Y-%m-%d") if not pd.isna(row["Data inizio contratto"]) else "NON PRESENTE",
            "Data fine contratto": datetime.strftime(row["Data fine contratto"], "%Y-%m-%d") if not pd.isna(row["Data fine contratto"]) else "NON PRESENTE",
            "Maintenance": row["Maintenance"],
            "Monitoraggio": row["Monitoraggio"],
            "Connection Type": row["Connection Type"],
            "Severity device": int(row["Severity device"]) if not pd.isna(row["Severity device"]) else "NON PRESENTE",
            "Network Layer": row["Network Layer\u00a0"] if not pd.isna(row["Network Layer\u00a0"]) else "NON PRESENTE",
            "Manufacturers": row["Manufacturers"],
            "Platform": row["Platform "] if not pd.isna(row["Platform "]) else "NON PRESENTE"
        }

        # Aggiungi il dizionario alla lista
        json_list.append(json_data)


    return json_list

# ausilio problemi su ip
def format_ip(ip):
    try:
        ip_obj = ipaddress.ip_address(ip)

        if ip_obj.version == 4:
            # Return the IPv4 address as is
            return str(ip_obj)
        else:
            ip = str(ip)
            if len(ip) == 12:
            # Dividi l'IP in gruppi da 3 cifre
                groups = [ip[i:i+3] for i in range(0, len(ip), 3)]
                # Unisci i gruppi separati da un punto
                ip = '.'.join(groups)
                # Unsupported IP version
            return ip
    except ValueError:
        # Invalid IP address
        return f"Invalid IP: {ip}"

# ESTRAZIONE DI UNA COLONNA INTERA IN BASE ALLA CHIAVE DI ESTRAZIONE ('serial_number')
def estrai_campo(json_list, chiave_da_estrazione):
    # Lista per salvare i valori della chiave
    valori_chiave = []

    # Itera sulla lista di oggetti JSON
    for json_obj in json_list:
        # Aggiungi il valore della chiave alla lista, se la chiave è presente
        if chiave_da_estrazione in json_obj:
            valori_chiave.append(json_obj[chiave_da_estrazione])
        else:
            valori_chiave.append("Chiave non presente")

    return valori_chiave

# ESTRAZIONE DEGLI ELEMENTI UNICI NECESSARI ALLA CREAZIONE SU NETBOX
def estrai_elementi_unici(json_list, chiave_da_estrazione):
    # Utilizza un set per garantire elementi unici
    valori_unici = set()

    # Itera sulla lista di oggetti JSON
    for json_obj in json_list:
        # Aggiungi il valore della chiave al set, se la chiave è presente
        if chiave_da_estrazione in json_obj:
            valori_unici.add(json_obj[chiave_da_estrazione])

    # Converti il set in una lista
    valori_unici_list = list(valori_unici)

    return valori_unici_list

# ESTRAZIONE E CONCATENZAIONE PER LA LOCATION UNICA
def extract_and_concatenate_unique(file_path):

    df = pd.read_excel(file_path)
    unique_concatenations = set()

    # Iterazione su DataFrame
    for index, row in df.iterrows():
        # Estarzione "Location"
        country_code = row['Country'][:3].lower(
        ) if pd.notnull(row['Country']) else ''

        # Estrazione "City"
        city_name = row['City'] if pd.notnull(row['City']) else ''

        # Concatena
        concatenated_value = f"{country_code}_{city_name}"

        # Aggiungi se unico
        unique_concatenations.add(concatenated_value)

    # Mettilo come lista
    return list(unique_concatenations)

#---------------------------------------------------------------------------------------------------
# CSV
def process_csv(input_file):
    print("Inserisci il nome del Tenant")
    tenant_add = input()
    print("Inserisci il nome del Site")
    site_add = input()
    print("Inserisci la Location nella forma nazione_citta es: ita_montebelluna")
    location_add = input()
    result_list = []

    with open(input_file, newline='', encoding='utf-8') as csvfile:
        csv_reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
        
        for row in csv_reader:
            entry = {
                "Hostname": row.get("Hostname", "NON PRESENTE"),
                "Tenant": tenant_add.replace("à", "a").replace("è", "e").replace("é","e").replace("ù", "u").replace("ì", "i").replace("ò", "o"),
                "Country": location_add[:3],
                "City": location_add.split('_')[1].replace("à", "a").replace("è", "e").replace("é","e").replace("ù", "u").replace("ì", "i").replace("ò", "o"),
                "Site": site_add.replace("à", "a").replace("è", "e").replace("é","e").replace("ù", "u").replace("ì", "i").replace("ò", "o"),
                "Location": location_add.replace("à", "a").replace("è", "e").replace("é","e").replace("ù", "u").replace("ì", "i").replace("ò", "o"),
                "Device Type": row.get("Model", "NON PRESENTE"),
                "Login IP": row.get("Login IP", "NON PRESENTE"),
                "Serial Number": row.get("Serial Number", "NON PRESENTE"),
                "Platform": row.get("Platform", "NON PRESENTE")
            }
            
            result_list.append(entry)

    return  result_list 
#---------------------------------------------------------------------------------------------------

#---------------------------------------------------------------------------------------------------
# Utility
def get_id_by_name(elements_list, name):
    for el in elements_list:
        if el['name'] == name:
            return el['id']
    return None

def extract_info(data):
    result = {}
    seen_device_types = set()

    for item in data:
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except json.JSONDecodeError:
                print(f"Errore nel caricare il JSON: {item}")
                continue

        device_type = item.get("device_type")
        device_role = item.get("device_role")
        
        if device_type:
            device_type_id = device_type.get("id")

            # Check if device_type_id is unique
            if device_type_id not in seen_device_types:
                seen_device_types.add(device_type_id)

                # Extract information and add to result
                result[device_type_id] = {
                    "device-type_id": device_type_id,
                    "manufacturers_id": device_type["manufacturer"]["id"],
                    "manufacturers_name": device_type["manufacturer"]["name"],
                    "device_type_display": device_type.get("display", ""),
                    "device_role_name": device_role.get("name", "")
                }

    return result

def extract_unique_pairs(json_list):
    unique_pairs = set()
    
    for device_json in json_list:
        manufacturers = device_json.get("Manufacturers")
        network_layer = device_json.get("Network Layer")
        
        if manufacturers is not None and network_layer is not None:
            unique_pairs.add((manufacturers, network_layer))
    
    result_list = [{"Manufacturers": m, "Network Layer": n} for m, n in unique_pairs]
    return result_list
#---------------------------------------------------------------------------------------------------


def filter_json(data):
    return {key: value for key, value in data.items() if key in ["Device Type", "Manufacturers"] and not (isinstance(value, float) and math.isnan(value))}

#---------------------------------------------------------------------------------------------------
#MAIN
_, file_extension = os.path.splitext(path)
if file_extension.lower() == '.xlsx':
    # Estrai tutti gli oggetti (riga per riga)
    all_devices = extract_all_objects_row(path)

    # Stampa la lista di oggetti JSON
    for json_obj in all_devices:
        print(json.dumps(json_obj, indent=2))

    # Estari Tenant
    tenant_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Tenant')
    print("I Tenants trovati sull'Excel sono:\n>",tenant_add,"\n")

    # Estari Device-Type
    device_type_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Device Type')
    print("I Device-Type trovati sull'Excel sono:\n>",device_type_add,"\n")
    # Applica la funzione di filtraggio a ciascun elemento della lista
    filtered_device_type_add = [filter_json(item) for item in all_devices]
    # Stampa il risultato
    #print(json.dumps(filtered_device_type_add, indent=2))

    # Estari Manufacturers
    #device_manufacturers_add = extract_unique_pairs(all_devices)
    #device_manufacturers_add = [entry for entry in device_manufacturers_add if entry["Manufacturers"] is not np.nan and entry["Manufacturers"] == entry["Manufacturers"]]
    #print("I Manufacturers trovati sull'Excel sono:\n>",device_manufacturers_add,"\n")

    device_manufacturers_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Manufacturers')
    if np.nan in device_manufacturers_add: device_manufacturers_add.remove(np.nan)
    print("I manufacturers trovati sull'Excel sono:\n>",device_manufacturers_add,"\n")

    # Estari Site
    site_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Site')
    print("I Sites trovati sull'Excel sono:\n>",site_add,"\n")

    # Estrai Location
    locations_add = extract_and_concatenate_unique(path)
    locations_add=[item for item in locations_add if "_n.d." not in item]
    print("Le Locations trovate sull'Excel sono:\n>",locations_add,"\n")
    print('finita estrazione excel')


elif file_extension.lower() == '.csv':
    all_devices=process_csv(path) 
    print(json.dumps(all_devices, indent=4)) #stampo solo la lista deei device, se voglio gli altri cambio numero
    
    tenant_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Tenant')
    print("Tenant CSV:\n>",tenant_add,"\n")

    site_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Site')
    print("I Sites trovati sull'Excel sono:\n>",site_add,"\n")
    
    print('finita estrazione CSV')
else:
    print('Formato non supportato')

#---------------------------------------------------------------------------------------------
DISCOVERY_TIMEOUT = 180
cur_dir = os.path.abspath(os.path.dirname(__file__))
conf = yaml.safe_load(open(os.path.join(cur_dir, "conf.yml")))
logging.basicConfig(filename=os.path.join(cur_dir, "cmk_nbox_push.log"), filemode='a+', level=logging.INFO,
                    format='[%(levelname)s] %(asctime)s - %(name)s: %(message)s')
logger = logging.getLogger()

nbox = YNetbox(**conf['netbox'])

# TENANTS
if len(tenant_add) > 1:
    print("error: more than one tenat found!")
    exit(1)

tenants = nbox.get_tenants()
for tenants_to_add in tenant_add:
    tenant_id = get_id_by_name(tenants, tenants_to_add)
    if tenant_id is None:
        print(f"site {tenants_to_add} mancante, lo creo")
        site_result = nbox.create_tenant(tenants_to_add)
        tenants.append(site_result)
    else:
        print(f"Tenant {tenants_to_add} già presente")
pass
print(tenant_id)
# SITES
sites = nbox.get_sites()
for site_to_add in site_add:
    site_id = get_id_by_name(sites, site_to_add)
    if site_id is None:
        print(f"site {site_to_add} mancante, lo creo")
        site_result = nbox.create_site(site_to_add, tenant_id)
        sites.append(site_result)
        print(site_id)
    else:
        print(f"site {site_to_add} già presente")
pass
print(site_id)

# LOCATIONS
locations = nbox.get_locations()
snmp_community_location = estrai_elementi_unici(all_devices, chiave_da_estrazione='snmp_community_device')
if "NON_PRESENTE" in snmp_community_location: snmp_community_location.remove("NON_PRESENTE")
#print (snmp_community_location)
for loc_to_add in locations_add:
    location_id = get_id_by_name(locations, loc_to_add)
    #print(location_id)
    if location_id is None:
        print(f"location {loc_to_add} mancante, lo creo")
        location_result = nbox.create_loction(loc_to_add, site_id, tenant_id, snmp_community_location[0])
        locations.append(location_result)
    else:
        print(f"location {loc_to_add} già presente")
pass

# MANUFACTURERS check & diff

#all_info_netbox = nbox.get_devices()['results']
#all_elements = (json.dumps(all_info_netbox, indent=4))
#all_elements=json.loads(all_elements)
#all_manufacturers_nbox=(json.dumps(nbox.get_manufacturers(), indent=4))
#print(all_manufacturers_nbox)

all_manufacturers_nbox = json.loads(json.dumps(nbox.get_manufacturers(), indent=4))
list_all_manufacturers_nbox=[]
for all_manufacturers in all_manufacturers_nbox["results"]:
    #print(all_manufacturers["name"])
    list_all_manufacturers_nbox.append(all_manufacturers["name"])
print(list_all_manufacturers_nbox)

list_id=[]
manufacturers_list=nbox.get_manufacturers()['results']
for elemento in device_manufacturers_add:
    if elemento in list_all_manufacturers_nbox:
        print(f"{elemento} è già presente")
    else:
        print(f"{elemento} non presente, lo creo")
        manufacturers_result=nbox.create_manufacturer(elemento, elemento)
        manufacturers_list.append(manufacturers_result)
#print(manufacturers_list)

# Lista con manufacturers e ID associato
id_man_to_associate = [{'name': manufacturer['display'], 'id': manufacturer['id']} for manufacturer in manufacturers_list]
print(json.dumps(id_man_to_associate, indent=4))


# CHEK DEVICE TYPE
# NETBOX 
device_type_nbox=nbox.get_devices_type()['results']
#print(json.dumps(device_type_nbox, indent=4))
all_device_type_on_nbox = []
for item in device_type_nbox:
    device_type = {"device_type": item["display"]}
    manufacturer = {"manufacturer": item["manufacturer"]["display"]}
    all_device_type_on_nbox.append({**device_type, **manufacturer})
print("I DEVICE_TYPE su NetBox sono: \n",all_device_type_on_nbox)
# FILE
all_device_type_on_file=[]
for device in filtered_device_type_add:
        all_device_type_on_file.append(device)
print("I DEVICE_TYPE su FILE sono: \n",all_device_type_on_file)

original_size_list1 = len(all_device_type_on_file)
original_size_list2 = len(all_device_type_on_nbox)

to_add = []
for element1 in all_device_type_on_file:
    if element1 not in all_device_type_on_nbox:
        to_add.append(element1)
    else: 
        pass
#print(to_add)
size_to_add = len(to_add)
  

to_add_all = [device for device in to_add if all(key in device for key in ['Device Type', 'Manufacturers'])]
print("I Device Type da porvare ad agguingere sono: \n",to_add_all)

manufacturer_id_map = {manufacturer['name']: manufacturer['id'] for manufacturer in id_man_to_associate}
#print(manufacturer_id_map)
# Aggiungi l'id corrispondente a ciascun dispositivo
for device in to_add_all:
    #print(device)
    manufacturer_name = device['Manufacturers']
    if manufacturer_name in manufacturer_id_map:
        device['id'] = manufacturer_id_map[manufacturer_name]

for elem in to_add_all:
    if 'Device Type' in elem:
        elem['Device Type'] = elem['Device Type'].replace(" ", "-")


# Stampare la lista dei dispositivi aggiornata
print(json.dumps(to_add_all, indent=4))
for device in to_add_all:
    try:
        nbox.create_device_type(device['id'], device["Device Type"])
        print(f"Device type '{device['Device Type']}' con ID {device['id']} creato con successo.")
    except requests.HTTPError as he:
        if he.response.status_code == 400 and "already exists" in he.response.text:
            print(f"Device type '{device['Device Type']}' con ID {device['id']} già esiste. Ignorato.")
        else:
            raise he
    
print("Fatto")


#########################################################################################################
# GESTIONE DEI DEVICE #

#to_add_all              # LA LISTA DEVICE TYPE -> ID
#id_man_to_assoc@iate    # LA LISTA MANUFATURERS -> ID
 
# Loc -> ID
filtered_loc = [{"id": item["id"], "name": item["name"]} for item in nbox.get_locations()] 
#print(json.dumps( filtered_loc, indent=4))

 # Role -> ID
filtered_roles = [{"id": item["id"], "name": item["name"]} for item in nbox.get_devices_roles()]
#print(json.dumps( filtered_roles, indent=4))

 # net_layer -> ID
filtered_net_layer = [{"id": item["id"], "display": item["display"]} for item in nbox.get_devices_net_layer()] # Role -> ID
#print(json.dumps( filtered_net_layer, indent=4))

 # Plat -> ID
filtered_platforms = [{"id": item["id"], "name": item["name"]} for item in nbox.get_platforms()]
#print(json.dumps( filtered_platforms, indent=4))

# Funzione per ottenere l'ID del ruolo
def get_role_id(role_name):
    for role in filtered_roles:
        if role["name"] == role_name:
            return role["id"]
    return None  

# Funzione per ottenere l'ID del layer di rete
def get_network_layer_id(layer_name):
    for layer in filtered_net_layer:
        if layer["display"] == layer_name:
            return layer["id"]
    return None  

# Funzione per ottenere l'ID della piattaforma
def get_platform_id(platform_name):
    for platform in filtered_platforms:
        if platform["name"] == platform_name:
            return platform["id"]
    return None  

# Funzione per ottenere l'ID del produttore
def get_manufacturer_id(manufacturer_name):
    for manufacturer in id_man_to_associate:
        if manufacturer["name"] == manufacturer_name:
            return manufacturer["id"]
    return None 

def get_device_type_id(device_type):
    for device_mapping in to_add_all:
        if device_mapping["Device Type"] == device_type:
            return device_mapping["id"]
    return None  

# Aggiorna la lista dei dispositivi con gli ID dei ruoli e dei layer di rete
for device in all_devices:
    role_name = device["Device Role"]
    network_layer_name = device["Network Layer"]
    platform_name = device["Platform"]
    print(platform_name)
    manufacturer_name = device["Manufacturers"]
    device_type = device["Device Type"]

    country = device.get("Country", "")
    city = device.get("City", "")
    device["Location"] = f"{country}_{city}"

    platform_id = get_platform_id(platform_name)
    manufacturer_id = get_manufacturer_id(manufacturer_name)
    role_id = get_role_id(role_name)
    network_layer_id = get_network_layer_id(network_layer_name)
    device_type_id = get_device_type_id(device_type)

    for location_mapping in filtered_loc:
        if location_mapping["name"] == device["Location"]:
            location_id = location_mapping["id"]
            break
    else:
        location_id = None

    # Aggiorna il campo "Location" con l'ID della location
    device["Location"] = location_id
    device["Site"] = site_id
    device["Tenant"] = tenant_id
    # Aggiorna il valore nei dispositivi
    device["Device Type"] = device_type_id
    # Aggiorna i valori nei dispositivi
    device["Device Role"] = role_id
    device["Network Layer"] = network_layer_id
    # Aggiorna i valori nei dispositivi
    device["Platform"] = platform_id
    #print(device["Platform"])
    device["Manufacturers"] = manufacturer_id

    # Ora la lista dei dispositivi contiene gli ID al posto dei nomi dei ruoli e dei layer di rete
#print(json.dumps(all_devices, indent=4))

# CREAZIONE DEI DEVICE #
    
# Esempio di utilizzo della funzione create_device con controllo sui campi
for device in all_devices:
    print(json.dumps(device, indent=4))
    # Estrai i parametri dal dispositivo
    name = device.get("Device Name")
    device_type = device.get("Device Type")
    role = device.get("Device Role")
    tenant = device.get("Tenant")
    platform = device.get("Platform")
    serial = device.get("Serial Number")
    site = device.get("Site")
    location = device.get("Location")
    snmp_com_device = device.get("snmp_community_device")
    net_layer = device.get("Network Layer")
    data_fine = device.get("Data fine contratto")
    data_inizio = device.get("Data inizio contratto")
    rma = ["Vendor"]
    #rma = device.get("RMA")
    sla = device.get("SLA")

    # Esegui la creazione del dispositivo
    result = nbox.create_device(
        name, device_type, role, tenant, platform, serial, site, location,
        snmp_com_device, net_layer, data_fine, data_inizio, rma, sla
    )

    # Verifica la risposta e gestisci i dispositivi non creati
    if "status" in result and result["status"] not in (200, 201):
        print(f"Errore nella creazione del dispositivo {name}: {result.get('message', 'Errore sconosciuto')}")
