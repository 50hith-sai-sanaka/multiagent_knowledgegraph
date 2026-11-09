# ProGRESS – Provenance‑Grounded Multi‑Agent Knowledge Graph

**A research‑grade system for ingesting, coordinating, and querying high‑volume Cyber Threat Intelligence (CTI) feeds.**

---

## 📖 Overview

- **Goal**: Build a multi‑agent, provenance‑aware CTI knowledge graph that can safely ingest feeds from ThreatFox, URLhaus, MalwareBazaar, and AlienVault OTX.
- **Key novelty**: Three coordination protocols are implemented and benchmarked:
  1. **Ad‑Hoc** – baseline, direct concurrent writes (intentionally produces conflicts).
  2. **MPAC** – full Multi‑Principal Agent Coordination protocol with session lifecycle, semantic locking, conflict detection, arbitration, and provenance tracking.
  3. **MPAC‑Ablation** – same as MPAC but with one component disabled at a time to show causal impact.
- **Outcome**: A Neo4j graph that stores both *domain entities* (Malware, IP, Domain, URL, FileHash) **and** a full provenance meta‑layer (`Claim`, `Evidence`, `Principal`, `Agent`, `Decision`, `Conflict`).

---

## 🚀 Quick Start

### 1️⃣ Prerequisites

- **Python 3.9+** (the project was built with 3.9).
- **Docker** (for the Neo4j and Redis containers).  Install from <https://docs.docker.com/get-docker/>.
- **Git** (obviously).
- **Make** (optional, for the convenience scripts).

### 2️⃣ Clone & Install

```bash
# Clone the repository (already done for you)
git clone https://github.com/50hith-sai-sanaka/multiagent_knowledgegraph.git
cd multiagent_knowledgegraph

# Create a fresh virtual environment (the old `venv/` was removed from git)
python -m venv venv
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3️⃣ Start supporting services

```bash
# Spin up Neo4j (5.20) and Redis (7.2) containers
docker-compose up -d   # brings up neo4j and redis
```

Verify they are running:

```bash
curl http://localhost:7474          # Neo4j Browser should respond
redis-cli ping                      # should return PONG
```

### 4️⃣ Initialise the database schema

```bash
python -c "from src.db.neo4j_client import Neo4jClient; Neo4jClient().initialize_schema()"
```

You should see a log confirming that **14 constraints** and **3 indexes** were created.

### 5️⃣ Run the ingestion pipeline (default: MPAC protocol)

```bash
PYTHONPATH=. ./venv/bin/python run_pipeline.py --protocol mpac
```

The pipeline will:
1. Load normalized CTI records from `data/normalized/`.
2. Spawn four principal agents (ThreatFox, URLhaus, MalwareBazaar, OTX).
3. Each agent extracts claims, runs peer‑verification (A2A), and submits to the chosen coordinator.
4. The coordinator writes domain nodes *and* provenance nodes atomically.

You will see a JSON summary printed with fields such as `operation_id`, `status`, `latency_ms`, and `conflict_detected`.

---

## 🏗️ Architecture at a Glance

```text
+-------------------+       +-------------------+       +-------------------+
|   ThreatFox M­C P |       |   URLhaus M‑C P   |  …   |   OTX MCP Tool    |
+-------------------+       +-------------------+       +-------------------+
          \                       |                        /
           \                      |                       /
            \                     v                      /
            +-------------------------------------------+
            |           Agent State Machine (LangGraph) |
            +-------------------------------------------+
                         |        ^
                         |        |
                         v        |
               +---------------------------+
               |   CoordinationAdapter     |
               |  (Ad‑Hoc / MPAC / Ablation) |
               +---------------------------+
                         |
                         v
                +-------------------+   Neo4j Graph DB (5.20)
                |   Domain Layer   |
                | Provenance Layer |
                +-------------------+
```

- **MCP** – Model Context Protocol, a thin wrapper around each feed’s API.
- **A2A (G²CP)** – Graph‑Grounded communication between agents for peer consensus.
- **Lock Manager** – Redis‑backed semantic locks to avoid write races.
- **Arbitration Engine** – Weighted decision based on authority, confidence, and consensus.

---

## 📊 Benchmark & Evaluation

Run the full benchmark suite (all three protocols + three ablation variants):

```bash
PYTHONPATH=. ./venv/bin/python benchmark/runner.py
```

Results are saved to `data/results/benchmark_results.json` and visualisations are generated in `data/results/charts/`.

Key metrics:
- **Graph Integrity Rate (GIR)** – % of edges free from corruption.
- **Conflict Resolution Accuracy (CRA)** – % of conflicts correctly arbitrated.
- **Provenance Traceability Completeness (PTC)** – % of domain entities with an unbroken provenance chain.
- **Coordination Latency** – wall‑clock overhead per operation.

---

## 🛠️ Development Workflow

| Sprint | Stories | Points |
|--------|---------|--------|
| **1** | Neo4j setup, Pydantic models, Ontology validator, Redis lock manager | **23** |
| **2** | Ad‑Hoc coordinator, Conflict detector, Full MPAC, MPAC‑Ablation | **26** |
| **3** | MCP adapters, A2A hub, LangGraph agent state machine | **24** |
| **4** | FastAPI gateway, GraphRAG retriever | **13** |
| **5** | Benchmark harness, results analysis | **13** |

All tests can be run with:

```bash
pytest tests/ -v
```

The repository is configured for CI – the CI pipeline runs the full test suite on every push.

---

## 🤝 Contributing

1. Fork the repo.
2. Create a feature branch (`git checkout -b feat/my‑feature`).
3. Write tests for any new code.
4. Ensure `pytest` passes locally.
5. Open a Pull Request – CI will verify formatting, linting, and tests.

Please keep the `venv/` directory out of version control; the `.gitignore` already excludes it.

---

## 📄 License

This project is released under the **Apache 2.0 License**. See `LICENSE` for details.

---

## 📞 Contact

- **Lead Architect**: Sohith Sai – `sohithsai@example.com`
- **Project Repo**: <https://github.com/50hith-sai-sanaka/multiagent_knowledgegraph>

Happy hacking! 🎉
