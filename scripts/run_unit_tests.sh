#!/usr/bin/env bash
#
# Run every tests/test_*.py module in its OWN pytest process.
#
# Why not a single `pytest tests/`: several modules install MagicMock stubs
# into sys.modules for the DB drivers (see tests/test_actions.py) so they can
# import application code on a machine with no Postgres. Those stubs persist
# for the rest of the process, so any module collected afterwards that needs
# the real driver — `from psycopg.errors import UniqueViolation` — fails with
# "'psycopg' is not a package". Collection order decides who breaks.
#
# CI used to dodge this with a hand-maintained list of seven files. That kept
# the signal green but silently excluded most of the suite: a new test file
# ran locally, passed, and was never executed by CI again. A guard nobody
# runs is not a guard.
#
# One process per module removes the ordering problem entirely and needs no
# list to maintain, so a new test file is covered the moment it is added.
set -uo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-src}"

# Per-module wall clock. A test CAN hang rather than fail — an auth guard
# that stops rejecting lets a TestClient open a real SSE stream and block
# forever — and without a bound that burns the whole CI job before anyone
# learns which module is stuck. `timeout` is GNU coreutils: present on the
# CI runner, absent on a stock macOS, so fall back to unbounded locally
# rather than refusing to run at all.
MODULE_TIMEOUT="${ARYX_TEST_MODULE_TIMEOUT:-120}"
TIMEOUT_CMD=""
if command -v timeout >/dev/null 2>&1; then
    TIMEOUT_CMD="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_CMD="gtimeout"
else
    echo "note: no timeout(1) available — running unbounded (brew install coreutils)"
fi

run_module() {
    if [ -n "${TIMEOUT_CMD}" ]; then
        "${TIMEOUT_CMD}" "${MODULE_TIMEOUT}" python -m pytest "$1" -q --no-header 2>&1
    else
        python -m pytest "$1" -q --no-header 2>&1
    fi
}

failed=()
timed_out=()
passed=0

for module in tests/test_*.py; do
    # Exit code, not output grepping: pytest returns non-zero on any failure
    # and timeout(1) returns 124 when it kills a hung module. Grepping stdout
    # would score a killed module as a pass, which is the one outcome that
    # must never look green.
    output=$(run_module "${module}")
    status=$?
    if [ ${status} -eq 0 ]; then
        passed=$((passed + 1))
        continue
    fi
    echo "::group::FAILED ${module} (exit ${status})"
    echo "${output}" | tail -30
    echo "::endgroup::"
    if [ ${status} -eq 124 ]; then
        timed_out+=("${module}")
    else
        failed+=("${module}")
    fi
done

echo
echo "unit test modules: ${passed} passed, ${#failed[@]} failed, ${#timed_out[@]} timed out"
[ ${#failed[@]} -gt 0 ] && printf '  failed:    %s\n' "${failed[@]}"
[ ${#timed_out[@]} -gt 0 ] && printf '  timed out: %s (>%ss)\n' "${timed_out[@]}" "${MODULE_TIMEOUT}"

if [ ${#failed[@]} -gt 0 ] || [ ${#timed_out[@]} -gt 0 ]; then
    exit 1
fi
exit 0
