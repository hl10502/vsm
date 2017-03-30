
# Copyright 2014 Intel Corporation, All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the"License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#  http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

from django.utils.translation import ugettext as _

from horizon import exceptions
from horizon import tabs

from vsm_dashboard.dashboards.vsm.flocking import utils
from .tables import FlockingInstancesTable

class DataTab(tabs.TableTab):
    name = _("Data")
    slug = "data"
    table_classes = (FlockingInstancesTable,)
    template_name = "horizon/common/_detail_table.html"
    preload = False

    def get_instances_data(self):
        try:
            instances = utils.get_instances_data(self.tab_group.request)
        except:
            instances = []
            exceptions.handle(self.tab_group.request,
                              _('Unable to retrieve instance list.'))
        return instances

class VizTab(tabs.Tab):
    name = _("Visualization")
    slug = "viz"
    template_name = "vsm/flocking/_flocking.html"

    def get_context_data(self, request):
        return None

class FlockingTabs(tabs.TabGroup):
    slug = "flocking"
    tabs = (VizTab, DataTab)
