# Speaking Script — EDA / Profiling Agent Layer

Narration script for presenting `docs/eda-profiling-system-documentation.docx` out loud, to a mixed audience of business stakeholders and engineers.

**Estimated run time:** ~40–45 minutes at a natural pace, including the Q&A prep appendix. Bracketed notes are stage directions — don't speak them. Everything else is written to be read aloud as-is, or used as a base you adapt in your own voice. Where it's useful, I've written in concrete "picture this" examples — those are illustrative, not literal excerpts from the system.

---

## Opening (1 minute)

[Pause, make eye contact, then begin]

What I want to walk you through today is a new safety checkpoint we're adding to our data pipeline — something that sits right before information gets written into our knowledge graph. This isn't a small tweak. It's a genuine architectural addition: six new pieces of automated checking logic, wired into one gate, sitting in front of the one place in our entire codebase that writes into the graph.

I'm going to do this in two passes. First, the business case — why we're doing this at all, in plain terms, no file names, no code. Then, a full technical walkthrough — I'm going to go through all ten sections of the design document, in order, in real depth, because I want the engineers in the room to leave here able to actually start building this, not just nod along. If you're not technical, stay for the first part, and then feel free to let your attention drift once the file names start flying — I'll flag exactly when we cross that line, and I'll flag when we come back out the other side at the end.

---

## Part 1 — The Business Case (5–6 minutes)

So here's the problem in one sentence: right now, nothing stops bad data from reaching our knowledge graph.

Let me unpack that, because it's worth sitting with. Today, when structured data comes in — spreadsheets, database tables, JSON files — we do some basic bookkeeping on the way in. We count values, we look at a few samples, we get a rough shape of the data. But none of that is a *gate*. Nothing actually *stops* a file that's missing required fields, or full of duplicate rows, or structurally broken, from reaching the graph. It goes in anyway, quietly, and it becomes indistinguishable from good data the moment it lands.

[Pause] Let me make that concrete. Picture this: someone on the data team uploads a customer dataset, and due to an upstream export bug, half the rows are missing a customer ID — the field everything else in that dataset is supposed to key off of. Today, that file sails through. It gets profiled — we'll count nulls, we'll notice something's off if anyone happens to look — but nothing stops it. It becomes part of the graph. Three weeks later, someone building a report notices the numbers don't reconcile, and now we're doing forensic work to figure out which run introduced the problem, instead of having stopped it at the door.

And it gets meaningfully worse once you leave structured data behind. XML uploads are currently rejected outright — the system won't even accept them today, full stop. And here's the part that should make everyone sit up: the reason we haven't just "turned it on" isn't only that the feature's incomplete. The parser sitting behind that door has a real, known security gap — specifically, it has no protection against a class of attack where a maliciously crafted XML file can either exhaust server resources or trick the parser into reading files it shouldn't have access to. So this isn't just "a feature we haven't built yet." It's a locked door with a broken lock behind it, and we have to fix the lock in the same motion as opening the door — not after.

So — why does any of this matter to the business, beyond "it's good hygiene"? Because the knowledge graph isn't a side project. It's the shared source of truth that our reporting, our entity resolution, and our analytics all depend on. Every dashboard, every downstream number, every automated decision that touches this data is standing on top of what's in that graph. If bad data gets in, it doesn't stay contained to the file that caused it — it quietly spreads into everything built on top. And the cost curve here is brutal and well understood in this industry: catching a data problem at the door costs you a validation rule. Catching it three weeks later, after it's propagated into five reports and a board deck, costs you days of forensic work and a credibility hit.

So what are we proposing? Six small, independent pieces we're calling "agents" — and I want to be precise about that word, because it gets overloaded in the industry right now. We are *not* talking about autonomous AI agents making judgment calls. An "agent" here just means a focused, self-contained checker with one job, one input, one output. Think of it more like a specialized inspector on an assembly line than a robot making decisions.

