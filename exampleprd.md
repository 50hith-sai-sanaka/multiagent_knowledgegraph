# AI Read-Only HMS Assistant - Product Requirements Document

## Document Information

| Field | Details |
|-------|---------|
| Product/Module | HMS Core / AI Assistant |
| Date Created | 2026-06-09 |
| Last Updated | 2026-06-09 |
| Prepared By | Staff AI Engineer & Enterprise PRD Writer |
| Stakeholders | Hospital Administrators, Clinic Leads, PM, Engineering Lead |
| Status | In Review |

---

## 1. Overview

### 1.1 Problem Statement

**What problem are we solving?**
Healthcare professionals (doctors, nurses, and administrators) spend a significant amount of time searching for specific patient records, clinical case sheets, and billing statuses across multiple clicks and nested menus in the Hospital Management System (HMS). This cognitive overload and navigation friction delays clinical review and reduces operational efficiency. We are building a read-only chatbot that allows users to instantly search, summarize, and retrieve clinical and financial context via natural language queries.

**Current State:**
- Users must manually navigate through the Patients list, search for a patient, click into details, click into EHR history, or open billing tabs to find information.
- The current workflow has high navigation latency and requires multiple context switches.

**Who is affected?**
- Clinicians (Doctors, Nurses) looking for patient summaries, vitals, case sheets, and history.
- Receptionists/Billing staff looking for appointment status, invoices, or billing queues.
- Administrators reviewing operational logs.

### 1.2 Solution Overview

**What are we building?**
An **AI Read-Only HMS Assistant**—a secure, context-aware chatbot widget embedded in the HMS. It enables staff to query patient summaries, appointments, vitals, clinical case sheets, and billing history using natural language. The assistant uses a tool-calling LLM that interfaces with a dedicated, strictly read-only tools layer to fetch data while strictly maintaining tenant isolation and role-based access control (RBAC).

**How does this fit into the product?**
It is a cross-cutting utility layer that links directly to existing read APIs of the Patients, Appointments, Case Sheets, EHR, and Invoices modules. It respects the multi-tenant architecture and does not write or modify any medical or billing data.

### 1.3 Success Criteria

**How will we know this is successful?**

| Metric | Current | Target | Timeline | Measurement Method |
|--------|---------|--------|----------|-------------------|
| Patient Search & Review Time | 120 seconds | < 15 seconds | 2 weeks post-launch | In-app event tracing |
| Chatbot Query Success Rate | N/A | > 92% | 2 weeks post-launch | LLM evaluation log |
| User Adoption Rate | 0% | > 45% of active staff | 2 weeks post-launch | Active session tracking |
| Support tickets for record finding | 15/month | < 3/month | 2 weeks post-launch | Helpdesk ticketing |

### 1.4 Scope & Boundaries

#### What's IN Scope (v1.0)
- [ ] Bottom-right floating chatbot widget in the HMS Portal.
- [ ] Natural language querying of:
  - Patient demographics and lightweight summaries.
  - Appointment lists, schedules, and token queues.
  - Clinical case sheets (chief complaints, diagnoses, vitals, examinations).
  - Patient history (medical, surgical, allergy details).
  - Billing invoices and payment statuses.
- [ ] Explicit multi-tenant context injection at the tool level.
- [ ] Enforced RBAC checking at the tool level (preventing users from viewing data they lack permissions for).
- [ ] User-level data isolation (e.g. doctors see only their own patients unless granted `read:all`).
- [ ] Database schema additions for Conversation Memory.

#### What's OUT of Scope
- ❌ Editing, creating, updating, or deleting any records (e.g., booking appointments, writing prescriptions, editing invoices) via the AI.
- ❌ Integration with public external medical databases.
- ❌ Patient-facing chatbot access (restricted solely to authenticated HMS staff).
- ❌ Voice query input (deferred to v2.0).
- ❌ Accessing or retrieving laboratory test results, lab orders, or sample queue data.

#### Future Considerations
- 💡 Audio-to-text dictation for generating clinical notes (v2.0).

---

## 2. Users & Personas

- **Administrators (`admin`):** Full read access to all metrics, invoices, audit trails, and patient summaries across the tenant.
- **Doctors (`doctor`):** Read access to patient clinical histories, vitals, case sheets, and appointments associated with their patients (subject to `patients:read:all` or `patients:read:own` permissions).
- **Nurses (`nurse`):** Read access to patient vitals, appointments, and general EHR summaries.
- **Receptionists/Billing Staff (`receptionist`):** Read access to appointment slots, invoice billing queues, payment statuses, and patient demographics.

---

## 3. User Experience

### 3.1 Key User Flows

