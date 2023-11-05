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


import copy
from typing import Any
from typing import Dict
from typing import Optional
from typing import Tuple

from orso.schema import ConstantColumn
from orso.schema import FlatColumn
from orso.schema import FunctionColumn
from orso.schema import RelationSchema

from opteryx.exceptions import AmbiguousIdentifierError
from opteryx.exceptions import ColumnNotFoundError
from opteryx.exceptions import FunctionNotFoundError
from opteryx.exceptions import InvalidInternalStateError
from opteryx.exceptions import UnexpectedDatasetReferenceError
from opteryx.functions import FUNCTIONS
from opteryx.managers.expression import NodeType
from opteryx.managers.expression import format_expression
from opteryx.models import Node
from opteryx.operators.aggregate_node import AGGREGATORS

COMBINED_FUNCTIONS = {**FUNCTIONS, **AGGREGATORS}


def hash_tree(node):
    from orso.cityhash import CityHash64

    def inner(node):
        _hash = 0

        # First recurse and do this for all the sub parts of the evaluation plan
        if node.left:
            _hash ^= inner(node.left)
        if node.right:
            _hash ^= inner(node.right)
        if node.centre:
            _hash ^= inner(node.centre)
        if node.parameters:
            for parameter in node.parameters:
                _hash ^= inner(parameter)

        if _hash == 0 and node.identity is not None:
            return CityHash64(node.identity)
        if _hash == 0 and node.schema_column is not None:
            return CityHash64(node.schema_column.identity)
        if _hash == 0 and node.value is not None:
            return CityHash64(str(node.value))
        if _hash == 0 and node.node_type == NodeType.WILDCARD:
            return CityHash64(str(node.source) + "*")
        return _hash

    _hash = CityHash64(format_expression(node, True)) ^ inner(node)
    return hex(_hash)[2:]


def merge_schemas(*schemas: Dict[str, RelationSchema]) -> Dict[str, RelationSchema]:
    """
    Handles the merging of relations, requiring a custom merge function.

    Parameters:
        dicts: Tuple[Dict[str, RelationSchema]]
            Dictionaries to be merged.

    Returns:
        A merged dictionary containing RelationSchemas.
    """
    merged_dict: Dict[str, RelationSchema] = {}
    for dic in schemas:
        if not isinstance(dic, dict):
            raise InvalidInternalStateError("Internal Error - merge_schemas expected dicts")
        for key, value in dic.items():
            if key in merged_dict:
                if isinstance(value, RelationSchema):
                    merged_dict[key] += value
                else:
                    raise InvalidInternalStateError(
                        "Internal Error - merge_schemas expects schemas"
                    )
            else:
                merged_dict[key] = copy.deepcopy(value)
    return merged_dict


def locate_identifier_in_loaded_schemas(
    value: str, schemas: Dict[str, RelationSchema]
) -> Tuple[Optional[str], Optional[RelationSchema]]:
    """
    Locate a given identifier in a set of loaded schemas.

    Parameters:
        value: str
            The identifier to locate.
        schemas: Dict[str, Schema]
            The loaded schemas to search within.

    Returns:
        A tuple containing the column and its source schema, if found.
    """
    found_source_relation = None
    column = None

    for schema in schemas.values():
        found = schema.find_column(value)
        if found:
            if column and found_source_relation:
                raise AmbiguousIdentifierError(identifier=value)
            found_source_relation = schema
            column = found

    return column, found_source_relation


def locate_identifier(node: Node, context: "BindingContext") -> Tuple[Node, Dict]:
    """
    Locate which schema the identifier is defined in. We return a populated node
    and the context.

    Parameters:
        node: Node
            The node representing the identifier
        context: BindingContext
            The current query context.

    Returns:
        Tuple[Node, Dict]: The updated node and the current context.

    Raises:
        UnexpectedDatasetReferenceError: If the source dataset is not found.
        ColumnNotFoundError: If the column is not found in the schema.
    """
    from opteryx.components.binder import BindingContext

    def create_variable_node(node: Node, context: BindingContext) -> Node:
        """Populates a Node object for a variable."""
        schema_column = context.connection.variables.as_column(node.value)
        new_node = Node(
            node_type=NodeType.LITERAL,
            schema_column=schema_column,
            type=schema_column.type,
            value=schema_column.value,
        )
        return new_node

    # get the list of candidate schemas
    if node.source:
        candidate_schemas = {
            name: schema
            for name, schema in context.schemas.items()
            if name.startswith("$shared") or name == node.source
        }
    else:
        candidate_schemas = context.schemas

    # if there are no candidates, we probably don't know the relation
    if not candidate_schemas:
        raise UnexpectedDatasetReferenceError(dataset=node.source)

    # look up the column in the candidate schemas
    column, found_source_relation = locate_identifier_in_loaded_schemas(
        node.source_column, candidate_schemas
    )

    # if we didn't find the column, suggest alternatives
    if not column:
        # Check if the identifier is a variable
        if node.current_name[0] == "@":
            node = create_variable_node(node, context)
            context.schemas["$derived"].columns.append(node.schema_column)
            return node, context

        from opteryx.utils import suggest_alternative

        suggestion = suggest_alternative(
            node.source_column,
            [
                column_name
                for _, schema in candidate_schemas.items()
                for column_name in schema.all_column_names()
                if column_name is not None
            ],
        )
        raise ColumnNotFoundError(column=node.value, suggestion=suggestion)
    elif node.current_name[0] == "@":
        new_node = Node(
            node_type=NodeType.LITERAL,
            schema_column=column,
            type=column.type,
            value=column.value,
        )
        return new_node, context

    # Update node.source to the found relation name
    if not node.source:
        node.source = found_source_relation.name

    # if we have an alias for a column not known about in the schema, add it
    if node.alias and node.alias not in column.all_names:
        column.aliases.append(node.alias)

    # Update node.schema_column with the found column
    node.schema_column = column
    # if may need to map source aliases to the columns if they weren't able to be
    # mapped before now
    if column.origin and len(column.origin) == 1:
        node.source = column.origin[0]
    return node, context


