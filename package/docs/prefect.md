# Prefect flow bodies and recurrence

Install `pytest-obligation[prefect]` for Prefect 3.7.

`prefect_flow_call(flow, runner)` turns a real `prefect.Flow` into a synchronous
history binding. It executes `flow.fn`, awaits the entire coroutine on the
caller-owned `asyncio.Runner`, and retains the production function's identity for
binding checks. Reuse the same runner for loop-bound clients such as Motor.
Each invocation copies the current context into the coroutine, even if the runner
was initialized earlier. The current host, fault scopes and tenant context
therefore reach the flow body.

This proves application recovery through the flow body. It does not run Prefect's
engine, task retries, hooks, result persistence or remote worker delivery. Test
those separately with the actual engine. A synchronous flow body is also supported;
returned generators and non-coroutine awaitables are rejected as unfinished work.

`assert_prefect_recurs(deployment, flow, start=..., within=..., runner=...)` checks a
real `RunnerDeployment`: the flow and entrypoint must match, it must be unpaused,
and active schedules must provide repeated dates within the requested interval.
Date calculation uses Prefect's own server schedule models, including timezone
semantics. This is evidence about the supplied declaration, not the state of a
remote deployment or whether a worker is alive. Bind the actual declaration your
application registers; reconstructing its cron in the test would miss drift.

The tests pair working bindings and schedules with paused, inactive, missing,
slow, wrong-flow and wrong-entrypoint controls.

The binding rejects deferred results from both synchronous and asynchronous flow
bodies. Awaiting the outer coroutine is insufficient when it returns a generator
or another awaitable. Schedule evidence checks the first **three future** runs,
excluding a tick exactly at `start`; it is a bounded declaration check, not proof
that an RRule continues forever or that a deployed worker executes those runs.

A rejected asyncio task/future belonging to the supplied runner is cancelled and
drained before the binding raises, so it cannot resume when the next history
uses that loop. Unrelated caller tasks and futures on other event loops remain
caller-owned. This is not a whole-loop or whole-process termination guarantee.

## Required adoption surface

Bind this flow callable and schedule evidence through an `ObligationContract` with
a collected `@due_work_contract_suite(CONTRACT)` class. Put histories in
`handoffs=` and claim only profiles for which production bindings exist.
Calling the adapter in ordinary tests alone is incomplete domain adoption; see
[required adoption shape](adopting.md#required-adoption-shape) for generated
cases and report artifacts.


## Native cancellation and database hosts

Compose `prefect_host` with the host that owns your database bindings:

```python
from pytest_obligation.host import hosted
from pytest_obligation.integrations.mongodb import mongodb_host
from pytest_obligation.integrations.prefect import prefect_host

with hosted(prefect_host(mongodb_host(client, {"your_app"}))):
    # Run the generated flow-body histories with this composed host.
    run_histories()
```

`prefect_host` returns a copy with Prefect 3.7's native `CancelledError` as its
cooperative stop signal. It preserves database inspectors, write/reply faults
and other capabilities. This cancellation derives from `BaseException`; injecting
an ordinary `Exception` would incorrectly blame a flow that catches individual
provider failures but correctly allows cancellation to escape.

The stop oracle checks that cancellation escapes, leaves the interrupted identity
owed and prevents later work. It detects swallowed or grouped cancellation, while
unrelated process interrupts still escape the harness. Tests exercise Prefect's
actual cancellation scope as well as the injected signal. This verifies flow-body
handling; it does not claim that a remote worker received a cancellation request.
