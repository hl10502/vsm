# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 Zadara Storage Inc.
# Copyright (c) 2011 OpenStack LLC.
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

"""The storage types extra specs extension"""

import webob

from vsm.api import extensions
from vsm.api.openstack import wsgi
from vsm.api import xmlutil
from vsm import db
from vsm import exception
from vsm.storage import storage_types

authorize = extensions.extension_authorizer('storage', 'types_extra_specs')

class HardwareTypeExtraSpecsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.make_flat_dict('extra_specs', selector='extra_specs')
        return xmlutil.MasterTemplate(root, 1)

class HardwareTypeExtraSpecTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        tagname = xmlutil.Selector('key')

        def extraspec_sel(obj, do_raise=False):
            # Have to extract the key and value for later use...
            key, value = obj.items()[0]
            return dict(key=key, value=value)

        root = xmlutil.TemplateElement(tagname, selector=extraspec_sel)
        root.text = 'value'
        return xmlutil.MasterTemplate(root, 1)

class HardwareTypeExtraSpecsController(wsgi.Controller):
    """ The storage type extra specs API controller for the OpenStack API """

    def _get_extra_specs(self, context, type_id):
        extra_specs = db.storage_type_extra_specs_get(context, type_id)
        specs_dict = {}
        for key, value in extra_specs.iteritems():
            specs_dict[key] = value
        return dict(extra_specs=specs_dict)

    def _check_type(self, context, type_id):
        try:
            storage_types.get_storage_type(context, type_id)
        except exception.NotFound as ex:
            raise webob.exc.HTTPNotFound(explanation=unicode(ex))

    @wsgi.serializers(xml=HardwareTypeExtraSpecsTemplate)
    def index(self, req, type_id):
        """ Returns the list of extra specs for a given storage type """
        context = req.environ['vsm.context']
        authorize(context)
        self._check_type(context, type_id)
        return self._get_extra_specs(context, type_id)

    @wsgi.serializers(xml=HardwareTypeExtraSpecsTemplate)
    def create(self, req, type_id, body=None):
        context = req.environ['vsm.context']
        authorize(context)

        if not self.is_valid_body(body, 'extra_specs'):
            raise webob.exc.HTTPBadRequest()

        self._check_type(context, type_id)

        specs = body['extra_specs']
        db.storage_type_extra_specs_update_or_create(context,
                                                    type_id,
                                                    specs)
        return body

    @wsgi.serializers(xml=HardwareTypeExtraSpecTemplate)
    def update(self, req, type_id, id, body=None):
        context = req.environ['vsm.context']
        authorize(context)
        if not body:
            expl = _('Request body empty')
            raise webob.exc.HTTPBadRequest(explanation=expl)
        self._check_type(context, type_id)
        if id not in body:
            expl = _('Request body and URI mismatch')
            raise webob.exc.HTTPBadRequest(explanation=expl)
        if len(body) > 1:
            expl = _('Request body contains too many items')
            raise webob.exc.HTTPBadRequest(explanation=expl)
        db.storage_type_extra_specs_update_or_create(context,
                                                    type_id,
                                                    body)
        return body

    @wsgi.serializers(xml=HardwareTypeExtraSpecTemplate)
    def show(self, req, type_id, id):
        """Return a single extra spec item."""
        context = req.environ['vsm.context']
        authorize(context)
        self._check_type(context, type_id)
        specs = self._get_extra_specs(context, type_id)
        if id in specs['extra_specs']:
            return {id: specs['extra_specs'][id]}
        else:
            raise webob.exc.HTTPNotFound()

    def delete(self, req, type_id, id):
        """ Deletes an existing extra spec """
        context = req.environ['vsm.context']
        self._check_type(context, type_id)
        authorize(context)
        db.storage_type_extra_specs_delete(context, type_id, id)
        return webob.Response(status_int=202)

class Types_extra_specs(extensions.ExtensionDescriptor):
    """Types extra specs support"""

    name = "TypesExtraSpecs"
    alias = "os-types-extra-specs"
    namespace = "http://docs.openstack.org/storage/ext/types-extra-specs/api/v1"
    updated = "2011-08-24T00:00:00+00:00"

    def get_resources(self):
        resources = []
        res = extensions.ResourceExtension('extra_specs',
                                           HardwareTypeExtraSpecsController(),
                                           parent=dict(member_name='type',
                                                       collection_name='types')
                                           )
        resources.append(res)

        return resources
