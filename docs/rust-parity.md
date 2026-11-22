# Rust Parity

Kogwistar Agent Suite now has an explicit dual-language implementation path.
Python remains the safe default and full compatibility surface. The Rust path
is opt-in, fail-closed, and delegates core runtime work to the
`kogwistar-runtime` crate from Kogwistar core v0.7.1.

## Goals and boundaries

- Keep the existing Python API stable.
- Let callers choose Python, Rust, or shadow comparison explicitly.
- Never silently fall back between implementations.
- Keep workflow authority, ACL authority, budgets, provenance, and persistence
  owned by Kogwistar core.

## Implementation selection

The default is always Python:

```text
KOGWISTAR_AGENT_IMPL_MODE=python
```

Select the native Rust path only when the packaged extension is available:

```text
KOGWISTAR_AGENT_IMPL_MODE=rust
```

`shadow` is reserved for comparing a Python result with the Rust result. It is
not a silent fallback mode and still requires the Rust extension when selected.

Per-seam environment overrides are:

| Seam | Variable |
| --- | --- |
| capability catalog | `KOGWISTAR_AGENT_IMPL_CATALOG` |
| tools | `KOGWISTAR_AGENT_IMPL_TOOLS` |
| runtime | `KOGWISTAR_AGENT_IMPL_RUNTIME` |
| adapters | `KOGWISTAR_AGENT_IMPL_ADAPTERS` |
| hooks | `KOGWISTAR_AGENT_IMPL_HOOKS` |

Accepted values are `python`, `rust`, and `shadow`. Invalid values fail before
a profile is built. The Python builder also accepts explicit values:

```python
from kogwistar_agent_suite import developer_profile

pack = developer_profile(
    ".",
    implementation="rust",
)
```

Missing `kogwistar_agent_suite._rust` raises
`SuiteImplementationUnavailable`; it does not fall back to Python.

## Current native surface

The first native bridge exposes:

| Operation | Rust-side behavior |
| --- | --- |
| capability search | descriptor filtering and BM25/semantic fallback |
| workspace listing/reading/searching | bounded path-safe file operations |
| Git status | read-only bounded command |
| core runtime run | native step execution through core `RuntimeNativeStepRequest` |
| core runtime resume | recorded transition reduction through core runtime |

The Rust runtime port uses Kogwistar core's `execute_native_step` and
`reduce_recorded_transition`. It does not duplicate workflow semantics or own
persistence. It validates and executes the core-owned durable contracts.

## Build and verification

The package uses Maturin. A native ABI3 wheel targets Python 3.12+:

```text
python -m maturin build --locked --out dist
```

Run the Rust and Python gates from the repository root:

```text
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
python -m ruff check src tests
python -m pytest -q --basetemp .pytest-tmp-suite
```

## Current boundary

The current Rust surface is a native parity foundation, not a claim that every
Python composition surface has been ported. Optional adapters, Slack contact
and notification sources, MCP invocation, and host-owned runtime composition
remain Python-owned until explicitly ported. The selection API and runtime port
are designed so those seams can move without changing the public Python
profile contract.
