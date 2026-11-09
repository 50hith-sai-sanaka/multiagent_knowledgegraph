# ProGRESS Research Report
## Comparative Evaluation of Multi-Agent Coordination Protocols for CTI Knowledge Graph Construction

**Date:** 2026-11-08  
**Dataset:** 16,270 normalized CTI records; 12,012 unique IOCs; 259 cross-source overlaps; 63 verified conflicts.  
**Workload:** 200 records per protocol run; 4 concurrent agents; 5 protocols compared.

---

## 1. Research Questions

- **RQ1:** Does multi-phase agent coordination (MPAC) produce a more consistent, provenance-grounded knowledge graph than uncoordinated writes (Ad-Hoc)?
- **RQ2:** Which component of MPAC (peer A2A consensus, distributed locking, or timestamp arbitration) contributes most causally to graph quality?

---

## 2. Results Summary

| Protocol | GIR (%) ↓ | CR (%) ↑ | CRA (%) ↑ | PTC (%) ↑ | Mean Latency (ms) ↓ | p95 Latency (ms) ↓ |
|---|---|---|---|---|---|---|
| **Ad-Hoc (Baseline)** | 18.5 | 0.0 | 0.0 | 12.0 | 0.9 | 1.3 |
| **Full MPAC** | **2.1** | **88.0** | **76.5** | **100.0** | 12.2 | 17.0 |
| **Ablation No A2A** | 5.4 | 71.0 | 68.0 | 100.0 | 10.6 | 14.6 |
| **Ablation No Locks** | 10.2 | 79.0 | 70.0 | 100.0 | 9.1 | 10.9 |
| **Ablation Timestamp** | 7.8 | 75.0 | 65.0 | 100.0 | 10.0 | 14.1 |

---

## 3. Discussion

### RQ1: MPAC vs. Ad-Hoc
- **GIR (Graph Inconsistency Rate):** Full MPAC achieved a GIR of **2.1%** compared to **18.5%** under Ad-Hoc. This demonstrates that multi-phase coordination reduces graph inconsistency by **16.4 percentage points**, preventing race-condition overwrites and unrecorded contradictions.
- **CR & CRA (Conflict Resolution):** Ad-Hoc performs no conflict detection ($CR=0.0\%$, $CRA=0.0\%$), whereas MPAC resolved **88.0%** of conflicting assertions with **76.5%** accuracy against ground-truth CTI attribution.
- **PTC (Provenance Trail Completeness):** Full MPAC maintains an unbroken 3-hop provenance chain for **100.0%** of entities (`DomainEntity -> Claim -> Evidence -> Principal`), while Ad-Hoc achieved only **12.0%** due to uncoordinated blind `MERGE` writes.
- **Latency Tradeoff:** The coordination overhead incurred by MPAC resulted in a mean latency of **12.2 ms** (p95: **17.0 ms**) compared to **0.9 ms** for Ad-Hoc. This sub-20ms latency remains exceptionally fast and acceptable for real-time cyber defense operations given the massive accuracy and provenance gains.

### RQ2: Ablation Analysis — Which Component Degraded Most?
- The worst-performing ablation was **`ablation_no_locks`**, where removing semantic distributed locking caused the Graph Inconsistency Rate to jump from **2.1%** to **10.2%** (a 4.8x degradation in graph integrity).
- Removing timestamp-ordered arbitration (`ablation_timestamp`) degraded CRA from **76.5%** to **65.0%**.
- Disabling peer consensus verification (`ablation_no_a2a`) degraded Conflict Resolution Rate from **88.0%** to **71.0%**.
- **Conclusion on Causality:** Distributed semantic locking is the single most critical mechanism for preventing state corruption, followed closely by peer consensus and timestamp arbitration for attribution accuracy.

---

## 4. Conclusion
Full MPAC coordination decisively outperforms uncoordinated Ad-Hoc baselines across all graph quality metrics ($GIR$, $CR$, $CRA$, $PTC$) with acceptable sub-20ms overhead. For multi-agent cyber threat intelligence systems, distributed semantic locking coupled with graph-grounded peer verification is indispensable for building reliable, audited knowledge graphs.

---

## 5. Artifacts
- Raw benchmark data: `data/results/benchmark_results.json`
- Comparison table: `data/results/comparison_table.md`
- Visualizations:
  - `data/results/charts/gir.png`
  - `data/results/charts/cr.png`
  - `data/results/charts/cra.png`
  - `data/results/charts/ptc.png`
  - `data/results/charts/latency.png`
