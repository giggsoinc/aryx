# Aryx Demo Setup Guide — Radio Equipment Support Case

## Overview

This guide walks you through setting up and demonstrating Aryx with a real **enterprise support ticketing system**. The demo uses 200 radio equipment support tickets with realistic escalation patterns, device failures, and agent expertise matching.

By the end, Aryx will extract a knowledge graph that lets you ask natural questions like:
- *"Which agent should handle this firmware bug?"*
- *"What's the failure pattern for RadioX-6000 devices?"*
- *"Show me escalation-prone tickets"*

---

# PART 1: THE BRIEF (5 minutes)

## What is the Brief?

The Brief is **your declared intent**. It answers 5 questions that ground Aryx's entity extraction in your domain, not generic NER.

Without a brief → Aryx sees: *Person, Company, Date, Email* (vanilla NLP)  
With a brief → Aryx sees: *Agent, Customer, Device, Ticket, Resolution* (domain-specific)

---

## 1. Domain of Interest

**Question:** *What industry/domain are we modeling?*

**Your Answer:**
```
Radio equipment support — enterprise networking

(or: SaaS enterprise support for network radio devices)
```

**Why:** Tells Aryx to look for radio-specific entities like `Device`, `Firmware`, `RF Interference`, not generic product names.

---

## 2. Aim — Purpose of the Knowledge Model

**Question:** *What should this graph enable? What outcome?*

**Your Answer:**
```
Match complex support tickets to the right expert agent based on device model, 
symptom, firmware version, and agent expertise. Expose patterns in device failures 
so we can predict RMA needs and recommend proactive firmware updates.
```

**Breaking it down:**
- **Outcome 1:** Smart routing (right agent for each ticket)
- **Outcome 2:** Pattern discovery (which devices fail, why, how often)
- **Outcome 3:** Predictive action (RMA early, firmware proactive)

**Why it matters:** When Aryx sees "firmware crash" + "RadioX-6000" + "6.2.1", it knows to link them because your aim explicitly mentions firmware versions and device models.

---

## 3. Objectives that Meet the Aim (One Per Line)

**Question:** *What specific measurable things should this graph surface?*

**Your Answer:**
```
Surface device failure patterns by model + firmware version
Match ticket symptom to agent expertise (firmware, hardware, network)
Identify escalation-prone tickets before L1 assignment
Track MTTR (mean time to resolution) by device model + agent level
Flag RMA-eligible devices proactively
```

**What each does:**
1. **Failure patterns** → Find "All RadioX-6000 with firmware 6.2.1 fail in high-temp environments"
2. **Expertise match** → "This firmware bug needs Sam Patel (has Firmware-6.2 tag)"
3. **Escalation prediction** → "Critical priority + hardware diagnostics = escalate immediately"
4. **MTTR tracking** → "L3 agents resolve firmware issues 3x faster than L1"
5. **RMA flag** → "Device has 3 failed resolutions → recommend RMA, not fix"

---

## 4. Scope — What's IN, What's OUT

**Question:** *What data matters; what's noise?*

**Your Answer:**
```
IN: 
  customers (network operators)
  sites (deployment locations)
  devices (radio models, firmware versions, config)
  tickets (symptoms, priority, status)
  agents (level, specialty, expertise)
  resolutions (solution type, success/fail)
  
OUT:
  customer billing/contracts
  sales/revenue
  on-site engineer dispatch
  RF spectrum licensing
  network topology details
```

**Why:** Keeps the graph **focused**. You're modeling support intelligence, not the entire business. Billing is irrelevant to "which agent solves this ticket."

---

## 5. Participant Roles (One Per Line)

**Question:** *Who uses this graph, and what do they need?*

**Your Answer:**
```
Support Agent (L1/L2/L3)      — "Show me similar tickets to help solve this one"
Support Manager               — "Which agents are overloaded? Device reliability trends?"
Product Engineer              — "What symptoms correlate with firmware 6.2.1 bugs?"
Customer Success Manager      — "Is this device RMA-eligible or can we push a fix?"
```

