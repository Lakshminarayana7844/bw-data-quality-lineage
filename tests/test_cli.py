import json
import os
import shutil

from bwdq.cli import main

ROOT = os.path.join(os.path.dirname(__file__), "..")
RULES = os.path.join(ROOT, "config", "rules.yaml")
LINEAGE = os.path.join(ROOT, "config", "lineage.yaml")


def test_sample_data_fails_the_gate_and_writes_reports(tmp_path):
    code = main(["--help"] if False else ["run", "--rules", RULES, "--lineage", LINEAGE, "--out", str(tmp_path)])
    assert code == 1
    data = json.loads((tmp_path / "report.json").read_text())
    assert data["summary"]["gate"] == "FAIL"
    assert "R002" in data["summary"]["blocking_rules"]
    assert "mermaid" in (tmp_path / "report.md").read_text()
    page = (tmp_path / "report.html").read_text()
    assert "Data quality report" in page and "R003" in page


def test_clean_data_passes(tmp_path):
    work = tmp_path / "w"
    shutil.copytree(os.path.join(ROOT, "config"), work / "config")
    shutil.copytree(os.path.join(ROOT, "data"), work / "data")
    # a clean extract: keep the first rows, which are healthy after removing defects
    import pandas as pd
    df = pd.read_csv(work / "data" / "ZSD_O01.csv", dtype=str, keep_default_na=False)
    df = df[(df.CUSTOMER != "") & (~df.MATERIAL.str.startswith("MAT9")) & (~df.QUANTITY.str.startswith("-"))
            & (~df.CALDAY.str.startswith("20261")) & df.CURRENCY.isin(["EUR", "USD", "CHF"])
            & df.UNIT.isin(["PC", "KG", "M"]) & (df.NET_VALUE.astype(float) < 100000)]
    df = df.drop_duplicates(["DOC_NUMBER", "DOC_ITEM"], keep=False)
    df.to_csv(work / "data" / "ZSD_O01.csv", index=False, lineterminator="\n")
    mat = pd.read_csv(work / "data" / "MAT_ATTR.csv", dtype=str, keep_default_na=False)
    mat["MATL_GROUP"] = mat["MATL_GROUP"].replace("", "HYD")
    mat.to_csv(work / "data" / "MAT_ATTR.csv", index=False, lineterminator="\n")
    cust = pd.read_csv(work / "data" / "CUST_ATTR.csv", dtype=str, keep_default_na=False)
    cust["COUNTRY"] = cust["COUNTRY"].replace("Germany", "DE")
    cust.to_csv(work / "data" / "CUST_ATTR.csv", index=False, lineterminator="\n")
    out = tmp_path / "out"
    code = main(["run", "--rules", str(work / "config" / "rules.yaml"),
                 "--lineage", str(work / "config" / "lineage.yaml"), "--out", str(out)])
    assert code == 0
    assert json.loads((out / "report.json").read_text())["summary"]["rules_failed"] == 0


def test_bad_config_returns_exit_code_2(tmp_path):
    bad = tmp_path / "rules.yaml"
    bad.write_text("datasets: {}\nrules: [{id: A, dataset: X, type: not_null, field: f}]\n")
    assert main(["run", "--rules", str(bad), "--lineage", LINEAGE, "--out", str(tmp_path)]) == 2
