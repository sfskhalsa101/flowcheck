"""Pure validation and reconciliation rules; no network or database side effects."""
import csv
import io
import re
from collections import defaultdict

RULE_VERSION = "1.0"
HEADERS = ["record_id", "shipment_id", "sku", "quantity"]
MAX_ROWS = 5000


class ValidationError(ValueError):
    pass


def parse_export(text, source):
    if not isinstance(text, str) or not text.strip():
        raise ValidationError(f"{source}: an export is required.")
    if len(text.encode("utf-8")) > 500_000:
        raise ValidationError(f"{source}: export exceeds 500 KB.")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
    rows, seen = [], set()
    try:
        if reader.fieldnames != HEADERS:
            raise ValidationError(f"{source}: expected columns in order: {','.join(HEADERS)}")
        for number, row in enumerate(reader, start=2):
            if len(rows) >= MAX_ROWS:
                raise ValidationError(f"{source}: maximum {MAX_ROWS} records.")
            if None in row or any(value is None for value in row.values()):
                raise ValidationError(f"{source}, record {number}: expected four fields.")
            row = {key: value.strip() for key, value in row.items()}
            for field in HEADERS[:3]:
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", row[field]):
                    raise ValidationError(f"{source}, record {number}: {field} must be a 1–64 character identifier (letters, numbers, _, ., -).")
            if row["record_id"] in seen:
                raise ValidationError(f"{source}, record {number}: duplicate record_id {row['record_id']}; batch rejected to prevent double counting.")
            if not re.fullmatch(r"[0-9]{1,7}", row["quantity"]) or not 1 <= int(row["quantity"]) <= 1_000_000:
                raise ValidationError(f"{source}, record {number}: quantity must be a whole number from 1 to 1,000,000.")
            row["quantity"] = int(row["quantity"])
            seen.add(row["record_id"])
            rows.append(row)
    except csv.Error as exc:
        raise ValidationError(f"{source}: malformed CSV: {exc}") from exc
    if not rows:
        raise ValidationError(f"{source}: at least one data record is required.")
    return rows


def reconcile(warehouse, transport):
    totals = []
    for rows in (warehouse, transport):
        grouped = defaultdict(int)
        for row in rows:
            grouped[(row["shipment_id"], row["sku"])] += row["quantity"]
        totals.append(grouped)
    wms, tms = totals
    issues, matched = [], 0
    keys = sorted(wms.keys() | tms.keys())
    for shipment, sku in keys:
        key = shipment, sku
        expected, actual = wms.get(key, 0), tms.get(key, 0)
        if key not in tms:
            rule, action = "MISSING_IN_TMS", "Check the manifest export scope and publishing job; verify the warehouse record before republishing."
        elif key not in wms:
            rule, action = "MISSING_IN_WMS", "Check for a stale manifest or an incomplete warehouse export; confirm the shipment with the source-system owner."
        elif expected != actual:
            rule, action = "QUANTITY_MISMATCH", "Compare pick and manifest lines, verify units of measure, and correct the source record before exporting again."
        else:
            matched += 1
            continue
        issues.append(dict(shipment_id=shipment, sku=sku, rule=rule, warehouse_qty=expected,
                           transport_qty=actual, delta=actual-expected, action=action))
    return {"summary": {"warehouse_records": len(warehouse), "transport_records": len(transport),
                        "line_keys": len(keys), "matched_keys": matched, "exception_keys": len(issues),
                        "warehouse_units": sum(wms.values()), "transport_units": sum(tms.values()),
                        "status": "review_required" if issues else "matched"}, "issues": issues}