def traversive_recursive_bind(node, context):
    # First recurse and do this for all the sub parts of the evaluation plan
    if node.left:
        node.left, context = inner_binder(node.left, context)
    if node.right:
        node.right, context = inner_binder(node.right, context)
    if node.centre:
        node.centre, context = inner_binder(node.centre, context)
    if node.parameters:
        node.parameters, new_contexts = zip(
            *(inner_binder(parm, context) for parm in node.parameters)
        )
        merged_schemas = merge_schemas(*[ctx.schemas for ctx in new_contexts])
        context.schemas = merged_schemas
    return node, context


def inner_binder(node: Node, context: Dict[str, Any]) -> Tuple[Node, Dict[str, Any]]:
    """
    Note, this is a tree within a tree. This function represents a single step in the execution
    plan (associated with the relational algebra) which may itself be an evaluation plan
    (executing comparisons).
    """
    # Import relevant classes and functions
    from opteryx.managers.expression import ExpressionColumn
    from opteryx.managers.expression import format_expression

    # Retrieve the node type for further processing.
    node_type = node.node_type

    # Early exit for columns that are already bound.
    # If the node has a 'schema_column' already set, it doesn't need to be processed again.
    # This is an optimization to avoid unnecessary work.
    if node.schema_column is not None:
        return node, context

    # Early exit for nodes representing IDENTIFIER types.
    # If the node is of type IDENTIFIER, it's just a simple look up to bind the node.
    if node_type in (NodeType.IDENTIFIER, NodeType.EVALUATED):
        return locate_identifier(node, context)

    # Expression Lists are part of how CASE statements are represented
    if node_type == NodeType.EXPRESSION_LIST:
        node.value, new_contexts = zip(*(inner_binder(parm, context) for parm in node.value))
        merged_schemas = merge_schemas(*[ctx.schemas for ctx in new_contexts])
        context.schemas = merged_schemas

    # Early exit for nodes representing calculated columns.
    # If the node represents a calculated column, if we're seeing it again it's because it
    # has appeared earlier in the plan and in that case we don't need to recalcuate, we just
    # need to treat the result like an IDENTIFIER
    # We discard columns not referenced, so this someonetimes holds the only reference to
    # child columns, e.g. MAX(id), we may not have 'id' next time we see it, only MAX(id)
    column_name = node.query_column or format_expression(node, True)
    for schema in context.schemas.values():
        found_column = schema.find_column(column_name)
        # If the column exists in the schema, update node and context accordingly.
        if found_column:
            node.schema_column = found_column
            node.query_column = node.alias or column_name

            return node, context

    schemas = context.schemas

    # do the sub trees off this node
    node, context = traversive_recursive_bind(node, context)

    # Now do the node we're at
    if node_type == NodeType.LITERAL:
        schema_column = ConstantColumn(
            name=column_name,
            aliases=[node.alias] if node.alias else [],
            type=node.type,
            value=node.value,
            nullable=False,
        )
        schemas["$derived"].columns.append(schema_column)
        node.schema_column = schema_column
        node.query_column = node.alias or column_name

    elif not node_type == NodeType.SUBQUERY and not node.do_not_create_column:
        schema_column = schemas["$derived"].find_column(column_name)

        if schema_column:
            schema_column = FlatColumn(
                name=column_name,
                aliases=[schema_column.aliases] if schema_column.aliases else None,
                type=0,
                identity=schema_column.identity,
            )
            schemas["$derived"].columns = [
                col for col in schemas["$derived"].columns if col.identity != schema_column.identity
            ]
            schemas["$derived"].columns.append(schema_column)
            node.schema_column = schema_column
            node.query_column = node.alias or column_name
            node.node_type = NodeType.EVALUATED

            return node, context

        elif node_type in (NodeType.FUNCTION, NodeType.AGGREGATOR):
            # we're just going to bind the function into the node
            func = COMBINED_FUNCTIONS.get(node.value)
            if not func:
                # v1:
                from opteryx.utils import suggest_alternative

                suggest = suggest_alternative(node.value, COMBINED_FUNCTIONS.keys())
                # v2: suggest = FUNCTIONS.suggest(node.value)
                raise FunctionNotFoundError(function=node.value, suggestion=suggest)

            # we need to add this new column to the schema
            identity = hash_tree(node)
            aliases = [node.alias] if node.alias else []
            schema_column = FunctionColumn(
                name=column_name, type=0, binding=func, aliases=aliases, identity=identity
            )
            schemas["$derived"].columns.append(schema_column)
            node.function = func
            node.derived_from = []
            node.schema_column = schema_column
            node.query_column = node.alias or column_name

        else:
            identity = hash_tree(node)
            schema_column = ExpressionColumn(
                name=column_name,
                aliases=[node.alias] if node.alias else [],
                type=0,
                expression=node.value,
                identity=identity,
            )
            schemas["$derived"].columns.append(schema_column)
            node.schema_column = schema_column
            node.query_column = node.alias or column_name

    context.schemas = schemas
    return node, context