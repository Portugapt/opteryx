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

"""
Set Variables Node

This is a SQL Query Execution Plan Node.
"""

from opteryx.constants import QueryStatus
from opteryx.models import NonTabularResult
from opteryx.models import QueryProperties

from . import BasePlanNode


class SetVariableNode(BasePlanNode):
    def __init__(self, properties: QueryProperties, **parameters):
        BasePlanNode.__init__(self, properties=properties, **parameters)

        self.variable = parameters.get("variable")
        self.value = parameters.get("value")
        self.variables = parameters.get("variables")

    @classmethod
    def from_json(cls, json_obj: str) -> "BasePlanNode":  # pragma: no cover
        raise NotImplementedError()

    @property
    def name(self):  # pragma: no cover
        return "Set Variables"

    @property
    def config(self):  # pragma: no cover
        return f"{self.variable} TO {self.value}"

    def execute(self, morsel) -> NonTabularResult:
        self.variables[self.variable] = self.value
        return NonTabularResult(record_count=1, status=QueryStatus.SQL_SUCCESS)  # type: ignore
