# STORY-001: Neo4j Docker Setup & Schema Initialization
## Complete Step-by-Step Execution Guide

| Field | Details |
|---|---|
| **Story ID** | STORY-001 |
| **Sprint** | Sprint 1 |
| **Points** | 5 |
| **Lead** | @member1 |
| **Support** | @member2 |
| **Estimated Time** | ~6 hours total |
| **Prerequisite** | Phase 1 tests must pass — verify in Section 0 first |

---

> **HOW TO USE THIS GUIDE**
> Read every word before typing any command. Each task has:
> - A **WHY** block — explains the purpose in plain English
> - An **exact code block** — copy-paste it exactly as shown, never retype manually
> - A **VERIFICATION CHECK** — run this immediately after the step. If it passes, move forward. If it fails, read the **IF IT FAILS** block before doing anything else.
>
> **Never skip a verification check. Never jump ahead.**

---

## Section 0 — Pre-Flight Checks

Run all 6 checks before writing a single line of code.

---

### Check 0.1 — Confirm Working Directory

```bash
pwd
```

**VERIFICATION CHECK 0.1**
You must see:
```
/Users/sohithsai/multiagent_knowledgegraph
```

**IF IT FAILS:**
```bash
cd /Users/sohithsai/multiagent_knowledgegraph
pwd
```

---

### Check 0.2 — Phase 1 Tests Pass

**WHY:** Before adding anything new, confirm existing code works. If Phase 1 is broken before you start, you cannot tell later if you broke it.

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_data_pipeline.py -v
```

**VERIFICATION CHECK 0.2**
Must end with: `2 passed`

**IF IT FAILS:** Do NOT proceed. Fix Phase 1 tests first. Check if you accidentally modified a source file.

---

### Check 0.3 — Docker Is Installed

**WHY:** Neo4j will run inside a Docker container. Docker must exist on your Mac.

```bash
docker --version
```

**VERIFICATION CHECK 0.3**
Output shows `Docker version 2x.x.x` — any version above 20 is fine.

**IF IT FAILS:**
1. Go to `https://www.docker.com/products/docker-desktop/`
2. Download **Docker Desktop for Mac** and install it
3. Open Docker Desktop from Applications, wait for the whale icon in your menu bar
4. Run `docker --version` again

---

### Check 0.4 — Docker Engine Is Running

```bash
docker ps
```

**VERIFICATION CHECK 0.4**
Must show a table header (even if the table is empty):
```
CONTAINER ID   IMAGE   COMMAND   CREATED   STATUS   PORTS   NAMES
```

**IF IT FAILS:** Docker is not running. Open Docker Desktop from Applications, wait 30 seconds, then run `docker ps` again.

---

### Check 0.5 — No Port Conflicts

**WHY:** Neo4j uses ports 7687 and 7474. Redis uses 6379. If something else is already on these ports, the containers will fail to start.

Run each command separately:

```bash
lsof -i :7687
```

```bash
lsof -i :7474
```

```bash
lsof -i :6379
```

**VERIFICATION CHECK 0.5**
Each command must return **blank output** — nothing at all. Blank means the port is free.

**IF YOU SEE OUTPUT (a process is using the port):**
```bash
# If Neo4j is installed locally via Homebrew:
brew services stop neo4j

# If a Docker container is using the port:
docker ps
docker stop <container_name_from_list>
```
Run the `lsof` commands again and confirm blank output.

---

### Check 0.6 — Venv Python Works

```bash
./venv/bin/python3 --version
```

**VERIFICATION CHECK 0.6**
Must show: `Python 3.9.6`

**IF IT FAILS:**
```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

---

**All 6 pre-flight checks passed? Now begin the tasks.**

---

## TASK INF-001 — Create docker-compose.yml and Start Containers

**Estimated time: 1 hour**

### WHY

Your 16,270 CTI records are flat JSON files — there are no connections between them. The goal of this entire project is to build a **Knowledge Graph**: a database where `(RedLine)-[USES_C2]->(185.220.101.4)` is a real relationship you can query. Neo4j is that graph database.

Docker runs Neo4j in an isolated "container" on your Mac — no permanent installation needed. When you are done with the project, you can stop or delete the container without affecting anything else on your Mac.

You also start **Redis** in the same file. Redis handles distributed locks in STORY-003. Starting both now means one less step later.

---

### Step INF-001-A — Add Neo4j Credentials to .env

**WHY:** Hardcoding passwords in files is a security risk — anyone who can read the file can see the password. The project already uses a `.env` file for API keys. Add the database credentials there too so they are never committed to git and can be changed without editing code.

```bash
# Add these lines to your existing .env file
cat >> .env << 'ENVEOF'

# Neo4j database credentials (used by docker-compose + Python client)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=[configure NEO4J_PASSWORD locally]

# Redis URL
REDIS_URL=redis://localhost:6379
ENVEOF
```

**VERIFICATION CHECK INF-001-A (env)**
```bash
grep "NEO4J_PASSWORD" .env
```
Must show: `NEO4J_PASSWORD=[configure NEO4J_PASSWORD locally]`

**IF MISSING:** Run the `cat >> .env` block above again.

---

### Step INF-001-B — Create docker-compose.yml

Open your Terminal (confirm you are in `/Users/sohithsai/multiagent_knowledgegraph`) and run this full block:

```bash
cat > docker-compose.yml << 'COMPOSEOF'
version: "3.8"

services:

  neo4j:
    image: neo4j:5.20.0
    container_name: neo4j-cti
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: ${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:?NEO4J_PASSWORD must be set in .env}
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    restart: unless-stopped

  redis:
    image: redis:7.2-alpine
    container_name: redis-cti
    ports:
      - "6379:6379"
    restart: unless-stopped

volumes:
  neo4j_data:
  neo4j_logs:
