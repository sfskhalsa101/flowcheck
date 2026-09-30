# Reconciliation runbook

1. Confirm both exports cover the same facility, operating window, shipment population, and units. If they do not, obtain comparable exports first.
2. Load the two CSVs and give the snapshot a meaningful label.
3. If validation fails, correct the source export. No partial comparison is saved. Never delete rows simply to suppress a discrepancy.
4. For a missing record, check export completeness and the publishing handoff. For a quantity difference, check source lines, picks, units, and manifest revisions.
5. Use the discrepancy CSV to support investigation. WMS is a comparison reference; validate against the appropriate source owner before deciding which record needs correction.
6. Make authorized corrections in the source system outside FlowCheck, obtain new complete exports, and run again.
7. Confirm the corrected snapshot matches and retain the original run and audit evidence. A matching result is not physical shipment confirmation.

## Troubleshooting

- Port already in use: start with `python3 server.py --port 8766`.
- Duplicate record ID: verify whether the export contains duplicate messages or whether line identifiers were omitted. Do not invent new IDs merely to pass validation.
- Every record is missing in one system: check shipment identifiers, SKU conventions, case, facility, and time window.
- Identical snapshot reused: this is expected even if the label changed. Modify the upstream data only when a real correction is needed.
- Lost history: confirm the `--db` path. By default it is `work/flowcheck.db` inside the repository, independent of your current directory.
- Backups: stop the application before copying the SQLite file. The repository excludes it from Git.

This application has no upstream credentials, so it cannot retry an integration job or change an operational record. Audit events are local application records, not a tamper-proof compliance ledger.