**What this does:** Different roles ask different questions. Aryx structures the graph so:
- Agents query: *symptom + device → similar tickets + agent expertise*
- Managers query: *team workload + device failure rates*
- Product eng queries: *failure patterns by firmware version*
- CSMs query: *device → RMA risk assessment*

---

# PART 2: THE INGEST (2 minutes)

## What Happens in Ingest?

You upload your data. Aryx **introspects** it and discovers entities.

```
Your tables (raw data):
  support_tickets (200 rows)
  support_devices (280 rows)
  support_agents (15 rows)
  ...
        ↓ Aryx introspection
  ↓ Infers entities:
        Ticket { id, status, priority, symptom, assigned_agent_id, ... }
        Device { model, firmware_version, status, ... }
        Agent { name, level, specialty, expertise_tags, ... }
  ↓ Infers relationships:
        Ticket —assignedTo→ Agent
        Ticket —affectsDevice→ Device
        Device —runsFirmware→ FirmwareVersion
        Agent —hasExpertise→ ExpertiseTag
        Ticket —resolvedBy→ Resolution
```

---

## Extra Optional Context (For Advanced Ingest)

If you want to guide Aryx's extraction:

```
Hint: "ticket.assigned_agent_id points to a L2/L3 support specialist with 
       certifications in firmware, hardware, or network troubleshooting"

Result: Aryx understands Agent urgency & expertise, not just names.
```

**Most of the time:** Leave hints blank. Aryx is smart enough to infer from Brief.

---

## The Ingest Flow in Aryx UI

### **Step 1: Click "Ingest" Tab**

You'll see:
```
This workspace has no graph yet — go to Ingest to add data.
```

Click **+ Add Data Source**

---

### **Step 2: Connect to Your Data**

**Option A: CSV File (Easiest)**
- Click **CSV Upload**
- Upload `/tmp/tickets.csv` (or any of the 6 exported CSVs)
- Aryx introspects columns → infers entity types

**Option B: PostgreSQL (If available)**
- Click **PostgreSQL Database**
- Enter: `host=postgres, port=5432, user=aryx, password=aryx, db=aryx`
- Aryx scans tables → offers table selection
- Select: support_customers, support_sites, support_devices, support_agents, support_tickets, support_resolutions, support_ticket_device_links

---

### **Step 3: Click "Introspect"**

Aryx scans your data and shows:

```
Found:
  - 200 rows: support_tickets
    Columns: id, site_id, assigned_agent_id, status, priority, symptom_text, ...
    Inferred entity: Ticket
    
  - 280 rows: support_devices
    Columns: id, site_id, model, firmware_version, status, ...
    Inferred entity: Device
    
  - 15 rows: support_agents
    Columns: id, name, level, specialty, ...
    Inferred entity: Agent
```

---

### **Step 4: Click "Ingest"**

Aryx **extracts entities** and **builds relationships**:

```
Extracting...
  ✓ 200 Ticket entities
  ✓ 280 Device entities
  ✓ 15 Agent entities
  ✓ 200 assignedTo relationships
  ✓ 280 runsFirmware relationships
  ✓ 300 deviceLinks relationships

Done! Graph built with 595 entities, 780 relationships.
```

**What just happened:**
- Every ticket became a `Ticket` node
- Every device became a `Device` node
- The `assigned_agent_id` column became edges: `Ticket —assignedTo→ Agent`
- The `device_model` + `firmware_version` became: `Device —runsFirmware→ FirmwareVersion`

---

# PART 3: GURU EXPLAINER (1 minute)

## Why We Do This & How It Works

**The Problem We're Solving:**

Your company has 200 support tickets, 280 devices, 15 agents. A customer calls with a problem on a RadioX-6000 device running firmware 6.2.1. Who do you call? How do you know if this device should be RMA'd or fixed? Are there patterns in failures?

**The Old Way (Manual):**
- Search ticket database by hand
- Find similar cases (slow, error-prone)
- Guess which agent is free
- Manually look up device failure history

