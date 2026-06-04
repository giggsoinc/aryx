# Aryx Demo — Q&A Samples with Reasoning

## Domain: Radio Equipment Support (Enterprise Networking)

This guide shows sample questions and reasoning for demonstrating Aryx onboarding with the support ticket dataset.

---

## BRIEF Phase — Competency Questions

**Scenario:** You're onboarding Aryx to manage support for an enterprise radio equipment vendor.

### Q1: Domain of Interest
**Question:** *What is the domain we're modeling?*

**Answer:** 
```
SaaS enterprise support for radio networking equipment
```

**Reasoning:**
- We're modeling enterprise radio device support, not consumer support
- Multiple customers (network operators) manage fleets of radios across sites
- Support is multi-tiered (L1/L2/L3) with escalation paths
- Domain-specific vocabulary: firmware versions, RF interference, SLA tiers

---

### Q2: Aim — Purpose of the Knowledge Model
**Question:** *What should this knowledge model enable us to do?*

**Answer:**
```
Enable intelligent ticket routing and escalation — match complex problems 
to the right agent based on device model, symptom, firmware version, and 
agent expertise. Expose patterns in failures so we can predict RMA needs 
and proactive firmware updates.
```

**Reasoning:**
- Current state: tickets assigned randomly or by availability
- Desired state: AI matches ticket symptoms + device context to agent expertise
- Secondary insight: pattern discovery in failures (e.g., "all 6.2.1 radios fail in high-temp environments")
- Measurable: reduce MTTR (mean time to resolution) by 30%

---

### Q3: Objectives that Meet the Aim (One Per Line)

**Questions:**
1. *What measurable outcomes define success?*
2. *Which entities matter most for ticket routing?*

**Answers:**
```
Surface device failure patterns by model + firmware version
Match ticket symptom to agent expertise (firmware, hardware, RF)
Identify escalation-prone tickets before L1 assignment
Track MTTR by device model + agent level (L1/L2/L3)
Flag RMA-eligible devices proactively
```

**Reasoning:**
- Each objective maps to a capability Aryx will surface
- "Surface patterns" → Graph queries find common failure combos
- "Match expertise" → Link agent tags to symptom keywords
- "Escalation-prone" → Classify high-priority symptoms (critical firmware, thermal shutdown)
- "Track MTTR" → Observability metrics
- "Flag RMA" → Derive fact from resolution type + success rate

---

### Q4: Scope — What's IN, What's OUT

**Question:** *What data matters; what doesn't?*

**Answer:**
```
IN: Customers, Sites, Devices (model, firmware, config), Tickets (symptom, priority, status), 
    Agents (level, specialty), Resolutions (solution type, success/fail), Expertise Tags
    
OUT: Customer contracts/billing, on-site engineer dispatch, sales/revenue, 
     network topology details, RF spectrum licensing
```

**Reasoning:**
- IN = operational support data (what happened, who solved it, why)
- OUT = commercial/legal/infrastructure (outside scope of support intelligence)
- Scope is tight: focus on ticket→resolution logic
- Don't bloat the graph with billing or RF engineering details

---

### Q5: Participant Roles

**Question:** *Who uses this ontology and what do they need?*

**Answers:**
```
Support Agent (L1/L2/L3)          - "Show me similar tickets to help solve this one"
Support Manager                   - "Which agents are overloaded? Which device models have high failure rates?"
Product Engineer                  - "What symptoms correlate with firmware bugs in 6.2.1?"
Customer Success Manager          - "Is this device RMA-eligible or can we push a fix?"
```

**Reasoning:**
- Different personas query the graph differently
- L1 agent: lookup by symptom + device
- Manager: aggregations (team workload, device reliability)
- Product Eng: failure pattern analysis (firmware regression)
- CSM: customer risk (RMA vs quick fix)

---

## INGEST Phase — Sample Queries

After you answer the 5 Brief questions, Aryx ingests the schema. Show these queries to the customer:

### Query 1: Device Inventory
```sql
SELECT model, firmware_version, COUNT(*) as count, 
       COUNT(CASE WHEN status = 'active' THEN 1 END) as active
FROM support_devices
GROUP BY model, firmware_version
ORDER BY count DESC;
```

**What Aryx extracts:**
- Entity type: `Device` (model, firmware_version, status)
- Relationship: `Device —hasFirmware→ FirmwareVersion`
- Attribute: `status` (active, degraded, rma, inactive)

---

### Query 2: Ticket Escalation Paths
```sql
SELECT 
  t.priority,
  t.status,
  COUNT(*) as ticket_count,
  COUNT(CASE WHEN t.escalation_reason IS NOT NULL THEN 1 END) as escalated
FROM support_tickets t
WHERE t.created_at > CURRENT_DATE - INTERVAL '30 days'
GROUP BY t.priority, t.status;
```

