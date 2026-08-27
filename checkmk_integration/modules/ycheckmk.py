import requests
import logging
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class YCheckMK(object):
    def __init__(self, base_url, usr, token):
        self.logger = logging.getLogger(__name__)
        self.base_url = base_url
        self.headers = {'Accept': 'application/json',
                        'Content-Type': 'application/json',
                        'Authorization': f"Bearer {usr} {token}"}

    def _request(self, method, url, timeout=10, **kwargs):
        try:
            self.logger.debug(f"{method} {url} request with {kwargs}")
            raw_res = requests.request(method=method,
                                       url=f"{self.base_url}{url}",
                                       headers=self.headers,
                                       timeout=timeout,
                                       verify=False, **kwargs)
            if not raw_res.ok:
                self.logger.error(f"{method} {url} failed [{raw_res.status_code}]: {raw_res.text}")
            raw_res.raise_for_status()
            if raw_res.status_code != 204:
                return raw_res.json()
        except Exception:
            raise
        return True

    def get(self, url, params=None, **kwargs):
        return self._request("GET", url=url, params=params, **kwargs)

    def post(self, url, json, **kwargs):
        return self._request("POST", url=url, json=json, **kwargs)

    def put(self, url, json, **kwargs):
        return self._request("PUT", url=url, json=json, **kwargs)

    def create_folder(self, folder_data):
        return self.post("/check_mk/api/1.0/domain-types/folder_config/collections/all", json=folder_data)

    def create_host(self, host_data):
        return self.post("/check_mk/api/1.0/domain-types/host_config/collections/all", json=host_data,
                         params={'bake_agent': True})

    def get_hosts(self):
        return self.get("/check_mk/api/1.0/domain-types/host_config/collections/all", params={'effective_attributes': True})

    def start_bulk_discovery(self, bulk_data):
        return self.post("/check_mk/api/1.0/domain-types/discovery_run/actions/bulk-discovery-start/invoke", json=bulk_data)

    def get_bulk_discovery_status(self):
        return self.get("/check_mk/api/1.0/objects/discovery_run/bulk_discovery")

    def update_hosts_bulk(self, entries):
        """
        entries: lista di dict, ognuno del tipo
            {"host_name": "<nome>", "update_attributes": {"parents": ["<nome-parent>"]}}
        IMPORTANTE: usare la chiave "update_attributes" (merge sugli attributi
        esistenti), non "attributes" (che li SOSTITUISCE integralmente e
        cancellerebbe ip, snmp, net layer, ecc. se non ripassati tutti).
        NOTA: l'endpoint bulk-update di CheckMK richiede il metodo PUT (non POST),
        a differenza della creazione host che usa POST. Non richiede header
        If-Match/ETag (a differenza dell'update sul singolo host).
        """
        bulk_data = {"entries": entries}
        return self.put(
            "/check_mk/api/1.0/domain-types/host_config/actions/bulk-update/invoke",
            json=bulk_data
        )
