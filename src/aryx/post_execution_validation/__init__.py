"""Post-Execution Validation (C13).

Confirms an ExecutionRun (C12) produced exactly what the approved spec
(C08/C09) and compiled plan (C11) requested: result identity, independently
recomputed arithmetic, sample-size reconciliation, evidence lineage, no
invented references, and result shape/type validation. Small-sample and
excluded-null conditions are warnings, never rejections — a structurally
valid but numerically incorrect result IS still blocked. No LLM. Chained
onto C12, right after an ExecutionRun is produced.
"""

from aryx.post_execution_validation.models import (
    PostExecutionReport, CheckResult, ValidationError, ValidationWarning, SMALL_SAMPLE_THRESHOLD,
)
from aryx.post_execution_validation.run import run_post_execution_validation
from aryx.post_execution_validation.validate import validate_execution

__all__ = [
    "run_post_execution_validation", "validate_execution",
    "PostExecutionReport", "CheckResult", "ValidationError", "ValidationWarning",
    "SMALL_SAMPLE_THRESHOLD",
]
