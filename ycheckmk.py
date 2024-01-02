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
            raw_res.raise_for_status()

            if raw_res.status_code != 204:
                return raw_res.json()

        except Exception as e:
            #self.logger.exception(f"Error on {method} {url} request with {kwargs}, details: {e}")
            raise
        return True

    def get(self, url, params=None, **kwargs):
        return self._request("GET", url=url, params=params, **kwargs)

    def post(self, url, json, **kwargs):
        return self._request("POST", url=url, json=json, **kwargs)

    def create_folder(self, folder_data):
        return self.post("/check_mk/api/1.0/domain-types/folder_config/collections/all", json=folder_data)

    def create_host(self, host_data):
        return self.post("/check_mk/api/1.0/domain-types/host_config/collections/all", json=host_data,
                         params={'bake_agent': True})

    def get_hosts(self):
        return self.get(f"/check_mk/api/1.0/domain-types/host_config/collections/all",
                        params={'effective_attributes': True})

    def start_bulk_discovery(self, bulk_data):
        return self.post(f"/check_mk/api/1.0/domain-types/discovery_run/actions/bulk-discovery-start/invoke",
                         json=bulk_data)

    def get_bulk_discovery_status(self):
        return self.get(f"/check_mk/api/1.0/objects/discovery_run/bulk_discovery")