COMPOSEOF
```

**VERIFICATION CHECK INF-001-B (docker-compose.yml)**
```bash
cat docker-compose.yml
```
You must see the full file printed. Confirm these exact lines exist:
- `image: neo4j:5.20.0`
- `NEO4J_AUTH: ${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:?` (the env-var form, not a hardcoded password)
- `image: redis:7.2-alpine`

Also verify docker-compose can see the env var:
```bash
docker compose config | grep NEO4J_AUTH
```
Must show the resolved value: `NEO4J_AUTH: neo4j/[configure NEO4J_PASSWORD locally]`

**IF docker compose config shows an error about NEO4J_PASSWORD:**
The `.env` file doesn't have the variable. Go back to Step INF-001-A.

**IF ANY LINE IS MISSING:** Delete the file and repeat:
```bash
rm docker-compose.yml
```
Then repeat Step INF-001-B.

---

### Step INF-001-B — Pull Docker Images

**WHY:** Docker needs to download the Neo4j and Redis software images from the internet. This only happens once — future runs use the cached copies.

```bash
docker compose pull
```

This takes 2–5 minutes. Progress bars will scroll by. This is normal.

**VERIFICATION CHECK INF-001-B**
The command completes with no `ERROR` lines. The last lines say:
```
✔ neo4j Pulled
✔ redis Pulled
```

**IF IT FAILS:** Check your internet connection. If it says `permission denied`, make sure Docker Desktop is running (Check 0.4).

---

### Step INF-001-C — Start the Containers

```bash
docker compose up -d
```

The `-d` flag means "detached" — it starts containers in the background and returns your terminal immediately.

**VERIFICATION CHECK INF-001-C**
```bash
docker ps
```
You must see **two rows** with `Up` in the STATUS column:
```
CONTAINER ID   IMAGE              STATUS          NAMES
abc123...      neo4j:5.20.0      Up X seconds    neo4j-cti
def456...      redis:7.2-alpine  Up X seconds    redis-cti
```

**IF STATUS shows "Exited" or a container is missing:**
```bash
docker compose logs neo4j
```
Read the error output. Most common causes and fixes:
- Port still in use → Go back to Check 0.5, free the port, then run `docker compose up -d` again
- Disk space → `docker system prune` to free space

---

### Step INF-001-D — Wait for Neo4j to Initialize

**WHY:** After Docker starts the Neo4j container, Neo4j needs 30–60 seconds to boot its internal database engine. If you connect too early, it refuses. This wait is mandatory.

```bash
sleep 45
```

Your terminal appears frozen for 45 seconds. This is normal.

---

### Step INF-001-E — Verify Neo4j Browser

Open your web browser and go to: **`http://localhost:7474`**

You must see the **Neo4j Browser** login page. Enter:
- **Username:** `neo4j`
- **Password:** `[configure NEO4J_PASSWORD locally]`

Click **Connect**. You should see a dark dashboard with a search bar at the top.

Type this in the search bar and press **Ctrl+Enter** (or click the play button):
```cypher
RETURN "Hello from Neo4j!" AS message
```

**VERIFICATION CHECK INF-001-E — Browser**
A green result card appears showing: `"Hello from Neo4j!"`

**IF THE BROWSER CANNOT CONNECT:** Neo4j is not ready. Wait 30 more seconds, refresh the browser. If it still fails after 2 minutes:
```bash
docker compose logs neo4j | tail -20
```
Look for the word `Started` near the bottom.

---

### Step INF-001-F — Verify Redis

```bash
docker exec redis-cti redis-cli ping
```

**VERIFICATION CHECK INF-001-F**
Must show exactly: `PONG`

**IF IT FAILS:**
```bash
docker compose restart redis
```
Wait 10 seconds, then try again.

---

**TASK INF-001 COMPLETE**

What you now have:
- Neo4j 5.20 at `localhost:7687` (database) and `localhost:7474` (browser UI)
- Redis 7.2 at `localhost:6379`
- Both containers restart automatically if your Mac reboots

---

## TASK INF-002 — Update requirements.txt and Install All Dependencies

**Estimated time: 1 hour**

### WHY

Your current `requirements.txt` has only 4 Phase 1 libraries. The full project across all 5 sprints needs 15 libraries. Installing everything now — in one shot — prevents broken imports in later sprints.

---

### Step INF-002-A — Replace requirements.txt

```bash
cat > requirements.txt << 'REQEOF'
# Phase 1 (existing — do not remove)
pydantic>=2.0.0
httpx>=0.24.0
python-dotenv>=1.0.0
pytest>=7.0.0

# STORY-001: Neo4j database driver + async test support
neo4j>=5.18.0
pytest-asyncio>=0.23.0

# STORY-003: Redis distributed locks
redis>=5.0.0

# STORY-008/009/010: LLM agent frameworks
langchain>=0.2.0
langchain-openai>=0.1.0
langgraph>=0.1.0

# STORY-011: FastAPI REST gateway + ASGI server
fastapi>=0.110.0
uvicorn>=0.28.0

# STORY-002B: Ontology semantic similarity
sentence-transformers>=2.7.0

# STORY-014: Benchmark chart generation
matplotlib>=3.8.0
REQEOF
```

**VERIFICATION CHECK INF-002-A**
```bash
grep "neo4j" requirements.txt
```
Must show: `neo4j>=5.18.0`

Also confirm the file has all sections:
```bash
cat requirements.txt
```

---

### Step INF-002-B — Install All Dependencies

```bash
./venv/bin/pip install -r requirements.txt
```

This takes 3–8 minutes. Many lines of output are normal.

**VERIFICATION CHECK INF-002-B**
The final line must contain `Successfully installed`. No `ERROR` lines anywhere.

Then run:
```bash
./venv/bin/python3 -c "import neo4j; print('neo4j version:', neo4j.__version__)"
```
Must show: `neo4j version: 5.x.x`

**IF neo4j import fails:**
```bash
./venv/bin/pip install "neo4j>=5.18.0"
```

**IF sentence-transformers times out:**
```bash
./venv/bin/pip install "sentence-transformers>=2.7.0" --timeout 120
```

---

### Step INF-002-C — Confirm Phase 1 Still Passes

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_data_pipeline.py -v
```

**VERIFICATION CHECK INF-002-C**
Must show: `2 passed`

**IF IT FAILS (a new package conflicted):**
```bash
./venv/bin/pip install "pydantic>=2.0.0" "httpx>=0.24.0" --force-reinstall
```
Then run the test again.

---

**TASK INF-002 COMPLETE**

---

## TASKS INF-003 + INF-004 — Create src/ Directory and neo4j_client.py

**Estimated time: 3 hours combined**

### WHY

There is no `src/` folder yet. From Phase 2 onward, all new code lives inside `src/` organized by responsibility:
- `src/db/` — database connection (this task)
- `src/coordination/` — agent protocols (Sprint 2)
- `src/agents/` — LangGraph workflows (Sprint 3)
- etc.

`neo4j_client.py` is the **central file every other component uses** to talk to Neo4j. If it breaks, everything breaks. It is written once and tested thoroughly.

INF-003 and INF-004 are combined here because `initialize_schema()` lives inside `neo4j_client.py` — there is no separate file for INF-004.

**This file implements the Two-Tier Hybrid Schema at the database layer:**
- **Tier 1 (Static):** 8 Tier 1 node types and 8 Tier 1 relationship types are hardcoded as `frozenset` constants — they never change. 14 uniqueness constraints enforce integrity at the DB level.
- **Tier 2 (Dynamic):** Any new entity type or relationship type an agent thinks should exist goes through `validate_and_register_type()`. This writes an `OntologyTerm` node with status `PENDING`. When a second agent confirms it, the status becomes `APPROVED`. Only then can agents use `create_dynamic_node()` or `create_dynamic_relationship()` with that new type.
- **Why both tiers here:** The STORY-002B `OntologyValidator` adds semantic similarity on top. But even before that validator exists, the Neo4jClient itself enforces the governance rule: **no unapproved labels can be written to the graph**. This makes the system safe from day one.

---

### Step INF-003-A — Create the Directory Structure

```bash
mkdir -p src/db src/coordination src/ontology src/mcp src/agents src/rag src/api src/utils
```

Create the `__init__.py` files (these empty files tell Python that each folder is a package that can be imported):

```bash
touch src/__init__.py
touch src/db/__init__.py
touch src/coordination/__init__.py
touch src/ontology/__init__.py
touch src/mcp/__init__.py
touch src/agents/__init__.py
touch src/rag/__init__.py
touch src/api/__init__.py
touch src/utils/__init__.py
```

**VERIFICATION CHECK INF-003-A**
```bash
find src -name "__init__.py" | sort
```
Must list exactly 9 files:
```
src/__init__.py
src/agents/__init__.py
src/api/__init__.py
src/coordination/__init__.py
src/db/__init__.py
src/mcp/__init__.py
src/ontology/__init__.py
src/rag/__init__.py
src/utils/__init__.py
```

**IF ANY FILE IS MISSING:** Run the missing `touch` command. Then run `find` again.

---

### Step INF-003-B — Create src/db/neo4j_client.py

This is the most important file in this story. It implements the **Two-Tier Hybrid Schema** at the database layer. Save this as `src/db/neo4j_client.py`:

```python
"""
Neo4j Async Client — Two-Tier Hybrid Schema
File: src/db/neo4j_client.py
Story: STORY-001 (Tasks INF-003 + INF-004)

TWO-TIER ARCHITECTURE:
  Tier 1 (Static): 8 fixed node types + 8 fixed relationship types.
                   Hardcoded as frozensets. Never change.
                   All Tier 1 nodes stamp node_schema_version='1.0'.

  Tier 2 (Dynamic): Any type an agent proposes goes through
                    validate_and_register_type(). Requires 2 distinct
                    agent confirmations before status becomes APPROVED.
                    Approved types stamp node_schema_version='2.0'.

AGENT ACCESS RULES:
  - Agents NEVER call run() with arbitrary Cypher.
  - Agents call validate_and_register_type() to propose new types.
  - Agents call create_dynamic_node() / create_dynamic_relationship()
    for all writes (both Tier 1 and Tier 2 approved types).
  - All full coordination (locking, conflict detection, provenance)
    is handled by the MPAC coordinator (STORY-006).
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver

logger = logging.getLogger(__name__)


# ── Tier 1 Static Vocabulary ──────────────────────────────────────────────────
# Frozen constants. Agents cannot modify these.
# OntologyValidator (STORY-002B) adds semantic similarity on top.

TIER1_NODE_TYPES: frozenset = frozenset({
    "Malware", "ThreatActor", "Campaign",
    "IP", "Domain", "URL", "FileHash", "AttackTechnique",
})

TIER1_RELATIONSHIP_TYPES: frozenset = frozenset({
    "USES_C2", "DISTRIBUTED_VIA", "HOSTED_ON", "ATTRIBUTED_TO",
    "PART_OF", "EXPLOITS", "TARGETS", "MITIGATED_BY",
})


class Neo4jClient:
    """
    Async Neo4j client with Two-Tier Hybrid Schema support.

    Credentials read from .env:
      NEO4J_URI      bolt://localhost:7687
      NEO4J_USER     neo4j
      NEO4J_PASSWORD [configure NEO4J_PASSWORD locally]
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "[configure NEO4J_PASSWORD locally]")
        self._driver: Optional[AsyncDriver] = None

    # ── Connection Lifecycle ──────────────────────────────────────────────────

    async def connect(self) -> None:
        """Open connection pool. Call before any other method."""
        self._driver = AsyncGraphDatabase.driver(
            self.uri, auth=(self.user, self.password)
        )
        await self._driver.verify_connectivity()
        logger.info("Neo4j connection pool opened at %s", self.uri)

    async def close(self) -> None:
        """Gracefully close connection pool. Always call on shutdown."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection pool closed.")

    # ── Raw Query (INTERNAL / INFRASTRUCTURE USE ONLY) ────────────────────────

    async def run(
        self,
        cypher: str,
        parameters: Optional[dict] = None,
    ) -> list:
        """
        Execute any Cypher query. Returns list of dicts.

        INTERNAL INFRASTRUCTURE USE ONLY.
        Agents must never call run() with arbitrary Cypher.
        Use create_dynamic_node() or create_dynamic_relationship() instead.
        """
        if self._driver is None:
            raise RuntimeError(
                "Neo4jClient is not connected. Call await client.connect() first."
            )
        async with self._driver.session() as session:
            result = await session.run(cypher, parameters or {})
            records = await result.data()
        return records

    # ── Schema Initialization ─────────────────────────────────────────────────

    async def initialize_schema(self) -> None:
        """
        Apply all constraints and indexes. IDEMPOTENT (IF NOT EXISTS).

        Sets up:
          Tier 1: 14 uniqueness constraints for all Tier 1 + provenance types
          Tier 2: OntologyTerm constraint + 4 indexes for fast governance lookup

        Safe to call multiple times — never raises on duplicate.
        """
        constraints = [
            # ── Tier 1 Core Entity Constraints ────────────────────────────────
            "CREATE CONSTRAINT cst_malware_name IF NOT EXISTS "
            "FOR (m:Malware) REQUIRE m.name IS UNIQUE",

            "CREATE CONSTRAINT cst_threat_actor_name IF NOT EXISTS "
            "FOR (a:ThreatActor) REQUIRE a.name IS UNIQUE",

            "CREATE CONSTRAINT cst_campaign_id IF NOT EXISTS "
            "FOR (c:Campaign) REQUIRE c.id IS UNIQUE",

            "CREATE CONSTRAINT cst_ip_value IF NOT EXISTS "
            "FOR (i:IP) REQUIRE i.value IS UNIQUE",

            "CREATE CONSTRAINT cst_domain_value IF NOT EXISTS "
            "FOR (d:Domain) REQUIRE d.value IS UNIQUE",

            "CREATE CONSTRAINT cst_url_value IF NOT EXISTS "
            "FOR (u:URL) REQUIRE u.value IS UNIQUE",

            "CREATE CONSTRAINT cst_hash_sha256 IF NOT EXISTS "
            "FOR (h:FileHash) REQUIRE h.sha256 IS UNIQUE",

            "CREATE CONSTRAINT cst_technique_id IF NOT EXISTS "
            "FOR (t:AttackTechnique) REQUIRE t.id IS UNIQUE",

            # ── Provenance Meta-Layer ─────────────────────────────────────────
            "CREATE CONSTRAINT cst_claim_id IF NOT EXISTS "
            "FOR (c:Claim) REQUIRE c.id IS UNIQUE",

            "CREATE CONSTRAINT cst_evidence_id IF NOT EXISTS "
            "FOR (e:Evidence) REQUIRE e.id IS UNIQUE",

            "CREATE CONSTRAINT cst_principal_id IF NOT EXISTS "
            "FOR (p:Principal) REQUIRE p.id IS UNIQUE",

            "CREATE CONSTRAINT cst_conflict_id IF NOT EXISTS "
            "FOR (cf:Conflict) REQUIRE cf.id IS UNIQUE",

            "CREATE CONSTRAINT cst_decision_id IF NOT EXISTS "
            "FOR (dc:Decision) REQUIRE dc.id IS UNIQUE",

            # ── Tier 2 Dynamic Extension Registry ────────────────────────────
            "CREATE CONSTRAINT cst_ontology_term_id IF NOT EXISTS "
            "FOR (o:OntologyTerm) REQUIRE o.term_id IS UNIQUE",
        ]

        indexes = [
            "CREATE INDEX idx_claim_subject_predicate IF NOT EXISTS "
            "FOR (c:Claim) ON (c.subject, c.predicate)",

            "CREATE INDEX idx_evidence_source_record IF NOT EXISTS "
            "FOR (e:Evidence) ON (e.source, e.record_id)",

            # OntologyTerm indexes for fast dynamic type governance
            "CREATE INDEX idx_ontology_term_name IF NOT EXISTS "
            "FOR (o:OntologyTerm) ON (o.term_name, o.status)",

            "CREATE INDEX idx_ontology_term_type IF NOT EXISTS "
            "FOR (o:OntologyTerm) ON (o.term_type)",
        ]

        if self._driver is None:
            raise RuntimeError(
                "Neo4jClient is not connected. Call await client.connect() first."
            )

        async with self._driver.session() as session:
            for stmt in constraints:
                await session.run(stmt)
                logger.debug("Applied: %s", stmt[:70])
            for stmt in indexes:
                await session.run(stmt)
                logger.debug("Applied: %s", stmt[:70])

        logger.info(
            "Schema initialized: %d constraints, %d indexes.",
            len(constraints), len(indexes),
        )

    # ── Tier 2 Dynamic Type Governance ────────────────────────────────────────

    async def validate_and_register_type(
        self,
        term_name: str,
        term_type: str,
        proposing_agent: str,
    ) -> Dict[str, Any]:
        """
        Database-level type governance for agent-proposed types.

        Decision flow:
          1. Exact Tier 1 match              → MERGE  (no DB write)
          2. Already APPROVED in OntologyTerm → APPROVED
          3. Already PENDING → increment count:
             a. count reaches 2 → auto-approve → APPROVE
             b. count < 2       → PENDING
          4. Brand new term → write PENDING

        Args:
          term_name:       e.g. "CryptoWallet", "FUNDS_VIA"
          term_type:       "NODE_LABEL" or "RELATIONSHIP_TYPE"
          proposing_agent: e.g. "Agent-ThreatFox"

        Returns:
          Dict: {decision, term_id, target_type, reason}
        """
        if term_type not in ("NODE_LABEL", "RELATIONSHIP_TYPE"):
            raise ValueError(
                f"term_type must be 'NODE_LABEL' or 'RELATIONSHIP_TYPE', got {term_type!r}"
            )

        tier1 = TIER1_NODE_TYPES if term_type == "NODE_LABEL" else TIER1_RELATIONSHIP_TYPES

        # Step 1: Exact Tier 1 Match — no DB write needed
        if term_name in tier1:
            return {
                "decision":    "MERGE",
                "term_id":     None,
                "target_type": term_name,
                "reason":      f"Exact Tier 1 match: use existing type '{term_name}'",
            }

        # Step 2/3: Check existing OntologyTerm
        rows = await self.run(
            "MATCH (o:OntologyTerm {term_name: $n, term_type: $t}) "
            "RETURN o.term_id AS id, o.status AS status, "
            "       o.confirmation_count AS cnt",
            {"n": term_name, "t": term_type},
        )

        if rows:
            row         = rows[0]
            existing_id = row["id"]
            status      = row["status"]
            count       = int(row["cnt"] or 1)

            if status == "APPROVED":
                return {
                    "decision":    "APPROVED",
                    "term_id":     existing_id,
                    "target_type": term_name,
                    "reason":      f"Already an approved Tier 2 type: '{term_name}'",
                }

            new_count = count + 1
            if new_count >= 2:
                # Auto-approve on 2nd confirmation
                await self.run(
                    "MATCH (o:OntologyTerm {term_id: $id}) "
                    "SET o.status = 'APPROVED', "
                    "    o.confirmation_count = $c, "
                    "    o.approved_at = timestamp()",
                    {"id": existing_id, "c": new_count},
                )
                logger.info("OntologyTerm APPROVED: %s (%d confirmations)", term_name, new_count)
                return {
                    "decision":    "APPROVE",
                    "term_id":     existing_id,
                    "target_type": term_name,
                    "reason":      f"'{term_name}' approved after {new_count} agent confirmations",
                }
            else:
                await self.run(
                    "MATCH (o:OntologyTerm {term_id: $id}) SET o.confirmation_count = $c",
                    {"id": existing_id, "c": new_count},
                )
                return {
                    "decision":    "PENDING",
                    "term_id":     existing_id,
                    "target_type": term_name,
                    "reason":      f"'{term_name}' is PENDING ({new_count}/2 confirmations)",
                }

        # Step 4: Brand New Term — write PENDING
        term_id = str(uuid.uuid4())
        await self.run(
            "MERGE (o:OntologyTerm {term_id: $term_id}) "
            "SET o.term_name          = $name, "
            "    o.term_type          = $type, "
            "    o.status             = 'PENDING', "
            "    o.confirmation_count = 1, "
            "    o.proposed_by        = $agent, "
            "    o.proposed_at        = timestamp(), "
            "    o.schema_version_assigned = 'pending'",
            {"term_id": term_id, "name": term_name, "type": term_type, "agent": proposing_agent},
        )
        logger.info("OntologyTerm PENDING: %s (proposed by %s)", term_name, proposing_agent)
        return {
            "decision":    "PENDING",
            "term_id":     term_id,
            "target_type": term_name,
            "reason":      f"New type '{term_name}' registered as PENDING (1/2 confirmations needed)",
        }

    # ── Dynamic Node Writer ───────────────────────────────────────────────────

    async def create_dynamic_node(
        self,
        label: str,
        key: str,
        value: str,
        properties: Optional[Dict[str, Any]] = None,
        principal: str = "unknown",
    ) -> bool:
        """
        MERGE a node with any validated label (Tier 1 OR approved Tier 2).

        Raises ValueError for labels that are neither Tier 1 nor APPROVED.

        node_schema_version:
          '1.0' → Tier 1 type
          '2.0' → approved Tier 2 type
        """
        is_tier1 = label in TIER1_NODE_TYPES

        if not is_tier1:
            approved = await self.run(
                "MATCH (o:OntologyTerm {term_name: $n, term_type: 'NODE_LABEL', "
                "       status: 'APPROVED'}) RETURN o.term_id AS id",
                {"n": label},
            )
            if not approved:
                raise ValueError(
                    f"Label '{label}' is neither Tier 1 nor an approved Tier 2 type. "
                    f"Call validate_and_register_type('{label}', 'NODE_LABEL', agent) "
                    "and get a second agent to confirm."
                )

        props = dict(properties or {})
        props[key]                    = value
        props["node_schema_version"]  = "1.0" if is_tier1 else "2.0"
        props["created_by"]           = principal

        await self.run(
            f"MERGE (n:{label} {{{key}: $val}}) SET n += $props SET n.created_at = timestamp()",
            {"val": value, "props": props},
        )
        logger.info("Node MERGE: (%s {%s: %r}) by %s", label, key, value, principal)
        return True

    # ── Dynamic Relationship Writer ───────────────────────────────────────────

    async def create_dynamic_relationship(
        self,
        from_label: str, from_key: str, from_val: str,
        rel_type:   str,
        to_label:   str, to_key:   str, to_val:   str,
        principal:  str = "unknown",
    ) -> bool:
        """
        MERGE a relationship with any validated type (Tier 1 OR approved Tier 2).

        Raises ValueError for types that are neither Tier 1 nor APPROVED.

        relationship_schema_version:
          '1.0' → Tier 1 type
          '2.0' → approved Tier 2 type
        """
        is_tier1 = rel_type in TIER1_RELATIONSHIP_TYPES

        if not is_tier1:
            approved = await self.run(
                "MATCH (o:OntologyTerm {term_name: $n, term_type: 'RELATIONSHIP_TYPE', "
                "       status: 'APPROVED'}) RETURN o.term_id AS id",
                {"n": rel_type},
            )
            if not approved:
                raise ValueError(
                    f"Relationship type '{rel_type}' is neither Tier 1 nor approved Tier 2. "
                    "Call validate_and_register_type() and get 2 agent confirmations."
                )

        schema_ver = "1.0" if is_tier1 else "2.0"
        cypher = (
            f"MATCH (a:{from_label}), (b:{to_label}) "
            f"WHERE (a.{from_key} = $fv OR a.value = $fv OR a.name = $fv) "
            f"  AND (b.{to_key} = $tv OR b.value = $tv OR b.name = $tv) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r.relationship_schema_version = $sv, "
            f"    r.created_by = $agent, r.created_at = timestamp()"
        )
        await self.run(cypher, {"fv": from_val, "tv": to_val, "sv": schema_ver, "agent": principal})
        logger.info("Rel MERGE: [%s]-[%s]->[%s] by %s", from_val, rel_type, to_val, principal)
        return True

    # ── Vocabulary Query ──────────────────────────────────────────────────────

    async def get_approved_vocabulary(self) -> Dict[str, List[str]]:
        """
        Returns the complete current vocabulary available for graph writes.
        Agents call this to discover all node labels and relationship types
        they are allowed to use without a governance error.

        Returns:
          {
            "tier1_nodes":         [...8 types...],
            "tier1_relationships": [...8 types...],
            "tier2_nodes":         [...approved extensions...],
            "tier2_relationships": [...approved extensions...],
            "all_nodes":           [...tier1 + tier2 combined...],
            "all_relationships":   [...tier1 + tier2 combined...],
          }
        """
        rows = await self.run(
            "MATCH (o:OntologyTerm {status: 'APPROVED'}) "
            "RETURN o.term_name AS name, o.term_type AS type"
        )
        tier2_nodes = {r["name"] for r in rows if r["type"] == "NODE_LABEL"}
        tier2_rels  = {r["name"] for r in rows if r["type"] == "RELATIONSHIP_TYPE"}

        return {
            "tier1_nodes":         sorted(TIER1_NODE_TYPES),
            "tier1_relationships": sorted(TIER1_RELATIONSHIP_TYPES),
            "tier2_nodes":         sorted(tier2_nodes),
            "tier2_relationships": sorted(tier2_rels),
            "all_nodes":           sorted(TIER1_NODE_TYPES | tier2_nodes),
            "all_relationships":   sorted(TIER1_RELATIONSHIP_TYPES | tier2_rels),
        }
```

**Save the code above as `src/db/neo4j_client.py`** (copy all lines inside the ```python block).


**VERIFICATION CHECK INF-003-B — Import Test**
```bash
PYTHONPATH=. ./venv/bin/python3 -c "
from src.db.neo4j_client import (
    Neo4jClient, TIER1_NODE_TYPES, TIER1_RELATIONSHIP_TYPES
)
print('Import OK:', Neo4jClient)
print('Tier 1 nodes:', len(TIER1_NODE_TYPES))
print('Tier 1 relationships:', len(TIER1_RELATIONSHIP_TYPES))
print('validate_and_register_type method:', hasattr(Neo4jClient, 'validate_and_register_type'))
print('create_dynamic_node method:', hasattr(Neo4jClient, 'create_dynamic_node'))
print('create_dynamic_relationship method:', hasattr(Neo4jClient, 'create_dynamic_relationship'))
print('get_approved_vocabulary method:', hasattr(Neo4jClient, 'get_approved_vocabulary'))
"
```
Must show:
```
Import OK: <class 'src.db.neo4j_client.Neo4jClient'>
Tier 1 nodes: 8
Tier 1 relationships: 8
validate_and_register_type method: True
create_dynamic_node method: True
create_dynamic_relationship method: True
get_approved_vocabulary method: True
```

**IF ModuleNotFoundError for neo4j:**
```bash
./venv/bin/pip install "neo4j>=5.18.0"
```

**IF SyntaxError or AttributeError:** Delete and re-save the file:
```bash
rm src/db/neo4j_client.py
```

---

### Step INF-003-C — Run initialize_schema() Against Live Neo4j

**WHY:** The code is written, but it has never been run against the actual database yet. This step calls it once from the Python shell to confirm it works end-to-end.

```bash
PYTHONPATH=. ./venv/bin/python3 -c "
import asyncio
from src.db.neo4j_client import Neo4jClient

async def main():
    client = Neo4jClient()
    await client.connect()
    print('Step 1 PASS: Connected to Neo4j.')
    await client.initialize_schema()
    print('Step 2 PASS: Schema initialized.')
    await client.close()
    print('Step 3 PASS: Connection closed.')

asyncio.run(main())
"
```

**VERIFICATION CHECK INF-003-C**
Must show all three lines in order:
```
Step 1 PASS: Connected to Neo4j.
Step 2 PASS: Schema initialized.
Step 3 PASS: Connection closed.
```

**IF ServiceUnavailable or Connection refused:**
Neo4j is not running. Start it and wait:
```bash
docker compose up -d && sleep 45
```
Then retry.

**IF AuthError:** Password mismatch between `.env` and Neo4j container. Run:
```bash
grep NEO4J_PASSWORD .env
docker compose config | grep NEO4J_AUTH
```
Both must show the same password. If they differ, fix `.env` and restart: `docker compose down && docker compose up -d`.

---

### Step INF-003-D — Verify Constraints in Neo4j Browser

Open `http://localhost:7474`, log in, then run this in the query bar:

```cypher
SHOW CONSTRAINTS
```

**VERIFICATION CHECK INF-003-D — Constraints**
Must show **14 rows**. These names must all appear in the `name` column:

| Name | Tier | What it protects |
|---|---|---|
| `cst_malware_name` | T1 | No two Malware nodes with same name |
| `cst_threat_actor_name` | T1 | No two ThreatActor nodes with same name |
| `cst_campaign_id` | T1 | No two Campaign nodes with same ID |
| `cst_ip_value` | T1 | No two IP nodes with same address |
| `cst_domain_value` | T1 | No two Domain nodes with same name |
| `cst_url_value` | T1 | No two URL nodes with same URL |
| `cst_hash_sha256` | T1 | No two FileHash nodes with same SHA-256 |
| `cst_technique_id` | T1 | No two ATT&CK technique nodes with same ID |
| `cst_claim_id` | Prov | No duplicate provenance claims |
| `cst_evidence_id` | Prov | No duplicate evidence records |
| `cst_principal_id` | Prov | No duplicate data source principals |
| `cst_conflict_id` | Prov | No duplicate conflict records |
| `cst_decision_id` | Prov | No duplicate arbitration decisions |
| `cst_ontology_term_id` | T2 | No duplicate dynamic type registrations |

Then run:
```cypher
SHOW INDEXES
```

**VERIFICATION CHECK INF-003-D — Indexes**
These 4 custom indexes must be present:
- `idx_claim_subject_predicate`
- `idx_evidence_source_record`
- `idx_ontology_term_name`
- `idx_ontology_term_type`

**IF ANY ARE MISSING:** Re-run Step INF-003-C. `initialize_schema()` is idempotent — running it again is completely safe.

---

**TASKS INF-003 AND INF-004 COMPLETE**

What you now have:
- Full `src/` directory with all 9 `__init__.py` files
- `src/db/neo4j_client.py` with the **Two-Tier Hybrid Schema** fully implemented:
  - `connect()`, `run()`, `close()`, `initialize_schema()`
  - `TIER1_NODE_TYPES` + `TIER1_RELATIONSHIP_TYPES` frozen vocabulary (8+8)
  - `validate_and_register_type()` — MERGE/PENDING/APPROVE governance flow
  - `create_dynamic_node()` — validated Tier 1 or Tier 2 approved writes
  - `create_dynamic_relationship()` — validated relationship writes
  - `get_approved_vocabulary()` — returns all usable types to agents
- All **14** constraints and **4** indexes live in the Neo4j database

---

## TASK INF-005 — Write Tests and pytest Configuration

**Estimated time: 1 hour**
**Owner: @member2**

### WHY

The test file is not optional documentation — it IS the official Definition of Done. The GATE command runs these tests. If any test fails, the story is not complete regardless of how good the code looks.

The tests verify **twelve** distinct things across both tiers:
1. Python can connect to Neo4j and run a query (basic connectivity)
2. `initialize_schema()` can run twice without errors (idempotency)
3. All 14 constraints exist in the database
4. All 4 custom indexes exist
5. The Tier 1 uniqueness constraint blocks duplicate nodes
6. Tier 1 exact match returns MERGE decision without DB write
7. A new type proposal writes a PENDING OntologyTerm node
8. Second agent confirmation auto-approves the type
9. Tier 1 node creation via `create_dynamic_node()` succeeds
10. Unapproved label raises ValueError in `create_dynamic_node()`
11. Approved Tier 2 label can create a node successfully
12. `get_approved_vocabulary()` returns all 8 Tier 1 node types

---

### Step INF-005-A — Create pytest.ini

**WHY:** The test file uses `async def` test functions. Pytest does not handle async automatically — you must configure it. `pytest.ini` tells pytest to handle all async tests automatically.

```bash
printf '[pytest]\nasyncio_mode = auto\n' > pytest.ini
```

**VERIFICATION CHECK INF-005-A**
```bash
cat pytest.ini
```
Must show exactly:
```
[pytest]
asyncio_mode = auto
```

---

### Step INF-005-B — Create tests/test_neo4j_client.py

Save this file as `tests/test_neo4j_client.py`:

```python
"""
STORY-001 Gate Tests — Two-Tier Hybrid Schema
File: tests/test_neo4j_client.py
Owner: @member2

