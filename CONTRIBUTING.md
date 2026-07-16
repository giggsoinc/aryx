# Contributing to Aryx Lite

Thanks for helping improve Aryx. Please read the
[Code of Conduct](CODE_OF_CONDUCT.md) first.

## Ways to contribute

- Bug reports and feature ideas (use [issue templates](.github/ISSUE_TEMPLATE/))
- Docs and examples (`docs/`, `examples/`)
- Fixes and features via pull request

## Development

```bash
# API unit tests (no full stack required for this subset)
PYTHONPATH=src pytest -q tests/test_ports_seam.py tests/test_grounding.py \
  tests/test_ab.py tests/test_explore.py tests/test_blocking.py

# Full stack: see docs/INSTALL.md
docker compose up -d
```

- Do not commit secrets (`.env`, API keys, `manifest.secrets.json`).
- Prefer small, reviewable PRs with a clear problem statement.
- Add or update tests when behavior changes.
- Product UI is **Next.js only** (`apps/web`). Graph store is **FalkorDB**.

## License of contributions

This project is **BSL 1.1** ([`LICENSE`](LICENSE), [`docs/LICENSING.md`](docs/LICENSING.md)).

By submitting a contribution you agree that:

1. You have the right to submit it.
2. You license it under the same **BSL 1.1** terms as the Licensed Work.
3. Maintainers may include it in other Aryx distributions under compatible terms
   while the public Lite tree remains under BSL until the Change Date.

If you cannot accept these terms, open an issue with the idea instead of a PR.

## Security

Report vulnerabilities privately — see [SECURITY.md](SECURITY.md). Do not file
public issues for active exploits.
