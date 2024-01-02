import time
import os
import requests
import yaml
from ycheckmk import YCheckMK
from ynetbox import YNetbox
import logging
from nazioni import nazioni

DISCOVERY_TIMEOUT = 180
cur_dir = os.path.abspath(os.path.dirname(__file__))
conf = yaml.safe_load(open(os.path.join(cur_dir, "conf.yml")))
logging.basicConfig(filename=os.path.join(cur_dir, "cmk_nbox_push.log"), filemode='a+', level=logging.INFO,
                    format='[%(levelname)s] %(asctime)s - %(name)s: %(message)s')
logger = logging.getLogger()


def split_string(input_string):
    # Dividi la stringa utilizzando il carattere "_"
    parts = input_string.split('_')

    if len(parts) != 2:
        # Verifica formato corretto
        return None  # Restituisci None per le stringhe con formato non valido

    # Estrai la nazione dalle prime tre lettere e mappa con il nome completo
    nazione = nazioni.get(parts[0], "Nazione non riconosciuta")
    # Sostituisci il carattere "_" con "/"
    resto = parts[1]
    risultato = f"{nazione}/{resto}"
    return risultato


def extract_information(response):
    data = response
    device_info_list = []

    for item in data["results"]:
        device_info = {
            "tenants": item["tenant"]["name"],
            "sites": item["site"]["name"],
            "snmp_communities_location": item["custom_fields"]["snmp_community_location"]
        }
        # Cerca il campo "name" subito dopo "id"
        name_found = False
        for key, value in item.items():
            if key == "id":
                name_found = True
            elif name_found and key == "name":
                device_info["names"] = value
                break
        else:
            device_info["names"] = None  # Se non è stato trovato un campo "name" dopo "id", aggiungi None

        device_info_list.append(device_info)

    return device_info_list


def check_directory(tenant_name, location):
    # Crea la stringa "path" concatenando "tenant_name" e "location"
    path = f"{tenant_name}/{location}"
    return path


def process_devices(devices_data):
    valid_controlled = []

    for device in devices_data["results"]:
        primary_ip = device.get("primary_ip")

        if primary_ip is not None:
            mgmt_ip_address = primary_ip.get("address", "N/A")
        else:
            mgmt_ip_address = "N/A"
        out_of_band_ip = mgmt_ip_address

        status = device.get("status", {}).get("value", "N/A")
        device_role = device.get("role", {}).get("name", "N/A")
        tenant = device.get("tenant")
        if tenant:
            tenant_name = tenant.get("name", "N/A")
        else:
            tenant_name = "N/A"
        location = device.get("location", {}).get(
            "name", "N/A") if isinstance(device.get("location", {}), dict) else "N/A"

        site = device.get("site", {}).get("name", "N/A")

        if "platform" in device and device["platform"]:
            platform = device["platform"].get("slug", "N/A")
        else:
            platform = "N/A"

        custom_fields = device.get("custom_fields", {})
        net_layer = custom_fields.get("net_layer", "N/A")
        snmp = custom_fields.get("snmp", "N/A")
        snmp_community = custom_fields.get("snmp_community", "N/A")
        snmp_community = snmp_community[0] if isinstance(
            snmp_community, list) and len(snmp_community) > 0 else snmp_community

        if all(x not in ["N/A", None] for x in [out_of_band_ip, status, device_role, tenant, location, site, platform,
                                                snmp]) and device_role != "ap_mgmt":
            # if all(x not in ["N/A", None] for x in [out_of_band_ip, status, device_role, tenant, location, site, platform, net_layer, snmp, snmp_community]):
            path = check_directory(tenant_name, split_string(location))

            device_info = {
                "Device Name": device["name"].replace("/", "_").replace("à", "a").replace("è", "e").replace("é",
                                                                                                            "e").replace(
                    "ù", "ù").replace("ì", "i").replace("ò", "o"),
                "Out-of-Band IP": out_of_band_ip,
                "Net Type (Device Role)": device_role,
                "Stato": status,
                "Tenant": tenant_name,
                "Location": location,
                "Site": site,
                "Platform": platform,
                "Net Layer": net_layer,
                "SNMP": snmp if snmp != "N/A" else "Non presente",
                "SNMP Community": snmp_community if snmp_community != "N/A" else "Non presente",
                "Path": path  # Aggiunge il percorso al dizionario
            }
            valid_controlled.append(device_info)

    return valid_controlled


