-- Run against work/flowcheck.db. Change run_id = 1 to the snapshot to inspect.
-- Aggregate split records, then compare the union of keys so neither source
-- can disappear through an inner join.
WITH totals AS (
  SELECT source, shipment_id, sku, SUM(quantity) AS units
  FROM source_records WHERE run_id = 1
  GROUP BY source, shipment_id, sku
), keys AS (
  SELECT DISTINCT shipment_id, sku FROM totals
)
SELECT k.shipment_id, k.sku,
       COALESCE(w.units,0) AS warehouse_units,
       COALESCE(t.units,0) AS transport_units,
       COALESCE(t.units,0)-COALESCE(w.units,0) AS delta,
       CASE WHEN w.units IS NULL THEN 'MISSING_IN_WMS'
            WHEN t.units IS NULL THEN 'MISSING_IN_TMS'
            ELSE 'QUANTITY_MISMATCH' END AS rule
FROM keys k
LEFT JOIN totals w ON w.source='WMS' AND w.shipment_id=k.shipment_id AND w.sku=k.sku
LEFT JOIN totals t ON t.source='TMS' AND t.shipment_id=k.shipment_id AND t.sku=k.sku
WHERE w.units IS NULL OR t.units IS NULL OR w.units<>t.units
ORDER BY k.shipment_id,k.sku;

-- Trace the original source records for a selected discrepancy.
SELECT * FROM source_records
WHERE run_id = 1 AND shipment_id = 'SHP-2402'
ORDER BY source, record_id;

-- Audit sequence and content fingerprint for reproducibility.
SELECT r.id, r.label, r.fingerprint, r.rule_version, a.event, a.created_at
FROM runs r JOIN audit_events a ON a.run_id = r.id
ORDER BY a.id;
