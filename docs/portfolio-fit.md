# Portfolio scope comparison

Reviewed on September 30, 2026 against the live portfolio and its repository README:
https://sfskhalsa101.github.io/hari-simran-khalsa-portfolio/
https://github.com/sfskhalsa101/hari-simran-khalsa-portfolio

| Existing project | Existing question | FlowCheck's different question |
| --- | --- | --- |
| Sort staffing & door assignment | How should people and doors be allocated to process volume? | Do warehouse and transportation exports agree? |
| Dispatch exception dashboard | Which late arrivals, missing scans, or service risks need attention? | Which cross-system line records are missing or quantitatively inconsistent? |
| AIncident | How was an operational reporting product built, delivered, and sold? | Can a data discrepancy be reproduced, traced, corrected upstream, and verified? |

Shared logistics vocabulary and an interface for reviewing problems are expected. The core work is distinct: data contracts, batch ingestion, normalized composite keys, SQLite persistence, deterministic reconciliation, idempotency, and retained source evidence. There is no staffing calculator, route optimizer, arrival-priority queue, or AI incident report.

The experience connection is the portfolio's Hidaka TMS/WMS work and Schneider implementation/transportation coordination. The project is a new independent demonstration, not software claimed to have run at those employers.

The initial DispatchIQ concept was dropped before implementation because dispatch and staffing functionality was already present in the portfolio.