**The New Way (Aryx Graph):**
- Ask: *"Device RadioX-6000 with firmware 6.2.1 crash — who handles this?"*
- Aryx finds: *Sam Patel (L2, Firmware specialist, 45 tickets resolved, 88% success, has Firmware-6.2 tag)*
- Aryx shows: *"8 similar tickets, 7 resolved by Sam, 1 escalated to L3"*
- Aryx recommends: *"Assign to Sam Patel"*

**How Aryx Does It:**

1. **Extract entities from your data** → Turns rows into nodes
2. **Infer relationships** → Turns foreign keys into graph edges
3. **Build ontology** → Understands "firmware version" connects to "device"
4. **Answer questions** → Traverses the graph to find answers

**Why the Brief Matters:**

Without the Brief, Aryx sees: *"A number in a table"*  
With the Brief, Aryx sees: *"A firmware version that's linked to device failures"*

The Brief is the **semantic anchor** that transforms raw data into domain knowledge.

---

# PART 4: ASK THE GRAPH (Questions to Try)

Once ingest is done, go to **Ask** tab and try these:

## Question 1: "Which agent should get this ticket?"

**Ask the Graph:**
```
"Device: RadioX-6000, Firmware: 6.2.1, Symptom: Firmware crashes on boot
Who is the best agent to assign this ticket?"
```

**What Aryx finds:**
```
Best match: Sam Patel (L2, Firmware specialist)
  - Has Firmware-6.2 expertise tag ✓
  - Resolved 7 similar tickets (firmware + RadioX-6000) ✓
  - 88% success rate on firmware issues ✓
  - Currently assigned: 3/5 tickets (has capacity) ✓

Confidence: 92%
Similar past tickets: 7 resolved, 1 escalated
Avg resolution time: 4 hours
```

---

## Question 2: "What's the failure pattern for device X?"

**Ask the Graph:**
```
"Show me all tickets related to RadioX-6000 devices in the last 30 days.
What are the common symptoms?"
```

**What Aryx finds:**
```
RadioX-6000: 15 total tickets
  - 8 resolved (53%)
  - 4 escalated (27%)
  - 3 RMA'd (20%)

Common symptoms:
  1. Firmware crashes on boot (5 tickets) → 6.2.1 firmware
  2. Power supply instability (4 tickets) → affects all models
  3. RF interference (3 tickets) → specific to high-density deployments

Insight: RadioX-6000 firmware 6.2.1 has a stability issue.
Recommendation: Proactive firmware update to 6.3.0
```

---

## Question 3: "Who is overloaded?"

**Ask the Graph:**
```
"Show me agent workload and resolution rates"
```

**What Aryx finds:**
```
Alex Chen (L3, Firmware specialist)
  - Assigned: 12 tickets
  - Resolved: 11 (92% rate)
  - Avg MTTR: 3 hours
  - Status: HIGH DEMAND (3 critical pending)

Sam Patel (L2, Firmware specialist)
  - Assigned: 8 tickets  
  - Resolved: 7 (88% rate)
  - Avg MTTR: 4 hours
  - Status: AVAILABLE (can take 2 more)

Recommendation: Route firmware tickets to Sam instead of Alex for now
```

---

## Question 4: "Is this device RMA-eligible?"

**Ask the Graph:**
```
"Device ID 42 (RadioX-6000, firmware 6.2.1) — should it be RMA'd or fixed?"
```

**What Aryx finds:**
```
Device 42 analysis:
  - Open tickets: 1 (firmware crash)
  - Resolved tickets: 3
  - Failed resolutions: 2/3 (67% failure rate) ⚠️
  - Average age: 18 months
  - Firmware attempts: 2 (both failed)

RMA Score: 7/10 (RECOMMEND RMA)
Reason: High failure rate on repairs + age + repeated failures

Cost analysis:
  - Cost to ship device back: $500
  - Cost of next repair attempt: $200 (likely to fail)
  - Customer satisfaction: High (quick replacement)

Recommendation: APPROVE RMA, ship replacement device
```

---

# PART 5: THE GRAPH (What to See & Why)

Once ingest completes, click **Graph** tab.

## What You See

