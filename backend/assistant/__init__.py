"""Ask Vermio — the agentic assistant for landlords.

Package layout (see docs/TRD-assistant.md §13):

    agent.py       run_agent — the tool-calling loop (§2)
    tools.py       TOOL_SCHEMAS + dispatch + read-only data tools (§3, §4)
    guardrails.py  sanitize_tool_output, cost caps, scope guard (§8)
    threads.py     conversation persistence (§7)

The public surface other modules should use is `run_agent`; everything else is
an implementation detail of the loop.
"""

from .agent import run_agent

__all__ = ["run_agent"]
