# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2014 Intel Corporation, All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging
import json

from django.http import HttpResponse
from django.views.generic import TemplateView
from vsm_dashboard.api import vsm as vsmapi

LOG = logging.getLogger(__name__)

class IndexView(TemplateView):
    template_name = 'vsm/settings/index.html'
    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)
        settings = [{
            'name': "storage_group_near_full_threshold",
            'value': 80,
            }]
        settings = vsmapi.get_settings(self.request)
        for setting in settings:
            setting.verbose_name = setting.name.upper()
        context['settings'] = [x for x in settings if
                               x.verbose_name in ("STORAGE_GROUP_NEAR_FULL_THRESHOLD",
                                                  "STORAGE_GROUP_FULL_THRESHOLD","DISK_NEAR_FULL_THRESHOLD","DISK_FULL_THRESHOLD",'CPU_DIAMOND_COLLECT_INTERVAL','CEPH_DIAMOND_COLLECT_INTERVAL','KEEP_PERFORMANCE_DATA_DAYS')]
        return context

def SettingsAction(request, action):
    data = json.loads(request.body)
    # TODO add cluster_id in data
    if not len(data):
        status = "error"
        msg = "No server selected"
    else:
        if action == "update":
            #vsmapi.add_servers(request, data)
            try:
                setting_value = int(data['keyValue'])
                if 0 < setting_value < 21600 or setting_value==0:
                    vsmapi.update_setting(request, data['keyName'], data['keyValue'])
                    status = "success"
                    msg = "Update Success"
                else:
                    status = "failed"
                    msg = "Update Failed"
            except:
                status = 'failed'
                msg = "Update Failed"
        else:
            LOG.error("error in server action %s" % data)
            status = "error"
            msg = "Invalid params"

    resp = dict(message=msg, status=status, data="")
    resp = json.dumps(resp)
    return HttpResponse(resp)