```
Visualization:
  
  [Agent: Sam Patel] —hasExpertise→ [Tag: Firmware-6.2]
        ↑                                    ↑
        |                                    |
   assignedTo                         usedBy (resolutions)
        |                                    |
        ↓                                    ↓
  [Ticket 42]  ←—affectsDevice—→  [Device: RadioX-6000]  ←—runsFirmware—→ [FW: 6.2.1]
        |                                    ↑
        |                                    |
   resolvedBy                        knownIssue
        |                                    |
        ↓                                    ↓
  [Resolution]  ←—solutionType—→ [FirmwareUpdate]

```

---

## How to Read the Graph

### **Click on a Ticket Node**
```
Ticket 42 details appear:
  - Status: escalated
  - Priority: critical
  - Symptom: "Firmware crashes on boot"
  - Assigned: Sam Patel
  - Affected device: RadioX-6000
  - Created: 2026-05-22
  - Escalation reason: "Hardware diagnostics inconclusive"
```

### **Click on a Device Node**
```
Device RadioX-6000 details:
  - Model: RadioX-6000
  - Firmware: 6.2.1
  - Status: degraded
  - Tickets affecting it: 8
  - Resolutions: firmware_update (3), config_push (2), rma (1)
  - Reliability: 67% (3/15 resolutions successful)
```

### **Click on an Agent Node**
```
Agent Sam Patel details:
  - Name: Sam Patel
  - Level: L2
  - Specialty: Firmware
  - Expertise tags: [Firmware-6.2, Power-management, Configuration-advanced]
  - Assigned tickets: 8
  - Resolved: 7 (88% success)
  - Avg MTTR: 4 hours
```

---

## Why We're Looking at the Graph

**Purpose:** See the **structure** of your support domain.

**Questions it answers:**
- *"Are there clusters of devices with the same problem?"* → See multiple devices in one color
- *"Is one agent a bottleneck?"* → See one agent node with many edges
- *"What patterns emerge?"* → See repeated device-symptom-resolution chains
- *"What's missing?"* → See isolated nodes with no connections

**Action:**
- **High-connectivity** agents: load-balance
- **Problematic devices**: proactive firmware/RMA
- **Unresolved issues**: escalate or redesign approach
- **Expert gaps**: hire/train in specialization

---

## Interactive Exploration

### **1. Search by Device Model**
```
Search: "RadioX-6000"
Shows: All RadioX-6000 nodes + their tickets + agents + resolutions
```

### **2. Filter by Status**
```
Filter: status = "escalated"
Shows: Only escalated tickets + their agents + devices
Insight: "Are escalations concentrated on certain device models?"
```

### **3. Traverse Relationships**
```
Click Ticket → click "affectsDevice" → see Device details
Click Device → click "runsFirmware" → see Firmware version + known issues
Click Agent → click "resolved" → see all tickets they closed
```

---

# PART 6: NEXT STEPS

After ingest and graph exploration:

## 1. **Ask Tab** (Query the graph with natural language)
```
"Show me critical tickets assigned to L1 agents"
"Which devices are RMA-eligible?"
"What's the most common symptom for firmware crashes?"
```

## 2. **Ontology Tab** (Export discovered model)
```
Export as RDF (shared with product/engineering teams)
Capture: Device → Firmware → KnownIssue → Solution pattern
Reusable: "This is how support works"
```

## 3. **Observability Tab** (Metrics dashboard)
```
Track: MTTR, escalation rate, agent utilization, device RMA rate
Alert: "RadioX-6000 failure rate > 30%"
Trend: "Firmware updates reduce RMA by 40%"
```

---

# Summary Checklist

- ✅ **Brief** — Answered 5 questions (domain, aim, objectives, scope, roles)
- ✅ **Ingest** — Uploaded data, Aryx extracted entities & relationships
- ✅ **Ask** — Queried graph with natural language (agent match, failure patterns, RMA decision)
- ✅ **Graph** — Explored entity relationships (saw device-agent-resolution chains)
- ✅ **Ontology** — (Optional) Export discovered domain model as RDF
- ✅ **Observability** — (Optional) View metrics dashboard

**Now:** You have a searchable, queryable knowledge graph of your support domain. Ask Claude via MCP, share with product team via RDF, monitor with metrics.

**Done.** 🎉
