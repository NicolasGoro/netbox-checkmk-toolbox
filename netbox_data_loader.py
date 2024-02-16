import pandas as pd
import json
import warnings
import os
from datetime import datetime
import ipaddress
import csv
import yaml
from modules.ynetbox import YNetbox, DuplicateObject
import logging
import numpy as np
import requests
import math
from collections import Counter
import sys

warnings.filterwarnings("ignore")
cur_dir = os.path.abspath(os.path.dirname(__file__))
conf = yaml.safe_load(open(os.path.join(cur_dir, "conf.yml")))
#logging.basicConfig(filename=os.path.join(cur_dir, "netbox_data_loader.log"), filemode='a+', level=logging.INFO,
#                    format='[%(levelname)s] %(asctime)s - %(name)s: %(message)s')

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(filename=os.path.join(cur_dir, "netbox_data_loader.log"), mode='a+'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger()
# Leggi il file Excel o CSV
if len(sys.argv) == 2:
    path = sys.argv[1]
else:
    print(f"Usage: python3 tool.py <filename>")
    print("Filename missing!")
    path = "AESSE.xlsx"

nbox = YNetbox(**conf['netbox'])
'''
# Ottieni gli URL usando le funzioni
net_layer_url = nbox.base_url + f"/extras/custom-field-choice-sets/{nbox.net_layer_cf_id}/choices"
conn_type_url = nbox.base_url + f"/extras/custom-field-choice-sets/{nbox.conn_type_cf_id}/choices"
print("URL per get_devices_net_layer:", net_layer_url)
print("URL per get_devices_connection_type:", conn_type_url)
'''
# EXCEL
# Estrazione riga per riga elementi
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
        # for index, row in df.iterrows():
        # Crea un dizionario per ogni riga
        json_data = {
            "Device Name": device_name,
            "Device Role": row["Device Role"],
            "Device Type": row["Device Type"],
            "Serial Number": row["Serial Number"],
            "Istance Number": "NON_PRESENTE" if pd.isna(row["Istance Number"]) else row["Istance Number"],
            "Country": row["Country"].replace("à", "a").replace("è", "e").replace("é", "e").replace("ù", "u").replace(
                "ì", "i").replace("ò", "o"),
            "City": row["City"].replace("à", "a").replace("è", "e").replace("é", "e").replace("ù", "u").replace("ì",
                                                                                                                "i").replace(
                "ò", "o"),
            "Site": row["Site"],
            "Status": row["Status"],
            "Tenant": row["Tenant"].replace("à", "a").replace("è", "e").replace("é", "e").replace("ù", "u").replace("ì",
                                                                                                                    "i").replace(
                "ò", "o"),
            "Management IP Address": "NON_PRESENTE" if pd.isna(row["Management IP Address"]) else format_ip(
                row["Management IP Address"]),
            "SLA": row["SLA"],
            "On site": "No" if pd.isna(row["On site"]) else row["On site"],
            "Fornitore": "NON_PRESENTE" if pd.isna(row["Fornitore"]) else row["Fornitore"],
            "SNMP": None if pd.isna(row["SNMP"]) else row["SNMP"],
            "snmp_community_device": None if pd.isna(row.get("snmp_community_device")) else row[
                "snmp_community_device"],
            "snmp_community_city": None if pd.isna(row.get("snmp_community_city")) else row[
                "snmp_community_city"],
            "Data inizio contratto": datetime.strftime(row["Data inizio contratto"], "%Y-%m-%d") if not pd.isna(
                row["Data inizio contratto"]) else "NON PRESENTE",
            "Data fine contratto": datetime.strftime(row["Data fine contratto"], "%Y-%m-%d") if not pd.isna(
                row["Data fine contratto"]) else "NON PRESENTE",
            "Maintenance": row["Maintenance"],
            "Monitoraggio": row["Monitoraggio"],
            "Connection Type": row["Connection Type"],
            "Severity device": int(row["Severity device"]) if not pd.isna(row["Severity device"]) else None,
            "Network Layer": row["Network Layer\u00a0"] if not pd.isna(row["Network Layer\u00a0"]) else None,
            "Manufacturers": row["Manufacturers"],
            "Platform": row["Platform "] if not pd.isna(row["Platform "]) else None
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
                groups = [ip[i:i + 3] for i in range(0, len(ip), 3)]
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
        # estrazione "Location"
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
                "Device Name": row.get("Hostname", "NON PRESENTE"),
                "Tenant": tenant_add.replace("à", "a").replace("è", "e").replace("é", "e").replace("ù", "u").replace(
                    "ì", "i").replace("ò", "o"),
                "Country": location_add[:3],
                "City": location_add.split('_')[1].replace("à", "a").replace("è", "e").replace("é", "e").replace("ù",
                                                                                                                 "u").replace(
                    "ì", "i").replace("ò", "o"),
                "Site": site_add.replace("à", "a").replace("è", "e").replace("é", "e").replace("ù", "u").replace("ì",
                                                                                                                 "i").replace(
                    "ò", "o"),
                "Location": location_add.replace("à", "a").replace("è", "e").replace("é", "e").replace("ù",
                                                                                                       "u").replace("ì",
                                                                                                                    "i").replace(
                    "ò", "o"),
                "Device Type": row.get("Model", "NON PRESENTE"),
                "Management IP Address": row.get("Login IP", "NON PRESENTE"),
                "Serial Number": row.get("Serial Number", "NON PRESENTE"),
                "Platform": row.get("Family", "NON PRESENTE"),
                "Device Role": row.get("Type", "NON PRESENTE"),
                "Manufacturers": row.get("Vendor", "NON PRESENTE")
            }

            result_list.append(entry)

    return result_list, location_add


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
                logger.info(f"Errore nel caricare il JSON: {item}")
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


def filter_json(data):
    return {key: value for key, value in data.items() if
            key in ["Device Type", "Manufacturers"] and not (isinstance(value, float) and math.isnan(value))}


def get_role_id(role_name, filtered_roles):
    for role in filtered_roles:
        if role["name"] == role_name:
            return role["id"]
    return None


# Funzione per ottenere l'ID del layer di rete
def get_network_layer_id(layer_name, filtered_net_layer):
    for layer in filtered_net_layer:
        if layer["display"] == layer_name:
            return layer["id"]
    return None


# Funzione per ottenere l'ID del layer di rete
def get_dev_type_id(layer_name, all_dev_type):
    for layer in all_dev_type:
        if layer["name"] == layer_name:
            return layer["id"]
    return None


# Funzione per ottenere l'ID del connectiontype
def get_connection_type_id(layer_name, all_conn_type):
    for layer in all_conn_type:
        if layer["name"] == layer_name:
            return layer["id"]
    return None


# Funzione per ottenere l'ID della piattaforma
def get_platform_id(platform_name, filtered_platforms):
    for platform in filtered_platforms:
        if platform["name"] == platform_name:
            return platform["id"]
    return None


# Funzione per ottenere l'ID del produttore
def get_manufacturer_id(manufacturer_name, id_man_to_associate):
    for man_name, man_id in id_man_to_associate.items():
        if man_name == manufacturer_name:
            return man_id
    return None


def match_for_VC(list1, list2):
    match_for_VC_list = []

    id_set = set(item2["id"] for item2 in list2)

    for item1 in list1:
        if item1["id"] in id_set:
            match_for_VC_list.append({"id": item1["id"], "name": item1["name"]})

    return match_for_VC_list


# MAIN

def main():
    _, file_extension = os.path.splitext(path)

    if file_extension.lower() == '.xlsx':
        # Estrai tutti gli oggetti (riga per riga)
        all_devices = extract_all_objects_row(path)

        # Stampa la lista di oggetti JSON
        for json_obj in all_devices:
            logger.debug(json.dumps(json_obj))

        # Estrai Tenant
        tenant_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Tenant')
        logger.info(f"I Tenants trovati sull'Excel sono:{tenant_add}")

        # Estrai Device-Type
        device_type_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Device Type')
        logger.info(f"I Device-Type trovati sull'Excel sono: {device_type_add}")
        # Applica la funzione di filtraggio a ciascun elemento della lista
        filtered_device_type_add = [filter_json(item) for item in all_devices]

        # Estrai Manufacturers

        device_manufacturers_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Manufacturers')
        if np.nan in device_manufacturers_add: device_manufacturers_add.remove(np.nan)
        logger.info(f"I manufacturers trovati sull'Excel sono: {device_manufacturers_add}")

        # Estrai Site
        site_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Site')
        logger.info(f"I Sites trovati sull'Excel sono: {site_add}")

        # Estrai Location
        locations_add = extract_and_concatenate_unique(path)
        locations_add = [item for item in locations_add if "_n.d." not in item]
        logger.info(f"Le Locations trovate sull'Excel sono: {locations_add}")
        logger.info('finita estrazione excel')


    elif file_extension.lower() == '.csv':
        all_devices, location_add = process_csv(path)
        locations_add = [location_add]
        logger.debug(
            json.dumps(all_devices))  # stampo solo la lista dei device, se voglio gli altri cambio numero

        tenant_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Tenant')
        logger.info(f"Tenant CSV:> {tenant_add}")

        site_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Site')
        logger.info(f"I Sites trovati sull'Excel sono: {site_add}")

        filtered_device_type_add = [filter_json(item) for item in all_devices]

        logger.info('finita estrazione CSV')
    else:
        logger.error('Formato non supportato')
        print("formato non supportato")
        exit(1)

    # TENANTS
    if len(tenant_add) > 1:
        logger.error("error: more than one tenant found!")
        exit(1)

    tenants = nbox.get_tenants()
    for tenants_to_add in tenant_add:
        tenant_id = get_id_by_name(tenants, tenants_to_add)
        if tenant_id is None:
            logger.info(f"site {tenants_to_add} mancante, lo creo")
            site_result = nbox.create_tenant(tenants_to_add)
            tenants.append(site_result)
            tenant_id = get_id_by_name(tenants, tenants_to_add)
        else:
            logger.info(f"Tenant {tenants_to_add} già presente")
    pass
    logger.info(f"Il Tenant ha id {tenant_id}")
    # SITES
    sites = nbox.get_sites()
    for site_to_add in site_add:
        site_id = get_id_by_name(sites, site_to_add)
        if site_id is None:
            logger.info(f"site {site_to_add} mancante, lo creo")
            site_result = nbox.create_site(site_to_add, tenant_id)
            sites.append(site_result)
            site_id = get_id_by_name(sites, site_to_add)
        else:
            logger.info(f"site {site_to_add} già presente")
    pass
    logger.info(f"Il Site ha id {site_id}")

    # LOCATIONS
    locations = nbox.get_locations()
    snmp_community_location = estrai_elementi_unici(all_devices, chiave_da_estrazione='snmp_community_city')
    if "NON_PRESENTE" in snmp_community_location:
        snmp_community_location.remove("NON_PRESENTE")

    for loc_to_add in locations_add:
        location_id = get_id_by_name(locations, loc_to_add)
        # logger.info(location_id)
        if location_id is None:
            logger.info(f"location {loc_to_add} mancante, lo creo")
            if snmp_community_location:
                location_result = nbox.create_loction(loc_to_add, site_id, tenant_id, snmp_community_location[0])
            else:
                location_result = nbox.create_loction(loc_to_add, site_id, tenant_id, None)
            locations.append(location_result)
        else:
            logger.info(f"location {loc_to_add} già presente")
    pass

    # MANUFACTURERS check & diff



    # CHEK DEVICE TYPE
    # NETBOX 
    device_type_nbox = nbox.get_devices_type()
    all_device_type_on_nbox = []
    for item in device_type_nbox:
        device_type = {"device_type": item["display"]}
        manufacturer = {"manufacturer": item["manufacturer"]["display"]}
        all_device_type_on_nbox.append({**device_type, **manufacturer})
    # FILE
    all_device_type_on_file = []
    for device in filtered_device_type_add:
        all_device_type_on_file.append(device)

    to_add = []
    for element1 in all_device_type_on_file:
        if element1 not in all_device_type_on_nbox:
            to_add.append(element1)
        else:
            pass

    to_add_all = [device for device in to_add if all(key in device for key in ['Device Type', 'Manufacturers'])]
    logger.info(f"I Device Type da provare ad aggiungere sono: {json.dumps(to_add_all)}")

    manufacturers_ids = nbox.get_manufacturers()["results"]

    manufacturer_id_map = {manufacturer['name']: manufacturer['id'] for manufacturer in manufacturers_ids}
    # Aggiungi l'id corrispondente a ciascun dispositivo
    for device in to_add_all:
        manufacturer_name = device['Manufacturers']
        if manufacturer_name in manufacturer_id_map:
            device['id'] = manufacturer_id_map[manufacturer_name]
        else:
            device['id'] = None
            logger.error(f"manufacturer {manufacturer_name} non presente in netbox")

    for elem in to_add_all:
        if 'Device Type' in elem:
            elem['Device Type'] = elem['Device Type'].replace(" ", "-")

    for device in to_add_all:
        try:
            if device['id']:
                nbox.create_device_type(device['id'], device["Device Type"])
                logger.info(f"Device type '{device['Device Type']}' con ID {device['id']} creato con successo.")
            else:
                logger.error(f"Device type '{device['Device Type']}' non creato per mancanza manufacturer")
        except DuplicateObject:
            logger.info(f"Device type '{device['Device Type']}' con ID {device['id']} già esiste. Ignorato.")
        except Exception as e:
            logger.error(f"Device type '{device['Device Type']}' non creato errore {e}")

    logger.info("Check su Device Type Fatto!")

    # GESTIONE DEI DEVICE

    # to_add_all              # LA LISTA DEVICE TYPE -> ID
    # id_man_to_assoc@iate    # LA LISTA MANUFATURERS -> ID

    # Loc -> ID
    filtered_loc = [{"id": item["id"], "name": item["name"]} for item in nbox.get_locations()]

    # Role -> ID
    filtered_roles = [{"id": item["id"], "name": item["name"]} for item in nbox.get_devices_roles()]

    # net_layer -> ID
    filtered_net_layer = [{"id": item["id"], "display": item["display"]} for item in nbox.get_devices_net_layer()]  # Role -> ID
    print("connection types" + str(filtered_net_layer))
    # Plat -> ID
    filtered_platforms = [{"id": item["id"], "name": item["name"]} for item in nbox.get_platforms()]

    # logger.info(json.dumps(nbox.get_devices_type()["results"]))
    all_dev_type = [{"id": item["id"], "name": item["display"]} for item in nbox.get_devices_type()]

    all_conn_type = [{"id": item["id"], "name": item["display"]} for item in nbox.get_devices_connection_type()]
    print("connection types" + str(all_conn_type))
    # Funzione per ottenere l'ID del ruolo

    lista_device_non_aggiunti = []

    # Aggiorna la lista dei dispositivi con gli ID dei ruoli e dei layer di rete
    for device in all_devices:
        role_name = device["Device Role"]
        network_layer_name = device.get("Network Layer")
        platform_name = device["Platform"]
        manufacturer_name = device["Manufacturers"]
        device_type = device["Device Type"].replace(" ", "-")

        country = device.get("Country", "")
        city = device.get("City", "")
        device["Location"] = f"{country}_{city}"
        conn_type = device.get("Connection Type")
        severity_dev=device.get("Severity device")

        connection_type_id = get_connection_type_id(conn_type, all_conn_type)
        device_type_id = get_dev_type_id(device_type, all_dev_type)
        platform_id = get_platform_id(platform_name, filtered_platforms)
        manufacturer_id = get_manufacturer_id(manufacturer_name, manufacturer_id_map)
        role_id = get_role_id(role_name, filtered_roles)
        network_layer_id = get_network_layer_id(network_layer_name, filtered_net_layer)

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
        # logger.info(device["Device Type"])
        # Aggiorna i valori nei dispositivi
        device["Device Role"] = role_id
        device["Network Layer"] = network_layer_id
        # Aggiorna i valori nei dispositivi
        device["Severity device"]=severity_dev
        device["Platform"] = platform_id
        device["Manufacturers"] = manufacturer_id
        device["Connection Type"] = connection_type_id
        # Ora la lista dei dispositivi contiene gli ID al posto dei nomi dei ruoli e dei layer di rete

    # CREAZIONE DEI DEVICE #

    # Esempio di utilizzo della funzione create_device con controllo sui campi
    for device in all_devices:
        # Estrai i parametri dal dispositivo
        name = device.get("Device Name")
        device_type = device.get("Device Type")
        role = device.get("Device Role")
        tenant = device.get("Tenant")
        platform = device.get("Platform")
        serial = device.get("Serial Number")
        site = device.get("Site")
        location = device.get("Location")
        conn_id = device.get("Connection Type")
        snmp_com_device = device.get("snmp_community_device")
        net_layer = device.get("Network Layer")
        data_fine = device.get("Data fine contratto")
        data_inizio = device.get("Data inizio contratto")
        sev_lvl = str(device.get("Severity device"))
        if sev_lvl in ["1", "2", "3", "4"]:
            sev_lvl = sev_lvl
        else:
            sev_lvl = None
        rma = "Vendor"
        sla = device.get("SLA")

        try:
            if pd.notna(name) and device_type:
                nbox.create_device(
                    name, device_type, role, tenant, platform, serial, site, location, conn_id,
                    snmp_com_device, net_layer, data_fine, data_inizio, rma, sla, sev_lvl
                )
                logger.info(f"Device '{name}' creato con successo.")

            else:
                lista_device_non_aggiunti.append(device)
                logger.error(f"error on {name}, device type o manufacturer non validi")

        except DuplicateObject:
            logger.info(f"Il device '{name}' già esiste. Ignorato.")
        except Exception as e:
            logger.exception(f"device creation exception: {e}")
            lista_device_non_aggiunti.append(device)

    for elemento in lista_device_non_aggiunti:
        logger.info(f"{elemento.get('Device Name')} non creato!")

    ## INTERFACCE ##
    logger.info("Creazione delle Interfacce")
    devices_added = nbox.get_devices(tenant_id=tenant_id)
    device_name_id = [{"id": item["id"], "name": item["name"]} for item in devices_added]

    for device in device_name_id:
        name = device.get("name")
        id_device = device.get("id")
        try:
            nbox.create_interface(id_device, name)
            logger.info(f"Interfaccia '{name}' creata con successa.")
        except DuplicateObject:
            logger.info(f"Interfaccia '{name}' già esiste. Ignorata.")
        except Exception as e:
            logger.error(f"errore {e} creando l'interfaccia {name}")

    ## IP ADDRESS ##
    interfaces_ids = nbox.get_interfaces()
    interface_device_info = [{"id": item["id"], "name": item["device"]["name"]} for item in interfaces_ids]
    logger.debug(json.dumps(interface_device_info))

    # Dispositivi rimanenti
    filtered_devices = []

    for device in all_devices:
        device_name = device["Device Name"]

        # Verifica se il nome del dispositivo è nella lista dei non aggiunti
        if device_name not in [device['Device Name'] for device in lista_device_non_aggiunti] and str(
                device_name) != 'nan' and device['Management IP Address'] != "NON_PRESENTE":
            filtered_devices.append(device)

    # lista da passare alla Function crea_IP
    address_interface_list = []

    # Itera attraverso i nomi dei dispositivi
    for device_name_info in interface_device_info:
        # Cerca il dispositivo corrispondente nella lista dei dispositivi
        matching_device = next(
            (device for device in filtered_devices if device["Device Name"] == device_name_info["name"]),
            None
        )
        # Se c'è una corrispondenza, crea un nuovo elemento JSON
        if matching_device:
            result_item = {
                "id": device_name_info["id"],
                "Management IP Address": matching_device["Management IP Address"],
                # Aggiungi altri campi desiderati...
            }
            address_interface_list.append(result_item)

    # Stampa la lista finale
    logger.info(f"Correlazione tra Interfacce e IP {address_interface_list}")

    for ip_info in address_interface_list:
        address = ip_info['Management IP Address']
        tenant_id = tenant_id
        interface_id = ip_info['id']
        try:
            nbox.create_ip_address(address, tenant_id, interface_id)
            logger.info(f"IP Address '{address}' collegato a ID dell'interfaccia {interface_id} creato con successo.")
        except DuplicateObject:
            logger.info(f"IP Address '{address}' collegato a ID dell'interfaccia {interface_id} già esiste. Ignorato.")
        except Exception as e:
            logger.error(f"IP address {address} not created error {e}")

    ips_address = nbox.get_IPs_address(tenant_id)
    all_ip_filtered = [{"id": item["id"], "name": item["assigned_object"]["device"]["name"]} for item in ips_address if item["assigned_object"] is not None]
    #all_ip_filtered = [{"id": item["id"], "name": item["assigned_object"]["device"]["name"]} for item in ips_address]
    logger.debug(json.dumps(all_ip_filtered))

    device_now_on_netbox = nbox.get_devices(tenant_id=tenant_id)
    devices_filtered = [{"id": item["id"], "name": item["name"]} for item in device_now_on_netbox]
    logger.debug(json.dumps(devices_filtered))

    # Dizionario per associare il nome del dispositivo ai dettagli del dispositivo
    device_details_dict = {device['Device Name']: device for device in all_devices}

    # Lista per i dispositivi non trovati
    not_found_devices = []

    # Lista con ID degli IP e Nome del Device
    result_list = []

    # Trova corrispondenze e crea la lista risultante
    for device in all_ip_filtered:
        device_name = device['name']
        if device_name in device_details_dict:
            # Corrispondenza trovata, aggiungi l'id e l'IP di gestione alla lista risultante
            result_list.append({
                "id_ip": device['id'],
                "Device Name": device_details_dict[device_name]["Device Name"]
            })
        else:
            # Nessuna corrispondenza trovata, aggiungi alla lista dei dispositivi non trovati
            not_found_devices.append(device_name)

    # Stampa il risultato
    logger.info(f"Dispositivi trovati: {json.dumps(result_list)}")

    # Creazione di un dizionario di corrispondenza tra name e id_ip
    name_to_id_ip = {item['Device Name']: item['id_ip'] for item in result_list}

    # Creazione della lista contenente "id_device" e "id_ip"
    ip_to_patch = [{"id_device": item1["id"], "id_ip": name_to_id_ip.get(item1["name"], None)} for item1 in
                   devices_filtered]

    # Stampa della lista risultante
    logger.info(f"Gli IP associati ai device da aggiungere sono: {json.dumps(ip_to_patch)}")

    for elem in ip_to_patch:
        id_address = elem['id_ip']
        id_device = elem['id_device']
        try:
            nbox.update_device_with_IP(id_device, id_address)
            logger.info(f"ID_ip Address '{id_address}' collegato a ID_device {id_device} con successo.")
        except DuplicateObject:
            logger.info(f"ID_ip Address '{id_address}' collegato a ID_device {id_device} già esiste. Ignorato.")
        except Exception as e:
            logger.error(f"errore {e} durante l'associazione di {id_address} al device {id_device}")

    # VIRTUAL CHASSIS #############################################################################
    # lista dei device multipli da aggiungere ai vari VC

    # lista all device - ID senza /
    # Estrai solo la prima parte del nome, se presente un '/'
    modified_list = [{'id': item['id'], 'name': item['name'].split('/')[0]} for item in devices_filtered]
    # Estrai tutti i valori dell'attributo 'name'
    names = [item['name'] for item in modified_list]
    # Conta quante volte ciascun nome appare nella lista
    name_counts = Counter(names)
    # Filtra gli elementi che hanno un nome che appare più di una volta
    result_list = [item for item in modified_list if name_counts[item['name']] > 1]
    # Aggiungi nuovamente la parte dopo '/' al nome nel risultato
    result_list = [{'id': item['id'],
                    'name': item['name'] + '/' + item['name'].split('/')[1] if '/' in item['name'] else item['name']}
                   for item in result_list]

    # Stampa la lista risultante
    logger.debug(json.dumps(result_list))

    device_match_for_VC = match_for_VC(devices_filtered, result_list)
    logger.debug(json.dumps(device_match_for_VC))

    for device in device_match_for_VC:
        try:
            if '/' not in device["name"]:
                nbox.create_virtual_chassis(device["name"], device["id"])
                logger.info(f"Creazione VC '{device['id']}' riuscita")
        except DuplicateObject:
            logger.info(f"creazione gia eseguita per VC con '{device['id']}' ")
        except Exception as e:
            logger.error(f"errore {e} creando VD per '{device['id']}' ")

    extract_vc = [{"id": item["id"], "name": item["name"]} for item in nbox.get_virtual_chassis()]
    logger.debug(json.dumps(extract_vc))

    # Rimuovi gli elementi con "/" nel nome
    elabora_dev_vc = [item for item in device_match_for_VC if '/' in item['name']]

    # Conta gli elementi con la stessa parte prima dello "/"
    count_dict = {}
    for item in elabora_dev_vc:
        prefix = item['name'].split('/')[0]
        count_dict[prefix] = count_dict.get(prefix, 1) + 1
        item['position'] = count_dict[prefix]

    # Stampa il risultato
    logger.info(f"I devices che occorre elaborare per ricavare le posizioni nel VC sono: {json.dumps(elabora_dev_vc)}")

    dev_to_update_vc = []

    for first_item in elabora_dev_vc:
        for second_item in extract_vc:
            if first_item['name'].startswith(second_item['name']):
                dev_to_update_vc.append({
                    "id_device": first_item['id'],
                    "id_vc": second_item['id'],
                    "position_in_vc": first_item['position']
                })

    logger.debug(json.dumps(dev_to_update_vc))

    for item in dev_to_update_vc:
        try:
            id_device = item["id_device"]
            id_vc = item["id_vc"]
            position_vc = item["position_in_vc"]
            nbox.update_virtual_chassis(id_device, id_vc, position_vc)
            logger.info(f"VC {id_device} settato con l'aggiunta dei devices richiesti")
        except DuplicateObject:
            logger.info(f"gia impostato")
        except Exception as e:
            logger.info(f"error - impossibile eseguire l'update: {e}")


if __name__ == "__main__":
    main()