#### Primary Flow: Staff queries patient EHR summary
**Entry Point:** Floating chat widget in bottom-right corner of the HMS.

**Steps:**
1. Staff member clicks the chatbot icon.
2. Chat widget slides open.
3. User enters prompt: *"Summarize the medical history and latest vitals for Patient John Doe."*
4. Widget sends the prompt along with the user's JWT to `POST /api/chatbot/query`.
5. Backend resolves the tenant and user context, forwards the prompt to the LLM.
6. The LLM selects `patient.getSummary` and `ehr.getHistory` tools.
7. The Tool Layer receives the request, validates that the user possesses `patients:read:all` or `patients:read:own` permission, and calls the respective read-only HMS services.
8. The service returns the data, formatted as context to the LLM.
9. The LLM synthesizes a response and streams/sends it back to the client.
10. The chatbot widget displays the response to the user.

**Success Outcome:** The user gets a correct clinical summary of the patient without leaving their current screen.

**Error Paths:**
- *Tenant Context Missing:* Promptly returns a `401 Unauthorized` / `403 Forbidden` response.
- *Insufficient Permissions:* If the user asks for financial data but lacks `billing:read`, the tool layer raises a security error and the LLM responds: *"I do not have authorization to display billing details for this tenant."*

**User Journey Map:**
```
[HMS Screen] → [Click Floating Widget] → [Chat Interface Opens] → [Enter Query] 
→ [JWT Authenticated & Handled by Backend] → [Tool Layer Enforces RBAC/Tenant Isolation]
                                                               ↓
                                             [Access Granted] ← → [Denied]
                                                    ↓                 ↓
                                         [Query Results Returned]   [Show Auth Error]
```

### 3.2 Use Cases

#### Use Case 1: Query Vitals
- **Actor:** Nurse
- **Trigger:** Nurse wants to know the latest blood pressure readings of a patient.
- **Precondition:** Nurse is logged in, tenant context resolved.
- **Main Flow:**
  1. Nurse asks: *"What is Jane Smith's latest blood pressure?"*
  2. The LLM invokes `patient.getVitals` tool.
  3. Tool verifies `patients:read:own` or `patients:read:all` is in user permissions.
  4. Tool queries the `CaseSheetVitals` table for the patient.
  5. Response returned to LLM, formatted, and shown to user.
- **Postcondition:** Latest BP reading displayed with timestamps.

---

### 3.3 Functional Requirements

| Requirement ID | Feature | Priority | User Story | Acceptance Criteria |
|----------------|---------|----------|------------|---------------------|
| FR-CHAT-01 | Chat Widget | Must Have | US #1 | Floating widget in bottom-right; toggle slide opening. |
| FR-CHAT-02 | Natural Language Query | Must Have | US #2 | Chat inputs support standard prompts up to 1000 characters. |
| FR-CHAT-03 | Contextual Tenant Isolation | Must Have | US #3 | Chatbot backend automatically filters all DB calls using the tenant context. |
| FR-CHAT-04 | Enforced Read-Only RBAC | Must Have | US #4 | LLM cannot call any write or modify tools. The tool layer actively validates user permission scopes. |
| FR-CHAT-05 | History & Memory | Should Have | US #5 | Conversations are persisted to database so the user can see recent chat history. |

---

### 3.4 Business Rules

| Rule ID | Business Rule | Rationale | Impact if Violated |
|---------|---------------|-----------|-------------------|
| BR-CHAT-01 | Zero Write Access | The chatbot is purely informational; it must never execute a DB write or patch. | Risk of accidental prescription changes, invoice modifications, or booking overlaps. |
| BR-CHAT-02 | Strict Tenant Isolation | The LLM tool parameters must never allow cross-tenant query injections. | Extreme risk of patient data leak across hospitals/clinics. |
| BR-CHAT-03 | Context-Aware RBAC | The chatbot cannot bypass role boundaries. If a user cannot view billing, the AI cannot fetch billing. | Information disclosure and privilege escalation. |

---

### 3.5 UI/UX Requirements

- **Design Aesthetics:** Rich dark/light mode integration, glassmorphism panel overlay, smooth transition animations, clean message bubbles with markdown parsing.
- **Widget Placement:** Bottom-right floating icon with a notification badge.
- **UI States:**
  - **Loading:** Subtle skeleton bubble or pulsing loading dots.
  - **Error:** Inline warning notice in the bubble.
  - **Success:** Markdown-parsed clinical text.

---

## 4. Content & Messaging

