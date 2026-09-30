"""SQLite persistence. A batch and its provenance commit in one transaction."""
from contextlib import contextmanager
import hashlib
import json
import sqlite3
from pathlib import Path
from .engine import RULE_VERSION, ValidationError, parse_export, reconcile


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript(Path(__file__).with_name("schema.sql").read_text())

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def run(self, label, warehouse, transport):
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80:
            raise ValidationError("Snapshot label must contain 1–80 characters.")
        wms, tms = parse_export(warehouse, "WMS"), parse_export(transport, "TMS")
        canonical = json.dumps([RULE_VERSION, sorted(wms, key=lambda r: r['record_id']),
                                sorted(tms, key=lambda r: r['record_id'])], sort_keys=True)
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        result = reconcile(wms, tms)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id FROM runs WHERE fingerprint=?", (fingerprint,)).fetchone()
            if existing:
                run_id, reused = existing["id"], True
                db.execute("INSERT INTO audit_events(run_id,event) VALUES(?,?)", (run_id, "IDENTICAL_SNAPSHOT_REUSED"))
            else:
                cursor = db.execute("INSERT INTO runs(fingerprint,label,rule_version,result_json) VALUES(?,?,?,?)",
                                    (fingerprint, label.strip(), RULE_VERSION, json.dumps(result)))
                run_id, reused = cursor.lastrowid, False
                for source, rows in (("WMS", wms), ("TMS", tms)):
                    db.executemany("INSERT INTO source_records VALUES(?,?,?,?,?,?)",
                                   [(run_id, source, r['record_id'], r['shipment_id'], r['sku'], r['quantity']) for r in rows])
                db.execute("INSERT INTO audit_events(run_id,event) VALUES(?,?)", (run_id, "SNAPSHOT_RECONCILED"))
        return dict(self.get(run_id), reused=reused)

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            result = dict(row)
            result.update(json.loads(result.pop("result_json")))
            result['audit'] = [dict(r) for r in db.execute("SELECT event,created_at FROM audit_events WHERE run_id=? ORDER BY id", (run_id,))]
            return result

    def history(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,label,created_at,result_json FROM runs ORDER BY id DESC LIMIT 100").fetchall()
            return [dict(id=r['id'], label=r['label'], created_at=r['created_at'],
                         **json.loads(r['result_json'])['summary']) for r in rows]
