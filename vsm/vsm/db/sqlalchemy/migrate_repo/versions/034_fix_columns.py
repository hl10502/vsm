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


def upgrade(migrate_engine):
    migrate_engine.execute("alter table devices modify avail_capacity_kb bigint(20) not null")
    migrate_engine.execute("alter table devices modify total_capacity_kb bigint(20) not null")
    migrate_engine.execute("alter table devices modify used_capacity_kb bigint(20) not null")

def downgrade(migrate_engine):
    migrate_engine.execute("alter table devices modify avail_capacity_kb int(11) not null")
    migrate_engine.execute("alter table devices modify total_capacity_kb int(11) not null")
    migrate_engine.execute("alter table devices modify used_capacity_kb int(11) not null")
