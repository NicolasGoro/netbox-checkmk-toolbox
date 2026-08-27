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
import math
from collections import Counter
import sys

warnings.filterwarnings("ignore")
cur_dir = os.path.abspath(os.path.dirname(__file__))
conf = yaml.safe_load(open(os.path.join(cur_dir, "conf.yml")))

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

# Ottieni gli URL usando le funzioni
net_layer_url = nbox.base_url + f"/extras/custom-field-choice-sets/{nbox.net_layer_cf_id}/choices"
conn_type_url = nbox.base_url + f"/extras/custom-field-choice-sets/{nbox.conn_type_cf_id}/choices"
print("URL per get_devices_net_layer:", net_layer_url)
print("URL per get_devices_connection_type:", conn_type_url)


# Caratteri accentati italiani da normalizzare in tutti i campi testuali che
# vengono usati come identificatori (slug, nomi, description, ecc.)
_ACCENTED_CHARS_MAP = {
    "à": "a", "è": "e", "é": "e", "ù": "u", "ì": "i", "ò": "o",
}


def normalize_it_accents(value):
    """Sostituisce le vocali accentate italiane con la corrispondente vocale semplice."""
    for accented, plain in _ACCENTED_CHARS_MAP.items():
        value = value.replace(accented, plain)
    return value


def clean_str(value):
    """
    Pulisce i valori letti da Excel da NaN e da caratteri "spazio" invisibili
    (es. \\xa0 - non-breaking space), che altrimenti passano i controlli pd.isna()
    ma vengono rifiutati da NetBox come scelta non valida nei custom field a scelta.
    """
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.replace("\xa0", "").strip()
        return value if value else None
    return value


# EXCEL
# Estrazione riga per riga elementi
def extract_all_objects_row(file_path):
    df = pd.read_excel(file_path, engine='openpyxl')

    json_list = []
    device_name_count = {}
    for index, row in df.iterrows():
        device_name = row["Device Name"]
        if device_name in device_name_count:
            device_name_count[device_name] += 1
            device_name = f"{device_name}/{row['Serial Number']}"
        else:
            device_name_count[device_name] = 1

        json_data = {
            "Device Name": device_name,
            "Device Role": row["Device Role"],
            "Device Type": row["Device Type"],
            "Serial Number": row["Serial Number"],
            "Istance Number": "NON PRESENTE" if pd.isna(row.get("Istance Number")) else str(int(row.get("Istance Number"))),
            "Country": normalize_it_accents(row["Country"]),
            "City": normalize_it_accents(row["City"]),
            "Site": row["Site"],
            "Status": row["Status"],
            "Tenant": normalize_it_accents(row["Tenant"]),
            "Management IP Address": "NON PRESENTE" if pd.isna(row["Management IP Address"]) else format_ip(row["Management IP Address"]),
            "SLA": clean_str(row.get("SLA")),
            "On site": None if pd.isna(row["On site"]) else row["On site"].strip().upper() == "SI",
            "Fornitore": "NON PRESENTE" if clean_str(row.get("Fornitore")) is None else clean_str(row.get("Fornitore")),
            "SNMP": None if pd.isna(row["SNMP"]) else row["SNMP"],
            "snmp_community_device": clean_str(row.get("snmp_community_device")),
            "snmp_community_city": clean_str(row.get("snmp_community_city")),
            "Data inizio contratto": datetime.strftime(row["Data inizio contratto"], "%Y-%m-%d") if not pd.isna(row["Data inizio contratto"]) else "NON PRESENTE",
            "Data fine contratto": datetime.strftime(row["Data fine contratto"], "%Y-%m-%d") if not pd.isna(row["Data fine contratto"]) else "NON PRESENTE",
            "Maintenance": clean_str(row.get("Maintenance")),
            "Monitoraggio": row["Monitoraggio"],
            "Connection Type": row["Connection Type"],
            "Severity device": int(row["Severity device"]) if not pd.isna(row["Severity device"]) else None,
            "Network Layer": row["Network Layer\u00a0"] if not pd.isna(row["Network Layer\u00a0"]) else None,
            "Manufacturers": row["Manufacturers"],
            "Platform": row["Platform"] if not pd.isna(row["Platform"]) else None,
            "Backup": None if pd.isna(row["Backup"]) else row["Backup"],
            # Nome (Device Name) dell'host che fungerà da "parent" su CheckMK.
            # Deve corrispondere esattamente al Device Name di un altro host presente/importato.
            "Agent Type": clean_str(row.get("Agent Type")),
            "Parent Device": clean_str(row.get("Parent Device")),
        }

        json_list.append(json_data)

    return json_list


