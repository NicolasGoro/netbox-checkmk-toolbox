import os
import requests
import yaml
from modules.ycheckmk import YCheckMK
from modules.ynetbox import YNetbox
import logging
from modules.nazioni import nazioni
import sys
import json

cur_dir = os.path.abspath(os.path.dirname(__file__))
conf = yaml.safe_load(open(os.path.join(cur_dir, "conf.yml")))
DISCOVERY_TIMEOUT = conf['misc']['discovery_timeout']
if conf['misc']['debug'] is True:
    logging.basicConfig(filename=os.path.join(cur_dir, "cmk_nbox_push.log"), filemode='a+', level=logging.DEBUG,
                        format='[%(levelname)s] %(asctime)s - %(name)s: %(message)s')
else:
    logging.basicConfig(filename=os.path.join(cur_dir, "cmk_nbox_push.log"), filemode='a+', level=logging.INFO,
                        format='[%(levelname)s] %(asctime)s - %(name)s: %(message)s')
logger = logging.getLogger()


# Caratteri accentati italiani da normalizzare nei campi usati come nome
# host/tenant/location (CheckMK non li accetta in folder/hostname)
_ACCENTED_CHARS_MAP = {
    "à": "a", "è": "e", "é": "e", "ù": "u", "ì": "i", "ò": "o",
}


def normalize_it_accents(value):
    """Sostituisce le vocali accentate italiane con la corrispondente vocale semplice."""
    for accented, plain in _ACCENTED_CHARS_MAP.items():
        value = value.replace(accented, plain)
    return value


def split_string(input_string):
    if not input_string:
        return None
    input_string = input_string.strip()
    if "_" not in input_string:
        return None

    country, rest = input_string.split("_", 1)
    nazione = nazioni.get(country.lower())
    if not nazione:
        return None

    # Usa SOLO "_" come separatore di livello gerarchico
    # Il "-" rimane parte del nome (es. San-Mauro-Pascoli)
    if "_" not in rest:
        # Caso semplice: ita_Bellaria, ita_San-Mauro-Pascoli
        return f"{nazione}/{rest}"
    else:
        # Caso multi-livello: ita_Network_Vega66, ita_Sistemi_Nas
        levels = rest.split("_")
        return "/".join([nazione] + levels)


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
        sev_type = custom_fields.get("severity_type", None)

        if sev_type is not None:
            if isinstance(sev_type, list) and len(sev_type) > 0:
                sev_type = int(sev_type[0])  # Prendi il primo elemento della lista
            else:
                sev_type = int(sev_type)
        else:
            sev_type = 'none'

        net_layer = custom_fields.get("net_layer", "N/A")
        snmp = custom_fields.get("snmp", "N/A")

        # Legge la SNMP community specifica del device da NetBox
        snmp_community = custom_fields.get("snmp_community_device")

        if isinstance(snmp_community, list):
            snmp_community = snmp_community[0] if len(snmp_community) > 0 else None
        if not snmp_community:
            snmp_community = "Non presente"

        logger.info(
            f"Device {device.get('name')} - SNMP community: {snmp_community}"
        )

        # Nome del device "parent" salvato su NetBox (custom field testuale parent_device)
        parent_device = custom_fields.get("parent_device") or None

        agent_type = custom_fields.get("agent_type")

        if isinstance(agent_type, dict):
            agent_type = agent_type.get("value")

        if all(x not in ["N/A", None] for x in [out_of_band_ip, device_role, tenant, location, site, platform,
                                                snmp]) and device_role != "ap_mgmt" and status == "active":
            loc_path = split_string(location)

            if not loc_path:
                logger.warning(
                    f"Skipping device {device['name']} "
                    f"because location '{location}' cannot be parsed"
                )
                continue

            path = f"/{tenant_name}/{loc_path}"

            device_info = {
                "Device Name": normalize_it_accents(device["name"].replace("/", "_")),
                "Out-of-Band IP": out_of_band_ip,
                "Net Type (Device Role)": device_role,
                "Stato": status,
                "Tenant": normalize_it_accents(tenant_name),
                "Location": normalize_it_accents(location),
                "Site": site,
                "Platform": platform,
                "Net Layer": net_layer,
                "SNMP": snmp if snmp != "N/A" else "Non presente",
                "SNMP Community": snmp_community if snmp_community != "N/A" else "Non presente",
                "Severity Type": sev_type,
                "Path": path,  # Aggiunge il percorso al dizionario
                "Parent Device": parent_device,
                "agent_type": agent_type,
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
                        "Path": device["Path"],
                        "ipv4 address": device['Out-of-Band IP'],
                        "snmp_community": device['SNMP Community'],
                        "snmp": "no-snmp" if not device['SNMP'] else "snmp-v2",
                        "site": device['Site'],
                        "layer_of_the_switch": device['Net Layer'],
                        "type_of_network_device": device['Net Type (Device Role)'],
                        "type_of_server": "none",
                        "severity_type": device['Severity Type'],
                        "agent": device.get("agent_type")
                    }
                    host_to_post.append(host_info)
    return host_to_post


