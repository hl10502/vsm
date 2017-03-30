# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2014 Intel Inc.
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

"""The conductors api."""

import webob
from webob import exc

from vsm.api import common
from vsm.api.openstack import wsgi
from vsm.api import xmlutil
from vsm import exception
from vsm import flags
from vsm.openstack.common import log as logging
from vsm.openstack.common import uuidutils
from vsm import utils
from vsm import conductor

LOG = logging.getLogger(__name__)

FLAGS = flags.FLAGS

def _translate_attachment_detail_view(_context, vol):
    """Maps keys for attachment details view."""

    d = _translate_attachment_summary_view(_context, vol)

    # No additional data / lookups at the moment

    return d

def _translate_attachment_summary_view(_context, vol):
    """Maps keys for attachment summary view."""
    d = {}

    conductor_id = vol['id']

    # NOTE(justinsb): We use the conductor id as the id of the attachment object
    d['id'] = conductor_id

    d['conductor_id'] = conductor_id
    d['server_id'] = vol['instance_uuid']
    if vol.get('mountpoint'):
        d['device'] = vol['mountpoint']

    return d

def _translate_conductor_detail_view(context, vol, image_id=None):
    """Maps keys for conductors details view."""

    d = _translate_conductor_summary_view(context, vol, image_id)

    # No additional data / lookups at the moment

    return d

def _translate_conductor_summary_view(context, vol, image_id=None):
    """Maps keys for conductors summary view."""
    d = {}

    d['id'] = vol['id']
    d['status'] = vol['status']
    d['size'] = vol['size']
    d['availability_zone'] = vol['availability_zone']
    d['created_at'] = vol['created_at']

    d['attachments'] = []
    if vol['attach_status'] == 'attached':
        attachment = _translate_attachment_detail_view(context, vol)
        d['attachments'].append(attachment)

    d['display_name'] = vol['display_name']
    d['display_description'] = vol['display_description']

    if vol['conductor_type_id'] and vol.get('conductor_type'):
        d['conductor_type'] = vol['conductor_type']['name']
    else:
        # TODO(bcwaldon): remove str cast once we use uuids
        d['conductor_type'] = str(vol['conductor_type_id'])

    d['snapshot_id'] = vol['snapshot_id']
    d['source_volid'] = vol['source_volid']

    if image_id:
        d['image_id'] = image_id

    LOG.audit(_("vol=%s"), vol, context=context)

    if vol.get('conductor_metadata'):
        metadata = vol.get('conductor_metadata')
        d['metadata'] = dict((item['key'], item['value']) for item in metadata)
    # avoid circular ref when vol is a Conductor instance
    elif vol.get('metadata') and isinstance(vol.get('metadata'), dict):
        d['metadata'] = vol['metadata']
    else:
        d['metadata'] = {}

    if vol.get('conductor_glance_metadata'):
        d['bootable'] = 'true'
    else:
        d['bootable'] = 'false'

    return d

def make_attachment(elem):
    elem.set('id')
    elem.set('server_id')
    elem.set('conductor_id')
    elem.set('device')

def make_conductor(elem):
    elem.set('id')
    elem.set('status')
    elem.set('size')
    elem.set('availability_zone')
    elem.set('created_at')
    elem.set('display_name')
    elem.set('display_description')
    elem.set('conductor_type')
    elem.set('snapshot_id')
    elem.set('source_volid')

    attachments = xmlutil.SubTemplateElement(elem, 'attachments')
    attachment = xmlutil.SubTemplateElement(attachments, 'attachment',
                                            selector='attachments')
    make_attachment(attachment)

    # Attach metadata node
    elem.append(common.MetadataTemplate())

conductor_nsmap = {None: xmlutil.XMLNS_VOLUME_V1, 'atom': xmlutil.XMLNS_ATOM}

class ConductorTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('conductor', selector='conductor')
        make_conductor(root)
        return xmlutil.MasterTemplate(root, 1, nsmap=conductor_nsmap)

class ConductorsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('conductors')
        elem = xmlutil.SubTemplateElement(root, 'conductor', selector='conductors')
        make_conductor(elem)
        return xmlutil.MasterTemplate(root, 1, nsmap=conductor_nsmap)

class CommonDeserializer(wsgi.MetadataXMLDeserializer):
    """Common deserializer to handle xml-formatted conductor requests.

       Handles standard conductor attributes as well as the optional metadata
       attribute
    """

    metadata_deserializer = common.MetadataXMLDeserializer()

    def _extract_conductor(self, node):
        """Marshal the conductor attribute of a parsed request."""
        conductor = {}
        conductor_node = self.find_first_child_named(node, 'conductor')

        attributes = ['display_name', 'display_description', 'size',
                      'conductor_type', 'availability_zone']
        for attr in attributes:
            if conductor_node.getAttribute(attr):
                conductor[attr] = conductor_node.getAttribute(attr)

        metadata_node = self.find_first_child_named(conductor_node, 'metadata')
        if metadata_node is not None:
            conductor['metadata'] = self.extract_metadata(metadata_node)

        return conductor

