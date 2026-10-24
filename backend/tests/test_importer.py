import io

import openpyxl

from app import importer

from .conftest import TESTDATA


def test_real_professor_list_is_valid():
    res = importer.parse("professors.csv", (TESTDATA / "professors.csv").read_bytes())
    assert res["fatal"] == ""
    assert res["valid"] == 65 and res["invalid"] == 0
    assert set(res["columns"].values()) == {"name", "email", "research_area"}
    assert res["column_warnings"] == []


def test_missing_email_column_is_fatal():
    res = importer.parse("x.csv", b"Professor,Research Area\nA,ML\n")
    assert "Email" in res["fatal"]


def test_bad_emails_and_duplicates_are_reported_per_row():
    data = b"Professor,Email\nA,a@ntu.edu.tw\nB,not-an-email\nC,\n,d@ntu.edu.tw\nA2,A@ntu.edu.tw\n"
    res = importer.parse("x.csv", data)
    errs = {r["row"]: r["errors"] for r in res["rows"] if r["errors"]}
    assert res["valid"] == 1
    assert "Invalid email" in errs[3][0]
    assert errs[4] == ["Email is missing"]
    assert errs[5] == ["Professor name is missing"]
    assert "Duplicate" in errs[6][0]


def test_columns_matched_by_name_in_any_order_with_warning():
    res = importer.parse("x.csv", b"E-mail;Research Interests;Name\nx@y.edu;AI;Prof X\n")
    assert res["valid"] == 1
    assert res["rows"][0]["data"]["name"] == "Prof X"
    assert any("different order" in w for w in res["column_warnings"])


def test_excel_upload():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["#", "Professor", "Email", "Research Area", "Homepage"])
    ws.append([1, "Pu-Jen Cheng", "pjcheng@csie.ntu.edu.tw", "IR", "www.csie.ntu.edu.tw/~pjcheng"])
    buf = io.BytesIO()
    wb.save(buf)
    res = importer.parse("list.xlsx", buf.getvalue())
    assert res["valid"] == 1
    assert res["rows"][0]["data"]["profile_url"].startswith("https://")