ALL 12 tests must pass before STORY-003 begins.

Requires: Neo4j Docker container running.
If not running: docker compose up -d && sleep 45
"""

import pytest
from src.db.neo4j_client import (
    Neo4jClient, TIER1_NODE_TYPES, TIER1_RELATIONSHIP_TYPES
)


@pytest.fixture
async def client():
    """Connected Neo4jClient for each test. Always closed after."""
    c = Neo4jClient()
    await c.connect()
    await c.initialize_schema()
    yield c
    await c.close()


# ── Foundation Tests ──────────────────────────────────────────────────────────

async def test_connection(client):
    """Neo4j must be reachable and return correct query results."""
    result = await client.run("RETURN 1 AS value")
    assert len(result) == 1
    assert result[0]["value"] == 1


async def test_schema_initialization_idempotent(client):
    """initialize_schema() must be safe to call multiple times (IF NOT EXISTS)."""
    await client.initialize_schema()  # Second call — must not raise


async def test_all_constraints_exist(client):
    """All 14 uniqueness constraints must exist."""
    result = await client.run("SHOW CONSTRAINTS YIELD name RETURN name")
    existing = {row["name"] for row in result}
    required = {
        "cst_malware_name", "cst_threat_actor_name", "cst_campaign_id",
        "cst_ip_value", "cst_domain_value", "cst_url_value",
        "cst_hash_sha256", "cst_technique_id",
        "cst_claim_id", "cst_evidence_id", "cst_principal_id",
        "cst_conflict_id", "cst_decision_id",
        "cst_ontology_term_id",
    }
    missing = required - existing
    assert not missing, f"MISSING constraints: {missing} — re-run initialize_schema()"


async def test_all_indexes_exist(client):
    """All 4 custom indexes must exist."""
    result = await client.run("SHOW INDEXES YIELD name RETURN name")
    existing = {row["name"] for row in result}
    required = {
        "idx_claim_subject_predicate",
        "idx_evidence_source_record",
        "idx_ontology_term_name",
        "idx_ontology_term_type",
    }
    missing = required - existing
    assert not missing, f"MISSING indexes: {missing} — re-run initialize_schema()"


async def test_uniqueness_constraint_enforced(client):
    """Tier 1 uniqueness constraint must block duplicate Malware nodes."""
    test_name = "__test_unit_malware__"
    await client.run("MATCH (m:Malware {name: $n}) DETACH DELETE m", {"n": test_name})
    await client.run("CREATE (m:Malware {name: $n, node_schema_version: '1.0'})", {"n": test_name})
    with pytest.raises(Exception) as exc:
        await client.run("CREATE (m:Malware {name: $n, node_schema_version: '1.0'})", {"n": test_name})
    err = str(exc.value).lower()
    assert "already exists" in err or "constraint" in err
    await client.run("MATCH (m:Malware {name: $n}) DETACH DELETE m", {"n": test_name})


# ── Tier 1 Vocabulary Tests ───────────────────────────────────────────────────

def test_tier1_node_types_count():
    """Tier 1 must define exactly 8 node types."""
    assert len(TIER1_NODE_TYPES) == 8


def test_tier1_relationship_types_count():
    """Tier 1 must define exactly 8 relationship types."""
    assert len(TIER1_RELATIONSHIP_TYPES) == 8


# ── Dynamic Type Governance Tests ─────────────────────────────────────────────

async def test_tier1_exact_match_returns_merge(client):
    """
    validate_and_register_type() for a Tier 1 type must return MERGE
    without writing any OntologyTerm node to the database.
    """
    result = await client.validate_and_register_type(
        "Malware", "NODE_LABEL", "Agent-ThreatFox"
    )
    assert result["decision"] == "MERGE"
    assert result["term_id"] is None  # No DB write for Tier 1


async def test_new_type_proposal_writes_pending(client):
    """
    A new type proposed by one agent must become PENDING.
    An OntologyTerm node with status=PENDING must exist in Neo4j.
    """
    test_type = "__TestCryptoWallet__"
    await client.run("MATCH (o:OntologyTerm {term_name: $n}) DETACH DELETE o", {"n": test_type})

    result = await client.validate_and_register_type(
        test_type, "NODE_LABEL", "Agent-ThreatFox"
    )
    assert result["decision"] == "PENDING"
    assert result["term_id"] is not None

    rows = await client.run(
        "MATCH (o:OntologyTerm {term_name: $n}) RETURN o.status AS s, o.confirmation_count AS c",
        {"n": test_type}
    )
    assert rows, "OntologyTerm node not written to DB"
    assert rows[0]["s"] == "PENDING"
    assert rows[0]["c"] == 1

    await client.run("MATCH (o:OntologyTerm {term_name: $n}) DETACH DELETE o", {"n": test_type})


async def test_second_confirmation_auto_approves(client):
    """
    When a second agent confirms the same type,
    status must change from PENDING to APPROVED automatically.
    """
    test_type = "__TestTelegramChannel__"
    await client.run("MATCH (o:OntologyTerm {term_name: $n}) DETACH DELETE o", {"n": test_type})

    r1 = await client.validate_and_register_type(test_type, "NODE_LABEL", "Agent-ThreatFox")
    assert r1["decision"] == "PENDING"

    r2 = await client.validate_and_register_type(test_type, "NODE_LABEL", "Agent-OTX")
    assert r2["decision"] == "APPROVE"

    rows = await client.run(
        "MATCH (o:OntologyTerm {term_name: $n}) RETURN o.status AS s", {"n": test_type}
    )
    assert rows[0]["s"] == "APPROVED"
    await client.run("MATCH (o:OntologyTerm {term_name: $n}) DETACH DELETE o", {"n": test_type})


# ── Dynamic Node Write Tests ──────────────────────────────────────────────────

async def test_create_dynamic_node_tier1_succeeds(client):
    """
    create_dynamic_node() with Tier 1 label must write node
    with node_schema_version='1.0'.
    """
    await client.run("MATCH (i:IP {value: '__test_dyn_ip__'}) DETACH DELETE i")
    ok = await client.create_dynamic_node(
        label="IP", key="value", value="__test_dyn_ip__",
        properties={"confidence": 0.9}, principal="Agent-ThreatFox"
    )
    assert ok is True
    rows = await client.run(
        "MATCH (i:IP {value: '__test_dyn_ip__'}) RETURN i.node_schema_version AS v"
    )
    assert rows and rows[0]["v"] == "1.0"
    await client.run("MATCH (i:IP {value: '__test_dyn_ip__'}) DETACH DELETE i")


async def test_unapproved_label_raises_value_error(client):
    """
    create_dynamic_node() with unapproved label must raise ValueError.
    No node should be written.
    """
    with pytest.raises(ValueError, match="neither Tier 1 nor"):
        await client.create_dynamic_node(
            label="__UnapprovedType__", key="value",
            value="test", principal="Agent-ThreatFox"
        )


async def test_get_approved_vocabulary_contains_tier1(client):
    """
    get_approved_vocabulary() must always include all 8 Tier 1
    node types and all 8 Tier 1 relationship types.
    """
    vocab = await client.get_approved_vocabulary()
    assert len(vocab["tier1_nodes"]) == 8
    assert len(vocab["tier1_relationships"]) == 8
    assert "Malware" in vocab["all_nodes"]
    assert "IP" in vocab["all_nodes"]
    assert "USES_C2" in vocab["all_relationships"]
```

**Save the file above as `tests/test_neo4j_client.py`.**


**VERIFICATION CHECK INF-005-B — Syntax Check**
```bash
PYTHONPATH=. ./venv/bin/python3 -c "
import ast
with open('tests/test_neo4j_client.py') as f:
    ast.parse(f.read())
print('Syntax OK')
"
```
Must show: `Syntax OK`

**VERIFICATION CHECK INF-005-B — Function Count**
```bash
echo "Async tests:"
grep -c "^async def test_" tests/test_neo4j_client.py
echo "Sync tests:"
grep -c "^def test_" tests/test_neo4j_client.py
```
Must show:
```
Async tests:
10
Sync tests:
2
```
(Total = 12 test functions)

**IF SyntaxError:** Delete and re-save:
```bash
rm tests/test_neo4j_client.py
```

---

**TASK INF-005 COMPLETE**

---

## GATE — Run the Official Test Suite

**The story is not done until this section shows all PASSED.**

---

### Step GATE-1 — Confirm Containers Are Running

```bash
docker ps
```

Both `neo4j-cti` and `redis-cti` must show `Up` in STATUS.

**If they are not running:**
```bash
docker compose up -d && sleep 45
```

---

### Step GATE-2 — Run Story-001 Gate Test

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_neo4j_client.py -v
```

**GATE PASSES — You Must See Exactly:**

```
test_neo4j_client.py::test_connection                           PASSED
test_neo4j_client.py::test_schema_initialization_idempotent    PASSED
test_neo4j_client.py::test_all_constraints_exist               PASSED
test_neo4j_client.py::test_all_indexes_exist                   PASSED
test_neo4j_client.py::test_uniqueness_constraint_enforced      PASSED
test_neo4j_client.py::test_tier1_node_types_count              PASSED
test_neo4j_client.py::test_tier1_relationship_types_count      PASSED
test_neo4j_client.py::test_tier1_exact_match_returns_merge     PASSED
test_neo4j_client.py::test_new_type_proposal_writes_pending    PASSED
test_neo4j_client.py::test_second_confirmation_auto_approves   PASSED
test_neo4j_client.py::test_create_dynamic_node_tier1_succeeds  PASSED
test_neo4j_client.py::test_unapproved_label_raises_value_error PASSED
test_neo4j_client.py::test_get_approved_vocabulary_contains_tier1 PASSED

=================== 12 passed ===================
```

**OLD EXPECTED OUTPUT (5 tests) — IGNORE THIS:** *(removed; updated test suite now expects 12 passing tests)*

All 5 must say `PASSED`. Zero failures, zero errors, zero warnings that block.

---

### Step GATE-3 — Run the Full Project Test Suite

**WHY:** Verify STORY-001 did not break anything from Phase 1.

```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
```

**Must Show:**
```
tests/test_data_pipeline.py::test_threatfox_normalization PASSED
tests/test_data_pipeline.py::test_urlhaus_normalization PASSED
tests/test_neo4j_client.py::test_connection PASSED
tests/test_neo4j_client.py::test_schema_initialization_idempotent PASSED
tests/test_neo4j_client.py::test_all_constraints_exist PASSED
tests/test_neo4j_client.py::test_all_indexes_exist PASSED
tests/test_neo4j_client.py::test_uniqueness_constraint_enforced PASSED

=================== 7 passed in X.XXs ===================
```

**7 passed. Zero failures.**

---

## Troubleshooting Reference

| Problem | Cause | Fix |
|---|---|---|
| `ServiceUnavailable` | Neo4j container not running | `docker compose up -d && sleep 45` |
| `AuthError` | Password mismatch between .env and container | `grep NEO4J_PASSWORD .env` and `docker compose config \| grep NEO4J_AUTH` — both must match |
| `ModuleNotFoundError: neo4j` | Package not installed | `./venv/bin/pip install neo4j>=5.18.0` |
| `RuntimeError: not connected` | Forgot to call `connect()` | Always call `await client.connect()` before `run()` |
| `PytestUnraisableExceptionWarning` | asyncio_mode not configured | Confirm pytest.ini has `asyncio_mode = auto` |
| `SyntaxError` in test file | Incomplete copy-paste | Delete file, repeat Step INF-005-B |
| Port 7687 already in use | Another process on port | `lsof -i :7687`, find and stop the process |
| `docker: command not found` | Docker not installed | Install Docker Desktop from docker.com |
| Browser shows blank page at 7474 | Neo4j still starting | Wait 30 more seconds, refresh browser |

---

## Story-001 Completion Checklist

Mark each box **only after its verification check passed**.

**Section 0 — Pre-Flight**
- [ ] Check 0.1 — `pwd` shows `/Users/sohithsai/multiagent_knowledgegraph`
- [ ] Check 0.2 — Phase 1 tests: `2 passed`
- [ ] Check 0.3 — `docker --version` shows version number
- [ ] Check 0.4 — `docker ps` shows table header
- [ ] Check 0.5 — `lsof` on ports 7687, 7474, 6379 returns blank output
- [ ] Check 0.6 — `./venv/bin/python3 --version` shows `Python 3.9.6`

**INF-001 — Docker**
- [ ] INF-001-A — `.env` contains `NEO4J_PASSWORD=[configure NEO4J_PASSWORD locally]`
- [ ] INF-001-B — `docker-compose.yml` uses `${NEO4J_PASSWORD}` form (no hardcoded password)
- [ ] INF-001-B — `docker compose config | grep NEO4J_AUTH` shows resolved password
- [ ] INF-001-C — `docker ps` shows 2 rows with `Up` status
- [ ] INF-001-E — Neo4j Browser at `localhost:7474` returns query result
- [ ] INF-001-F — `docker exec redis-cti redis-cli ping` returns `PONG`

**INF-002 — Dependencies**
- [ ] INF-002-A — `requirements.txt` contains `neo4j>=5.18.0`
- [ ] INF-002-B — `pip install` completed; `neo4j` import returns version
- [ ] INF-002-C — Phase 1 still shows `2 passed`

**INF-003 + INF-004 — Source Code**
- [ ] INF-003-A — `find src -name "__init__.py"` shows 9 files
- [ ] INF-003-B — `neo4j_client.py` import shows `Import OK`
- [ ] INF-003-C — Smoke test shows all 3 PASS lines
- [ ] INF-003-D — Browser shows **14 constraints**; 3 custom indexes present (inc. `cst_threat_actor_name`, `cst_campaign_id`)

**INF-005 — Tests**
- [ ] INF-005-A — `cat pytest.ini` shows `asyncio_mode = auto`
- [ ] INF-005-B — Syntax check shows `Syntax OK`; function count shows `5`

**Gate**
- [ ] GATE-1 — Both containers show `Up`
- [ ] GATE-2 — `5 passed` on `tests/test_neo4j_client.py`
- [ ] GATE-3 — `7 passed` on full `tests/` suite

---

**When all 24 boxes are checked: STORY-001 is DONE.**

**Next step: Begin STORY-002 (Core Pydantic Data Contracts) in parallel with STORY-001 being complete.**
