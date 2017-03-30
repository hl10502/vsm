#  Copyright 2014 Intel Corporation, All Rights Reserved.
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

"""
Cluster interface (1.1 extension).
"""

import urllib
from vsmclient import base

class Cluster(base.Resource):
    """A vsm is an extra block level storage to the OpenStack instances."""
    def __repr__(self):
        try:
            return "<Cluster: %s>" % self.id
        except AttributeError:
            return "<Cluster: summary>"

    def delete(self):
        """Delete this vsm."""
        self.manager.delete(self)

    def update(self, **kwargs):
        """Update the display_name or display_description for this vsm."""
        self.manager.update(self, **kwargs)

    def attach(self, instance_uuid, mountpoint):
        """Set attachment metadata.

        :param instance_uuid: uuid of the attaching instance.
        :param mountpoint: mountpoint on the attaching instance.
        """
        return self.manager.attach(self, instance_uuid, mountpoint)

    def detach(self):
        """Clear attachment metadata."""
        return self.manager.detach(self)

    def reserve(self, vsm):
        """Reserve this vsm."""
        return self.manager.reserve(self)

    def unreserve(self, vsm):
        """Unreserve this vsm."""
        return self.manager.unreserve(self)

    def begin_detaching(self, vsm):
        """Begin detaching vsm."""
        return self.manager.begin_detaching(self)

    def roll_detaching(self, vsm):
        """Roll detaching vsm."""
        return self.manager.roll_detaching(self)

    def initialize_connection(self, vsm, connector):
        """Initialize a vsm connection.

        :param connector: connector dict from nova.
        """
        return self.manager.initialize_connection(self, connector)

    def terminate_connection(self, vsm, connector):
        """Terminate a vsm connection.

        :param connector: connector dict from nova.
        """
        return self.manager.terminate_connection(self, connector)

    def set_metadata(self, vsm, metadata):
        """Set or Append metadata to a vsm.

        :param type : The :class: `Cluster` to set metadata on
        :param metadata: A dict of key/value pairs to set
        """
        return self.manager.set_metadata(self, metadata)

    def upload_to_image(self, force, image_name, container_format,
                        disk_format):
        """Upload a vsm to image service as an image."""
        self.manager.upload_to_image(self, force, image_name, container_format,
                                     disk_format)

    def force_delete(self):
        """Delete the specified vsm ignoring its current state.

        :param vsm: The UUID of the vsm to force-delete.
        """
        self.manager.force_delete(self)

class ClusterManager(base.ManagerWithFind):
    """
    Manage :class:`Cluster` resources.
    """
    resource_class = Cluster

    def create(self, name="default", file_system="xfs", journal_size=None, 
                size=None, management_network=None,
                ceph_public_network=None, cluster_network=None,
                primary_public_netmask=None, secondary_public_netmask=None,
                cluster_netmask=None, servers=[]):

        """
        Create a cluster.
        """

        body = {'cluster': {'name': name,
                            "file_system": file_system,
                            "journal_size": journal_size,
                            "size": size, 
                            "management_network": management_network,
                            "ceph_public_network": ceph_public_network,
                            "cluster_network": cluster_network,
                            "primary_public_netmask": primary_public_netmask,
                            "secondary_public_netmask": secondary_public_netmask,
                            "cluster_netmask": cluster_netmask,
                            "servers": servers,
                           }}
        return self._create('/clusters', body, 'cluster')

    def get(self, vsm_id):
        """
        Get a vsm.

        :param vsm_id: The ID of the vsm to delete.
        :rtype: :class:`Cluster`
        """
        return self._get("/clusters/%s" % vsm_id, "cluster")

    def list(self, detailed=False, search_opts=None):
        """
        Get a list of all vsms.

        :rtype: list of :class:`Cluster`
        """
        #print ' comes to list'
        if search_opts is None:
            search_opts = {}

        qparams = {}

        for opt, val in search_opts.iteritems():
            if val:
                qparams[opt] = val

        query_string = "?%s" % urllib.urlencode(qparams) if qparams else ""

        detail = ""
        if detailed:
            detail = "/detail"

        ret = self._list("/clusters%s%s" % (detail, query_string),
                          "clusters")
        return ret

    def delete(self, vsm):
        """
        Delete a vsm.

        :param vsm: The :class:`Cluster` to delete.
        """
        self._delete("/clusters/%s" % base.getid(vsm))

    def update(self, vsm, **kwargs):
        """
        Update the display_name or display_description for a vsm.

        :param vsm: The :class:`Cluster` to delete.
        """
        if not kwargs:
            return

        body = {"cluster": kwargs}

        self._update("/clusters/%s" % base.getid(vsm), body)

    def _action(self, action, vsm, info=None, **kwargs):
        """
        Perform a vsm "action."
        """
        body = {action: info}
        self.run_hooks('modify_body_for_action', body, **kwargs)
        url = '/clusters/%s/action' % base.getid(vsm)
        return self.api.client.post(url, body=body)

    def initialize_connection(self, vsm, connector):
        """
        Initialize a vsm connection.

        :param vsm: The :class:`Cluster` (or its ID).
        :param connector: connector dict from nova.
        """
        return self._action('os-initialize_connection', vsm,
                            {'connector': connector})[1]['connection_info']

    def terminate_connection(self, vsm, connector):
        """
        Terminate a vsm connection.

        :param vsm: The :class:`Cluster` (or its ID).
        :param connector: connector dict from nova.
        """
        self._action('os-terminate_connection', vsm,
                     {'connector': connector})

    def summary(self):
        """
        summary
        """
        url = "/clusters/summary"
        return self._get(url, 'cluster-summary')

    def get_service_list(self):
        """
        get_service_list
        """
        url = "/clusters/get_service_list"
        return self.api.client.get(url)

    def refresh(self):
        url = "/clusters/refresh"
        return self.api.client.post(url)

    def import_ceph_conf(self,cluster_name,ceph_conf_path=None):
        body = {'cluster': {
                            "cluster_name": cluster_name,
                            "ceph_conf_path":ceph_conf_path,
                           }}
        url = "/clusters/import_ceph_conf"
        return self.api.client.post(url,body=body)

    def check_pre_existing_cluster(self,body):
        url = "/clusters/check_pre_existing_cluster"
        return self.api.client.post(url,body=body)

    def import_cluster(self,body):
        url = "/clusters/import_cluster"
        return self.api.client.post(url,body=body)


    def detect_crushmap(self,body):
        url = "/clusters/detect_crushmap"
        return self.api.client.post(url,body=body)

    def get_crushmap_tree_data(self,body):
        url = "/clusters/get_crushmap_tree_data"
        return self.api.client.post(url,body=body)

    def integrate(self,servers=[]):
        body = {'cluster': {
                            "servers": servers,
                           }}
        url = "/clusters/integrate"
        return self.api.client.post(url)

    def stop_cluster(self,cluster_id):
        body = {'cluster': {
                            "id": cluster_id,
                           }}
        url = "/clusters/stop_cluster"
        return self.api.client.post(url,body=body)

    def start_cluster(self,cluster_id):
        body = {'cluster': {
                            "id": cluster_id,
                           }}
        url = "/clusters/start_cluster"
        return self.api.client.post(url,body=body)

    def get_ceph_health_list(self):
        """
        ceph_status
        """
        url = "/clusters/get_ceph_health_list"
        resp, ceph_status = self.api.client.get(url)
        return ceph_status