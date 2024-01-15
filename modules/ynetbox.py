import requests
import logging
import urllib3
import pandas

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class YNetbox(object):
    def __init__(self, ip, token):
        self.logger = logging.getLogger(__name__)
        self.base_url = f'https://{ip}/api'
        self.headers = {'Accept': 'application/json',
                        'Content-Type': 'application/json',
                        'Authorization': f"Token {token}"}

    def _request(self, method, url, timeout=10, **kwargs):
        try:
            self.logger.debug(f"{method} {url} request with {kwargs}")
            raw_res = requests.request(method=method,
                                       url=f"{self.base_url}{url}",
                                       headers=self.headers,
                                       timeout=timeout,
                                       verify=False, **kwargs)

            # print(raw_res.text)
            raw_res.raise_for_status()

            if raw_res.status_code != 204:
                return raw_res.json()

        except requests.HTTPError as he:
            if ((he.response.status_code != 400 or "already exists" not in he.response.text)
                    and not "dcim_device_unique_name_site_tenant" in he.response.text
                    and not "Duplicate IP address" in he.response.text and not "Related object not found using the provided attributes" in he.response.text):
                self.logger.exception(f"Error on {method} {url} request with {kwargs}, details: {he} {he.response.text}")
            raise
        except Exception as e:
            self.logger.exception(
                f"Error on {method} {url} request with {kwargs}, details: {e}")
            raise
        return True

    def get(self, url, params=None, **kwargs):
        return self._request("GET", url=url, params=params, **kwargs)

    def post(self, url, json, **kwargs):
        return self._request("POST", url=url, json=json, **kwargs)

    def patch(self, url, json, **kwargs):
        return self._request("PATCH", url=url, json=json, **kwargs)

    def put(self, url, json, **kwargs):
        return self._request("PUT", url=url, json=json, **kwargs)

    # GET FUNCTIONS

    def get_tenants(self):
        LIMIT = 999
        res = self.get("/tenancy/tenants", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res['results']

    def get_sites(self):
        LIMIT = 999
        res = self.get("/dcim/sites", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res['results']

    def get_locations(self):
        LIMIT = 999
        res = self.get("/dcim/locations", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res['results']

    def get_devices(self):
        LIMIT = 999
        res = self.get("/dcim/devices", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res['results']

    def get_manufacturers(self):
        return self.get("/dcim/manufacturers")

    def get_devices_type(self):
        LIMIT = 999
        res = self.get("/dcim/device-types", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res['results']

    def get_devices_roles(self):
        return self.get("/dcim/device-roles")['results']

    def get_devices_net_layer(self):
        return self.get("/extras/custom-field-choice-sets/2/choices")['results']

    def get_devices_connection_type(self):
        return self.get("/extras/custom-field-choice-sets/1/choices")['results']

    def get_interfaces(self):
        LIMIT = 999
        res = self.get("/dcim/interfaces", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res['results']

    def get_platforms(self):
        return self.get("/dcim/platforms")['results']

    def get_IPs_address(self):
        LIMIT = 999
        res = self.get("/ipam/ip-addresses", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res['results']

    def get_virtual_chassis(self):
        LIMIT = 999
        res = self.get("/dcim/virtual-chassis", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res['results']

    # POST FUNCTIONS - Creazione Oggetti

    def create_tenant(self, name, description="", comments=""):
        tenant_data = {
            "name": name,
            "slug": name.lower(),
            "description": description,
            "comments": comments
        }
        return self.post("/tenancy/tenants/", json=tenant_data)

    def create_site(self, name, tenant_id):
        site_data = {
            "name": name,
            "slug": name.lower(),
            "status": "active",
            "tenant": tenant_id
        }
        return self.post("/dcim/sites/", json=site_data)

    def create_loction(self, name, site_id, tenant_id, snmp_community_location):
        location_data = {
            "name": name,
            "slug": name.lower(),
            "site": site_id,
            "status": "active",
            "tenant": tenant_id,
            "custom_fields": {
                "snmp_community_location": snmp_community_location
            }
        }
        return self.post("/dcim/locations/", json=location_data)

    def create_device(self, name, device_id, role_id, tenant_id, platform_id, serial_number, site_id, location_id,
                      conn_id, snmp_com_device, net_layer_id, data_fine, data_inizio, rma, sla):
        device_data = {
            "name": name,
            "device_type": device_id,
            "role": role_id,
            "tenant": tenant_id,
            "platform": platform_id,
            "serial": serial_number if not pandas.isna(serial_number) else "",  # string
            "site": site_id,
            "location": location_id,
            "status": "active",
            "custom_fields": {
                "conn_type": [conn_id] if conn_id else None,
                "snmp": True,
                "snmp_community_device": snmp_com_device,
                "net_layer": [net_layer_id] if net_layer_id else None,
                "end_contract": data_fine,
                "start_contract": data_inizio,
                "rma": [rma] if (rma and not pandas.isna(rma)) else None,
                "sla": [sla] if (sla and not pandas.isna(sla)) else None
            }}
        return self.post("/dcim/devices/", json=device_data)

    def create_manufacturer(self, name, dominio_description):
        manufactures_data = {
            "name": name,
            "slug": name.lower(),
            "description": dominio_description
        }
        return self.post("/dcim/manufacturers/", json=manufactures_data)

    def create_device_type(self, manufacturers_id, name_new_device):
        device_type_data = {
            "manufacturer": manufacturers_id,  # id assegnato ai vendor censiti
            "model": name_new_device,
            "slug": name_new_device.lower()
        }
        return self.post("/dcim/device-types/", json=device_type_data)

    def create_interface(self, device_id, name):
        name = f"{name} - MGMT"
        interface_data = {
            "device": device_id,
            "name": name,
            "type": "virtual",
            "mgmt_only": True
        }
        return self.post("/dcim/interfaces/", json=interface_data)

    def create_virtual_chassis(self, name, id_master):
        vc_data = {
            "name": name,
            "domain": " ",
            "master": id_master,
            "description": " ",
            "comments": " "
        }
        return self.post("/dcim/virtual-chassis/", json=vc_data)

    def create_ip_address(self, address, tenant_id, interface_id):
        address = f"{address}/32"
        data_ip_addr = {
            "address": address,
            "tenant": tenant_id,
            "status": "active",
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": interface_id
        }
        return self.post("/ipam/ip-addresses/", json=data_ip_addr)

    # PATCH FUNCTIONS -UPDATE- [ATTENZIONE I DATA SONO UN TYPE LIST]

    def update_tenant(self, tenant_id, name, description="", comments=""):
        tenant_data = [
            {
                "id": tenant_id,
                "name": name,
                "slug": name.lower(),
                "description": description,
                "comments": comments
            }
        ]
        return self.patch("/tenancy/tenants/", json=tenant_data)

    def update_site(self, site_id, name, tenant_id):
        site_data = [
            {
                "id": site_id,
                "name": name,
                "slug": name.lower(),
                "status": "active",
                "tenant": tenant_id
            }
        ]
        return self.patch("/dcim/sites/")

    def update_location(self, location_id, name, site_id, tenant_id, snmp_community_location):
        location_data = [
            {
                "id": location_id,
                "name": name,
                "slug": name.lower(),
                "site": site_id,
                "status": "active",
                "tenant": tenant_id,
                "custom_fields": {
                    "snmp_community_location": snmp_community_location
                }
            }
        ]
        return self.patch("/dcim/locations/", json=location_data)

    def update_device_with_IP(self, id_device, id_address):
        device_data = [
            {
                "id": id_device,
                "primary_ip4": {
                    "id": id_address
                }
            }
        ]
        return self.patch("/dcim/devices/", json=device_data)

    def update_virtual_chassis(self, id_device_to_add, id_VC, position):
        device_data = [
            {
                "id": id_device_to_add,
                "virtual_chassis": id_VC,
                "vc_position": position
            }
        ]
        return self.patch("/dcim/devices/", json=device_data)

    def update_device(self, device_id, name, device_type_id, role_id, tenant_id, platform_id, serial_number, site_id,
                      location_id, conn_id, snmp_com_device, net_layer_id, data_fine, data_inizio, rma, sla):
        device_data = [
            {
                "id": device_id,
                "name": name,
                "device_type": device_type_id,
                "role": role_id,
                "tenant": tenant_id,
                "platform": platform_id,
                "serial": serial_number,  # string
                "site": site_id,
                "location": location_id,
                "status": "active",
                "custom_fields": {
                    "conn_type": [conn_id],
                    "snmp": True,
                    "snmp_community_device": snmp_com_device,
                    "net_layer": [net_layer_id],
                    "end_contract": data_fine,
                    "start_contract": data_inizio,
                    "rma": [rma],
                    "sla": [sla]
                }
            }
        ]
        return self.patch("/dcim/devices/", json=device_data)

    def update_manufacturer(self, manufacturers_id, name, dominio_description):
        manufactures_data = [
            {
                "id": manufacturers_id,
                "name": name,
                "slug": name.lower(),
                "description": dominio_description
            }
        ]
        return self.patch("/dcim/manufactures/", json=manufactures_data)

    def update_device_type(self, device_type_id, manufacturers_id, name_new_device):
        device_type_data = [
            {
                "id": device_type_id,
                "manufacturer": manufacturers_id,
                "model": name_new_device,
                "slug": name_new_device.lower()
            }
        ]
        return self.patch("dcim/device-types/", json=device_type_data)

    def update_interface(self, interfcae_id, device_id, name):
        interface_data = [
            {
                "id": interfcae_id,
                "device": device_id,
                "name": name,
                "type": "virtual",
                "mgmt_only": True
            }
        ]
        return self.patch("/dcim/interfaces/", json=interface_data)

    def update_ip_address(self, address_id, address, tenant_id, interface_id):
        data_ip_addr = [
            {
                "id": address_id,
                "address": address,
                "tenant": tenant_id,
                "status": "active",
                "assigned_object_type": "dcim.interface",
                "assigned_object_id": interface_id
            }
        ]
        return self.patch("/ipam/ip-addresses/", json=data_ip_addr)