Each of the six owns one job. One checks structured data — spreadsheets and tables — and importantly, it mostly *reuses* analytics we've already built elsewhere in the system rather than reinventing them. One checks XML files specifically — that one's a genuinely new capability. One checks documents and free text — things like PDFs and Word docs — for type, language, length, entities, and general quality. One is a dedicated data-quality checker that looks across everything for nulls, duplicates, broken records, and encoding problems. One pulls out metadata — where a file came from, its size, its structure, when it arrived. And one, which is optional, simply figures out what *kind* of file it's looking at and routes it to the right checker among the others.

Here's the detail that makes this whole design hang together: every single one of these six produces the exact same shape of report. Not six different formats to learn — one format, six sources. That means whoever reviews the output, whether it's a person or another piece of automation, only has to understand one thing, and it looks the same whether the problem came from a spreadsheet or a scanned PDF.

And critically — not every finding stops the show. If any of these checkers finds something *serious* — a required field that's genuinely missing, sensitive personal data sitting somewhere it shouldn't be, a file that's structurally broken — the run stops. Full stop, nothing reaches the graph. But an ordinary quality warning — say, a column that looks a little more diverse than usual — doesn't halt anything. It gets recorded, and the run proceeds. That distinction between "block" and "warn" is doing a lot of work in this design, and we'll come back to it more than once.

One more thing worth saying plainly, because I don't want to oversell where we are: this hasn't been built yet. What I'm walking you through is the architecture — the blueprint, grounded in a real, careful read of our actual codebase, not a hypothetical greenfield sketch. It's implementation-ready, not implemented. The last section of the document lays out exactly what we'd build first, and what can wait.

