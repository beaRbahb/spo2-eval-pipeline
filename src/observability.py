"""Phoenix tracing setup — Rung 1 of the Arize learning track.

This module is the single entry point for LLM observability. It auto-traces
every Anthropic call the pipeline makes (handoff generation + the 3 LLM-judge
evaluators) by instrumenting the `anthropic` client at the library level —
no changes to call sites in `llm_utils.py`.

DESIGN GOALS (why it looks the way it does):
  - Off by default. Tracing only activates when PHOENIX_TRACING=1. So the
    default `python -m src.pipeline.orchestrator`, pytest, and $0 mock runs
    are completely unaffected.
  - Fail soft. Missing packages or a launch error print a warning and return
    — they never crash the pipeline.
  - Idempotent. Safe to call setup_tracing() more than once per process.

HOW TO USE:
    PHOENIX_TRACING=1 python -m src.pipeline.orchestrator
    # open http://localhost:6006 — traces appear when use_llm=True makes calls.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

# Module-level guard so repeated calls (e.g. tests importing run_pipeline)
# don't launch the app or register the tracer twice.
_TRACING_INITIALIZED = False


def setup_tracing(project_name: str = "spo2-eval") -> None:
    """Launch a local Phoenix UI and auto-instrument the Anthropic client.

    No-op unless the PHOENIX_TRACING environment variable is truthy.
    """
    global _TRACING_INITIALIZED

    if not os.environ.get("PHOENIX_TRACING"):
        return  # disabled — the default path
    if _TRACING_INITIALIZED:
        return  # already set up this process

    try:
        from phoenix.otel import register

        # register(auto_instrument=True) discovers every installed OpenInference
        # instrumentor — including openinference-instrumentation-anthropic — and
        # patches the anthropic client so each messages.create() becomes a span
        # carrying prompt, completion, token counts, latency, and model.
        endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
        if endpoint:
            # A persistent `phoenix serve` is already running — send spans there
            # so the UI (and data) outlive this process. Best for exploring.
            register(project_name=project_name, auto_instrument=True)
            where = endpoint
        else:
            # No server running — launch an in-process one for convenience.
            # NOTE: this UI dies when the process exits (traces are in-memory).
            import phoenix as px

            session = px.launch_app()
            register(project_name=project_name, auto_instrument=True)
            where = session.url

        _TRACING_INITIALIZED = True
        print(f"[PHOENIX] Tracing on — {where} (project: {project_name})")
    except ImportError as e:
        print(
            f"[PHOENIX] PHOENIX_TRACING set but packages missing ({e}). "
            "Install with: pip install arize-phoenix openinference-instrumentation-anthropic"
        )
    except Exception as e:  # noqa: BLE001 — observability must never break the run
        print(f"[PHOENIX] Tracing setup failed, continuing without it: {e}")


@contextmanager
def trace_span(name: str, kind: str = "CHAIN", **attributes):
    """Create a manual span around a block of work, with custom attributes.

    This is how we add MEANING to the raw auto-instrumented `messages.create`
    spans. Any LLM call made inside this block nests UNDER this span in the
    Phoenix trace tree, and the attributes we set here become filterable in the
    UI (e.g. `metadata["evaluator"] == "clinical_accuracy"`).

    `kind="CHAIN"` tags this as a grouping/orchestration span (vs the child
    LLM spans) so Phoenix renders a proper tree.

    No-op (yields None, zero overhead) unless tracing is initialized — so the
    default mock path and pytest are unaffected.
    """
    if not (os.environ.get("PHOENIX_TRACING") and _TRACING_INITIALIZED):
        yield None
        return

    from opentelemetry import trace as _otel

    tracer = _otel.get_tracer("spo2.pipeline")
    with tracer.start_as_current_span(name) as span:
        # OpenInference span-kind + a metadata blob keep Phoenix's UI happy:
        # span-kind drives the tree icon; metadata.* is the filterable bucket.
        import json

        span.set_attribute("openinference.span.kind", kind)
        clean = {k: v for k, v in attributes.items() if v is not None}
        for k, v in clean.items():
            span.set_attribute(k, v)
        if clean:
            span.set_attribute("metadata", json.dumps(clean))
        yield span
