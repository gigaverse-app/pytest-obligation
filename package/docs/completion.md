# Terminal completion and duplicate delivery

`ObligationContract.completions` accepts named factories returning
`BoundedCompletion`. Supply an independent `expected` product outcome, real
recovery, a controlled scheduler clock, and a maximum elapsed time. An optional
minimum wait catches skipped business delays; `remaining` catches reversed or
negative progress. The generated `completion-…-assert_completes_within` case
checks terminal completion, rather than accepting the first successful stage.
This is a simulated scheduler bound, not a wall-clock production SLA.

`delivery_replays` accepts named `DeliveryReplay` factories. Re-deliver the same
production message, count actual entries at that delivery boundary, and count
actual business callback entries independently. Two deliveries must enter while
only one callback commits the required product outcome. This is distinct from
profile H's raw external-effect replay: a fenced-out second delivery does not
prove a payment provider or database callback is independently idempotent.

Both families require explicit expected outcomes and generate ordinary contract
cases, so collection reports and `--obligation-verify` include them. Keep fixture,
production, external-seam and observation annotations beside each binding.
Neither helper manufactures work state or implements retries for the adopter.
