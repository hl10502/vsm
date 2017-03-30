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

from sqlalchemy import and_, String, Column, MetaData, select, Table, Integer

def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    storage_pools = Table('storage_pools', meta, autoload=True)
    replica_storage_pool = Column('replica_storage_pool', String(length=255))

    storage_pools.create_column(replica_storage_pool)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    storage_pools = Table('storage_pools', meta, autoload=True)

    storage_pools.drop_column('replica_storage_pool')
