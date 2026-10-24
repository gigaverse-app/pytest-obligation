# Inline recovery selection binding test plan

Profile A's unwaivable selection-equivalence proof previously required a page
size before it ran the production tick. An inline service without a declared
per-tick bound therefore could not bind its actual selection and report the
missing bound separately. Supplying a made-up limit would hide this evidence gap.

The comparison now seeds a finite test fixture and compares every selected
identity when `page_size=None`. A declared page size still bounds the expected
prefix exactly as before. No execution mode, scheduler or application behavior
changes. `assert_tick_is_bounded` still refuses a missing limit.

Controls first failed on the premature page-size refusal. After the change, an
unbounded reference tick passes equivalence; removing its first identity, its
last identity, or truncating it to a page fails with the actual selection
mismatch. A recorder copied from the query still fails before the tick starts.
The pre-existing missing-bound negative control remains unchanged.

Run the automatic-recovery tests and the contract/declaration controls, plus
formatting and type checks. This is a prerequisite for binding AI's actual
inline billing sweep, not evidence that AI's recovery profile is already complete.