def check_host(device_data, host_list):
    host_to_post = []  # Inizializza una lista per gli host da inserire

    # Estrai i Device_Name
    device_names = [device['Device Name'] for device in device_data]

    for device_name in device_names:
        found = False
        for host in host_list:
            if host['hostname'] == device_name:
                found = True
                break

        if not found:
            # Se il Device_Name non è stato trovato tra gli hostname
            # Crea un oggetto con le caratteristiche di Device_Name
            for device in device_data:
                if device['Device Name'] == device_name:
                    host_info = {
                        "hostname": device_name,
                        "folder": "/",
                        "location": split_string(device['Location']),
                        "customer": device['Tenant'],
                        "ipv4 address": device['Out-of-Band IP'],
                        "snmp_community": device['SNMP Community'],
                        "snmp": "no-snmp" if not device['SNMP'] else "snmp-v2",  ######## controllarew
                        "site": device['Site'],
                        "layer_of_the_switch": device['Net Layer'],
                        "type_of_network_device": device['Net Type (Device Role)'],
                        "type_of_server": "none",
                        "agent": "cmk-agent"
                    }
                    host_to_post.append(host_info)

    return host_to_post


def mapping(entry):
    if entry["snmp_community"] != "Non presente":

        hostname_object = {
            # "folder":"/",
            "folder": f"/{entry['customer'].lower()}/{entry['location'].lower()}",
            "host_name": entry['hostname'],
            "attributes": {
                "ipaddress": entry['ipv4 address'].split('/')[0],
                "snmp_community": {
                    "type": "v1_v2_community",
                    "community": entry['snmp_community']
                },
                "tag_snmp_ds": entry['snmp'].lower(),
                "site": entry['site'].lower(),
                "tag_nettype": entry['type_of_network_device'].lower(),
                "tag_servertype": entry['type_of_server'].lower(),
                "tag_netlayer": str(entry['layer_of_the_switch']).lower()
            }
        }
    else:
        hostname_object = {
            # "folder":"/",
            "folder": f"/{entry['customer'].lower()}/{entry['location'].lower()}",
            "host_name": entry['hostname'],
            "attributes": {
                "ipaddress": entry['ipv4 address'].split('/')[0],
                "tag_snmp_ds": entry['snmp'].lower(),
                "site": entry['site'].lower(),
                "tag_nettype": entry['type_of_network_device'].lower(),
                "tag_servertype": entry['type_of_server'].lower(),
                "tag_netlayer": str(entry['layer_of_the_switch']).lower()
            }
        }
    return hostname_object


def fetch_checkmk_data(data):
    # Estrai i dati richiesti
    result = []

    for item in data['value']:
        folder = item['extensions'].get('folder', 'N/A')
        customer = (folder.split('/')[1]) if '/' in folder else 'N/A'  # Selezione della directory genitore
        hostname = item.get('id', 'N/A')

        attributes = item['extensions'].get('attributes', {})
        ipv4_address = attributes.get('ipaddress', 'N/A')

        effective_attributes = item['extensions'].get('effective_attributes', {})

        snmp_community = effective_attributes.get('snmp_community', {})
        snmp = effective_attributes.get('tag_snmp_ds', 'N/A')

        layer_of_the_switch = effective_attributes.get('tag_netlayer', 'N/A')
        type_of_network_device = effective_attributes.get('tag_nettype', 'N/A')
        type_of_server = effective_attributes.get('tag_servertype', 'N/A')
        agent = effective_attributes.get('tag_agent', 'N/A')

        host_attributes = {
            "hostname": hostname,
            "folder": folder,
            "customer": customer,
            "ipv4 address": ipv4_address,
            "snmp_community": snmp_community,
            "snmp": snmp,
            "layer_of_the_switch": layer_of_the_switch,
            "type_of_network_device": type_of_network_device,
            "type_of_server": type_of_server,
            "agent": agent
        }

        result.append(host_attributes)

    return result


