
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

from django.conf.urls import patterns, url
from .views import IndexView,CreateView,RenameView
from .views import CreateErasureCodedPoolView
from .views import AddCacheTierView
from .views import RemoveCacheTierView
from .views import add_cache_tier,remove_cache_tier,create_replicated_pool,create_ec_pool,rename_pool
from .views import get_default_pg_number_storage_group

urlpatterns = patterns('',
    url(r'^$', IndexView.as_view(), name='index'),
    url(r'^create/$', CreateView.as_view(), name='create'),
    url(r'^create_ec_pool/$', CreateErasureCodedPoolView.as_view(), name='create_ec_pool'),
    url(r'^rename/(?P<poolId>[^/]+)/$', RenameView.as_view(), name='rename'),
    url(r'^add_cache_tier/$', AddCacheTierView.as_view(), name='add_cache_tier'),
    url(r'^remove_cache_tier/$', RemoveCacheTierView.as_view(), name='remove_cache_tier'),
    url(r'^add_cache_tier_action/$', add_cache_tier, name='add_cache_tier_action'),
    url(r'^remove_cache_tier_action/$', remove_cache_tier, name='remove_cache_tier_action'),
    url(r'^create_replicated_pool_action/$', create_replicated_pool, name='create_replicated_pool_action'),
    url(r'^rename_pool_action/$', rename_pool, name='rename_pool_action'),
    url(r'^create_ec_pool_action/$', create_ec_pool, name='create_ec_pool_action'),
    url(r'^get_default_pg_number_storage_group/$', get_default_pg_number_storage_group, name='get_default_pg_number_storage_group'),
)

