import requests
import logging
import urllib3

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
            if kwargs.get("full_url", False) is False:
                raw_res = requests.request(method=method,
                                           url=f"{self.base_url}{url}",
                                           headers=self.headers,
                                           timeout=timeout,
                                           verify=False, **kwargs)
            else:
                kwargs.pop("full_url")
                raw_res = requests.request(method=method,
                                           url=url,
                                           headers=self.headers,
                                           timeout=timeout,
                                           verify=False, **kwargs)
            raw_res.raise_for_status()

            if raw_res.status_code != 204:
                return raw_res.json()

        except Exception as e:
            self.logger.exception(f"Error on {method} {url} request with {kwargs}, details: {e}")
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

    def get_locations(self):
        LIMIT = 999
        res = self.get("/dcim/locations", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res

    def get_devices(self):
        LIMIT = 999
        res = self.get("/dcim/devices", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res

    def get_tenants(self):
        LIMIT = 999
        res = self.get("/tenancy/tenants", params={"limit": LIMIT})
        while res['next'] is not None:
            res_tmp = self.get(url=res['next'], full_url=True)
            res['results'] += res_tmp['results']
            res['next'] = res_tmp['next']
        return res

    def create_tenant(self, name, description="", comments=""):
        tenant_data = {
            "name": name,
            "slug": name.lower(),
            "description": description,
            "comments": comments
        }
        return self.post("/tenancy/tenants/", json=tenant_data)

    def get_sites(self):
        return self.get("/dcim/sites")

    def create_site(self, name, tenant_id):
        tenant_data = {
            "name": name,
            "slug": name.lower(),
            "status": "active",
            "tenant": tenant_id
        }
        return self.post("/dcim/sites/", json=tenant_data)
