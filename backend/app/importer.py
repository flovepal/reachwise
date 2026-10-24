"""Reading and checking professor lists (CSV or Excel)."""
import csv
import io

from email_validator import EmailNotValidError, validate_email

FIELDS = ["name", "email", "research_area", "university", "department", "profile_url", "notes"]
REQUIRED = ["name", "email"]
EXPECTED_ORDER = ["name", "email", "research_area"]

ALIASES = {
    "name": ["professor", "name", "professor name", "prof", "prof name", "faculty", "full name"],
    "email": ["email", "e-mail", "email id", "mail", "email address", "mail id"],
    "research_area": ["research area", "research", "area", "research areas", "research interests",
                      "interests", "research interest"],
    "university": ["university", "institution", "school", "college"],
    "department": ["department", "dept", "dept."],
    "profile_url": ["profile url", "url", "homepage", "website", "link", "profile", "lab page"],
    "notes": ["notes", "note", "comments", "comment"],
}
_LOOKUP = {alias: field for field, names in ALIASES.items() for alias in names}
IGNORED = {"#", "no", "no.", "s.no", "sno", "sr", "sr.", "id", "serial"}


def check_email(value: str) -> tuple[str, str]:
    """Return (normalized_email, error)."""
    value = (value or "").strip()
    if not value:
        return "", "Email is missing"
    try:
        v = validate_email(value, check_deliverability=False)
        return v.normalized, ""
    except EmailNotValidError as e:
        return value, f"Invalid email: {e}"


def clean_row(raw: dict) -> tuple[dict, list[str]]:
    row = {f: str(raw.get(f) or "").strip() for f in FIELDS}
    errors = []
    if not row["name"]:
        errors.append("Professor name is missing")
    row["email"], err = check_email(row["email"])
    if err:
        errors.append(err)
    if row["profile_url"] and not row["profile_url"].lower().startswith(("http://", "https://")):
        row["profile_url"] = "https://" + row["profile_url"]
    return row, errors


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp950", "gb18030", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _table(filename: str, data: bytes) -> list[list[str]]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        return [["" if c is None else str(c) for c in row] for row in ws.iter_rows(values_only=True)]
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


def parse(filename: str, data: bytes) -> dict:
    """Check an uploaded file. Nothing is saved here.

    Returns {columns, column_warnings, rows:[{row, data, errors}], valid, invalid, duplicates, fatal}
    """
    result = {"columns": {}, "column_warnings": [], "rows": [], "valid": 0, "invalid": 0,
              "duplicates": 0, "fatal": ""}
    if not filename.lower().endswith((".csv", ".xlsx", ".xlsm", ".tsv", ".txt")):
        result["fatal"] = "Upload a .csv or .xlsx file."
        return result
    try:
        table = [r for r in _table(filename, data) if any(str(c).strip() for c in r)]
    except Exception as e:  # noqa: BLE001
        result["fatal"] = f"Could not read the file: {e}"
        return result
    if not table:
        result["fatal"] = "The file is empty."
        return result

    header = [str(h).strip() for h in table[0]]
    mapping: dict[int, str] = {}
    unknown = []
    for i, h in enumerate(header):
        key = h.lower().strip()
        if key in IGNORED or not key:
            continue
        field = _LOOKUP.get(key)
        if field and field not in mapping.values():
            mapping[i] = field
        else:
            unknown.append(h)
    result["columns"] = {header[i]: f for i, f in mapping.items()}

    missing = [f for f in REQUIRED if f not in mapping.values()]
    if missing:
        nice = {"name": "Professor", "email": "Email"}
        result["fatal"] = ("Missing required column(s): " + ", ".join(nice[m] for m in missing)
                           + ". Found: " + ", ".join(h for h in header if h))
        return result
    if unknown:
        result["column_warnings"].append("Ignored columns: " + ", ".join(unknown))
    found_order = [f for _, f in sorted(mapping.items()) if f in EXPECTED_ORDER]
    if found_order != [f for f in EXPECTED_ORDER if f in found_order]:
        result["column_warnings"].append(
            "Columns are in a different order than the template (Professor, Email, Research Area). "
            "They were matched by name, so this is fine.")

    seen = set()
    for n, raw_row in enumerate(table[1:], start=2):
        raw = {f: (raw_row[i] if i < len(raw_row) else "") for i, f in mapping.items()}
        row, errors = clean_row(raw)
        key = row["email"].lower()
        if not errors and key in seen:
            errors.append("Duplicate email in this file (first one kept)")
            result["duplicates"] += 1
        if not errors:
            seen.add(key)
            result["valid"] += 1
        else:
            result["invalid"] += 1
        result["rows"].append({"row": n, "data": row, "errors": errors})
    return result


def to_csv(professors: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["#", "Professor", "Email", "Research Area", "University", "Department", "Profile URL", "Notes"])
    for i, p in enumerate(professors, start=1):
        w.writerow([i, p.get("name", ""), p.get("email", ""), p.get("research_area", ""), p.get("university", ""),
                    p.get("department", ""), p.get("profile_url", ""), p.get("notes", "")])
    return buf.getvalue()
