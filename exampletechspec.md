# AI Read-Only HMS Assistant - Technical Design Specification

## Document Information

| Field | Details |
|-------|---------|
| Feature/Module | HMS Core / AI Read-Only Assistant |
| Related PRD | [PRD_ASSIST_PROD.md](file:///c:/Users/mural/hms-app-ag-10124b56/docs/PRD_ASSIST_PROD.md) |
| Date Created | 2026-06-19 |
| Last Updated | 2026-06-19 |
| Prepared By | Principal AI Systems Architect |
| Reviewers | Staff Engineers, Security Board, Backend Lead |
| Status | Production Architecture Approved (Implementation In Progress) |

---

## 1. Overview

### 1.1 Purpose

This technical design specification details **HOW** we implement the **AI Read-Only HMS Assistant** for the MediKloud SaaS platform. It establishes the secure bridging of downstream PostgreSQL clinical modules with AWS Bedrock / GLM LLM streaming query coordinators while enforcing absolute tenant isolation and role-based access control (RBAC).

This document details the system components built so far, analyzes the applied database migrations, and maps out the concrete designs for the Phase 2 Deliverables (local semantic routing, failover, caching, rate limiting, and tool quotas).

### 1.2 Background & Context

Healthcare providers spend significant effort navigating patient histories, case sheets, billing statuses, and schedules. The AI Assistant acts as a secure read-only sidebar chat widget in `apps/hms-portal` that retrieves this information via natural language queries.

**Key Constraints & Requirements:**
- **Zero-Write Policy**: The chatbot must never modify or insert clinical records.
- **Tenant Isolation**: Session-bounded `tenantId` must govern all queries.
- **Dynamic RBAC**: User permissions must be strictly verified before tool executions.
- **Cost & Latency Management**: Prompt caching, vector-based semantic routing, and background history summarization are mandatory.

### 1.3 Scope

**Technical Scope (Built & Verified):**
- JWT auth integration and request token extractors.
- Floating sidebar widget UI container and streaming BFF Proxy middleware (`raw=1`).
- NestJS chatbot module and core service orchestrator supporting Vercel AI SDK streams.
- 15 specialized read-only database query tool definitions.
- Prisma migration `20260611071859_init_chatbot_memory` fully applied.

**Phase 2 Deliverables (Implementation Roadmap):**
- Local MiniLM Context-Synthesized Semantic Router for pre-classification and routing.
- Redis-backed sliding-window memory (last 10 messages) and background history compression.
- Tenant AI Limits enforcement (`TenantAiLimits`) and Redis-based user rate limiters.
- Model cascading failover (Bedrock Claude primary → GLM-4.7-Flash fallback) with `AbortController` cancellation.
- Tool reliability validation middleware and execution status reporting.
- Automated CI/CD Golden Evaluation pipeline (3,000 queries) and quality gates.

---

## 2. Architecture & Data Flow Specification

### 2.1 Component Data Flow & Module Architecture

The following block-level flowchart represents the precise operational lifecycle of a chat query transaction, mapping out the internal sub-processes, data shapes, and parameters passed across boundaries:

```text
DIAGRAM A: CHAT WIDGET INITIALIZATION & CONVERSATION HISTORY FLOWS
================================================================================
                               User Actions
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
                 ▼                  ▼                  ▼
          [ Mount Widget ]    [ Click "+" New ]  [ Click "History" ]
                 │                  │                  │
                 ▼                  ▼                  │
 ┌────────────────────────┐  ┌──────────────┐          │
 │ Read "conversationId"  │  │ Generate new │          │
 │ from localStorage      │  │ session UUID │          │
 └───────┬────────────────┘  └──────┬───────┘          │
         │                          │                  │
     ID Found?                      ▼                  ▼
    ┌────┴────┐              ┌──────────────┐  ┌──────────────────────────────┐
    │         │              │ 1. Clear UI  │  │ Fetch list of chats via BFF  │
  [Yes]      [No]            │ 2. Set ID in │  │ GET /chatbot/conversations   │
    │         │              │ localStorage │  └──────────────┬───────────────┘
    ▼         ▼              └──────────────┘                 │
    │  ┌──────────────┐                                       ▼ (NestJS DB Query)
    │  │ Generate new │                        ┌──────────────────────────────┐
    │  │ session UUID │                        │ SELECT conversations WHERE   │
    │  │ ID           │                        │ userId = :uid AND            │
    │  └──────┬───────┘                        │ tenantId = :tid              │
    │         │                                └──────────────┬───────────────┘
    │         ▼                                               │
    │  ┌──────────────┐                                       ▼
    │  │ Clear chat   │                        ┌──────────────────────────────┐
    │  │ UI window    │                        │ Render History Sidebar List  │
    │  └──────────────┘                        └──────────────┬───────────────┘
    ▼                                                         │
┌────────────────────────────────┐                            │  User Clicks on Chat item
│ Load message log via BFF       │◄───────────────────────────┘
│ GET /conversations/:id         │
└─────────────┬──────────────────┘
              │
              ▼ (NestJS DB Query)
┌────────────────────────────────┐
│ SELECT messages WHERE          │
│ conversationId = :id           │
└─────────────┬──────────────────┘
              │
              ▼
┌────────────────────────────────┐
│ Render message history in UI   │
└────────────────────────────────┘


DIAGRAM B: CHAT TRANSACTION, REDIS IDEMPONTENCY, INTENT ROUTING & FAILOVER
================================================================================
 [ User Sends Natural Language Message ]
           │
           ▼
 ┌─────────────────────────────────────────────────────────┐
 │ Next.js UI Appends transient active screen metadata     │
 │ Body: { message, conversationId, metadata: { tab, id } }│
 └────────────────────────────┬────────────────────────────┘
                              │
                              ▼ (POST /api/proxy?path=/chatbot/chat&raw=1)
 ┌─────────────────────────────────────────────────────────┐
 │ NestJS Idempotency Guard (Redis Check)                  │
 │ Key: "idem:tenant_id:conversationId:sha256(messageText)"│
 └────────────────────────────┬────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  Key exists?      │
                    └─┬───────────────┬─┘
                      │ [Yes]         │ [No]
                      ▼               ▼
 ┌────────────────────────────────┐ ┌────────────────────────────────┐
 │ Return HTTP 409 (Conflict)     │ │ 1. Set Redis key (10s TTL)     │
 │ UI swallows error & keeps      │ │ 2. Proceed to Concurrency check│
 │ rendering active stream        │ └───────────────┬────────────────┘
 └────────────────────────────────┘                 │
                                                    ▼
                                    ┌────────────────────────────────┐
                                    │ Redis Concurrency & Quota Gate:│
                                    │ Check tenant budget limits &   │
                                    │ user rate limit counters       │
                                    └───────────────┬────────────────┘
                                                    │
                                                    ▼ (Passed Limits)
                                    ┌────────────────────────────────┐
                                    │ MiniLM Semantic Intent Router: │
                                    │ CPU vector similarity check for│
                                    │ tool classification & model    │
                                    └───────────────┬────────────────┘
                                                    │
                                                    ▼
                                    ┌────────────────────────────────┐
                                    │ Vercel AI SDK & Primary Bedrock│
                                    │ Stream execution loop          │
                                    └───────────────┬────────────────┘
                                                    │
                                           ┌────────┴────────┐
                                           │ Primary timeout │
                                           │ or 429/503 err? │
                                           └─┬─────────────┬─┘
                                             │ [Yes]       │ [No]
                                             ▼             ▼
                              ┌────────────────────┐ ┌───────────────┐
                              │ 1. Abort primary   │ │ Stream SSE    │
                              │ 2. Cascade GLM API │ │ chunks to UI  │
                              │    fallback stream │ └───────┬───────┘
                              └────────┬───────────┘         │
                                       │                     │
                                       ▼                     ▼
                                    ┌────────────────────────────────┐
                                    │ Write to Background Queue:     │
                                    │ 1. Publish save message task   │
                                    │ 2. Publish write telemetry task│
                                    │    to Redis BullMQ Job Queue   │
                                    └───────────────┬────────────────┘
                                                    │
                                                    ▼
                                    ┌────────────────────────────────┐
                                    │ BullMQ Asynchronous Workers:   │
                                    │ Pull logs and write immutable  │
                                    │ records to PostgreSQL DB       │
                                    └────────────────────────────────┘


DIAGRAM C: SYSTEM COMPONENT ARCHITECTURE & INFRASTRUCTURE NODES
================================================================================
┌──────────────────────────────────────────────────────────────────────────────┐
│                            CLIENT INTERFACE (UI Node)                        │
│  [Next.js Chat Widget UI] <───> [localStorage (saves active conversationId)]  │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │ (HTTPS Rest Calls & SSE Streams)
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         BFF SECURITY GATEWAY (Proxy Node)                    │
│  [Next.js BFF Proxy] ───> reads session cookie & injects Auth0 JWT/TenantId  │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │ (Headers: Authorization, x-tenant-id)
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       NESTJS BACKEND APPLICATION (App Node)                  │
│                                                                              │
│  ┌───────────────────────┐             ┌──────────────────────────────────┐  │
│  │ Chatbot Controller    │ ──────────> │ Idempotency & Rate Limit (Redis) │  │
│  │ (Parses Auth Headers) │             │ (idem keys, user rate limits)    │  │
│  └──────────┬────────────┘             └──────────────────────────────────┘  │
│             │                                                                │
│             ▼                                                                │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ MiniLM Semantic Intent Router (ONNX CPU vector search Node)            │  │
│  │  - Category classifier & model routing (Haiku / Sonnet)                │  │
│  └──────────┬─────────────────────────────────────────────────────────────┘  │
│             │                                                                │
│             ▼                                                                │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ Chatbot Service Orchestrator (Vercel AI SDK streamText Engine)         │  │
│  │  - Cascading failover circuit breaker (primary timeout trigger)        │  │
│  └──────────┬───────────────────────────────────────────────────────▲────────┘  │
│             │ (Sends Prompt & Tool Scopes)                          │ (Runs Vercel AI SDK Tool Loop)
│             ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────┴────────┐  │
│  │ Dynamic Tool Registry Factory (Tool Registry Node)                     │  │
│  │  - patient_lookup   - patient_vitals   - case_sheet_details            │  │
│  │  - invoice_details  - appointment_list - lab_reports                   │  │
│  └──────┬───────────────────────────────────────────────────────▲────────┘  │
│         │ (Database Queries)                                    │ (Validated JSON payload)
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────┴────────┐  │
│  │ Tool Validator Interceptor (Validation Node)                           │  │
│  │  - Strips metadata, runs Zod schema structure checks                   │  │
│  │  - Enforces statement timeouts (2s) and shapes response payload        │  │
│  └──────┬───────────────────────────────────────────────────────▲────────┘  │
│         │ (Prisma Client SELECT Queries)                        │ (Raw Database Rows)
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────┴────────┐  │
│  │ BullMQ Job Producer Node                                               │  │
│  │  - Publishes message saves & audit logs to Redis Queue background jobs │  │
│  └──────┬─────────────────────────────────────────────────────────────────┘  │
└─────────┼────────────────────────────────────────────────────────────────────┘
          │ (Background Telemetry & Logging Job Broker)
          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                  REDIS QUEUE BROKER (BullMQ Message Broker Node)             │
│  [Redis Queue Cache] <───> [BullMQ Telemetry Worker background daemon]       │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │ (Background Worker writes)
                                       ▼
┌──────────────────────────────┐       ▼    ┌────────────────────────────────┐
│   EXTERNAL LLM PROVIDERS     │            │   DATABASE LAYOUT (DB Node)    │
│  ┌────────────────────────┐  │            │  [Prisma DB Client]            │
│  │ Bedrock Primary API    │  │            │  (Connection cap limit = 10)   │
│  │ (Claude 3.5 Sonnet)    │  │            │  (Statement timeout = 2s)      │
│  └──────────┬─────────────┘  │            │               │                │
│             │ (Failover      │            │               ▼                │
│             ▼  Timeout)      │            │  [PostgreSQL Clinical DB]      │
│  ┌────────────────────────┐  │            │  - chat_conversations          │
│  │ GLM Failover API       │  │            │  - chat_messages               │
│  │ (GLM-4.7 Flash Engine)  │  │            │  - chat_audit_logs             │
│  └────────────────────────┘  │            │  - tenant_ai_limits            │
│  ┌────────────────────────┐  │            │                                │
│  │ Tool Calling Loop      │  │            │                                │
│  │ LLM requests execution ├──┼───────────►│                                │
│  │ of name + args parameters │  │  (Executes │                                │
│  │◄───────────────────────┼──┼────────────│                                │
│  └────────────────────────┘  │  │   Tool)    │                                │
└──────────────────────────────┘            └────────────────────────────────┘
```

### 2.2 Module Specifications: Inputs, Outputs & Functions

Every operational block in the transaction pipeline is strictly segregated with typed inputs, outputs, and functions:

| Module / Block | Core Technical Function | Inputs | Outputs |
| :--- | :--- | :--- | :--- |
| **Next.js Chat UI** | User interface widget. Captures user prompts, reads back SSE streams, parses Markdown. | **Input:** User text prompt ($\le 1000$ chars), active conversation context (`conversationId`). | **Output:** HTTP Request payload containing `{ message: string }`, browser session cookie. |
| **Next.js BFF Proxy** | Security gateway proxy. Validates cookie sessions and injects Auth0 JWT parameters. | **Input:** Cookie session payload, destination path `/chatbot/chat`. | **Output:** Authorization header (`Bearer JWT`), `x-tenant-id` header forwarded to NestJS. |
| **ChatbotController** | API Router & Guard coordinator. Handles JWT validation, deserialization, and SSE headers. | **Input:** `QueryChatbotDto` (`{ message: string }`), Request object `req.user` (`{ id, tenantId, permissions }`). | **Output:** Server-Sent Event stream (`text/event-stream`), HTTP connection headers. |
| **Idempotency Guard** | Redis lookup key filter. Prevents processing duplicate requests due to network lag. | **Input:** Composite key string: `tenantId + conversationId + sha256(messageText)`. | **Output:** Boolean. If `true`, redirects stream from cache; if `false`, locks key for 10s and routes query. |
| **Concurrency & Quota Guard** | Throttler gate. Checks concurrency counts and quota settings in Redis before execution. | **Input:** `tenantId`, `userId`. Active request locks in Redis. | **Output:** Boolean. Blocks with `429 Too Many Requests` or permits transaction. |
| **MiniLM Semantic Router** | ONNX pre-classifier running local CPU vector searches to resolve intents. | **Input:** Assembled string: `ActivePatientId: {id}. ActiveTab: {tab}. Query: {query}`. | **Output:** Matching category (`patients \| billing \| appointments \| labs \| ambiguous`), complexity rating, target model. |
| **ChatbotService Orchestrator** | Main coordinator. Assembles prompts, dynamically loads tools, handles the Vercel SDK loop. | **Input:** Classify parameters, active user context, dynamic tools subset, LLM client mappings. | **Output:** SSE stream, raw LLM token outputs. |
| **Model Cascade Interceptor** | Resiliency interceptor. Captures timeouts and HTTP errors, routing to backup models. | **Input:** Bedrock client exceptions, `AbortController` signals, active query payloads. | **Output:** Backup text stream connection (GLM-4.7-Flash). |
| **Dynamic Tool Closures** | Dynamic repository queries executing sandboxed database lookups. | **Input:** Zod schema parameters (e.g. `patientId: string`), trusted context closure (`tenantId: string`). | **Output:** SQL row query returns. |
| **Tool Validator Interceptor** | Data reliability layer. Enforces timeouts, strips metadata, and builds safety wrappers. | **Input:** SQL result sets, Zod schema requirements. Statement timeout limit (2s). | **Output:** JSON wrapper (`{ status: SUCCESS \| PARTIAL \| FAILED, reason, data }`). |
| **BullMQ Async Logger** | Telemetry queue. De-couples database logging writes from LLM streaming pipelines. | **Input:** Telemetry job containing token counts, calculated cost, latency, model used, and `requestId`. | **Output:** Queue insertion job in Redis; committed logging row in `chat_audit_logs` table. |
| **Telemetry API Controller** | Admin endpoints providing aggregated token usage, cost profiles, and error metrics. | **Input:** Query filter arguments (`tenantId`, `userId`, `dateRange`, `modelName`). | **Output:** Aggregated analytics metrics for cost, token volumes, latency percentiles, and failover rates. |
| **Cost & Observability Dashboard** | Admin Portal interface. Visualizes billing charts, rate allocations, and model errors. | **Input:** User interaction clicks, selected subdomains, and filter ranges. | **Output:** Cost attribution curves, error canary alerts, and tenant quota consumption bars. |

### 2.3 Detailed Request-Response Lifecycle Sequence

```
User             Next.js UI           BFF Proxy         ChatController       ChatbotService        SemanticRouter        LLM Provider        Prisma Client        BullMQ Queue
 │                   │                    │                   │                     │                     │                     │                    │                  │
 │ Type query        │                    │                   │                     │                     │                     │                    │                  │
 ├──────────────────►│                    │                   │                     │                     │                     │                    │                  │
 │                   │ POST /chat         │                   │                     │                     │                     │                    │                  │
 │                   ├───────────────────►│                   │                     │                     │                     │                    │                  │
 │                   │                    │ Forward request   │                     │                     │                     │                    │                  │
 │                   │                    │ + JWT & Tenant ID │                     │                     │                     │                    │                  │
 │                   │                    ├──────────────────►│                     │                     │                     │                    │                  │
 │                   │                    │                   │ 1. Check idempotency│                     │                     │                    │                  │
 │                   │                    │                   │    key in Redis     │                     │                     │                    │                  │
 │                   │                    │                   │ 2. Check limits     │                     │                     │                    │                  │
 │                   │                    │                   ├────────────────────►│                     │                     │                    │                  │
 │                   │                    │                   │                     │ 3. Forward query    │                     │                    │                  │
 │                   │                    │                   │                     │    context          │                     │                    │                  │
 │                   │                    │                   │                     ├────────────────────►│                     │                    │                  │
 │                   │                    │                   │                     │                     │ 4. Local vector ONNX│                    │                  │
 │                   │                    │                   │                     │                     │    search similarity│                    │                  │
 │                   │                    │                   │                     │◄────────────────────┤                     │                    │                  │
 │                   │                    │                   │                     │ Category + Model    │                     │                    │                  │
 │                   │                    │                   │                     │                     │                     │                    │                  │
 │                   │                    │                   │                     │ 5. Compile prompt   │                     │                    │                  │
 │                   │                    │                   │                     │    + tools subset   │                     │                    │                  │
 │                   │                    │                   │                     ├──────────────────────────────────────────►│                    │                  │
 │                   │                    │                   │                     │                                           │ 6. LLM executes    │                  │
 │                   │                    │                   │                     │                                           │    tool calling    │                  │
 │                   │                    │                   │                     │◄──────────────────────────────────────────┤                    │                  │
 │                   │                    │                   │                     │ Tool Call request:                        │                    │                  │
 │                   │                    │                   │                     │ { tool: "patient_lookup", params }        │                    │                  │
 │                   │                    │                   │                     │                                           │                    │                  │
 │                   │                    │                   │                     │ 7. Dynamic Closure executes tool query    │                    │                  │
 │                   │                    │                   │                     │    Injecting strict tenantId closure      │                    │                  │
 │                   │                    │                   │                     ├───────────────────────────────────────────────────────────────►│                  │
 │                   │                    │                   │                     │                                                                │ 8. Query DB      │
 │                   │                    │                   │                     │                                                                │    statement     │
 │                   │                    │                   │                     │                                                                │    timeout = 2s  │
 │                   │                    │                   │                     │                                                                ├─────────────────►│
 │                   │                    │                   │                     │                                                                │◄─────────────────┤
 │                   │                    │                   │                     │                                                                │ Row Data Return  │
 │                   │                    │                   │                     │◄───────────────────────────────────────────────────────────────┤                  │
 │                   │                    │                   │                     │ 9. Tool Validator Interceptor checks format,   │                    │                  │
 │                   │                    │                   │                     │    strips metadata, outputs standard JSON wrapper               │                  │
 │                   │                    │                   │                     ├──────────────────────────────────────────►│                    │                  │
 │                   │                    │                   │                     │ Forward JSON validation payload to LLM    │                    │                  │
 │                   │                    │                   │                     │◄──────────────────────────────────────────┤                    │                  │
 │                   │                    │                   │                     │ Stream Response back to orchestrator      │                    │                  │
 │                   │                    │                   │◄────────────────────┤                                           │                    │                  │
 │                   │                    │◄──────────────────┤ Write SSE Chunks    │                                           │                    │                  │
 │                   │◄───────────────────┤ Piping Stream     │                     │                                           │                    │                  │
 │ Stream Answer     │                    │                   │                     │                                           │                    │                  │
 │◄──────────────────┤                    │                   │                     │                                           │                    │                  │
 │                   │                    │                   │                     │ 10. Queue Telemetry Job asynchronously    │                    │                  │
 │                   │                    │                   │                     ├──────────────────────────────────────────────────────────────────────────────►│
 │                   │                    │                   │                     │                                                                                │ 11. Write audit  │
 │                   │                    │                   │                     │                                                                                │     log row to   │
 │                   │                    │                   │                     │                                                                                │     Postgres     │
 │                   │                    │                   │                     │                                                                                ├─────────────────►│
```

### 2.4 Telemetry & Cost Dashboard Lifecycle Sequence

*Phase 2 Deliverable:* The following lifecycle sequence details the flow of data when a platform administrator loads the Cost & Observability dashboard inside the Admin Portal:

```
Admin User           Admin Dashboard (UI)        BFF Proxy         TelemetryController      Prisma Client        PostgreSQL DB
    │                         │                      │                      │                     │                    │
    │ 1. Open Dashboard page  │                      │                      │                     │                    │
    ├────────────────────────►│                      │                      │                     │                    │
    │                         │ 2. GET /telemetry    │                      │                     │                    │
    │                         ├─────────────────────►│                      │                     │                    │
    │                         │    + Session Cookie  │                      │                     │                    │
    │                         │                      │ 3. Validate Token &  │                     │                    │
    │                         │                      │    inject headers    │                     │                    │
    │                         │                      ├─────────────────────►│                     │                    │
    │                         │                      │                      │ 4. Query aggregates │                    │
    │                         │                      │                      ├────────────────────►│                     │
    │                         │                      │                      │                     │ 5. SQL SELECT      │
    │                         │                      │                      │                     │    aggregates on   │
    │                         │                      │                      │                     │    chat_audit_logs │
    │                         │                      │                      │                     │    (using replica) │
    │                         │                      │                      │                     ├───────────────────►│
    │                         │                      │                      │                     │◄───────────────────┤
    │                         │                      │                      │                     │ Return analytical  │
    │                         │                      │                      │                     │ rows               │
    │                         │                      │                      │◄────────────────────┤                    │
    │                         │                      │                      │                     │                    │
    │                         │                      │◄─────────────────────┤                     │                    │
    │                         │◄─────────────────────┤ JSON formatted metrics                     │                    │
    │                         │                      │                      │                     │                    │
    │ 6. Render chart curves  │                      │                      │                     │                    │
    │◄────────────────────────┤                      │                      │                     │                    │
```

---


## 3. Data Design

### 3.1 Database Schema & Applied Migrations

The database changes have been baseline migrated via Prisma under `apps/backend/prisma/migrations/20260611071859_init_chatbot_memory/migration.sql`.

```
                  ┌──────────────────────┐
                  │       tenants        │
                  ├──────────────────────┤
                  │ id (PK, UUID)        │
                  └──────────────────────┘
                             │
                             │ 1:N (Cascade delete)
                             ▼
                  ┌──────────────────────┐
                  │  chat_conversations  │
                  ├──────────────────────┤
                  │ id (PK, UUID)        │
                  │ tenant_id (FK, UUID) │
                  │ user_id (FK, UUID)   │
                  │ title (VARCHAR)      │
                  │ is_archived (BOOLEAN)│
                  │ created_at (TIMESTAMPTZ)
                  │ updated_at (TIMESTAMPTZ)
                  └──────────────────────┘
                             │
                             ├──────────────────────────┐
                             │ 1:N (Cascade delete)     │ 1:N (Immutable)
                             ▼                          ▼
                  ┌──────────────────────┐   ┌──────────────────────┐
                  │    chat_messages     │   │   chat_audit_logs    │
                  ├──────────────────────┤   ├──────────────────────┤
                  │ id (PK, UUID)        │   │ id (PK, UUID)        │
                  │ conversation_id (FK) │   │ tenant_id (UUID)     │
                  │ role (VARCHAR)       │   │ user_id (UUID)       │
                  │ content (TEXT)       │   │ conversation_id (UUID)
                  │ tool_calls (JSONB)   │   │ tool_name (VARCHAR)  │
                  │ created_at (TIMESTAMPTZ) │ tool_version (VARCHAR)
                  └──────────────────────┘   │ tool_arguments (JSONB)
                                             │ result_status (VARCHAR)
                                             │ model_name (VARCHAR) 
                                             │ prompt_tokens (INT)  
                                             │ completion_tokens(INT)
                                             │ cost_usd (DECIMAL)   
                                             │ latency_ms (INT)     
                                             │ request_id (VARCHAR) 
                                             │ created_at (TIMESTAMPTZ)
                                             └──────────────────────┘
```

### 3.2 Prisma Schema Specifications

The following schemas are defined in `apps/backend/prisma/schema.prisma` (lines 4544-4588):

```prisma
model chat_conversations {
  id          String            @id @default(uuid()) @db.Uuid
  tenant_id   String            @db.Uuid
  user_id     String            @db.Uuid
  title       String            @db.VarChar(255)
  created_at  DateTime          @default(now()) @db.Timestamptz(6)
  updated_at  DateTime          @updatedAt @db.Timestamptz(6)
  is_archived Boolean           @default(false)
  messages    chat_messages[]
  tenant      tenants           @relation(fields: [tenant_id], references: [id], onDelete: Cascade)
  user        tenantpanel_users @relation(fields: [user_id], references: [id], onDelete: Cascade)

  @@index([tenant_id])
  @@index([user_id])
  @@map("chat_conversations")
}

model chat_messages {
  id              String             @id @default(uuid()) @db.Uuid
  conversation_id String             @db.Uuid
  role            String             @db.VarChar(50)
  content         String             @db.Text
  tool_calls      Json?
  created_at      DateTime           @default(now()) @db.Timestamptz(6)
  conversation    chat_conversations @relation(fields: [conversation_id], references: [id], onDelete: Cascade)

  @@index([conversation_id])
  @@map("chat_messages")
}

model chat_audit_logs {
  id                      String   @id @default(uuid()) @db.Uuid
  tenant_id               String   @db.Uuid
  user_id                 String   @db.Uuid
  conversation_id         String   @db.Uuid
  tool_name               String   @db.VarChar(100)
  tool_version            String   @db.VarChar(50) // Track tool versions for regression analysis
  tool_arguments          Json
  execution_result_status String   @db.VarChar(50)
  model_name              String   @db.VarChar(100) // Mapped LLM used for billing analysis
  prompt_tokens           Int      @default(0)      // Cost tracking metric
  completion_tokens       Int      @default(0)      // Cost tracking metric
  cost_usd                Decimal  @db.Decimal(10,6) // Calculated USD billing
  latency_ms              Int      @default(0)      // Execution speed metric
  request_id              String   @db.VarChar(255) // Correlation identifier
  created_at              DateTime @default(now()) @db.Timestamptz(6)

  @@index([tenant_id])
  @@index([user_id])
  @@index([conversation_id])
  @@map("chat_audit_logs")
}
```

*Phase 2 Deliverable*: The tenant quota tracking table `TenantAiLimits` needs to be created to enforce monthly/daily AI spend limits:

```prisma
model TenantAiLimits {
  id                String   @id @default(uuid()) @db.Uuid
  tenantId          String   @unique @map("tenant_id") @db.Uuid
  monthlyTokenLimit Int      @map("monthly_token_limit")
  monthlyCostLimit  Decimal  @map("monthly_cost_limit") @db.Decimal(10, 4)
  dailyRequestLimit Int      @map("daily_request_limit")
  tenant            tenants  @relation(fields: [tenantId], references: [id], onDelete: Cascade)

  @@map("tenant_ai_limits")
}
```

### 3.3 Database Memory Constraints & Compliance
- **Immutable Audit Trail**: `chat_audit_logs` are never deleted by cascade triggers when a user deletes their chat conversation history. They are retained indefinitely for HIPAA compliance and historical data access validation.
- **90-Day Archival Schedule**: Conversation message tables (`chat_conversations` and `chat_messages`) undergo automated partition pruning or soft-delete archival routines after 90 days.

---

## 4. Backend

### 4.1 Permissions

The chatbot checks caller scopes before invoking queries. These scopes are mapped to roles and returned in the user's JWT context.

| Action / Resource | Required Scope | Additional Constraints Checked in Tool |
|-------------------|----------------|----------------------------------------|
| View patient lists / records | `patients:read` | Checked in `patient-lookup.tool` |
| View patient vitals | `patients:read` | Checks if doctor owns relationship unless `patients:read:all` |
| View patient case sheets | `patients:read` | Checked in `case-sheet-details.tool` |
| View appointments | `appointments:read` | Filtered by doctorId unless receptionist/admin |
| View invoices / financial items | `billing:read` | Blocked for nurse/doctor without financial clearance |
| View laboratory reports | `labs:read` | Checked in `lab-reports.tool` |

### 4.2 API Design & Lifecycle

**Base URL:** `/api`  
**Authentication:** HTTP Bearer JWT Validation (via BFF proxy)

#### 4.2.1 Submit Chat Query
- **Endpoint:** `POST /chatbot/chat`
- **Security:** `JwtAuthGuard` enforced. Injects `tenantId`, `userId`, and `permissions` into request headers.
- **Request Body (`QueryChatbotDto`):**
  ```json
  {
    "message": "What are the latest vitals for patient John Doe?"
  }
  ```
  *Constraint:* Message length must be validated to be $\le 1000$ characters.
- **Response Protocol:** Server-Sent Events (SSE) stream (`text/event-stream; charset=utf-8`).

#### 4.2.2 Server-Sent Event (SSE) Stream Chunks
The payload is streamed as JSON text chunks in the following format:
```text
event: text
data: {"text":"The latest "}

event: text
data: {"text":"blood pressure is "}

event: text
data: {"text":"130/80 mmHg."}
```
If tool execution errors or permissions checks fail, a failure event is written to the stream:
```text
event: error
data: {"code":"FORBIDDEN","message":"You do not have permission to view billing data."}
```

### 4.3 Vercel AI SDK Integration

The system leverages the Vercel AI SDK to orchestrate the generation and tool invocation loops. The primary client is configured inside `apps/backend/src/chatbot/providers/llm.provider.ts` using an OpenAI-compatible provider client pointing to Bedrock Mantle:

```typescript
import { createOpenAI } from '@ai-sdk/openai';
// Mapped to Bedrock Mantle base URL:
const bedrockClient = createOpenAI({
  apiKey: configService.get<string>('BEDROCK_API_KEY'),
  baseURL: configService.get<string>('BEDROCK_API_BASE_URL') || 'https://bedrock-mantle.ap-south-1.api.aws/v1',
});
```

---

## 5. Business Logic & Core Systems

### 5.1 Dynamic Tool Execution & Security Sandbox

All chatbot tools reside in `apps/backend/src/chatbot/tools/` and are built using functional closures with Vercel AI SDK's `tool()` function.

**Registry Factory Pattern (`registry.factory.ts`):**
```typescript
export function buildToolsRegistry(services: ServiceMap, context: ToolContext) {
  const tools: Record<string, any> = {};
  
  if (context.userPermissions.includes('patients:read')) {
    tools.patient_lookup = patientLookupTool(services.patientsService, context);
    tools.patient_vitals = patientVitalsTool(services.caseSheetsService, context);
    // ...
  }
  if (context.userPermissions.includes('billing:read')) {
    tools.invoice_details = invoiceDetailsTool(services.invoicesService, context);
    // ...
  }
  return tools;
}
```
**Absolute Security Enforcements:**
- **Tenant Context Isolation**: Tools do not allow the LLM to supply `tenantId` as a parameter. It is hard-injected directly from the trusted JWT context closure:
  ```typescript
  execute: async ({ searchName }) => {
    return await patientsService.findByName(searchName, context.tenantId);
  }
  ```

### 5.2 MiniLM Context-Synthesized Semantic Router

*Phase 2 Deliverable:* Instead of loading all tools for every single query, a local vector-similarity router will be implemented to categorize intent and load only the relevant tools.

1. **Model Specs**: A local `sentence-transformers/all-MiniLM-L6-v2` ONNX model runs locally in-memory on CPU (resolving in <10ms).
   - **Production Gotcha (Event Loop Trap)**: Because Node.js is single-threaded, running CPU-heavy matrix operations directly on the main event loop would block incoming requests and cause active SSE streams to stutter under concurrent load.
   - **Architecture Solution**: The ONNX inference must be offloaded from the main event loop. The system will implement this by either:
     - Offloading inference to Node.js `worker_threads` managed by a strict thread pool (using a library like `piscina` restricted to 2-4 concurrent threads) to prevent CPU spikes and Out-Of-Memory (OOM) crashes under heavy load.
     - Deploying a lightweight python/FastAPI sidecar service (highly recommended, as Python handles native ONNX/PyTorch matrix operations far better without container resource contention).
2. **Context Synthesis**: Current query is pre-pended with the active session context before vectorization:
   ```text
   ActivePatientId: {id}. ActiveTab: {tab}. Query: {query}
   ```
   - **Vulnerability (Context Synthesis Overwrite)**: If a user queries details about a patient who is different from the currently open dashboard entity (e.g. asking about "Jane Smith" while looking at "John Doe"), the active entity prefix can pollute the vector embedding, misrouting the intent and leading to data exposure/hallucinations.
   - **Remediation**: The router service must programmatically strip the active entity prefix from the embedding payload if the user query contains explicit entity identifiers (e.g., patient surnames, date identifiers, or unique medical IDs).
3. **Anchor Mapping**: Computes similarity scores against a dictionary of golden anchors for `patients`, `appointments`, `billing`, and `labs`.
4. **Top-K & Margin Routing Policy**:
   - `top_k: 3` highest scoring categories.
   - `margin: 0.05` margin tolerance.
   - `absolute_floor: 0.65`.
   - **Vulnerability (Tight Vector Clustering)**: Small 384-dimensional models exhibit tight clustering vector spaces in medical contexts. Cosine similarity scores between distinct intents (e.g. billing vs. medications) often cluster closely (e.g. `0.68 - 0.74`), causing the `0.05` margin policy to trigger false complex-path fallbacks to the expensive Claude Sonnet tier.
   - **Remediation**: We implement hierarchical classification (separating billing/admin domains from clinical domains in a first-pass route before allocating sub-category tools) and normalize similarity scores against category historical averages to prevent unnecessary model escalations.
   - *Ambiguous Query (Highest score < 0.65)*: Route to **Claude Haiku** with a **Safe Tool Subset** (only `patient_lookup` and basic profile parameters) to ask clarifying questions.
   - *Simple Single-Domain (Highest score > 0.65, others outside 0.05 margin)*: Register only tools of that domain and route to **Claude Haiku**.
   - *Complex Multi-Domain (Highest scores > 0.65 and within 0.05 margin)*: Register the union of tools and route to **Claude Sonnet**.
5. **Future Routing Scalability Plan**:
   While golden anchors meet accuracy requirements for v1.0, expanding the model beyond 8 domains (e.g. adding claims, inventory, staff, pharmacy, scheduling queues) will degrade vector collision bounds. The system architecture defines a path to replace anchor matching with a dedicated, lightweight local classifier model (e.g., DistilBERT trained on medical administrative intent) running inside ONNX on the NestJS instance.

### 5.3 Model Cascading Failover (Primary Bedrock → GLM Fallback)

*Phase 2 Deliverable:* A custom NestJS interceptor catches connection dropouts, `429 Too Many Requests`, `503 Service Unavailable`, or connection hanging timeouts ($> 4.0$ seconds).

```typescript
// NestJS Chatbot Service Failover Loop
let controller = new AbortController();
try {
  return await streamText({
    model: this.llmClient.chat('anthropic.claude-3-5-sonnet'),
    abortSignal: controller.signal,
    // ...
  });
} catch (error) {
  if (isCascadableError(error)) {
    // 1. CRITICAL: Cancel Bedrock call to prevent double tool executions
    controller.abort(); 
    
    // 2. Log failover telemetry to DB
    await this.logFailoverTelemetry(error);
    
    // 3. Fallback to GLM-4.7-Flash
    return await streamText({
      model: this.glmClient.chat('zai.glm-4.7-flash'),
      // ...
    });
  }
}
```

### 5.4 Caching Strategy

*Phase 2 Deliverable:* To control API spend and speed up retrieval, a three-tiered caching architecture is specified:

1. **Semantic Query Cache (Redis)**:
   - Cosine similarity threshold must fall within `0.85 - 0.88`.
     - **Production Gotcha (Threshold Rigidity)**: Using a threshold of `> 0.95` requires practically identical character matches, rendering the cache ineffective for natural human language variations. Setting it between `0.85 - 0.88` ensures variations of common questions (e.g., "How do I reset my password?" vs "I forgot my login password") hit the cache successfully.
   - **Allowed Entities (FAQ / Help / Policies)**: Queries seeking static help texts, usage procedures, or standard operational guidelines can return cached answers.
   - **Forbidden Entities (Patient Data / Billing / Labs / Vitals)**: Banned from semantic caching to prevent patient identification collisions (e.g. John Doe vs. Jon Doe query confusion).
   - Expiration TTL: 24 hours.
2. **Tool Result Cache (Redis)**:
   - Caches database tool outputs for `5 minutes` keyed by `tenant_id` and query arguments.
   - **Cacheable Entities**: Appointments, invoices, schedules.
   - **Non-Cacheable Entities (0s TTL / Direct DB Query)**: Vitals (heart rate, blood pressure), lab status queue, and active room assignments.
   - **Event-Driven Invalidation**: NestJS repository hooks (e.g. `appointment:created`, `patient:updated`) clear related cache keys immediately.
3. **Prompt Caching (AWS Bedrock)**:
   - Splits prompt into static (System prompt, hospital policies, tool declarations) and dynamic (user query) sections. Static sections are cached on Bedrock, yielding up to 90% cost savings for subsequent queries.

### 5.5 Tool Execution Limits & Cost Protection

To protect system resources and billing budgets, the following hard limits are enforced during execution loops:

- **Dynamic Tool Execution Caps**:
  - `simple` (Claude Haiku execution path): `max_tool_calls_per_query: 5`
  - `complex` (Claude Sonnet execution path): `max_tool_calls_per_query: 10` (allows resolving multi-hop dependencies: patient -> appointments -> invoices -> medications -> doctor)
- `max_tokens_per_request: 8192` (Input context ceiling).
- `max_completion_tokens: 1024` (Output token ceiling).
- `max_context_size: 4096` (Dynamic context window limit).

**Database Query Cost Protection Parameters:**
- `statement_timeout = 2s`: Relational PostgreSQL executions triggered by any tool are capped at a maximum of 2,000ms.
- `max_join_depth: 3`: Relational queries constructed via Prisma are restricted to a join depth of 3 to avoid database execution lockouts.
- `max_result_size_mb: 2`: The total memory footprint of any returned dataset from a tool execution cannot exceed 2 Megabytes.
- `max_tool_rows_returned: 100`: Any query results exceeding 100 rows are paginated and truncated.
- **Vulnerability (DB Connection Pool Starvation & Replication Lag)**: Running heavy queries on the primary database pool can starve normal clinical CRUD operations. However, using a read-replica exposes the AI to replication lag: if a clinician queries a newly registered invoice or patient, the replica might show stale data and reply that the record doesn't exist.
- **Remediation**: The assistant module will instantiate a separate, dedicated Prisma client instance configured with a distinct, isolated connection pool pointing exclusively to the PostgreSQL **Read-Replica** cluster. To prevent read-after-write inconsistency, if a tool query seeking a highly specific or recent identifier returns empty, the tool is allowed a single, highly constrained fallback query directly against the Primary database before declaring the record missing.

### 5.6 Context Window Tiering & Assembly
Prompt context compilation prioritizes data density:
- **Tier 1 (Mandatory)**: Last 5 raw chat messages.
- **Tier 2 (High Priority)**: Conversation Summary (history compressed using GLM-4.7-Flash).
  - **Summary Refresh Frequency**: Run background compression jobs exactly every 20 messages to prevent long-context reasoning drift.
  - **Summary Quality Verification**: Summaries undergo automated cross-validation tests in the CI pipeline to ensure key patient clinical anchors are retained.
- **Tier 3 (Medium Priority)**: Active Entity Metadata (details of patients/invoices currently selected on dashboard).

### 5.7 Tool Reliability Layer (Payload Wrapper)
All tools route their database outputs through a validator that intercepts errors and shapes the response in a standardized JSON payload structure:

```json
{
  "status": "SUCCESS" | "PARTIAL" | "FAILED",
  "reason": null | "TIMEOUT" | "DB_CONNECTION_ERROR" | "PERMISSION_DENIED" | "VALIDATION_FAILED",
  "data": []
}
```
- **Execution Status Categories**:
  - `SUCCESS`: Database responded successfully with fully formed rows.
  - `PARTIAL`: The query output was limited due to operational caps:
    * Row limit exceeded.
    * Pagination truncation.
    * Timeout occurred after partial retrieval.
  - `FAILED`: Database returned errors, timed out, or connection was refused.

### 5.8 Human Escalation Path
If the semantic router similarity score falls below `0.65` for 3 consecutive turns, or if tool executions fail 3 times consecutively, or a critical security guardrail is tripped:
- The execution loop bypasses LLM text generation entirely.
- The assistant streams a safe fallback redirect prompt:
  ```text
  "Unable to verify the requested information. Please use the patient search screen directly."
  ```

---

## 6. Frontend Architecture

## 6. Frontend Architecture

The frontend components are strictly split across the two portals in our monorepo: **HMS Portal** (for clinicians and patients) and **Admin Portal** (for global platform administrators).

### 6.1 HMS Portal: Chat Widget UI (`apps/hms-portal`)

- **Widget Placement**: Floating container mounted in the bottom-right corner of the layout wrapper `apps/hms-portal/app/(modules)/layout.tsx`.
- **State & Hooks (`use-chatbot.ts`)**:
  - Uses `@ai-sdk/react`'s `useChat` hook connected to `/api/proxy?path=/chatbot/chat&raw=1`.
  - Captures message chunks and updates UI states reactively.
  - Automatically appends active context flags (active tab, active patient ID) to query payloads.
  - **UI Error Handling (Idempotency 409/429 Exception Swallowing)**: The hook's `onError` callback explicitly intercepts and swallows `409 Conflict` and `429 Too Many Requests` status codes triggered by double-clicks or lag. The UI silently ignores the duplicate click events and continues rendering the active stream typing progress instead of rendering error banners in front of the clinician.
- **UI Components (`apps/hms-portal/components/shared/chatbot/`)**:
  - `chat-panel.tsx`: Toggles sliding transitions, houses messages scroll areas.
  - `chat-bubble.tsx`: Render engine with markdown parsing. Supports HTML tables, bullet points, and warning styles.
  - Typing indicators and skeleton loaders trigger during active stream reads.

### 6.2 Admin Portal: Cost & Observability Dashboard (`apps/admin-portal`)

*Phase 2 Deliverable:* An administrative monitoring console is mounted inside the Admin Portal (`apps/admin-portal/app/(dashboard)/ai-analytics/page.tsx`) to track AI platform operations:
- **Telemetry Visualizations**:
  - **Cost Attribution Charts**: Renders monthly/daily USD cost accumulation graphs segmented by tenant and user.
  - **Token Volume Distribution**: Shows prompt vs. completion tokens and maps prompt-cache hits.
  - **Latency Percentile Graphs (p50, p95, p99)**: Isolates slow tool executions and network delays.
  - **Failover & Error Rate Canaries**: Real-time indicator displaying the frequency of cascades to the GLM fallback.
- **Dynamic Policy Controls**:
  - clinic quota adjustments (direct overrides of `TenantAiLimits` thresholds).
  - Feature flag toggles (`enable_glm_fallback`, `enable_semantic_cache`, `enable_new_router`) manageable via toggle switches.

---

## 7. Integration Points

### 7.1 Upstream Dependencies

- **Auth0 Service**: Resolves user token claims and permission lists.
- **Next.js BFF Proxy**: Validates cookies, maps `/api/proxy` to `/api`, and injects security headers.
- **PostgreSQL Database**: Direct source of truth for read tools.
- **Redis Cache Instance**: Holds rate limits, caching vectors, and session history state.

---

## 8. Testing Strategy

### 8.1 Golden Evaluation Suite & Automated CI/CD Testing

To prevent regressions in model quality or security, a comprehensive **Golden Dataset of 3,000 queries** runs as a CI/CD pipeline gate during deployments (`pnpm test:ai`):

- **500 Simple Queries**: Retrievability and spelling tolerance.
- **500 Medium Queries**: Single-domain tool executions.
- **500 Complex Queries**: Multi-domain reasoning and tool chaining.
- **500 Adversarial Queries**: Prompt injection and jailbreak tests.
- **500 RBAC Guard Tests**: Asserting unauthorized request blocks (e.g. Doctor querying billing logs).
- **500 PHI Redaction Tests**: Validating SSNs/phone numbers are scrubbed from inputs.

**Quality Target Gate thresholds (Failure blocks deployment):**
- **Routing Accuracy**: $\ge 95\%$
- **RBAC Accuracy**: $100\%$ (Strictly zero access leaks)
- **Hallucination Rate**: $< 1\%$
- **Tool Accuracy**: $\ge 97\%$

---

## 9. Deployment & Risks

### 9.1 Database Migrations & Seed Scripts
- Schema tables are already migrated using Prisma on PostgreSQL.
- Master prompt configurations will be pre-seeded into the database to support prompt versioning rollbacks.

### 9.2 Canary Rollout & Deployment Configuration
Operational changes are rolled out incrementally using feature-flagged routing:
- **Canary Splits**: Prompt and model changes are evaluated using weighted traffic splits configured inside the Admin Portal (e.g. routing 5% of requests to `new_router` and 10% to `new_prompt` versions).
- **Rollback Playbooks**: If latency anomalies or accuracy drops are detected in telemetry logs, configuration version pointers in PostgreSQL are rolled back in <5s to a known stable Git commit hash.

### 9.3 Risks & Mitigation Matrix

| Risk | Impact | Probability | Mitigation Strategy |
|------|--------|-------------|---------------------|
| Cross-tenant data leak | Critical | Low | Injected `tenantId` parameter via request JWT closure (not model-provided). |
| Latency overhead (>2s delay) | High | Medium | Implement local Vector Semantic Intent Router to register only necessary tools. |
| Cost explosions (API Spikes) | High | Medium | Enforce `TenantAiLimits` quotas in Redis and hourly user rate limiters. |
| DB locks on audit logging | Medium | Low | Ensure `chat_audit_logs` are written asynchronously using decoupled worker pools. |

---

## 10. Open Questions & Decisions

- **Audit Retention Policy**: Legal and compliance must decide whether chat audit telemetry logs are pruned after 1 year or retained indefinitely for HIPAA audit requirements.
- **Local Summarization Models**: Evaluate if local CPU-based summarizers can replace the background GLM-4.7-Flash calls to run 100% locally.

---

## 11. Operational Excellence

*Phase 2 Deliverables:* The operational safeguards, scaling controls, and error logging configurations detailed below are designed for implementation in Phase 2 to ensure production stability:

### 11.1 Concurrency Controls
To prevent load spikes on downstream databases and LLM provider token allocations during high-traffic clinical operations (e.g. shifts changing), the following concurrency gates are enforced via Redis sliding lock structures:
- `max_concurrent_requests_per_tenant: 20`: Maximum active chat streams executing concurrently inside a single hospital/clinic. Additional queries receive a `429 Concurrent Limit Exceeded` message.
- `max_concurrent_tool_calls: 50`: Total concurrent Prisma database query executions across the entire backend assistant module.
- `max_concurrent_streams: 100`: Maximum global active SSE connections.

### 11.2 Circuit Breakers
To prevent requests from hanging on degraded third-party API providers, a sliding window Circuit Breaker is maintained in Redis:
- **Failure Threshold**: If a provider (AWS Bedrock or GLM) returns $> 20$ failures (timeouts, `503`, `429`) within a sliding window of `5 minutes`, the breaker transitions to **OPEN**.
- **Vulnerability (Global Breaker Poisoning)**: Tripping a global breaker due to one single misconfigured or noisy tenant will degrade service quality across all other independent tenants on the SaaS platform.
- **Remediation**: The circuit breaker Redis keys must be strictly namespaced by tenant ID: `tenant:${tenantId}:circuit_breaker`. This isolates outages and ensures a single client's failures cannot disrupt other clinics.
- **Cooldown Interval**: While OPEN, the orchestrator bypasses that provider entirely for `10 minutes`, routing all traffic directly to the fallback provider.
- **Recovery Check**: After the cooldown period, the breaker enters **HALF-OPEN**, routing 3 test requests to check availability before reverting to **CLOSED**.

### 11.3 Provider Health Registry
The routing engine references a live, Redis-backed health registry to check model statuses *before* initiating requests, rather than relying solely on try/catch latency overrides:

```
Provider Registry
├─ Bedrock (Claude Sonnet / Haiku): HEALTHY | DEGRADED | DOWN
└─ GLM (GLM-4.7-Flash): HEALTHY | DOWN
```
- **HEALTHY**: Active and responsive; latency within SLA target thresholds.
- **DEGRADED**: Breaker has detected partial timeout clusters (latencies $> 3s$). Sonnet queries default-fallback to Haiku or GLM standard mode to preserve latency.
- **DOWN**: Circuit breaker is OPEN. All traffic is auto-routed to alternate healthy providers.

### 11.4 Disaster Recovery (DR) & Multi-Region Strategy
To guarantee compliance with medical data persistence rules and ensure platform availability under region outages:
- **Primary Region**: AWS Mumbai (`ap-south-1`).
- **DR / Secondary Region**: AWS Singapore (`ap-southeast-1`).
- **DR Mode**: Active-Passive. Global Route 53 DNS routes all clinic users to Mumbai. Upon a complete region outage, DNS failover redirects traffic to Singapore in under 2 minutes.
- **Recovery Point Objective (RPO)**: 15 minutes.
- **Recovery Time Objective (RTO)**: 1 hour.
- **Data Replicas & Backups**:
  - **PostgreSQL Database**: Cross-region read replicas actively replicate data from Mumbai to Singapore. Point-in-Time Recovery (PITR) backups run every 15 minutes in both regions.
  - **Redis Cache**: Configuration is backed up daily. Rates/concurrency limits are allowed to rebuild dynamically in the secondary region memory.
  - **Prompt Configuration & Versioning**: Versioned prompt configurations are tracked in PostgreSQL and duplicated inside staging Git repositories to enable rapid restore.
  - **Compliance Audit Logs**: `chat_audit_logs` are replicated to cross-region read-only cold S3 storage buckets every 15 minutes, independent of PostgreSQL main database states.

### 11.5 SLA Targets & SLOs
To hold operational metrics accountable, performance telemetry is evaluated against the following strict targets:

**Operational SLA Targets:**
- `patient_lookup`: p95 latency $< 200\text{ms}$.
- `appointment_lookup`: p95 latency $< 300\text{ms}$.
- `case_sheet_details`: p95 latency $< 400\text{ms}$.
- `lab_reports`: p95 latency $< 500\text{ms}$.

**Operational Service Level Objectives (SLOs):**
- **Availability**: $99.9\%$ uptime over any 30-day billing period.
- **Tool Success Rate**: $99.0\%$ execution completion rate.
- **Routing Accuracy**: $95.0\%$ correct semantic router intent classification.

### 11.6 Tool Versioning
Every clinical query tool in the dynamic registry is tagged with a semantic version number:
```typescript
export const ToolMetadata = {
  name: "patient_vitals",
  toolVersion: "1.0.2"
}
```
During execution, the `toolVersion` is logged in the `chat_audit_logs` table alongside the `tool_name`. This enables immediate pinpointing of regressions if a database schema update breaks compatibility with a specific tool query version.

### 11.7 Queue Architecture & Retry Safety
To prevent audit logging overhead from blocking client stream threads, audit logs are decoupled using **BullMQ**:
- **Execution Pipeline**: `Main Queue` -> `Retry Queue` -> `Dead Letter Queue (DLQ)`.
- The NestJS interceptor publishes logging jobs to a high-speed Redis queue.
- Dedicated background worker pools consume the jobs and write to the database asynchronously.
- Worker failures trigger automatic retry policies (max 3 retries) with exponential backoff.
- If a logging job fails 3 consecutive times, it is automatically routed to a Dead Letter Queue (DLQ) with alert hooks to notify engineers of database ingestion failures and prevent silent telemetry loss.

### 11.8 Streaming Recovery Policy
To handle unstable clinical environments, the SSE pipeline implements client disconnection recovery:
- **Client Disconnection**: If the user closes the chat drawer or the browser tab, the BFF proxy detects the socket closure and immediately calls the `AbortController` to cancel the upstream LLM generation.
  - **Vulnerability (Aborted Stream Token Leak & Tokenizer Mismatch)**: Upstream LLM providers do not return token usage statistics for aborted streams, leaving a loophole for users to bypass limits. Furthermore, generic tokenizers (like OpenAI's BPE-based `tiktoken`) yield a 10%-30% counting discrepancy for Claude and GLM models.
  - **Remediation**: When a stream is aborted mid-generation, the system will run a local token calculation using model-specific tokenizers (e.g. `@anthropic-ai/tokenizer` for Claude, and Zhipu's model-specific tokenizer or character-to-token ratio estimators for GLM-4.7) to calculate dynamic usage and write these metrics to `chat_audit_logs`.
- **Browser Refresh**: The React chat widget caches the `conversationId` in local storage. On refresh, the client polls the backend using the cached ID to reload recent messages.
- **Network Interruption**: The frontend client attempts automatic reconnection (max 5 times) and displays a loading state without clearing the user prompt.

### 11.9 PHI Encryption Standards
To comply with HIPAA security regulations, Protected Health Information (PHI) is protected across all states:
- **In Transit**: All connections use TLS 1.3.
- **At Rest**: PostgreSQL and Redis disks are encrypted using AES-256.
- **Audit Logs**: Raw patient details are redacted from audit log arguments. Any temporary variables are encrypted at the database row-level using PostgreSQL pg_crypto before writing.

### 11.10 Break-Glass Access Policy
- **Intentional Scope Boundary**: The HMS Assistant is strictly **read-only** and **respects existing RBAC permissions**.
- **Break-Glass Exclusion**: There is **no break-glass (emergency bypass) mode** allowed for the AI Assistant. This prevents privilege escalation or unauthorized views of restricted files. In clinical emergencies, clinicians must use standard HMS screens (EHR/Case Sheets) where standard hospital break-glass protocols are actively monitored.

### 11.11 Cost & Quota Controls

#### 11.11.1 Idempotency Strategy
To prevent duplicate execution requests triggered by network lag or duplicate user clicks:
- The NestJS client generates a dynamic idempotency key matching: `conversationId + sha256(messageText)`.
- On receiving a request, the API controller queries Redis for the key.
- **Production Gotcha (Active Stream Multiplexing)**: SSE connections are long-lived, stateful HTTP sockets. Multiplexing or copying an active, live-generating SSE stream from Redis to multiple secondary client connections is highly error-prone.
- **Architecture Solution**: If an active idempotency lock key is detected while a stream is actively generating, the second duplicate request is immediately rejected with a `409 Conflict` or `429 Too Many Requests` status code and a clear error payload (e.g., `"Message already processing"`).
- If not found, the key is saved in Redis with a `10s TTL`.

#### 11.11.2 Tenant Budget Enforcement Rules
Monthly AI spend is actively enforced using the `TenantAiLimits` registry bounds:
- **80% of Quota Reach**: Dispatches a warning email and Slack web-hook to the clinic administrator.
- **95% of Quota Reach**: Renders an inline warning toast on the clinic administrative panel sidebar.
- **100% of Quota Reach**: Denies further queries immediately, blocking backend LLM calls. The chatbot displays a safe system notification:
  ```text
  "The monthly AI assistant limit for this clinic has been reached. Please contact your system administrator."
  ```

#### 11.11.3 Cost Attribution Dashboard
An enterprise analytics portal in the Admin Portal exposes the following aggregated telemetry counters:
- **Cost per Tenant**: Total token expense segmented by client Hospital/Clinic subdomain.
- **Cost per User**: Identifies high-volume users and potential resource misallocations.
- **Cost per Tool**: Renders execution profiles of tools to isolate expensive DB joins.
- **Cost per Model**: Aggregates API spend between Bedrock Sonnet, Bedrock Haiku, and GLM-4.7-Flash.
- **Cost per Conversation**: Tracks total cost trends across conversational multi-turn sessions.
- **Cost per Intent Category**: Segments billing aggregates into clinical domains: `patient_queries`, `billing_queries`, `lab_queries`.

#### 11.11.4 Feature Flags
System capabilities can be enabled or disabled dynamically at runtime without requiring hotfix deployments:
- `enable_glm_fallback`: Toggle failover to GLM-4.7-Flash.
- `enable_semantic_cache`: Turn on or off Redis vector similarity matching.
- `enable_new_router`: Toggle ON/OFF the ONNX MiniLM semantic intent classifier.
- `enable_new_prompt`: Control prompts upgrades between prompt database releases.

---

## 11.12 On-Call Incident Runbooks

### 11.12.1 AWS Bedrock API Failure Runbook
1. **Detection**: OpenTelemetry alarms alert on Bedrock HTTP 503/429 counts exceeding 5% in 1 minute.
2. **Automated Action**: Custom interceptor initiates cascade failover to GLM-4.7-Flash. Circuit breaker switches to OPEN.
3. **Manual Verification**: On-call engineer checks AWS Service Health Dashboard for Bedrock outages.
4. **Remediation**: If Bedrock remains down and GLM shows high load, scale GLM backend instance pools. Once Bedrock reports recovery, confirm circuit breaker enters HALF-OPEN.

### 11.12.2 Redis Cache Cluster Down Runbook
1. **Detection**: Datadog throws connection failure alarms on Redis nodes.
2. **Automated Action**: Interceptor enters pass-through mode, bypassing semantic caching and rate limiting checks. Queries direct SQL lookups for user auth tracking.
3. **Manual Verification**: SSH to Redis node, check memory allocation and system logs.
4. **Remediation**: Execute Redis service restart command. If data corruption occurs, restore daily backup. Rate limits will re-initialize dynamically.

### 11.12.3 Database statement_timeout Runbook
1. **Detection**: DB logs report `statement_timeout (2000ms exceeded)` errors.
2. **Automated Action**: Tool validator wraps query fail state as FAILED with status code TIMEOUT.
3. **Manual Verification**: Query PostgreSQL pg_stat_activity to check lock contentions or slow joins.
4. **Remediation**: If slow queries originate from a specific tool (e.g., `invoice_list`), toggle corresponding tool feature flag (`enable_tool_invoice_list = false`) in the Admin portal to block database access until indices are rebuilt.

### 11.12.4 Monthly Cost Quota Spike Runbook
1. **Detection**: Telemetry tracker registers cost spikes exceeding monthly budget limits.
2. **Automated Action**: Limit manager locks out tenant, blocking further requests and responding with the monthly limit exceeded notification.
3. **Manual Verification**: Audit cost dashboard to identify compromised API keys or anomalous query loops.
4. **Remediation**: Adjust the budget ceiling in `TenantAiLimits` via the Admin Portal if the spike is approved; otherwise, verify user tokens and tighten rate limits.

---

## 11.13 Tool Dependency Registry

To avoid tool-calling loops and prevent execution loops in complex clinical queries, all tools strictly adhere to the following permitted calling path registry:

```
Tool Dependency Mappings
├─ patient_lookup
│   ├─ May invoke: patient_vitals
│   └─ May invoke: appointments
└─ appointments
    └─ May invoke: invoice_details
```
- **Rule Verification**: The Vercel AI SDK execution interceptor validates that no dependent tool (e.g. `invoice_details`) is executed in the loop unless its prerequisite lookup tool (e.g. `appointments`) has resolved a valid parent ID in a prior turn of that query block.





