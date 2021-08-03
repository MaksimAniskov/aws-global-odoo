from locust import HttpUser, task, between
import re
import random
import json
import os


class OdooUser:
    if os.environ.get('HOST'):
        host = os.environ.get('HOST')

    wait_time = between(20, 40)

    def on_start(self):
        response = self.client.get("/web/login")
        assert response.status_code == 200
        csrf_token = re.search(
            r'input type="hidden" name="csrf_token" value="(.+)"', response.text).group(1)

        response = self.client.post(
            "/web/login", data={
                "csrf_token": csrf_token,
                "login": os.environ.get('ODOO_USER_NAME'),
                "password": os.environ.get('ODOO_USER_PASSWORD'),
                "redirect": ""
            })
        assert response.status_code == 200

        response = self.client.get("/web")
        assert response.status_code == 200
        session_info = re.search(
            r'odoo.session_info\s*=\s*(.+);', response.text).groups(1)[0]
        session_info = json.loads(session_info)

        self.thecontext = {
            "uid": session_info['uid'],
            "company_id": session_info['company_id'],
            "allowed_company_ids": [session_info['company_id']],
            "lang": session_info['user_context']['lang'],
            "tz": session_info['user_context']['tz']
        }

        response = self.client.get(
            f'/web/webclient/load_menus/${session_info["cache_hashes"]["load_menus"]}')
        assert response.status_code == 200
        response = json.loads(response.content)
        crm_menu = next(
            filter(lambda item: item['name'] == 'CRM', response['children']))
        self.crm_action_id = int(crm_menu['action'].split(',')[1])

        self.call_jsonrpc(
            "/web/dataset/call_kw/res.users/systray_get_activities",
            model="res.users",
            method="systray_get_activities",
            kwargs={"context": self.thecontext},
            args=[]
        )

        response = self.client.get(
            "/web/image?model=res.users", params={'field': 'image_128', 'id': self.thecontext['uid']})
        assert response.status_code == 200

        response = self.call_action(
            "/web/action/run", action_id=self.crm_action_id)
        result = json.loads(response.content)['result']
        self.thecontext.update(result['context'])

    def call_jsonrpc(self, url, **params):
        response = self.client.post(
            url,
            json={
                "id": random.randrange(10000000000),
                "params": {**params},
                "jsonrpc": "2.0", "method": "call"
            }
        )
        assert response.status_code == 200
        response = json.loads(response.content)
        assert 'error' not in response
        return response['result']

    def call_action(self, url, action_id):
        response = self.client.post(
            url,
            json={
                "id": random.randrange(10000000000),
                "params": {
                    "action_id": action_id,
                },
                "jsonrpc": "2.0", "method": "call"
            }
        )
        assert response.status_code == 200
        assert 'error' not in json.loads(response.content)
        return response


class OdooUserCrmKanban(OdooUser, HttpUser):
    @task
    def crm_kanban(self):
        self.call_action("/web/action/run", action_id=self.crm_action_id)

        domain = [
            "&",
            ["type", "=", "opportunity"],
            ["user_id", "=", self.thecontext['uid']]
        ]

        self.call_jsonrpc(
            "/web/dataset/call_kw/crm.lead/read_progress_bar",
            model="crm.lead", method="read_progress_bar",
            kwargs={
                "domain": domain,
                "group_by": "stage_id",
                "progress_bar": {
                    "field": "activity_state",
                    "colors": {
                        "planned": "success",
                        "today": "warning",
                        "overdue": "danger"
                    },
                    "sum_field": "expected_revenue",
                    "modifiers": {}
                }
            },
            args=[]
        )

        result = self.call_jsonrpc(
            "/web/dataset/call_kw/crm.lead/web_read_group",
            model="crm.lead", method="web_read_group",
            kwargs={
                "domain": domain,
                "fields": [
                    "stage_id",
                    "color",
                    "priority",
                    "expected_revenue",
                    "kanban_state",
                    "activity_date_deadline",
                    "user_email",
                    "user_id",
                    "partner_id",
                    "activity_summary",
                    "active",
                    "company_currency",
                    "activity_state",
                    "activity_ids",
                    "name",
                    "tag_ids",
                    "activity_exception_decoration",
                    "activity_exception_icon"
                ],
                "groupby": ["stage_id"],
                "orderby": "",
                "lazy": True
            },
            args=[]
        )

        for group in result['groups']:
            result = self.call_jsonrpc(
                "/web/dataset/search_read",
                model="crm.lead",
                domain=[
                    "&", ["stage_id", "=",  group['stage_id'][0]],
                    "&", ["type", "=", "opportunity"],
                    ["user_id", "=", self.thecontext['uid']]
                ],
                fields=[
                    "stage_id",
                    "color",
                    "priority",
                    "expected_revenue",
                    "kanban_state",
                    "activity_date_deadline",
                    "user_email",
                    "user_id",
                    "partner_id",
                    "activity_summary",
                    "active",
                    "company_currency",
                    "activity_state",
                    "activity_ids",
                    "name",
                    "tag_ids",
                    "activity_exception_decoration",
                    "activity_exception_icon"
                ],
                limit=80,
                sort="",
                context={
                    "bin_size": True
                }
            )

        # TODO: /web/dataset/call_kw/crm.tag/read
        # TODO: /web/dataset/call_kw/crm.stage/read


