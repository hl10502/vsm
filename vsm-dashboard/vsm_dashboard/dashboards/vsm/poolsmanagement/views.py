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
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse_lazy, reverse
from django.views.generic import TemplateView

from horizon import exceptions
from horizon import tables
from horizon import forms

from vsm_dashboard.api import vsm as vsmapi
from .form import CreateErasureCodedPool, RenamePoolForm
from .form import RemoveCacheTier
from .tables import ListPoolTable

from vsm_dashboard.api import vsm as vsmapi
import json
from django.http import HttpResponse

LOG = logging.getLogger(__name__)

class IndexView(tables.DataTableView):
    table_class = ListPoolTable
    template_name = 'vsm/poolsmanagement/index.html'

    def get_data(self):
        pools = []

        try:
            rsp, body = vsmapi.pools_list(self.request, all_pools=True)
            if body:
                pools = body["pool"]
            logging.debug("resp body in view: %s" % pools)
        except:
            exceptions.handle(self.request,
                              _('Unable to retrieve storage pool list. '))
        pools = sorted(pools, lambda x,y: cmp(x['poolId'], y['poolId']))
        #pools = [pool for pool in pools if pool['tag'] != "SYSTEM"]
        return pools

class CreateView(TemplateView):
    template_name = 'vsm/poolsmanagement/create_replicated_pool.html'
    success_url = reverse_lazy('horizon:vsm:poolsmanagement:index')
    def get_context_data(self, **kwargs):
        context = super(CreateView, self).get_context_data(**kwargs)
        context["sg_list"] = []
        return context

class RenameView(forms.ModalFormView):
    form_class = RenamePoolForm
    template_name = 'vsm/poolsmanagement/rename_pool.html'
    success_url = reverse_lazy('horizon:vsm:poolsmanagement:index')
    def get_context_data(self, **kwargs):
        context = super(RenameView, self).get_context_data(**kwargs)
        context["poolId"] = self.kwargs['poolId']
        pool_ref = vsmapi.storage_pool1(None, self.kwargs['poolId'])
        context["poolName"] = pool_ref[1]['pool']['name']
        return context

class CreateErasureCodedPoolView(forms.ModalFormView):
    form_class = CreateErasureCodedPool
    template_name = 'vsm/poolsmanagement/create_erasure_coded_pool.html'
    success_url = reverse_lazy('horizon:vsm:poolsmanagement:index')

class AddCacheTierView(TemplateView):
    template_name = 'vsm/poolsmanagement/add_cache_tier.html'
    success_url = reverse_lazy('horizon:vsm:poolsmanagement:index')
    def get_context_data(self, **kwargs):
        context = super(AddCacheTierView, self).get_context_data(**kwargs)
        #get pool list
        pools = vsmapi.pool_status(None)
        context["pool_list"] = [(pool.pool_id, pool.name) for pool in pools if not pool.cache_tier_status]
        context["cache_mode_list"] = [('writeback', "Writeback"), ('readonly', "Read-only")]
        context["hit_set_type_list"] = [('bloom', "bloom")]
        #get the settings
        setting_list = vsmapi.get_settings(None)
        context["settings"] = dict([(setting.name, setting.value) for setting in setting_list])
        return context


class RemoveCacheTierView(forms.ModalFormView):
    form_class = RemoveCacheTier
    template_name = 'vsm/poolsmanagement/remove_cache_tier.html'
    success_url = reverse_lazy('horizon:vsm:poolsmanagement:index')


def add_cache_tier(request):
    status = ""
    msg = ""
    body = json.loads(request.body)

    try:
        ret = vsmapi.add_cache_tier(request,body=body)
        status = "OK"
        msg = "Add Cache Tier Successfully!"
    except:
        status = "Failed"
        msg = "Add Cache Tier Failed!"

    resp = dict(message=msg, status=status)
    resp = json.dumps(resp)
    return HttpResponse(resp)


def remove_cache_tier(request):
    status = ""
    msg = ""
    body = json.loads(request.body)
    try:
        ret = vsmapi.remove_cache_tier(request,body=body)
        status = "OK"
        msg = "Remove Cache Tier Successfully!"
    except:
        status = "Failed"
        msg = "Remove Cache Tier Failed!"

    resp = dict(message=msg, status=status)
    resp = json.dumps(resp)
    return HttpResponse(resp)


def create_replicated_pool(request):
    status = ""
    msg = ""
    body = json.loads(request.body)
    print body
    try:
        rsp, ret = vsmapi.create_storage_pool(request,body=body)
        res = str(ret['message']).strip()
        if res.startswith('pool') and res.endswith('created'):
            status = "OK"
            msg = "Created storage pool successfully!"
    except:
        status = "Failed"
        msg = "Create Replication Pool Failed!"
    resp = dict(message=msg, status=status)
    resp = json.dumps(resp)
    return HttpResponse(resp)

def rename_pool(request):
    status = ""
    msg = ""
    body = json.loads(request.body)
    print body
    try:
        rsp, ret = vsmapi.rename_storage_pool(request,body=body)
        res = str(ret['message']).strip()
        if res.startswith('pool') and res.endswith('renamed'):
            status = "OK"
            msg = "Rename storage pool successfully!"
    except:
        status = "Failed"
        msg = "Rename Pool Failed!"
    resp = dict(message=msg, status=status)
    resp = json.dumps(resp)
    return HttpResponse(resp)

def create_ec_pool(request):
    status = ""
    msg = ""
    body = json.loads(request.body)
    print body

    try:
        rsp, ret = vsmapi.create_storage_pool(request,body=body)
        res = str(ret['message']).strip()
        if res.startswith('pool') and res.endswith('created'):
            status = "OK"
            msg = "Created storage pool successfully!"
    except:
        status = "Failed"
        msg = "Remove Cache Tier Failed!"

    resp = dict(message=msg, status=status)
    resp = json.dumps(resp)
    return HttpResponse(resp)

def get_default_pg_number_storage_group(request):
    storage_group_list = []
    rsp, group_list= vsmapi.get_storage_group_list(request)
    for key in group_list:
        rsp, default_pg_num = vsmapi.get_default_pg_num_by_storage_group(request, \
                                                   {'storage_group_name':group_list[key]})
        if default_pg_num['pg_num_default'] > 0:
            storage_group_list.append((key, group_list[key], default_pg_num['pg_num_default']))
    resp = json.dumps({"storage_group_list":storage_group_list})
    return HttpResponse(resp)