class CreateDeserializer(CommonDeserializer):
    """Deserializer to handle xml-formatted create conductor requests.

       Handles standard conductor attributes as well as the optional metadata
       attribute
    """

    def default(self, string):
        """Deserialize an xml-formatted conductor create request."""
        dom = utils.safe_minidom_parse_string(string)
        conductor = self._extract_conductor(dom)
        return {'body': {'conductor': conductor}}

class ConductorController(wsgi.Controller):
    """The Conductors API controller for the OpenStack API."""

    def __init__(self, ext_mgr):
        self.conductor_api = conductor.API()
        self.ext_mgr = ext_mgr
        super(ConductorController, self).__init__()

    def delete(self, req, id):
        """Delete a conductor."""
        context = req.environ['vsm.context']

        LOG.audit(_("Delete conductor with id: %s"), id, context=context)

        try:
            conductor = self.conductor_api.get(context, id)
            self.conductor_api.delete(context, conductor)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        return webob.Response(status_int=202)

    @wsgi.serializers(xml=ConductorsTemplate)
    def index(self, req):
        """Returns a summary list of conductors."""
        LOG.debug(' comes to index')
        return self._items(req, entity_maker=_translate_conductor_summary_view)

    @wsgi.serializers(xml=ConductorsTemplate)
    def host_status(self, req, body=None):
        """Returns a detailed list of host status."""
        body_info = body.get('request', None)
        search_opts = {}
        search_opts.update(req.GET)

        context = req.environ['vsm.context']
        remove_invalid_options(context,
                               search_opts, self._get_conductor_search_options)

        res = self.conductor_api.host_status(context)
        LOG.info(' API return value')
        LOG.info(res)
        return {'host_list': res}

    @wsgi.serializers(xml=ConductorsTemplate)
    def resource_info(self, req, body=None):
        """Returns a detailed list of host status."""
        body_info = body.get('request', None)
        search_opts = {}
        search_opts.update(req.GET)

        context = req.environ['vsm.context']
        remove_invalid_options(context,
                               search_opts, self._get_conductor_search_options)

        res = self.conductor_api.resource_info(context)
        LOG.info(' API return value')
        LOG.info(res)
        return {'resource_info': res}

    @wsgi.serializers(xml=ConductorsTemplate)
    def detail(self, req):
        """Returns a detailed list of conductors."""
        LOG.debug(' comes to detail')
        return self._items(req, entity_maker=_translate_conductor_detail_view)

    def _items(self, req, entity_maker):
        """Returns a list of conductors, transformed through entity_maker."""

        LOG.info('')
        LOG.info(req)
        search_opts = {}
        search_opts.update(req.GET)

        context = req.environ['vsm.context']
        remove_invalid_options(context,
                               search_opts, self._get_conductor_search_options())

        res = self.conductor_api.test_service(context)
        return {'conductor': res}

    def _get_conductor_search_options(self):
        """Return conductor search options allowed by non-admin."""
        return ('display_name', 'status')

    @wsgi.serializers(xml=ConductorTemplate)
    def update(self, req, id, body):
        """Update a conductor."""
        context = req.environ['vsm.context']

        if not body:
            raise exc.HTTPUnprocessableEntity()

        if 'conductor' not in body:
            raise exc.HTTPUnprocessableEntity()

        conductor = body['conductor']
        update_dict = {}

        valid_update_keys = (
            'display_name',
            'display_description',
            'metadata',
        )

        for key in valid_update_keys:
            if key in conductor:
                update_dict[key] = conductor[key]

        try:
            conductor = self.conductor_api.get(context, id)
            self.conductor_api.update(context, conductor, update_dict)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        conductor.update(update_dict)

        return {'conductor': _translate_conductor_detail_view(context, conductor)}

def create_resource(ext_mgr):
    return wsgi.Resource(ConductorController(ext_mgr))

def remove_invalid_options(context, search_options, allowed_search_options):
    """Remove search options that are not valid for non-admin API/context."""
    if context.is_admin:
        # Allow all options
        return
    # Otherwise, strip out all unknown options
    unknown_options = [opt for opt in search_options
                       if opt not in allowed_search_options]
    bad_options = ", ".join(unknown_options)
    log_msg = _("Removing options '%(bad_options)s' from query") % locals()
    LOG.debug(log_msg)
    for opt in unknown_options:
        del search_options[opt]