class OdooUserCrmLeadCreate(OdooUser, HttpUser):
    @task
    def crm_lead_create(self):
        partners = self.call_jsonrpc(
            "/web/dataset/call_kw/res.partner/name_search",
            model="res.partner", method="name_search",
            kwargs={
                "name": "",
                "args": ["|", ["company_id", "=", False], ["company_id", "=", 1]],
                "operator": "ilike",
                "limit": 8
            },
            args=[]
        )

        random_partner_id = random.choice(partners)[0]

        result = self.call_jsonrpc(
            "/web/dataset/call_kw/crm.lead/onchange",
            model="crm.lead", method="onchange",
            kwargs={},
            args=[
                [],
                {
                    "partner_id": random_partner_id,
                    "company_id": self.thecontext['company_id'],
                    "user_id": self.thecontext['uid'],
                    "team_id": self.thecontext['default_team_id'],
                    "name": False,
                    "email_from": False,
                    "phone": False,
                    "expected_revenue": 0,
                    "priority": "0",
                    "company_currency": 1,
                    "type": "opportunity",
                    "partner_name": False,
                    "contact_name": False,
                    "country_id": False,
                    "state_id": False,
                    "city": False,
                    "street": False,
                    "street2": False,
                    "zip": False,
                    "mobile": False,
                    "website": False,
                    "function": False,
                    "title": False
                },
                "partner_id",
                {
                    "partner_id": "1",
                    "name": "",
                    "email_from": "",
                    "phone": "1",
                    "expected_revenue": "",
                    "priority": "",
                    "company_currency": "",
                    "company_id": "1",
                    "user_id": "1",
                    "team_id": "",
                    "type": "1",
                    "partner_name": "",
                    "contact_name": "",
                    "country_id": "1",
                    "state_id": "",
                    "city": "",
                    "street": "",
                    "street2": "",
                    "zip": "1",
                    "mobile": "1",
                    "website": "",
                    "function": "",
                    "title": ""
                }
            ]
        )
        partner = result['value']
        partner['id'] = random_partner_id

        result = self.call_jsonrpc(
            "/web/dataset/call_kw/crm.lead/create",
            model="crm.lead", method="create",
            kwargs={},
            args=[{
                "type": "opportunity",
                "expected_revenue": random.randrange(1000, 1000000, 1000),
                "company_id": self.thecontext['company_id'],
                "user_id": self.thecontext['uid'],
                "team_id": self.thecontext['default_team_id'],
                "priority": "0",
                "partner_id": partner['id'],
                "name": partner.get('name', False),
                "email_from": partner.get('email_from', False),
                "phone": partner.get('phone', False),
                "partner_name": partner.get('partner_name', False),
                "contact_name": partner.get('contact_name', False),
                "country_id": partner['country_id'][0],
                "state_id": partner['state_id'][0],
                "city": partner.get('city', False),
                "street": partner.get('street', False),
                "street2": partner.get('street2', False),
                "zip": partner.get('zip', False),
                "function": partner.get('function', False),
                "title": partner.get('title', False)
            }]
        )
        if result % 100 == 0:
            print('CRM lead id created:', result)


if __name__ == "__main__":
    from locust.env import Environment
    my_env = Environment(user_classes=[OdooUserCrmKanban])
    OdooUserCrmKanban(my_env).run()
