# Enroll a passive validate-then-commit boundary

Keep Python as the executed source. A function that stages references locally,
validates every input, then applies monotone writes can use the same conservative
heap backend. The names are application choices, not compiler fixtures:

```python
# heap-schema: {"types":{"Entry":{"fields":{"seen":"bool","events":"list[str]"}}}}
# @ verified
def combine(retained: dict[str, Entry], shard: dict[str, Entry]) -> None:
    pending: dict[str, Entry] = {}
    pairs: list[tuple[Entry, Entry]] = []
    for key, value in shard.items():
        if key not in retained:
            pending[key] = value
            continue
        prior = retained[key]
        assert prior.seen == value.seen
        pairs.append((prior, value))
    retained.update(pending)
    for prior, value in pairs:
        prior.seen |= value.seen
        prior.events.extend(value.events)
```

`Entry` must be the application's actual passive model, with the exact declared
fields. Declare any external pure method explicitly and document its reads,
returned aliases and exceptional behavior. Use `opaque` for passively compared
metadata rather than inventing a false concrete primitive type. The schema is a
trusted API contract, not automatic discovery of external purity.

Enroll `combine` in a version-1 project manifest with a fixed nonempty target ID,
`backend: "dafny-heap"`, its source file, actual model/helper dependencies and an
optional `.proofs.dfy` sidecar. Set `sources` to the intended annotated source
inventory and pin Dafny 4.11.0. Run `veripy project generate MANIFEST --json`,
review generated artifacts and enrollment, then `veripy project check MANIFEST
--json` in CI. Unsupported syntax is a failed required target; implement support
or refactor a useful production boundary and prove that actual boundary.

Add independent real API histories for compatible accumulation, late rejection,
input preservation and reference identity. Require actual early-write and
identity-replacement source mutations to fail Dafny semantically. Also remove a
compatibility guard and omit commit: those may preserve the conditional source
frame theorem, so the runtime histories must detect them. Keep fixed runtime
collection/outcome enrollment and declared CI inputs. The report integration and
the verifier's generic heap tests provide executable examples of these checks.