def format_ip(ip):
    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.version == 4:
            return str(ip_obj)
        else:
            ip = str(ip)
            if len(ip) == 12:
                groups = [ip[i:i + 3] for i in range(0, len(ip), 3)]
                ip = '.'.join(groups)
            return ip
    except ValueError:
        return f"Invalid IP: {ip}"


def estrai_campo(json_list, chiave_da_estrazione):
    valori_chiave = []
    for json_obj in json_list:
        if chiave_da_estrazione in json_obj:
            valori_chiave.append(json_obj[chiave_da_estrazione])
        else:
            valori_chiave.append("Chiave non presente")
    return valori_chiave


def estrai_elementi_unici(json_list, chiave_da_estrazione):
    valori_unici = set()
    for json_obj in json_list:
        if chiave_da_estrazione in json_obj:
            valori_unici.add(json_obj[chiave_da_estrazione])
    return list(valori_unici)


def extract_and_concatenate_unique(file_path):
    df = pd.read_excel(file_path)
    unique_concatenations = set()
    for index, row in df.iterrows():
        country_code = row['Country'][:3].lower() if pd.notnull(row['Country']) else ''
        city_name = row['City'] if pd.notnull(row['City']) else ''
        concatenated_value = f"{country_code}_{city_name}"
        unique_concatenations.add(concatenated_value)
    return list(unique_concatenations)


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
                "Tenant": normalize_it_accents(tenant_add),
                "Country": location_add[:3],
                "City": normalize_it_accents(location_add.split('_')[1]),
                "Site": normalize_it_accents(site_add),
                "Location": normalize_it_accents(location_add),
                "Device Type": row.get("Model", "NON PRESENTE"),
                "Management IP Address": row.get("Login IP", "NON PRESENTE"),
                "Serial Number": row.get("Serial Number", "NON PRESENTE"),
                "Platform": row.get("Family", "NON PRESENTE"),
                "Device Role": row.get("Type", "NON PRESENTE"),
                "Manufacturers": row.get("Vendor", "NON PRESENTE"),
                # Il CSV (import da altri tool) di solito non porta questa informazione,
                # ma il campo viene comunque valorizzato a None per uniformità con il flusso Excel.
                "Parent Device": None,
            }
            result_list.append(entry)

    return result_list, location_add


def get_id_by_name(elements_list, name):
    for el in elements_list:
        if el['name'] == name:
            return el['id']
    return None


def get_location_id_by_name_and_site(locations_list, name, site_id):
    """
    Cerca una location per nome E site_id, evitando di riutilizzare per errore
    location di altri tenant/site che abbiano lo stesso nome.
    """
    for loc in locations_list:
        if loc['name'] == name and loc.get('site', {}).get('id') == site_id:
            return loc['id']
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
            if device_type_id not in seen_device_types:
                seen_device_types.add(device_type_id)
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
    return [{"Manufacturers": m, "Network Layer": n} for m, n in unique_pairs]


def filter_json(data):
    return {key: value for key, value in data.items() if
            key in ["Device Type", "Manufacturers"] and not (isinstance(value, float) and math.isnan(value))}


def get_role_id(role_name, filtered_roles):
    for role in filtered_roles:
        if role["name"] == role_name:
            return role["id"]
    return None


def get_network_layer_id(layer_name, filtered_net_layer):
    for layer in filtered_net_layer:
        if layer["display"] == layer_name:
            return layer["id"]
    return None


def get_dev_type_id(layer_name, all_dev_type):
    for layer in all_dev_type:
        if layer["name"] == layer_name:
            return layer["id"]
    return None


def get_connection_type_id(layer_name, all_conn_type):
    for layer in all_conn_type:
        if layer["name"] == layer_name:
            return layer["id"]
    return None


