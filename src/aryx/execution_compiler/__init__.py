"""Execution Compiler (C11).

Compiles an approved DashboardSpec (C08/C09's output) into a typed, acyclic
execution plan built exclusively from vetted operation templates — parsing
only approved specification nodes, mapping each operation to a template,
binding columns/constants as parameters, wiring dependencies, applying
resource/row limits, and generating deterministic operation IDs. No LLM, no
arbitrary code generation (see compile.py's module docstring for the "Key
control"). Chained onto C10 inside andie_planner.run, right after an approved
spec's AnalysisDataset is produced.
"""

from aryx.execution_compiler.compile import compile_plan, compile_plan_for_spec
from aryx.execution_compiler.models import CompilationIssue, ExecutionNode, ExecutionPlan

__all__ = [
    "compile_plan", "compile_plan_for_spec",
    "ExecutionPlan", "ExecutionNode", "CompilationIssue",
]