[Pause here — this is a natural point for non-technical folks to step out if needed. If anyone's leaving, this is the moment.]

---

## Part 2 — The Technical Walkthrough (30–35 minutes)

Alright. Let's get into how this actually works in the code, section by section, exactly as the document lays it out.

### Section 1 — Mapping the ingestion flow

First question the design had to answer: where does data actually come in today? And the honest answer is — there's no single front door. There are two public APIs, and underneath each of them, a set of per-type connectors that do the actual work of reading a file.

Structured data — CSV, JSON, SQL tables, Postgres tables, REST API responses — comes in through two endpoints. One is a general file-ingest endpoint, the other is a document-discovery endpoint. Depending on which route it takes, it gets handed off to one of several connectors, each one specialized: a CSV connector, a JSON connector, a SQL connector, a Postgres connector, a REST API connector, and one more for replaying already-built records.

XML is the interesting case, and I want to slow down here because it's the clearest illustration of the gap this whole project closes. There is *already* a connector for XML files in our codebase — it's called the Markup Connector — and the internal router that dispatches files to connectors already knows how to send `.xml` files to it. The plumbing exists. But neither public API's list of accepted file extensions actually includes XML. So today, if you try to upload an XML file through either front door, it gets rejected with an HTTP 400 error before it ever reaches that connector. The door is built. It's just locked from the outside, and — as I mentioned — the lock itself needs replacing before we open it.

Documents — PDFs, Word documents, PowerPoint files, images — go through both APIs and get routed by file extension to their matching connector: one for PDFs, one for Word docs, one for PowerPoint, one for images that runs OCR to pull text out of a picture.

All of these, no matter which door they came through, eventually converge on one common internal shape — something we call a raw record. Structured connectors emit one raw record per row or per object in a file. Documents take a meaningfully different path: they get broken into chunks, those chunks get screened for personally identifiable information, and then they get passed through an entity-extraction step that pulls out named things — people, organizations, whatever's relevant — before *those* also become raw records. So structured and unstructured data start from very different shapes, but they land in the same place. From there, everything flows through a step called "discover," which cleans the data, profiles it at a basic level, and lands it into storage.

Second question the design had to answer, and this is the one that really matters operationally: where is the actual point of no return? Where's the last moment before something gets permanently written into the graph? The answer is a single function called `project_graph`. It is the *only* place, in the entire codebase, that writes nodes and edges into FalkorDB — that's our graph database. Everything before that point only touches our regular Postgres database. Nothing is "in the graph" until that one function runs.

And here's a subtlety that's easy to miss, and that the design specifically calls out because missing it would make the whole gate pointless: there are actually *two* separate places in the code that call `project_graph`. One is during the normal, everyday pipeline run. The other is a second call that happens later, when foreign-key relationships between records get resolved after the fact — sometimes minutes or hours after the original run. If we only put our gate in front of the first call site, that second call becomes a silent, totally unintentional bypass — a way for data to reach the graph without ever passing through our new checks. So any gate we build has to wrap *both* call sites, or it isn't really a gate.

There's one more thing worth knowing here, because it changes how we should think about "how much new work is this really." We already have two other profiling systems in this codebase that compute a lot of what we're describing — one profiles a raw dataset snapshot with real depth: type inference, quality flags, role assignment. Another profiles the shape of the graph itself after it's built. Both of these are real, already exist, and already compute genuinely useful things. But both of them run through a code path that explicitly wraps every call in a try-except that just logs a warning and moves on. In plain terms: today, nothing profiling-related can actually stop a graph write. Everything runs best-effort, after the fact, with no teeth. That's really the core finding of this whole first section — the *analytics* mostly already exist in this codebase. What's missing is the *gate*.

Third question: given all that, where should our new checking agents actually run? The design lands on two distinct trigger points, because they're answering two genuinely different questions. First — per file, right at the moment it's ingested. That's where type detection and the format-specific profiling naturally belong, because that's the one moment we still have the raw file or the raw chunk in hand, before it's been dissolved into the rest of the pipeline. Second — once, as a hard gate, immediately before each of those two `project_graph` calls. That's where the aggregate verdict — the final "proceed, warn, or block" decision — actually gets evaluated, and where we genuinely stop a bad run before it touches the graph.

[If showing the diagram now: point to it] This flowchart captures that exact shape. A file comes in on the left, gets classified by the type detector, runs through whichever profiling agent matches its kind, everything rolls up through the metadata agent into one aggregated report, and only after passing through the Data Quality Agent's gate does anything reach the graph on the right. Notice the two colored boxes — blue for the gate, green for the graph itself — that's deliberate, they're the two moments in this whole flow that actually matter for risk.

### Section 2 — What each of the six agents actually does

Let's go through them one at a time, in real depth.

**The Structured Data Profiling Agent.** This one doesn't reinvent anything, and that's a feature, not a shortcut. We already have a lightweight accumulator that counts nulls and distinct values inline as data streams past, during the normal ingest step. And separately, we already have a much richer profiler — one that infers actual data types, assigns each column an analytical role like identifier, measure, dimension, time, or status, and flags real issues: a column that's secretly constant, one with high cardinality, one with mixed types jammed together, statistical outliers. Today, that richer profiler runs *after* the pipeline has already finished, and it never blocks anything — it's advisory only. The change this design calls for is genuinely small: expose that existing profiler's output synchronously, right into our new gate, and make a decision about which of its existing flags should actually halt a run versus just attach a warning. Picture this: a required "region" column that's supposed to vary comes back completely constant — every row says "Unknown." Today that's a shrug. Under this design, that's a `block`.

**The XML Profiling Agent.** This one is genuinely new — nothing like it exists today. Right now, our XML parser throws away all structure the instant it touches a file: it walks the document and flattens everything down into plain "tag: text" lines before anything downstream even sees the shape the original file had. Picture an invoice file with nested line items, each with a tax field — today, all of that nesting just becomes a flat list of lines with no relationship between them. This agent's entire job is to capture what's currently being thrown away: the schema, the nesting depth, which elements repeat, which ones are missing, and what data type each field actually seems to hold.

**The Unstructured Data Profiling Agent.** This one operates on document chunks, and only *after* they've already been screened for sensitive information — that ordering is not incidental, we'll come back to it. It reports the document's type, its length, its language, a lightweight signal of the entities and keywords it contains — and here's a genuinely important efficiency detail: it reuses a language model we've *already* loaded elsewhere in the system, for that PII screening step, rather than paying for a second, expensive model call just to profile a document. We are not running two AI models where one will do.

**The Data Quality Agent.** This is, operationally, the one that matters most, because it's the aggregate gatekeeper — the one whose verdict actually decides whether the graph write happens. It looks at everything the other agents reported for a given run, and it adds some checks of its own that only make sense in aggregate: duplicate record detection, malformed-record detection, encoding issues like garbled text from a bad character-set conversion. It rolls all of that into one final recommendation — proceed, warn, or block — and that single value is what our orchestration layer reads to make the actual go/no-go decision.

**The Metadata Extraction Agent.** This is the quiet, always-on one, and it's deliberately simple — it never blocks anything, ever. It just records where a file came from, what type it is, how big it is, its structure, and when it arrived and when it was processed. Think of it as the paper trail, running alongside everything else, so we always know the provenance of what's in the graph.

**The Data Type Detector.** Optional, and — I want to be honest about this one — it's not even a new algorithm. It's consolidating dispatch logic that already exists, split across two different places in our code, into one clean, explicitly testable component. Its whole job is answering one question: "what kind of thing is this file?" — so every other agent doesn't have to re-derive that answer independently.

### Section 3 — One shared report format, in detail

Here's a design decision that makes everything else in this system simpler, and I want to walk through it field by field, because it's genuinely the backbone of the whole thing.

Every single agent — all six — returns the exact same JSON shape. At the top, a `source` block: what type of data this was, which system and dataset it came from, a unique identifier, and its file path. Then a `schema_info` block: what fields or paths were found, how deeply nested the data was, which elements repeated, what types got inferred. Then `statistics`: how many records or chunks, and stats per field or path. Then, critically, `quality_issues` — a list, where each entry names a specific problem, gives it a severity of either `block` or `warn`, says exactly where it was found, and describes it in plain language. Then `extracted_metadata` — file type, size, timestamps, identifiers. Then `anomalies` and `warnings` as their own lists. And finally, one single field that everything else feeds into: `recommended_next_action`, which is always one of exactly three values — proceed, warn, or block.

Picture this: an XML profiling agent runs against a file, and it finds one field that's supposed to be required but is missing from every single record it looked at. Its report would show one `quality_issues` entry, severity `block`, pointing at that exact field, and its own `recommended_next_action` would read `block`. That result rolls up into the Data Quality Agent's aggregate decision, and *that's* what actually stops the run.

There's one more field worth explaining because it's easy to skip past: `agent_version`. Every report carries the version of the agent that produced it. Why does that matter? Because some of our checks — like drift detection — compare today's result against a historical baseline. If we silently change how an agent computes something without bumping its version number, we'd be comparing apples to oranges without knowing it. This field exists specifically to prevent that quiet failure mode.

Because every agent speaks this exact same language, the code that aggregates all six agents' results together doesn't need six different sets of special-case logic. It's one format, six producers, one aggregator. That's a genuinely large simplification, and it's the kind of decision that pays for itself every time we add a seventh agent later.

### Section 4 — Actually building XML support, step by step

This is worth real time, because it's the single biggest concrete gap this design closes, and the sequencing here is not optional — it's load-bearing.

**Step one: fix the allow-list.** Literally, add the XML and HTML file extensions to the lists our two public APIs check against. That's a small code change. It lets files that were previously rejected actually reach the connector that's already sitting there, ready to receive them.

**Step two — and I need to be very clear that this has to ship in the exact same change as step one, never after — harden the parser.** Let me explain the actual risk in plain terms, because "security gap" can sound abstract until you see the shape of it. Today, our XML parser uses a very basic, standard library tool that trusts the file it's given completely. That opens the door to two real, well-known attack patterns. One is sometimes called a "billion laughs" attack — a tiny, few-kilobyte XML file that defines a value, then defines ten more values that each reference the first ten times, then ten more that each reference *those* ten times, and so on — and by the time a naive parser tries to fully expand that file in memory, a file smaller than this paragraph can balloon into gigabytes and crash or freeze the server that's trying to read it. The other is called an external entity attack, where a crafted XML file can trick a naive parser into reaching outside the file itself — potentially reading local files off the server's disk that were never meant to be exposed. Both of these are well-documented, well-understood attack classes, not edge cases. The fix is to swap in a hardened parsing library that's specifically built to reject both patterns — and the good news is, it's a near drop-in replacement; the rest of our XML-handling logic doesn't need to change. But — and this is the whole point of sequencing steps one and two together — if we open the door in step one without the hardened lock from step two already installed, we've taken a security gap that was previously unreachable and made it directly reachable from the outside world. That's strictly worse than doing nothing.

**Step three: add a structure-preserving pass, alongside the existing flattening logic, not instead of it.** Today, the parser walks an XML tree exactly once and only ever produces that flattened "tag: text" output. This step adds a second pass over that *same already-parsed* tree — no second parse, no extra cost there — that builds four things: a map of every distinct tag path in the document, from the root down, along with how often each one appears and what attributes it carries; the nesting depth at each path; detection of repeated elements, like a list of line items under an invoice; and detection of optional or missing nodes, by comparing tag paths across a sample of similar documents — and I want to flag something important here — XML doesn't have a schema by default, so an element being absent in one document isn't automatically an error, it's a *signal*, something worth surfacing, not something to hard-fail on, unless someone's actually supplied a formal schema to validate against.

**Step four, and this one is really more of a guarantee than a step: the existing flattened output has to stay byte-for-byte identical, before and after this change.** We are strictly adding a new capability here. Nothing that currently reads that flattened text should ever notice this change happened.

### Section 5 — Unstructured document analysis, in detail

For documents — PDFs, Word files, scanned images — once they've been broken into chunks, we're extracting several things, and I want to walk through why each one earns its place. Document and file type — no new detection work needed here, we just read what the router already determined. Text length and basic statistics — character count, word count, how many chunks a document produced. Language — a lightweight detection pass over a bounded sample of the text; if it fails, that's not an error, it just comes back as "unknown" and we move on. A lightweight signal of entities and keywords, reusing that same already-loaded language model I mentioned earlier, specifically so we're not running an expensive second AI call just for profiling purposes. Document structure — which, again, is nearly free, because page and slide boundaries are already tracked on every chunk; a "structure summary" here is really just aggregating information we already have sitting right there. Duplicate and near-duplicate content detection — picture a scanned document where the same boilerplate legal disclaimer appears on every single page; a similarity-signature technique can flag that kind of repetition, both within one document and, optionally, across an entire run, to catch near-duplicate documents. And finally, missing or corrupted content — picture a badly scanned page that produces mostly OCR noise instead of real text; we flag that explicitly rather than silently accepting garbage as valid content.

One thing I want to underline again because it matters for trust: every single one of these runs *after* the PII screening step, never before. The profiling agent never sees unscreened text. That ordering is a deliberate, existing boundary in our system, and this design respects it rather than working around it.

### Section 6 — The orchestration layer, in detail

We need exactly one lightweight coordinator here — and I want to be specific about what that is *not*. It's not a message bus. It's not a service mesh. It's not a new piece of infrastructure at all. It's an in-process coordinator, consistent with the way our pipeline already checkpoints its stages today.

Walking through what it actually does, step by step: it receives the incoming file or dataset, at the exact same point our existing connectors already receive it — no new entry point. It asks the Data Type Detector what kind of thing this is. It then invokes the matching profiling agent — structured, XML, or unstructured, whichever applies — *and* the Metadata Extraction Agent, at the same time, concurrently, because neither depends on the other's output and there's no reason to make one wait on the other. It aggregates both of their results into one per-artifact record and persists it — we'll get to exactly what "persists" means in Section 8. Once every artifact for a given run has landed, it calls the Data Quality Agent exactly once, against the full aggregate, and that call is the one that produces the real verdict. On a block, it halts the run using the exact same mechanism our existing pipeline stages already use to halt on failure — and I'll say it a third time because it's that important — that halt has to cover *both* of those `project_graph` call sites, or it isn't a real gate. On a warn, or a plain pass, the run proceeds, and the results simply ride along as metadata attached to that run.

One design rule I want to make sure lands clearly: if one individual agent fails — it times out, it throws an exception, it gets fed malformed input it can't handle — that does *not* fail the entire run. It only means that one agent's specific contribution gets marked as "skipped" in the aggregate. Picture this: the Unstructured Profiling Agent times out on one unusually large document. Under this design, that document's other checks still run, the rest of the batch still processes, and only if the Data Quality Agent itself comes back with an explicit block does anything actually stop. A single agent having a bad day should never be able to take down an entire run.

### Section 7 — Why these six have to stay independent

Every one of these six agents lives in its own module, behind one fixed, shared interface. I want to be clear this is a hard requirement in the design, not a style preference we could relax under time pressure. Any one of these six needs to be addable, removable, or replaceable without touching any of the others' code, and each one needs to be fully testable completely on its own, with a test fixture, with zero dependency on the orchestration layer even being present.

And I want to be precise about what "independent" means here, because the word gets used loosely elsewhere in the industry. It means independent *modules*, running inside the same process. It does not mean six separate deployed services talking over a network. There is no scale justification in our system today for spinning up six separate services just to run these checks, and doing so would add a real amount of deployment complexity, network failure surface, and operational overhead, for no benefit we actually need right now. Same reasoning, by the way, that already applies to the tabular and XML gate work this design builds on top of.

### Section 8 — Keeping a record

Every single agent run needs to be inspectable after the fact — and that has to hold true whether or not the run actually made it all the way to the graph. Picture this scenario, because it's the one that makes this section matter: three weeks from now, someone asks "why did last Tuesday's ingest run stop partway through?" Without this section, the honest answer is "we'd have to re-run it and hope we can reproduce the problem." With this section, the answer is: we look it up.

Concretely, we persist each agent's standardized report, keyed by the run and by the specific file or artifact it came from, using the same storage pattern our system already uses for run metadata — deliberately, no new storage technology gets introduced here. And for every single agent invocation, we log which agent ran and its version, its final status — pass, warn, block, skipped, or error — failure detail if something went wrong, the full profiling result or at minimum a pointer to it if it's large, how long it took to run, and an identifier for the input, so a later reprocessing run can be directly compared against this one. The whole point is that the aggregated report for any given run has to be queryable by that run's ID *before* anyone decides whether a warning or a block is worth investigating further — not after someone's already re-run the whole pipeline just to find out what happened the first time.

### Section 9 — How we'll actually test this

We're building a deliberately varied set of test files, and I want to walk through why each category earns its place rather than just listing them.

Structured data: well-formed CSV and JSON as the baseline, plus a file with a missing required column, plus one with mixed types jammed into a single column — these prove the basic block conditions actually fire.

Simple XML: a shallow, well-formed file with a handful of repeated sibling elements — proves the basic structural capture works before we stress it.

Deeply nested XML: something like an invoice with line items, each with their own tax sub-element — multiple levels deep — specifically to exercise the tag-path and nesting-depth logic under real complexity, not just a toy case.

Malformed XML: unclosed tags, bad encoding declarations, and — deliberately — an actual billion-laughs payload and an actual external-entity payload, because we need to *prove*, not just claim, that the hardened parser rejects both attack patterns.

Plain text: both short and long documents, including one that's nearly empty — that last one matters specifically because we need to prove a legitimately sparse, short document doesn't get falsely flagged as broken just because there's not much text in it.

Large documents: multi-hundred-page PDFs and Word files, to genuinely exercise chunking behavior and timeout handling under real load, not a two-page sample.

And mixed-quality, unstructured content: scanned and OCR-noisy documents, documents with embedded images, documents with partially corrupted encoding — the messy, realistic end of what actually gets uploaded in practice.

Against all of that, here's what we're actually proving, not just hoping: that every fixture's output genuinely matches our shared JSON format — real schema validation, not just "did it run without crashing." That anything which *should* block — a missing required field, XML that's malformed beyond what the fallback can handle, detected sensitive data — genuinely halts the run before *both* graph-write call sites, demonstrated in an actual integration test, not just asserted in a design doc. That anything which should only warn — a cardinality anomaly, a sparse-but-legitimate document, a dataset's very first run before any historical baseline exists — never halts anything. That one agent failing never blocks the overall graph flow for the artifacts other agents handled successfully — we simulate a forced failure and confirm the run still completes. And that running the exact same input twice produces the exact same verdict both times — because a checking system that gives different answers to the same question on different days isn't trustworthy, no matter how sophisticated its logic is.

### Section 10 — What we actually build first

We are deliberately not building all of this at once. The first version — what the document calls v1 — covers: the type detector; the XML agent, shipped together with both of its prerequisite security fixes, never staggered apart; the unstructured document agent; the Data Quality Agent, initially built by reusing our existing profiling logic and simply making it run synchronously instead of best-effort; the metadata agent; wiring the final verdict into both of those `project_graph` call sites as a new checkpointed stage in our pipeline; and — I want to underline this because it's easy to deprioritize — the logging and persistence layer ships *with* this first version, not as a fast-follow. A block that nobody can actually go investigate afterward isn't a safety feature. It's just noise that trains people to ignore it.

A few things are deliberately, explicitly deferred, and I want to name them so nobody's surprised later that they're not in v1: the richer role-inference reuse from our graph-shape profiler — that's a genuinely separate concern from pre-graph gating, and it's fine staying best-effort for now; duplicate detection across an entire run rather than within a single document; and formal schema-aware XML validation that goes beyond what we can reasonably infer just from sampling documents. All three are real, legitimate ideas. None of them are blocking this first version, and none of them should quietly creep back into scope without an explicit decision to bring them in.

---

## Closing (1–2 minutes)

So, to bring it all the way back to where we started: today, nothing stops bad data from reaching our shared source of truth. This design closes that gap with six small, focused, independently testable checks, all speaking the exact same report format, gated at the one place in the whole system that actually matters — right before the graph gets permanently written, at both of the places that can trigger that write. It reuses far more of what we've already built than it replaces. And the riskiest single piece — the XML security gap — gets fixed in the very same breath as it gets opened up for the first time, not as an afterthought.

[Pause] Happy to take questions — either on the business case, or on any of the ten sections we just walked through in detail.

---

## Appendix — Anticipated Questions (reference only, not scripted)

[This section is for your prep, not for reading aloud verbatim. Skim it before presenting so you're not caught flat-footed.]

**"Why not just fix this with better validation rules in the database?"** — Because the problem spans three very different shapes of data (structured, XML, unstructured), arriving through multiple entry points, converging on one shared write path. A database constraint can't see a malformed PDF or a billion-laughs XML payload before it's already been processed.

**"Doesn't this slow down ingestion?"** — Every agent declares a timeout, and a slow or hung agent degrades to "skipped," not a stall. The one place real latency could show up is the unstructured agent's use of a language model — which is exactly why it reuses an already-loaded model instead of paying for a second one.

**"What happens to a run that gets blocked — is data lost?"** — No. A block halts *before* the graph write. The data that caused it is sitting exactly where it landed, inspectable via the persistence layer in Section 8, with a specific reason attached. Nothing is silently discarded.

**"Why six agents instead of one big checker?"** — Section 7's answer: independent testability and the ability to change one without risking the others. A monolithic checker means every change to XML logic risks breaking PII detection, because it's all one function.

**"Is this going to require new infrastructure — servers, queues, anything like that?"** — No. Everything here runs in-process, using the same checkpointing pattern the pipeline already uses. That's a deliberate, repeated design constraint, not an oversight.

**"What's actually new here versus what already existed?"** — The XML agent and the unstructured agent are genuinely new. The structured agent and the Data Quality Agent mostly wire up and expose analytics that already exist elsewhere in the codebase but currently run non-blocking, after the fact.