**What Aryx extracts:**
- Entity type: `Ticket` (priority, status, escalation_reason)
- Relationship: `Ticket —hasStatus→ TicketStatus`
- Pattern: escalation correlates with priority (critical → escalated)

---

### Query 3: Agent Expertise & Workload
```sql
SELECT 
  a.name, a.level, a.specialty,
  COUNT(t.id) as tickets_assigned,
  COUNT(CASE WHEN t.status = 'resolved' THEN 1 END) as resolved,
  COUNT(DISTINCT ae.tag_id) as expertise_count
FROM support_agents a
LEFT JOIN support_tickets t ON a.id = t.assigned_agent_id
LEFT JOIN support_agent_expertise ae ON a.id = ae.agent_id
GROUP BY a.id, a.name, a.level, a.specialty
ORDER BY a.level DESC, resolved DESC;
```

**What Aryx extracts:**
- Entity type: `Agent` (level, specialty, expertise_tags)
- Relationships:
  - `Agent —hasLevel→ L1|L2|L3`
  - `Agent —hasSpecialty→ Firmware|Hardware|Network`
  - `Agent —hasExpertise→ ExpertiseTag`
- Metric: workload per agent, resolution rate

---

### Query 4: Device-Ticket Correlation (Root Cause Analysis)
```sql
SELECT 
  d.model,
  d.firmware_version,
  COUNT(t.id) as ticket_count,
  COUNT(DISTINCT r.solution_type) as unique_solutions
FROM support_devices d
LEFT JOIN support_ticket_device_links tdl 
  ON d.id = tdl.device_id AND tdl.device_role = 'root_cause'
LEFT JOIN support_tickets t ON tdl.ticket_id = t.id
LEFT JOIN support_resolutions r ON t.id = r.ticket_id
WHERE d.status IN ('active', 'degraded')
GROUP BY d.model, d.firmware_version
HAVING COUNT(t.id) > 5
ORDER BY ticket_count DESC;
```

**What Aryx extracts:**
- Complex relationship: `Device —rootCauseOf→ Ticket —resolvedBy→ Resolution —ofType→ SolutionType`
- Pattern: specific firmware versions have recurring solutions (e.g., "all 6.2.1 → firmware_update")
- Insight: RMA decision (if success_flag = false, escalate to RMA)

---

## ASK Phase — Pre-Canned Questions for Demo

After Aryx has ingested, show these live queries:

### Question 1: "Show me open tickets assigned to L3 agents"

**Demo SQL:**
```sql
SELECT t.id, t.priority, t.symptom_text, a.name, a.specialty
FROM support_tickets t
JOIN support_agents a ON t.assigned_agent_id = a.id
WHERE t.status = 'open' AND a.level = 'L3'
LIMIT 10;
```

**Aryx reasoning:**
- User asked for: tickets (status=open) + agents (level=L3)
- Aryx inferred: join condition via `assigned_agent_id`
- Aryx filtered: priority visible for urgency sorting

---

### Question 2: "Which devices have unresolved tickets?"

**Demo SQL:**
```sql
SELECT DISTINCT d.model, d.firmware_version, COUNT(t.id) as open_count
FROM support_devices d
JOIN support_ticket_device_links tdl ON d.id = tdl.device_id
JOIN support_tickets t ON tdl.ticket_id = t.id
WHERE t.status IN ('open', 'in_progress', 'escalated')
GROUP BY d.model, d.firmware_version
ORDER BY open_count DESC;
```

**Aryx reasoning:**
- Pattern: certain firmware versions cluster failures
- Recommendation: "Proactive firmware update candidate for 6.2.1"

---

### Question 3: "Show me escalations that are still open"

**Demo SQL:**
```sql
SELECT t.id, t.created_at, t.escalation_reason, a.name, a.level
FROM support_tickets t
LEFT JOIN support_agents a ON t.assigned_agent_id = a.id
WHERE t.status = 'escalated' AND t.escalation_reason IS NOT NULL
ORDER BY t.created_at DESC;
```

**Aryx reasoning:**
- Escalation reason is semantic context (why it escalated, not just that it did)
- Trend: "80% escalations cite 'hardware diagnostics inconclusive'" → design better L1 diagnostic

---

### Question 4: "Which agent should get this new ticket?"

**Demo input:** 
```
Device: RadioX-6000 firmware 6.2.1
Symptom: Firmware crashes on boot
```

**Aryx reasoning:**
1. Parse entities: Device(RadioX-6000, 6.2.1) + Symptom(firmware)
2. Find agent with `Firmware` specialty
3. Filter for `Firmware-6.2` expertise tag
4. Check workload: assign to L2 if available, else escalate to L3
5. Result: Sam Patel (L2, Firmware, Firmware-6.2 tag, 3/5 tickets)

