# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
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

import webob

from vsm.api import extensions
from vsm.api.openstack import wsgi
from vsm.api import xmlutil
from vsm import db
from vsm import exception
from vsm import quota

QUOTAS = quota.QUOTAS

authorize = extensions.extension_authorizer('storage', 'quota_classes')

class QuotaClassTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('quota_class_set',
                                       selector='quota_class_set')
        root.set('id')

        for resource in QUOTAS.resources:
            elem = xmlutil.SubTemplateElement(root, resource)
            elem.text = resource

        return xmlutil.MasterTemplate(root, 1)

class QuotaClassSetsController(object):

    def _format_quota_set(self, quota_class, quota_set):
        """Convert the quota object to a result dict"""

        result = dict(id=str(quota_class))

        for resource in QUOTAS.resources:
            result[resource] = quota_set[resource]

        return dict(quota_class_set=result)

    @wsgi.serializers(xml=QuotaClassTemplate)
    def show(self, req, id):
        context = req.environ['vsm.context']
        authorize(context)
        try:
            db.sqlalchemy.api.authorize_quota_class_context(context, id)
        except exception.NotAuthorized:
            raise webob.exc.HTTPForbidden()

        return self._format_quota_set(id,
                                      QUOTAS.get_class_quotas(context, id))

    @wsgi.serializers(xml=QuotaClassTemplate)
    def update(self, req, id, body):
        context = req.environ['vsm.context']
        authorize(context)
        quota_class = id
        for key in body['quota_class_set'].keys():
            if key in QUOTAS:
                value = int(body['quota_class_set'][key])
                try:
                    db.quota_class_update(context, quota_class, key, value)
                except exception.QuotaClassNotFound:
                    db.quota_class_create(context, quota_class, key, value)
                except exception.AdminRequired:
                    raise webob.exc.HTTPForbidden()
        return {'quota_class_set': QUOTAS.get_class_quotas(context,
                                                           quota_class)}

class Quota_classes(extensions.ExtensionDescriptor):
    """Quota classes management support"""

    name = "QuotaClasses"
    alias = "os-quota-class-sets"
    namespace = ("http://docs.openstack.org/storage/ext/"
                 "quota-classes-sets/api/v1.1")
    updated = "2012-03-12T00:00:00+00:00"

    def get_resources(self):
        resources = []

        res = extensions.ResourceExtension('os-quota-class-sets',
                                           QuotaClassSetsController())
        resources.append(res)

        return resources