def mapping(entry):
    """
    entry arriva da check_host() e DEVE contenere:
    - Path
    - hostname
    - ipv4 address
    - snmp_community
    - snmp
    - site
    - layer_of_the_switch
    - type_of_network_device
    - type_of_server
    - severity_type

    NOTA: qui NON viene impostato l'attributo "parents". Il campo Parent Device
    viene applicato in un secondo momento (funzione build_parent_updates +
    cmk.update_hosts_bulk), quando è garantito che l'eventuale host parent
    esista già su CheckMK.
    """

    hostname_object = {
        "folder": entry["Path"],
        "host_name": entry["hostname"],
        "attributes": {
            "ipaddress": entry["ipv4 address"].split("/")[0],
            "tag_snmp_ds": entry["snmp"].lower(),
            "site": entry["site"].lower(),
            "tag_nettype": entry["type_of_network_device"].lower(),
            "tag_servertype": entry["type_of_server"].lower(),
            "tag_severitytype": str(entry["severity_type"]),
        }
    }
    if entry.get("agent"):
        hostname_object["attributes"]["tag_agent"] = entry["agent"]

    # SNMP community (solo se presente)
    if entry["snmp_community"] != "Non presente":
        hostname_object["attributes"]["snmp_community"] = {
            "type": "v1_v2_community",
            "community": entry["snmp_community"]
        }

    # Net layer (stringa o lista)
    if isinstance(entry["layer_of_the_switch"], str):
        hostname_object["attributes"]["tag_netlayer"] = entry["layer_of_the_switch"].lower()
    elif isinstance(entry["layer_of_the_switch"], list) and entry["layer_of_the_switch"]:
        hostname_object["attributes"]["tag_netlayer"] = entry["layer_of_the_switch"][0].lower()

    return hostname_object


def build_parent_updates(valid_netbox_devices, known_hostnames):
    """
    Costruisce la lista di entries per cmk.update_hosts_bulk(), una per ogni
    device NetBox che ha un "Parent Device" valorizzato. Il campo "Parent Device"
    può contenere PIÙ nomi separati da virgola (es. "SW-CORE01_SMP, SW-CORE02_SMP"):
    ognuno viene validato singolarmente contro gli host CheckMK conosciuti
    (known_hostnames). I parent non (ancora) presenti su CheckMK vengono
    scartati singolarmente e loggati come warning, senza bloccare gli altri
    parent validi dello stesso host.
    """
    entries = []
    for device in valid_netbox_devices:
        host_name = device["Device Name"]
        raw_parents = device.get("Parent Device")

        if not raw_parents:
            continue

        if host_name not in known_hostnames:
            # l'host stesso non è (ancora) su CheckMK, niente da aggiornare
            continue

        # split su virgola per gestire più parent nello stesso campo Excel
        candidate_parents = [p.strip() for p in raw_parents.split(",") if p.strip()]

        valid_parents = []
        for parent_name in candidate_parents:
            if parent_name == host_name:
                logger.warning(f"host '{host_name}' ha se stesso come parent: skip")
                continue
            if parent_name not in known_hostnames:
                logger.warning(
                    f"host '{host_name}' ha come parent '{parent_name}', "
                    f"ma quest'ultimo non risulta (ancora) presente su CheckMK: skip"
                )
                continue
            valid_parents.append(parent_name)

        if not valid_parents:
            continue

        entries.append({
            "host_name": host_name,
            # NOTA: "update_attributes" fa un merge sugli attributi esistenti
            # dell'host. La chiave "attributes" invece li SOSTITUISCE per
            # intero: usarla qui cancellerebbe ip, snmp, net layer, ecc.
            "update_attributes": {
                "parents": valid_parents
            }
        })

    return entries


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

        sev_type = effective_attributes.get("tag_severitytype", 'N/A')

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
            "tag_severitytype": sev_type,
            "agent": agent
        }
        result.append(host_attributes)
    return result


