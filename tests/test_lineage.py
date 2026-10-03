import os

import pytest

from bwdq.lineage import Lineage, LineageError

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def lin():
    return Lineage.load(os.path.join(ROOT, "config", "lineage.yaml"))


def test_dataset_level_impact_reaches_everything_downstream(lin):
    assert set(lin.downstream("ZSD_O01")) == {
        "ZSD_C01", "Q_REV_MONTH", "Q_TOP_MAT", "Q_CUST_REGION", "APP_SALES", "APP_CUSTOMER"}


def test_field_level_impact_follows_the_mapping(lin):
    reached = lin.downstream("ZSD_O01", "CUSTOMER")
    assert set(reached) == {"ZSD_C01", "Q_CUST_REGION", "APP_CUSTOMER"}
    assert reached["ZSD_C01"] == "0CUSTOMER"


def test_field_that_no_query_reads_stops_at_the_cube(lin):
    assert set(lin.downstream("ZSD_O01", "COMP_CODE")) == {"ZSD_C01"}


def test_master_data_field_impact(lin):
    assert set(lin.downstream("MAT_ATTR", "MATL_GROUP")) == {"ZSD_C01", "Q_TOP_MAT", "APP_SALES"}


def test_upstream(lin):
    assert set(lin.upstream("APP_CUSTOMER")) == {
        "Q_CUST_REGION", "ZSD_C01", "ZSD_O01", "SRC_SD", "MAT_ATTR", "CUST_ATTR"}


def test_unknown_node_and_edge_are_errors(lin):
    with pytest.raises(LineageError):
        lin.downstream("NOPE")
    with pytest.raises(LineageError):
        Lineage([{"id": "A", "label": "A"}], [{"from": "A", "to": "B"}])


def test_cycles_are_rejected():
    nodes = [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}]
    with pytest.raises(LineageError):
        Lineage(nodes, [{"from": "A", "to": "B"}, {"from": "B", "to": "A"}])


def test_mermaid_highlights_nodes(lin):
    text = lin.to_mermaid({"ZSD_C01"})
    assert text.startswith("flowchart LR")
    assert "class ZSD_C01 hit" in text