def main():
    nbox = YNetbox(**conf['netbox'])
    cmk = YCheckMK(**conf['checkmk'])

    # region folder
    raw_location = nbox.get_locations()

    # Stampa la lista di oggetti contenenti le informazioni
    device_info_list = extract_information(raw_location)

    all_paths = []
    all_tenants = []
    snmp_loc = []

    # Stampa la lista di oggetti contenenti le informazioni
    for device_info in device_info_list:
        tenant = device_info["tenants"]
        folder = device_info["names"]
        split_result = split_string(folder)
        # nazione_path = get_nation(folder)
        # print(split_result)
        if split_result is not None and '/' in split_result:
            path = "/" + tenant + "/" + split_result
            all_paths.append(path)

    for device_info in device_info_list:
        tenant = device_info["tenants"]
        if tenant not in all_tenants:
            all_tenants.append(tenant)
            snmp_loc = device_info["snmp_communities_location"]
            # print(snmp_loc)

    logger.info(f"folders to be created based on netbox data: {all_paths}")

    for data in all_paths:
        try:
            folder_object_1 = {
                "name": (data.split("/"))[1].lower(),
                "title": (data.split("/"))[1].lower(),
                "parent": "/",
                "attributes": {
                    "snmp_community": {
                        "type": "v1_v2_community",
                        "community": snmp_loc
                    },
                    "tag_snmp_ds": "snmp-v2"
                }
            }
            folder_object_2 = {
                "name": (data.split("/"))[2].lower(),
                "title": (data.split("/"))[2].lower(),
                "parent": "/" + (data.split("/"))[1].lower(),
                "attributes": {
                    "snmp_community": {
                        "type": "v1_v2_community",
                        "community": snmp_loc
                    },
                    "tag_snmp_ds": "snmp-v2"
                }
            }
            folder_object_3 = {
                "name": (data.split("/"))[3].lower(),
                "title": (data.split("/"))[3].lower(),
                "parent": "/" + (data.split("/"))[1].lower() + "/" + (data.split("/"))[2].lower(),
                "attributes": {
                    "snmp_community": {
                        "type": "v1_v2_community",
                        "community": snmp_loc
                    },
                    "tag_snmp_ds": "snmp-v2"
                }
            }
            try:
                cmk.create_folder(folder_object_1)
                logger.info(f"created folder {folder_object_1['name']}")
            except requests.HTTPError as he:
                if he.response.status_code == 400 and "already exists" in he.response.text:
                    logger.info(f"folder {folder_object_1['name']} already exists")
                else:
                    raise he
            try:
                cmk.create_folder(folder_object_2)
                logger.info(f"created folder {folder_object_2['name']}")
            except requests.HTTPError as he:
                if he.response.status_code == 400 and "already exists" in he.response.text:
                    logger.info(f"folder {folder_object_2['name']} already exists")
                else:
                    raise he
            try:
                cmk.create_folder(folder_object_3)
                logger.info(f"created folder {folder_object_3['name']}")
            except requests.HTTPError as he:
                if he.response.status_code == 400 and "already exists" in he.response.text:
                    logger.info(f"folder {folder_object_3['name']} already exists")
                else:
                    raise he


        except Exception as e:
            logger.exception(f"error {e} handling {data}")

    # endregion

    # region devices
    raw_netbox_devices = nbox.get_devices()
    valid_netbox_devices = process_devices(raw_netbox_devices)
    logger.debug(f"valid netbox devices are: {valid_netbox_devices}")

    raw_checkmk_hosts = cmk.get_hosts()
    logger.debug(f"valid netbox devices are: {raw_checkmk_hosts}")

    netbox_check_mk_diff = check_host(valid_netbox_devices, fetch_checkmk_data(raw_checkmk_hosts))
    logger.debug(f"netbox host not in checkmk: {netbox_check_mk_diff}")

    unique_json_objects = [mapping(h) for h in netbox_check_mk_diff]
    logger.info(f"host that will be created: {unique_json_objects}")

    successfully_created_hosts = []

    for host in unique_json_objects:
        try:
            cmk.create_host(host)
            successfully_created_hosts.append(host['host_name'])
        except Exception as e:
            logger.exception(f"error {e} on {host}")

    bulk_data = {
        "hostnames": successfully_created_hosts,
        "mode": "refresh",
        "do_full_scan": True,
        "bulk_size": 10,
        "ignore_errors": True
    }
    if successfully_created_hosts:
        cmk.start_bulk_discovery(bulk_data)
        logger.info(f"started bulk check discovery for: {successfully_created_hosts}")
        time.sleep(2)
        discovery_status = cmk.get_bulk_discovery_status()
        counter = 0
        while discovery_status['extensions']['state'] != "finished" and counter < DISCOVERY_TIMEOUT / 2:
            time.sleep(2)
            counter += 1
            discovery_status = cmk.get_bulk_discovery_status()

        logger.info(f"bulk check discovery completed. results: {discovery_status['extensions']['logs']['result']}")
    else:
        logger.info(f"bulk check discovery will not be started as no new host has been created")

    # endregion


if __name__ == "__main__":
    main()
