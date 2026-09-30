# Interview walkthrough

## Opening explanation

“My operations experience includes warehouse and transportation systems, where a handoff can look complete in one system but incomplete in another. I built FlowCheck to demonstrate how I translate that operating problem into a data contract, a repeatable comparison, and a verification workflow. It uses fictional data rather than employer records.”

## Show the evidence

1. Run the seeded exports. Explain why the two WMS lines for SHP-2401 aggregate to the same 150 units in TMS. Different row counts are not automatically errors.
2. Open the three discrepancies. Explain why a missing record is different from a quantity mismatch and why the suggested action starts with checking source scope.
3. Run identical inputs again. Explain the normalized content fingerprint, the original label being retained, and the audit event for reuse.
4. Load corrected exports. Explain why a new snapshot preserves the original evidence rather than overwriting it.
5. Open `docs/investigation.sql` and explain the compound shipment/SKU join and the delta direction.
6. Run the automated tests. Point to duplicate rejection, whole-batch validation, and simultaneous retry coverage.

## Design decisions to understand

- Whole-batch rejection avoids falsely labeling missing records when an invalid row was silently dropped.
- SQLite and Python's standard library make the demo easy to reproduce. A shared service would need different hosting and access controls.
- Rules are deterministic because these discrepancies can be defined precisely; an LLM is unnecessary for matching quantities.
- A content fingerprint deduplicates retries, but is not proof that the source system is correct.
- Matching totals cannot detect every problem. Wrong units, inconsistent facility windows, or the same error in both systems can produce false agreement.

## Honest résumé wording

Built a Python and SQLite WMS/TMS reconciliation workbench with CSV validation, shipment-level quantity checks, idempotent batch processing, audit history, and automated API tests using synthetic logistics data.

Only use this after you can explain and demonstrate the implementation. Do not claim employer adoption, production deployment, or realized savings from this demonstration.

## Suggested next learning exercise

Add facility and snapshot timestamps to the contract; reject comparisons across incompatible scopes. Write the mismatch test before modifying the engine. This would address a current documented limitation and give you a concrete enhancement to explain in interviews.
