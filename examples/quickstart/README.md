# Quickstart example data

Small CSVs you can upload in **Onboard → Files** to see multi-file typing,
relationship inference, and the Data → Graph explorer.

## Files

| File | Role |
|------|------|
| `customers.csv` | Customer entities |
| `tickets.csv` | Support tickets with `customer_id` FK |

## Steps

1. Start Aryx ([INSTALL.md](../../docs/INSTALL.md)): `docker compose up -d`
2. Open http://localhost:3000 → **New workspace**
3. **Onboard** → skip or set simple goals → choose **Files**
4. Upload **both** CSVs in one batch
5. Wait for the pipeline; then open **Data → Graph**
6. Search for a customer name; click a node for neighbors and detail
7. **Ask**: e.g. *“Which customers have open tickets?”*

## Expected shape

- Types similar to **Customer** and **Ticket** (exact names may vary by inference)
- Edges linking tickets to customers via shared ids
- Provenance on entities in Tree/Table lenses

These files are illustrative only — replace with your own data for real work.
