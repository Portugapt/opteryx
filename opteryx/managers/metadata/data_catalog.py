# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from opteryx import config

from opteryx.managers.kvstores import KV_store_factory
from opteryx.managers.kvstores import LocalKVJson
from opteryx.managers.kvstores import RocksDB_KVStore


def metadata_factory():
    if config.METADATA_SERVER is None or config.METADATA_SERVER.upper() == "LOCAL":
        # if rocks is installed, use that
        if RocksDB_KVStore.can_use():
            return RocksDB_KVStore
        return LocalKVJson
    else:
        # use the configured one
        return KV_store_factory(config.METADATA_SERVER)


def put():
    pass


def get():
    pass