### 4.1 In-Product Copy
- **Empty State:** *"Hello! I can help you search for patients, check schedules, read clinical vitals, or track invoices. What would you like to know?"*
- **Error - Unauthorized:** *"I'm sorry, but you do not have permission to view this resource."*
- **Error - Server Timeout:** *"I am having trouble connecting to the medical records service. Please try again shortly."*

---

## 5. Integration & Dependencies

### 5.1 System Dependencies

| System/Service | What We Need | Impact if Unavailable |
|----------------|--------------|---------------------|
| Auth0 Authentication | User identity token (JWT) | Chatbot completely disabled |
| Tenant Context Middleware | Resolving tenant workspace ID | Chatbot returns 403 (No tenant context) |
| Prisma / Postgres Database | Fetching HMS entities and storing conversations | Cannot fetch records or maintain history |

---

### 5.2 Data Requirements

**Database Schema Additions (Prisma):**

```prisma
model chat_conversations {
  id          String         @id @default(uuid()) @db.Uuid
  tenant_id   String         @db.Uuid
  user_id     String         @db.Uuid
  title       String         @db.VarChar(255)
  created_at  DateTime       @default(now()) @db.Timestamptz(6)
  updated_at  DateTime       @updatedAt @db.Timestamptz(6)
  is_archived Boolean        @default(false)
  messages    chat_messages[]
  tenant      tenants        @relation(fields: [tenant_id], references: [id], onDelete: Cascade)
  user        tenantpanel_users @relation(fields: [user_id], references: [id], onDelete: Cascade)

  @@index([tenant_id])
  @@index([user_id])
  @@map("chat_conversations")
}

model chat_messages {
  id              String             @id @default(uuid()) @db.Uuid
  conversation_id String             @db.Uuid
  role            String             @db.VarChar(50) // 'user' | 'assistant' | 'system'
  content         String             @db.Text
  created_at      DateTime           @default(now()) @db.Timestamptz(6)
  tool_calls      Json?              // Logs LLM tool invocation metadata
  conversation    chat_conversations @relation(fields: [conversation_id], references: [id], onDelete: Cascade)

  @@index([conversation_id])
  @@map("chat_messages")
}
```

---

## 6. Edge Cases & Scenarios

| Scenario | Expected Behavior | User Experience |
|----------|-------------------|-----------------|
| User asks for patient records they do not own under `read:own` | Tool layer raises a Forbidden error. | Chatbot displays: *"You are not authorized to view John Doe's records."* |
| User tries to inject database commands inside the chat prompt | System filters input; LLM ignores SQL/Prisma instructions and treats it as text. | Chatbot displays standard response without SQL execution. |
| User switches between different tabs | Chatbot maintains conversation state in the floating window. | Conversation remains intact. |

---

## 7. Risks & Mitigation

| Risk | Probability | Impact | Mitigation Strategy | Owner |
|------|-------------|--------|-------------------|-------|
| Prompt Injection (Jailbreaking) | Medium | High | Strict system prompt rules, LLM temperature limits, and hard boundaries in the Tool Layer. | Security / AI Engineer |
| Cross-tenant data leak | Low | Critical | Ensure the tool layer forces the `tenantId` parameter from the user session and rejects arguments from the LLM prompt. | Principal Architect |
| Performance latency in tool calling | Medium | Medium | Implement Redis caching for common master-data lists and optimize Prisma query projections. | Backend Lead |

---

## 8. Open Questions & Decisions

| Question | Options | Impact | Decision By | Deadline |
|----------|---------|--------|-------------|----------|
| Which LLM provider should be used? | A) OpenAI GPT-4o-mini<br>B) Anthropic Claude 3.5 Sonnet<br>C) Google Gemini 1.5 Pro | High (cost & latency) | Architecture Board | Before dev starts |
| Should we support response streaming? | A) Yes, for fast UX<br>B) No, wait for complete payload | Medium (UI complexity) | Frontend Lead | Before dev starts |

---

## 9. Appendix

### 9.1 References
- NestJS Custom Guarding: [NestJS Guards](https://docs.nestjs.com/guards)
- Prisma Client Transactions: [Prisma Transactions](https://www.prisma.io/docs/concepts/components/prisma-client/transactions)

### 9.2 Change Log
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-09 | Staff AI Engineer | Initial PRD draft for AI HMS Assistant |
| 1.1 | 2026-06-09 | Staff AI Engineer | Removed laboratory modules from scope; tightened success criteria timeline to 2 weeks post-launch. |

---

## Document Sign-Off

**Stakeholder Review:**
- [ ] Product Manager: Approved / Changes Needed
- [ ] Engineering Lead: Approved / Changes Needed
- [ ] Design Lead: Approved / Changes Needed
- [ ] Security Architect: Approved / Changes Needed