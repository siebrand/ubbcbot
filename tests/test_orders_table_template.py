"""The orders table in template.yaml has the indexes the code queries, and the test database has the same ones.

Reading through an index that the deployed table does not have fails at run time, so this is checked here.
"""

from pathlib import Path

import pytest
import yaml

from repositories import order_repository
from repositories.order_repository import BOX_INDEX, STATUS_INDEX, OrderRepository

TEMPLATE = Path(__file__).resolve().parent.parent / "template.yaml"


class _CloudFormationLoader(yaml.SafeLoader):
    """Reads template.yaml although it has CloudFormation tags such as !Sub and !Ref"""


def _any_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_CloudFormationLoader.add_multi_constructor("!", _any_tag)


def _orders_table() -> dict:
    template = yaml.load(TEMPLATE.read_text(), Loader=_CloudFormationLoader)  # noqa: S506 (SafeLoader subclass)
    return template["Resources"]["OrdersTable"]["Properties"]


def _indexes() -> dict[str, dict]:
    return {index["IndexName"]: index for index in _orders_table()["GlobalSecondaryIndexes"]}


def _queried_indexes() -> set[str]:
    return {value for name, value in vars(order_repository).items() if name.endswith("_INDEX")}


def test_the_template_can_be_read():
    assert {"customer-index", "offer-index"} <= set(_indexes())


def test_every_key_of_every_index_is_declared_as_an_attribute():
    declared = {attribute["AttributeName"] for attribute in _orders_table()["AttributeDefinitions"]}
    keys = {key["AttributeName"] for index in _indexes().values() for key in index["KeySchema"]}

    assert keys <= declared


def test_the_status_index_is_hashed_on_the_status_and_has_whole_orders():
    index = _indexes()[STATUS_INDEX]
    attributes = {a["AttributeName"]: a["AttributeType"] for a in _orders_table()["AttributeDefinitions"]}

    assert index["KeySchema"] == [{"AttributeName": "status", "KeyType": "HASH"}]
    assert attributes["status"] == "S"
    assert index["Projection"] == {"ProjectionType": "ALL"}


def test_the_box_index_is_hashed_on_the_box_and_has_whole_orders():
    index = _indexes()[BOX_INDEX]
    attributes = {a["AttributeName"]: a["AttributeType"] for a in _orders_table()["AttributeDefinitions"]}

    assert index["KeySchema"] == [{"AttributeName": "box_id", "KeyType": "HASH"}]
    assert attributes["box_id"] == "S"
    assert index["Projection"] == {"ProjectionType": "ALL"}


def test_every_index_the_repository_queries_is_in_the_template():
    assert {STATUS_INDEX, BOX_INDEX} <= _queried_indexes()
    assert sorted(_queried_indexes() - set(_indexes())) == []


@pytest.mark.usefixtures("dynamodb")
def test_the_test_database_has_the_indexes_of_the_template():
    indexes = {index["IndexName"] for index in OrderRepository().table.global_secondary_indexes}

    assert indexes == set(_indexes())