---

## GRAPH Phase — Entity Relationships (RDF Preview)

**Sample triples Aryx will surface:**

```turtle
# Device → Firmware
:Device_RadioX6000_001 rdf:type :Device ;
  :hasModel "RadioX-6000" ;
  :runsFirmware :Firmware_6_2_1 ;
  :atSite :Site_NYC_HQ .

# Firmware → Known Issues
:Firmware_6_2_1 rdf:type :FirmwareVersion ;
  :version "6.2.1" ;
  :hasKnownIssue :Issue_CrashOnBoot ;
  :typePrefix "Firmware" .

# Ticket → Root Cause
:Ticket_131 rdf:type :SupportTicket ;
  :hasPriority :Priority_High ;
  :symptom "Firmware crashes on boot" ;
  :rootCause :Device_RadioX6000_001 ;
  :assignedTo :Agent_SamPatel ;
  :resolved :Resolution_131 .

# Agent → Expertise
:Agent_SamPatel rdf:type :SupportAgent ;
  :name "Sam Patel" ;
  :hasLevel :L2 ;
  :hasSpecialty :Firmware ;
  :hasExpertise :Tag_Firmware_6_2 ;
  :resolvedTickets "45" .

# Resolution → Success
:Resolution_131 rdf:type :Resolution ;
  :solutionType "firmware_update" ;
  :success true ;
  :knowledgeLink "https://kb.example.com/firmware-6.2-known-issues" .
```

**What customer sees:**
- Clear entity types (Device, Ticket, Agent, Resolution)
- Relationships make reasoning explicit (why this agent, why this solution)
- Reusability: next ticket with same device+symptom → use same resolution

---

## ONTOLOGY Export — RDF Format

**What Aryx publishes (sample):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:aryx="https://aryx.example.com/support-ontology#">
  <rdf:Description rdf:about="https://aryx.example.com/support-ontology#Device">
    <rdf:type rdf:resource="http://www.w3.org/2000/01/rdf-schema#Class"/>
    <rdfs:comment>Physical radio equipment deployed at a customer site</rdfs:comment>
  </rdf:Description>
  <rdf:Description rdf:about="https://aryx.example.com/support-ontology#hasFirmware">
    <rdf:type rdf:resource="http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"/>
    <rdfs:domain rdf:resource="https://aryx.example.com/support-ontology#Device"/>
    <rdfs:range rdf:resource="https://aryx.example.com/support-ontology#FirmwareVersion"/>
  </rdf:Description>
</rdf:RDF>
```

---

## OBSERVABILITY Phase — Metrics Dashboard

**What Aryx shows the manager:**

```
📊 Support Team Metrics (Last 30 days)

Total Tickets:        200
Resolved:             174 (87%)
Open:                  26 (13%)
Escalated:             18 (9%)

By Priority:
  Critical:  8 tickets, 75% escalated, avg MTTR 4h
  High:     32 tickets, 40% escalated, avg MTTR 8h
  Medium:   95 tickets,  5% escalated, avg MTTR 16h
  Low:      65 tickets,  0% escalated, avg MTTR 24h

By Device Model:
  RadioX-9000: 45 tickets, 92% resolved, 0 RMA
  RadioX-7000: 38 tickets, 89% resolved, 1 RMA
  RadioX-6000: 52 tickets, 79% resolved, 3 RMA  ⚠️

By Agent:
  Alex Chen (L3):        45 resolved, 98% success
  Jordan Martinez (L3):  38 resolved, 95% success
  Sam Patel (L2):       42 resolved, 88% success
  
🎯 Insights:
  • RadioX-6000 firmware 6.2.1 has 3x higher RMA rate
  • L1 agents close 30% faster with Firmware-6.2 expertise tag
  • Critical tickets w/ escalation reason "hardware inconclusive" 
    → 60% higher RMA → suggest better L1 diagnostics
```

---

## Demo Script (15 min)

1. **Brief (2 min):** Show redesigned Q&A form, fill in answers, click Save
   - *"This is the context Aryx will use for extraction"*

2. **Ingest (2 min):** Point Aryx at the 6 tables, show sample row
   - *"Aryx scans schema and sample data"*

3. **Ask (3 min):** Run 2–3 pre-written queries live
   - *"You already know these queries; Aryx learns from them"*

4. **Graph (4 min):** Show entity triples, explain relationships
   - *"This is the domain model Aryx discovered"*

5. **Ontology (2 min):** Export to RDF, explain reusability
   - *"Now you can share this with your product team"*

6. **Observability (2 min):** Show metrics dashboard
   - *"This is what gets updated every time a ticket is resolved"*

---

**Timing:** 15 min live demo, 10 min Q&A. Total 25 min.