def get_platform_id(platform_name, filtered_platforms):
    for platform in filtered_platforms:
        if platform["name"] == platform_name:
            return platform["id"]
    return None


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
        all_devices = extract_all_objects_row(path)

        for json_obj in all_devices:
            logger.debug(json.dumps(json_obj))

        tenant_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Tenant')
        logger.info(f"I Tenants trovati sull'Excel sono:{tenant_add}")

        device_type_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Device Type')
        logger.info(f"I Device-Type trovati sull'Excel sono: {device_type_add}")
        filtered_device_type_add = [filter_json(item) for item in all_devices]

        device_manufacturers_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Manufacturers')
        if np.nan in device_manufacturers_add:
            device_manufacturers_add.remove(np.nan)
        logger.info(f"I manufacturers trovati sull'Excel sono: {device_manufacturers_add}")

        site_add = estrai_elementi_unici(all_devices, chiave_da_estrazione='Site')
        logger.info(f"I Sites trovati sull'Excel sono: {site_add}")

        locations_add = extract_and_concatenate_unique(path)
        locations_add = [item for item in locations_add if "_n.d." not in item]
        logger.info(f"Le Locations trovate sull'Excel sono: {locations_add}")
        logger.info('finita estrazione excel')

    elif file_extension.lower() == '.csv':
        all_devices, location_add = process_csv(path)
        locations_add = [location_add]
        logger.debug(json.dumps(all_devices))

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
    logger.info(f"Il Tenant ha id {tenant_id}")

    # VRF - Creazione basata sul Tenant
    vrfs = nbox.get_vrfs()
    vrf_name = tenant_add[0]
    vrf_id = get_id_by_name(vrfs, vrf_name)

    if vrf_id is None:
        logger.info(f"VRF '{vrf_name}' mancante, lo creo")
        vrf_result = nbox.create_vrf(vrf_name, tenant_id)
        vrfs.append(vrf_result)
        vrf_id = get_id_by_name(vrfs, vrf_name)
    else:
        logger.info(f"VRF '{vrf_name}' già presente")

    logger.info(f"Il VRF ha id {vrf_id}")

    # SITES
    sites = nbox.get_sites()
    for site_to_add in site_add:
        site_id_tmp = get_id_by_name(sites, site_to_add)
        if site_id_tmp is None:
            logger.info(f"site {site_to_add} mancante, lo creo")
            site_result = nbox.create_site(site_to_add, tenant_id)
            sites.append(site_result)
        else:
            logger.info(f"site {site_to_add} già presente")

    # Mappa nome site -> id (usata da device e location)
    site_name_to_id = {s['name']: s['id'] for s in sites}
    logger.info(f"Site map: {site_name_to_id}")

    # LOCATIONS
    # Cerca la location per nome E site_id per evitare conflitti con
    # location omonime già presenti su NetBox ma legate ad altri site/tenant
    locations = nbox.get_locations()

    for loc_to_add in locations_add:
        # Trova il site_id, la città e la snmp_community_city corretti per questa
        # location cercando tra i device (community e city sono legate allo stesso
        # device, così restano coerenti anche se ci sono più community diverse
        # nello stesso file, una per città)
        loc_site_id = None
        loc_city = None
        loc_snmp_community = None
        for dev in all_devices:
            country = dev.get("Country", "")
            city = dev.get("City", "")
            if f"{country}_{city}" == loc_to_add:
                loc_site_id = site_name_to_id.get(dev.get("Site"))
                loc_city = city
                loc_snmp_community = dev.get("snmp_community_city")
                break

        if loc_site_id is None:
            logger.error(f"Impossibile trovare il site per la location {loc_to_add}, la salto")
            continue

        # Description = "<Tenant> <Città>", es. "Helvetia Firenze"
        loc_description = f"{tenant_add[0]} {loc_city}" if loc_city else tenant_add[0]

        location_id = get_location_id_by_name_and_site(locations, loc_to_add, loc_site_id)
        if location_id is None:
            logger.info(f"location {loc_to_add} mancante per site {loc_site_id}, la creo")
            location_result = nbox.create_loction(loc_to_add, loc_site_id, tenant_id, loc_snmp_community, loc_description)
            locations.append(location_result)
        else:
            logger.info(f"location {loc_to_add} già presente per site {loc_site_id}, aggiorno description/SNMP community")
            try:
                nbox.update_location(location_id, loc_to_add, loc_site_id, tenant_id, loc_snmp_community, loc_description)
            except DuplicateObject:
                logger.info(f"location {loc_to_add} già allineata")
            except Exception as e:
                logger.error(f"errore {e} aggiornando la location {loc_to_add}")

    # CHECK DEVICE TYPE
    device_type_nbox = nbox.get_devices_type()
    all_device_type_on_nbox = []
    for item in device_type_nbox:
        device_type = {"device_type": item["display"]}
        manufacturer = {"manufacturer": item["manufacturer"]["display"]}
        all_device_type_on_nbox.append({**device_type, **manufacturer})

    all_device_type_on_file = []
    for device in filtered_device_type_add:
        all_device_type_on_file.append(device)

    to_add = []
    for element1 in all_device_type_on_file:
        if element1 not in all_device_type_on_nbox:
            to_add.append(element1)

    to_add_all = [device for device in to_add if all(key in device for key in ['Device Type', 'Manufacturers'])]
    logger.info(f"I Device Type da provare ad aggiungere sono: {json.dumps(to_add_all)}")

    manufacturers_ids = nbox.get_manufacturers()["results"]
    manufacturer_id_map = {manufacturer['name']: manufacturer['id'] for manufacturer in manufacturers_ids}

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
    # Ricarica le locations dopo la creazione, così include quelle appena create
    locations = nbox.get_locations()
    filtered_roles = [{"id": item["id"], "name": item["name"]} for item in nbox.get_devices_roles()]
    filtered_net_layer = [{"id": item["id"], "display": item["display"]} for item in nbox.get_devices_net_layer()]
    print("connection types" + str(filtered_net_layer))
    filtered_platforms = [{"id": item["id"], "name": item["name"]} for item in nbox.get_platforms()]
    all_dev_type = [{"id": item["id"], "name": item["display"]} for item in nbox.get_devices_type()]
    all_conn_type = [{"id": item["id"], "name": item["display"]} for item in nbox.get_devices_connection_type()]
    print("connection types" + str(all_conn_type))

    lista_device_non_aggiunti = []

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
        severity_dev = device.get("Severity device")

        # Salva il nome del site prima di sovrascriverlo
        site_name_original = device.get("Site")

        connection_type_id = get_connection_type_id(conn_type, all_conn_type)
        device_type_id = get_dev_type_id(device_type, all_dev_type)
        platform_id = get_platform_id(platform_name, filtered_platforms)
        manufacturer_id = get_manufacturer_id(manufacturer_name, manufacturer_id_map)
        role_id = get_role_id(role_name, filtered_roles)
        network_layer_id = get_network_layer_id(network_layer_name, filtered_net_layer)

        # Cerca la location per nome E site_id corretto per questo device,
        # evita di prendere la location omonima di un altro site
        device_site_id = site_name_to_id.get(site_name_original)
        location_id = get_location_id_by_name_and_site(locations, device["Location"], device_site_id)
        if location_id is None:
            logger.error(f"Location '{device['Location']}' non trovata per site '{site_name_original}' (id: {device_site_id}) per il device {device.get('Device Name')}")

        device["Location"] = location_id
        # Assegna il site_id corretto per questo specifico device
        device["Site"] = device_site_id
        if device["Site"] is None:
            logger.error(f"Site '{site_name_original}' non trovato nella mappa per il device {device.get('Device Name')}")
        device["Tenant"] = tenant_id
        device["Device Type"] = device_type_id
        device["Device Role"] = role_id
        device["Network Layer"] = network_layer_id
        device["Severity device"] = severity_dev
        device["Platform"] = platform_id
        device["Manufacturers"] = manufacturer_id
        device["Connection Type"] = connection_type_id

    # CREAZIONE DEI DEVICE
    for device in all_devices:
        name = device.get("Device Name")
        device_type = device.get("Device Type")
        role = device.get("Device Role")
        tenant = device.get("Tenant")
        platform = device.get("Platform")
        serial = device.get("Serial Number")
        site = device.get("Site")
        location = device.get("Location")
        status = device.get("Status")
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
        rma = device.get("Maintenance")
        sla = device.get("SLA")
        onsite = device.get("On site")
        snmp_value = device.get("SNMP")
        backup_value = device.get("Backup")
        istance_number = device.get("Istance Number")
        # Nome del device "parent" (per il campo CheckMK "Parents"), letto da Excel
        agent_type = device.get("Agent Type")
        parent_device = device.get("Parent Device")

        try:
            if pd.notna(name) and device_type:
                nbox.create_device(
                    name, device_type, role, tenant, platform, serial, site, location, status, conn_id, onsite,
                    snmp_value, snmp_com_device, net_layer, data_fine, data_inizio, rma, sla, sev_lvl, backup_value,
                    istance_number, parent_device, agent_type)
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

    filtered_devices = []
    for device in all_devices:
        device_name = device["Device Name"]
        if device_name not in [device['Device Name'] for device in lista_device_non_aggiunti] and str(
                device_name) != 'nan' and device['Management IP Address'] != "NON_PRESENTE":
            filtered_devices.append(device)

    address_interface_list = []
    for device_name_info in interface_device_info:
        matching_device = next(
            (device for device in filtered_devices if device["Device Name"] == device_name_info["name"]),
            None
        )
        if matching_device:
            result_item = {
                "id": device_name_info["id"],
                "Management IP Address": matching_device["Management IP Address"],
            }
            address_interface_list.append(result_item)

    logger.info(f"Correlazione tra Interfacce e IP {address_interface_list}")

    for ip_info in address_interface_list:
        address = ip_info['Management IP Address']
        interface_id = ip_info['id']
        try:
            nbox.create_ip_address(address, tenant_id, interface_id, vrf_id)
            logger.info(f"IP Address '{address}' collegato a ID dell'interfaccia {interface_id} creato con successo.")
        except DuplicateObject:
            logger.info(f"IP Address '{address}' collegato a ID dell'interfaccia {interface_id} già esiste. Ignorato.")
        except Exception as e:
            logger.error(f"IP address {address} not created error {e}")

    ips_address = nbox.get_IPs_address(tenant_id)
    all_ip_filtered = [{"id": item["id"], "name": item["assigned_object"]["device"]["name"]} for item in ips_address if item["assigned_object"] is not None]
    logger.debug(json.dumps(all_ip_filtered))

    device_now_on_netbox = nbox.get_devices(tenant_id=tenant_id)
    devices_filtered = [{"id": item["id"], "name": item["name"]} for item in device_now_on_netbox]
    logger.debug(json.dumps(devices_filtered))

    device_details_dict = {device['Device Name']: device for device in all_devices}
    not_found_devices = []
    result_list = []

    for device in all_ip_filtered:
        device_name = device['name']
        if device_name in device_details_dict:
            result_list.append({
                "id_ip": device['id'],
                "Device Name": device_details_dict[device_name]["Device Name"]
            })
        else:
            not_found_devices.append(device_name)

    logger.info(f"Dispositivi trovati: {json.dumps(result_list)}")

    name_to_id_ip = {item['Device Name']: item['id_ip'] for item in result_list}
    ip_to_patch = [{"id_device": item1["id"], "id_ip": name_to_id_ip.get(item1["name"], None)} for item1 in devices_filtered]
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

    # VIRTUAL CHASSIS
    modified_list = [{'id': item['id'], 'name': item['name'].split('/')[0]} for item in devices_filtered]
    names = [item['name'] for item in modified_list]
    name_counts = Counter(names)
    result_list = [item for item in modified_list if name_counts[item['name']] > 1]
    result_list = [{'id': item['id'],
                    'name': item['name'] + '/' + item['name'].split('/')[1] if '/' in item['name'] else item['name']}
                   for item in result_list]

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

    elabora_dev_vc = [item for item in device_match_for_VC if '/' in item['name']]
    count_dict = {}
    for item in elabora_dev_vc:
        prefix = item['name'].split('/')[0]
        count_dict[prefix] = count_dict.get(prefix, 1) + 1
        item['position'] = count_dict[prefix]

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