def main():
    if len(sys.argv) == 2:
        tenants_filter = [t.lower() for t in sys.argv[1].split(",")]
        logger.info(f"only devices of tenants {tenants_filter} will be imported")

    else:
        tenants_filter = []
    nbox = YNetbox(**conf['netbox'])
    cmk = YCheckMK(**conf['checkmk'])

    # filtro VSS tenants
    all_tenants = nbox.get_tenants()
    vss_tenants = [t['name'] for t in all_tenants['results'] if t.get('custom_fields', {}).get('monitoring', True) is False]

    for tenant in vss_tenants:
        if tenant.lower() in tenants_filter:
            logger.warning(f"skipping tenant {tenant['name'].lower()} because it has monitoring disabled")

    # region folder
    raw_location = nbox.get_locations()

    if tenants_filter:
        raw_location['results'] = [l for l in raw_location['results'] if l['tenant']['name'].lower() in tenants_filter]

    raw_location['results'] = [l for l in raw_location['results'] if l['tenant']['name'] not in vss_tenants]

    # Stampa la lista di oggetti contenenti le informazioni
    device_info_list = extract_information(raw_location)

    all_paths = dict()
    seen_tenants = []

    # Stampa la lista di oggetti contenenti le informazioni
    for device_info in device_info_list:
        tenant = device_info["tenants"]
        folder = device_info["names"]
        split_result = split_string(folder)
        if split_result is not None and '/' in split_result:
            path = "/" + tenant + "/" + split_result
            all_paths[path] = device_info['snmp_communities_location']

    for device_info in device_info_list:
        tenant = device_info["tenants"]
        if tenant not in seen_tenants:
            seen_tenants.append(tenant)

    logger.info(f"folders to be created based on netbox data: {all_paths}")

    for data, snmp_data in all_paths.items():
        try:
            # data = "/Veronesi/Italia/Bes"
            # data = "/CRD/Italia/Network/Vega66"

            levels = [p for p in data.split("/") if p]
            # ["Veronesi", "Italia", "Bes"]
            # ["CRD", "Italia", "Network", "Vega66"]

            parent = "/"
            for idx, level in enumerate(levels):
                folder_obj = {
                    "name": level,
                    "title": level,
                    "parent": parent
                }

                # SNMP solo sull'ULTIMO livello
                if idx == len(levels) - 1 and snmp_data:
                    folder_obj["attributes"] = {
                        "snmp_community": {
                            "type": "v1_v2_community",
                            "community": str(snmp_data)
                        },
                        "tag_snmp_ds": "snmp-v2"
                    }

                try:
                    cmk.create_folder(folder_obj)
                    logger.info(f"created folder {parent}/{level}")
                except requests.HTTPError as he:
                    if he.response.status_code == 400 and "already exists" in he.response.text:
                        logger.info(f"folder {parent}/{level} already exists")
                    else:
                        raise

                parent = f"{parent}/{level}".replace("//", "/")

        except Exception as e:
            logger.exception(f"error handling {data}: {e}")

    # endregion

    # region devices
    raw_netbox_devices = nbox.get_devices()
    if tenants_filter:
        raw_netbox_devices['results'] = [d for d in raw_netbox_devices['results'] if d and d.get('tenant', {}) and d.get('tenant', {}).get('name', '').lower() in tenants_filter]

    raw_netbox_devices['results'] = [d for d in raw_netbox_devices['results'] if d and d.get('tenant', {}) and d.get('tenant', {}).get('name', '') not in vss_tenants]

    valid_netbox_devices = process_devices(raw_netbox_devices)
    logger.debug(f"valid netbox devices are: {[d['Device Name'] for d in valid_netbox_devices]}")

    raw_checkmk_hosts = cmk.get_hosts()
    logger.debug(f"valid netbox devices are: {[d['id'] for d in raw_checkmk_hosts['value']]}")

    netbox_check_mk_diff = check_host(valid_netbox_devices, fetch_checkmk_data(raw_checkmk_hosts))
    logger.debug(f"netbox host not in checkmk: {json.dumps(netbox_check_mk_diff)}")

    unique_json_objects = [mapping(h) for h in netbox_check_mk_diff]
    logger.info(f"host that will be created: {json.dumps(unique_json_objects)}")

    successfully_created_hosts = []

    for host in unique_json_objects:
        try:
            cmk.create_host(host)
            successfully_created_hosts.append(host['host_name'])
        except Exception as e:
            logger.exception(f"error {e} on {host}")

    logging.info(f"successfully created {len(successfully_created_hosts)} hosts on checkmk")

    bulk_data = {
        "hostnames": successfully_created_hosts,
        "options": {
            "monitor_undecided_services": True,
            "remove_vanished_services": True,
            "update_service_labels": True,
            "update_service_parameters": True,
            "update_host_labels": True
        },
        "do_full_scan": True,
        "bulk_size": 10,
        "ignore_errors": True
    }
    if successfully_created_hosts:
        cmk.start_bulk_discovery(bulk_data)
        logger.info(f"started bulk check discovery for: {successfully_created_hosts}")
    else:
        logger.info(f"bulk check discovery will not be started as no new host has been created")

    # endregion

    # region parents
    # A questo punto tutti gli host validi di NetBox esistono già su CheckMK
    # (quelli pre-esistenti + quelli appena creati sopra). Ricalcoliamo quindi
    # l'elenco completo degli hostname noti a CheckMK e applichiamo il campo
    # "parents" a tutti i device NetBox che hanno un Parent Device valorizzato.
    refreshed_checkmk_hosts = cmk.get_hosts()
    known_hostnames = {item['id'] for item in refreshed_checkmk_hosts['value']}

    parent_updates = build_parent_updates(valid_netbox_devices, known_hostnames)

    if parent_updates:
        try:
            cmk.update_hosts_bulk(parent_updates)
            logger.info(
                f"aggiornato il campo 'parents' su {len(parent_updates)} host: "
                f"{[e['host_name'] + '->' + ','.join(e['update_attributes']['parents']) for e in parent_updates]}"
            )
        except Exception as e:
            logger.exception(f"errore durante l'aggiornamento bulk dei parents: {e}")
    else:
        logger.info("nessun aggiornamento di 'parents' da applicare in questo run")
    # endregion


if __name__ == "__main__":
    main()
