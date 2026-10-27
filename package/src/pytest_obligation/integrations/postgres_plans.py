"""
What a PostgreSQL ``EXPLAIN (FORMAT JSON)`` plan says about a scheduled selection.

Pure functions over the plan tree PostgreSQL returns: no database driver, no ORM,
no connection. Any PostgreSQL integration captures a plan its own way and hands
the ``"Plan"`` object here for the verdict, which keeps the reasoning about plan
shapes in one place and lets the harness's self-tests pin it against canned plans
without a database.

Two readings are offered:

* :func:`index_served_verdict` / :func:`assert_plan_is_index_served` — whether an
  index actually narrows every scan of the selection's own table (profile A,
  invariant 5);
* :func:`scan_counts` — rows returned against rows read and discarded by
  filters, from an ``EXPLAIN ANALYZE`` plan (the scan-ratio proof);
* :func:`read_cost` — buffers touched and rows visited, from an
  ``EXPLAIN (ANALYZE, BUFFERS)`` plan (the retained-history proof).
"""

import json
import re
from collections.abc import Collection, Iterator, Mapping
from typing import Any, TypeAlias

from pytest_obligation.host import ReadCost
from pytest_obligation.integrations._internal.postgres_sql import bare_identifiers, blank_literals_and_comments

#: Plan keys proving an index narrowed the rows a scan node returned.
CATALOG_INDEX = "Catalog Index"
"""Catalog access method, ordered keys and predicate attached to each named index."""

PRUNING_KEYS = ("Index Cond", "Recheck Cond")


def iter_plan_nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Traverse a PostgreSQL plan once; every plan reading shares this JSON boundary."""
    yield plan
    for child in plan.get("Plans", ()):
        yield from iter_plan_nodes(child)


def _rendered(plan: dict[str, Any]) -> str:
    return f"Plan:\n{json.dumps(plan, indent=2)}"


#: A partial index's name, with the columns its predicate constrains (read from the catalog).
PredicateIndexes: TypeAlias = Mapping[str, Collection[str]] | Collection[str]


def index_served_verdict(plan: dict[str, Any], *, table: str, predicate_indexes: PredicateIndexes = ()) -> str | None:
    """
    ``None`` when an index narrows every scan of ``table``, else why not, with the plan.

    The reasoning behind each rule is on :func:`assert_plan_is_index_served`.
    ``predicate_indexes`` names partial indexes a catalog-backed caller verified,
    each with the columns its predicate constrains; a bitmap built from one of
    them needs no ``Index Cond``. A Filter above it may test other columns (the
    time bound a predicate cannot hold, removing backlog), but not those: a
    Filter that re-tests a column the predicate constrains means the predicate
    does not imply the selection's condition there, and the index keeps rows the
    selection throws away (``status IS NOT NULL`` keeps the whole settled
    history). What the plan cannot show, how much history a legitimate index
    holds, :func:`~pytest_obligation.profiles.automatic_recovery.assert_selection_cost_does_not_grow_with_the_history`
    measures. Names alone, or an arbitrary ``Recheck Cond``, never establish the guarantee.
    """
    constrained = _constrained_columns(predicate_indexes)
    alone = {node.get("Relation Name") for node in iter_plan_nodes(plan) if "Relation Name" in node} == {table}
    scans = [node for node in iter_plan_nodes(plan) if node.get("Relation Name") == table]
    if not scans:
        return (
            f"no plan node scans {table!r}, so this proof cannot be evaluated. "
            f"Does the selection read the expected table?\n{_rendered(plan)}"
        )
    for node in scans:
        node_type = node.get("Node Type", "")
        own = _own_names(node)
        if re_tested := _re_tested_predicate(node, constrained):
            index, columns = re_tested
            return (
                f"the partial index {index!r} named as serving the selection constrains {sorted(columns)} in its "
                f"predicate, and the scan of {table!r} filters on them again: the predicate does not imply the "
                f"selection's own condition on those columns, so the index keeps rows the selection throws away "
                f"(a predicate as wide as the settled history keeps all of it). Give the partial index the "
                f"selection's condition on {sorted(columns)}.\n{_rendered(plan)}"
            )
        if "Seq Scan" in node_type:
            return (
                f"the due-work selection falls back to a sequential scan of {table!r} even with "
                f"sequential scans disabled, so no usable index exists. This query runs on a "
                f"schedule forever.\n{_rendered(plan)}"
            )
        if node_type == "Bitmap Heap Scan":
            # A bitmap heap node always carries a Recheck Cond, whatever built
            # the bitmap, so reading it as evidence of pruning accepts a bitmap
            # assembled by scanning an entire index. The selectivity lives one
            # level down, on the Bitmap Index Scan.
            bitmap_scans = list(_bitmap_index_inputs(node))
            # Every input is read to build AND/OR bitmaps: one selective branch
            # cannot vouch for another that walks its entire unrelated index.
            if not bitmap_scans or not all(
                "Index Cond" in scan
                or scan.get("Index Name") in constrained
                or (alone and "Filter" not in node and scan.get(CATALOG_INDEX, {}).get("Predicate") is not None)
                for scan in bitmap_scans
            ):
                return (
                    f"the selection builds a bitmap over {table!r} from an index scan with no index "
                    f"condition, so the whole index is read and the heap rows are then filtered. The "
                    f"Recheck Cond on the heap node is not evidence of pruning — it is present for "
                    f"every bitmap. Add an index whose leading columns match the selection's "
                    f"predicate.\n{_rendered(plan)}"
                )
            for scan in bitmap_scans:
                if "Index Cond" in scan and (failure := _index_condition_failure(scan, table, plan)):
                    return failure
                if "Filter" in node and (failure := _join_key_failure(scan, own, constrained, table, plan)):
                    return failure
            continue
        if "Index Cond" in node:
            if failure := _index_condition_failure(node, table, plan):
                return failure
            # A condition the selection itself states narrows the read; a Filter above it drops only the
            # residual. A condition made only of join keys narrows nothing the selection's Filter asks for.
            if "Filter" in node and (failure := _join_key_failure(node, own, constrained, table, plan)):
                return failure
            continue
        # A named partial index narrows by its own predicate, as it does for a bitmap: the re-tested
        # predicate is refused above, so a Filter left here drops only backlog the predicate cannot hold.
        if node.get("Index Name") in constrained:
            continue
        if "Filter" in node:
            return (
                f"the selection reaches an index on {table!r} ({node_type}) but no index condition "
                f"narrows it — every row is walked and filtered. That is a full scan by another name, "
                f"on a schedule. Add an index whose leading columns match the selection's "
                f"predicate.\n{_rendered(plan)}"
            )
        if failure := _unconditioned_scan_failure(node, alone, table, plan):
            return failure
    return None


def _own_names(scan: dict[str, Any]) -> frozenset[str]:
    """The names a scan's own columns may be qualified with: its alias and its relation."""
    return frozenset(str(scan[key]) for key in ("Alias", "Relation Name") if key in scan)


#: A column qualified by a relation name or alias, as PostgreSQL prints another relation's column in a
#: Match the complete identifier: backtracking must not turn schema.clock() into schema.cloc.
#: parameterized scan (``(parent_id = p.id)``); a qualified name followed by ``(`` is a function, not a column.
_QUALIFIED = re.compile(r'(?<![\w$."])("[^"]+"|[A-Za-z_][\w$]*)\.(?:"[^"]+"|[A-Za-z_][\w$]*)(?![\w$"]|\s*\()')


def _conjuncts(expression: str) -> list[str]:
    """The top-level ``AND`` clauses of a condition PostgreSQL printed, literals and comments blanked."""
    text = _CAST.sub("", blank_literals_and_comments(expression)).strip()
    while text.startswith("(") and _closing_paren(text) == len(text) - 1:
        text = text[1:-1].strip()
    clauses, depth, start = [], 0, 0
    for index, char in enumerate(text):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth == 0 and text.startswith(" AND ", index):
            clauses.append(text[start:index])
            start = index + len(" AND ")
    clauses.append(text[start:])
    return [clause.strip() for clause in clauses if clause.strip()]


def _closing_paren(text: str) -> int:
    """The index of the parenthesis closing the one ``text`` opens with."""
    depth = 0
    for index, char in enumerate(text):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth == 0:
            return index
    return -1


def _borrowed_from_a_join(access: dict[str, Any], own: frozenset[str]) -> bool:
    """
    Whether every clause of ``access``'s Index Cond compares a key with another relation's column.

    That condition positions the scan once per row of the relation driving the
    join, so the rows it reads are those of every driving row: it narrows by the
    join, not by anything the selection asks of this table. One clause the
    selection states itself (a literal, a parameter, ``now()``) is a narrowing
    condition, wherever the join keys sit in the index.
    """
    clauses = _conjuncts(str(access.get("Index Cond", "")))
    return bool(clauses) and all(
        any(qualifier.strip('"') not in own for qualifier in _QUALIFIED.findall(clause)) for clause in clauses
    )


#: One side of an equality PostgreSQL printed: a column, optionally qualified by its relation or alias.
_COLUMN = re.compile(r'(?:("[^"]+"|[A-Za-z_][\w$]*)\.)?("[^"]+"|[A-Za-z_][\w$]*)')


def _pins_one_row(access: dict[str, Any], own: frozenset[str]) -> bool:
    """
    Whether ``access``'s Index Cond fixes every key column of a full unique index by equality.

    Such a probe reads at most one row per row driving the join (an identity
    lookup, such as an anti-join on a one-to-one dependency), so the join key
    narrows the read completely. Only plain btree key columns count, each
    compared with ``=`` to another column; a range, an ``= ANY`` list, an
    expression key or a key column left open reads more. A partial unique
    index is unique only within its predicate and follows the partial-index
    rules instead: it must be named in ``partial_indexes``.
    """
    catalog = access.get(CATALOG_INDEX)
    if not catalog or not catalog.get("Unique") or catalog.get("Predicate") is not None:
        return False
    if catalog.get("Access Method") != "btree":
        return False
    keys = [str(key).strip('"') for key in catalog.get("Key Columns", ())]
    if not keys or any(not _COLUMN.fullmatch(key) or "." in key for key in keys):
        return False
    pinned: set[str] = set()
    for clause in _conjuncts(str(access.get("Index Cond", ""))):
        while clause.startswith("(") and _closing_paren(clause) == len(clause) - 1:
            clause = clause[1:-1].strip()
        sides = clause.split(" = ")
        if len(sides) != 2:
            continue
        for column, other in (sides, sides[::-1]):
            mine, theirs = _COLUMN.fullmatch(column.strip()), _COLUMN.fullmatch(other.strip())
            if mine is None or theirs is None:
                continue
            qualifier = (mine.group(1) or "").strip('"')
            if not qualifier or qualifier in own:
                pinned.add(mine.group(2).strip('"'))
    return set(keys) <= pinned


def _join_key_failure(
    access: dict[str, Any], own: frozenset[str], constrained: Mapping[str, Collection[str]], table: str, plan: dict
) -> str | None:
    """Refuse a scan whose only index condition is a join key while its Filter carries the selection's condition."""
    if access.get("Index Name") in constrained or not _borrowed_from_a_join(access, own):
        return None
    if _pins_one_row(access, own):
        return None
    return (
        f"the selection reaches {table!r} through index {access.get('Index Name')!r} with only a join key as its "
        f"index condition ({access['Index Cond']}), and filters the rows it reads. The join key narrows nothing the "
        f"selection asks of {table!r}: each row driving the join reads every one of its rows here, and over realistic "
        f"data that is the whole table. Index the selection's own condition on {table!r} (as the leading key, or "
        f"after the join key in the same index), or name a partial index whose predicate it "
        f"implies.\n{_rendered(plan)}"
    )


def _unconditioned_scan_failure(node: dict[str, Any], alone: bool, table: str, plan: dict[str, Any]) -> str | None:
    """
    Refuse a scan with no index condition and no Filter unless a partial index alone narrows it.

    Such a scan reads every entry of its index. That is how a *partial* index
    serves a predicate it implies — the narrowing lives in the index's own WHERE
    clause, which EXPLAIN does not surface — so it is accepted when no other
    relation in the plan can discard what it yields. A full index read that way
    is the whole table, whatever the selection's condition elsewhere.
    """
    index = node.get("Index Name")
    catalog = node.get(CATALOG_INDEX)
    if catalog is None:
        return (
            f"the selection reads index {index!r} on {table!r} with no index condition, and the plan carries no "
            f"catalog definition to say whether its own predicate narrows it; capture it with "
            f"explain_index_eligibility.\n{_rendered(plan)}"
        )
    if catalog["Predicate"] is None:
        return (
            f"the selection reads index {index!r} on {table!r} with no index condition, and it is not a partial "
            f"index: every entry is read, so nothing the selection asks narrows the read of {table!r}. A join that "
            f"discards rows afterwards does not shorten it, and a table that holds only owed rows today does not "
            f"stay that way. Index the selection's own condition on {table!r}.\n{_rendered(plan)}"
        )
    if not alone:
        return (
            f"the selection reads the partial index {index!r} on {table!r} whole, and joins another relation that "
            f"can discard what it yields: the selection's narrowing is in the join, not in the index. Index that "
            f"condition, or name the index in partial_indexes when its predicate bounds the read on its own and "
            f"what the join discards is backlog.\n{_rendered(plan)}"
        )
    return None


def _constrained_columns(predicate_indexes: PredicateIndexes) -> dict[str, frozenset[str]]:
    if isinstance(predicate_indexes, Mapping):
        return {name: frozenset(columns) for name, columns in predicate_indexes.items()}
    return {name: frozenset() for name in predicate_indexes}


def _re_tested_predicate(node: dict[str, Any], constrained: dict[str, frozenset[str]]) -> tuple[str, set[str]] | None:
    """The named partial index behind this scan whose predicate's columns its Filter tests again, if any."""
    if "Filter" not in node:
        return None
    indexes = [node.get("Index Name")] + [scan.get("Index Name") for scan in _bitmap_index_inputs(node)]
    for index in indexes:
        if index in constrained and (columns := referenced_columns(node["Filter"], constrained[index])):
            return index, columns
    return None


_IDENTIFIER = re.compile(r'"([^"]+)"|\b([A-Za-z_][A-Za-z0-9_$]*)\b')


def referenced_columns(expression: str, candidates: Collection[str]) -> set[str]:
    """Which of ``candidates`` an expression PostgreSQL printed names, outside its string literals."""
    text = blank_literals_and_comments(expression)
    names = {quoted or bare for quoted, bare in _IDENTIFIER.findall(text)}
    return names & set(candidates)


#: A cast as PostgreSQL prints one, including its multi-word type names; removed before reading comparisons.
_CAST = re.compile(r'::(?:"[^"]+"|[\w.]+)(?: (?:with|without) time zone| varying| precision)?(?:\[\])?')
_OPERAND = r'"[^"]+"|[A-Za-z_][\w$]*'
#: One range comparison, with the operand on either side. The lookarounds keep ``<>`` (not a range),
#: ``<=``/``>=`` (matched whole) and the JSON arrow ``->`` from reading as ``<`` or ``>``. The optional
#: ``(`` after the right operand marks a function call (``now()``), which is not a column.
_RANGE = re.compile(
    rf"(?P<left>{_OPERAND})?\)*\s*(?:<=|>=|<(?![>=])|(?<![<-])>(?!=))\s*\(*(?P<right>{_OPERAND})?(?P<call>\s*\()?"
)
#: Words PostgreSQL prints beside an operator that are not columns.
_NOT_COLUMNS = frozenset({"ALL", "AND", "ANY", "ARRAY", "FALSE", "IS", "NOT", "NULL", "OR", "SOME", "TRUE"})


def bitmap_overturns_the_walk(
    walked: dict[str, Any], bitmap: dict[str, Any], *, table: str, predicate_indexes: PredicateIndexes = ()
) -> bool:
    """
    Whether a bitmap-only plan shows an index narrows the selection after the walked plan said none does.

    On a tiny table every index walk costs about the same, so with sequential
    scans off the planner may walk an unrelated index (a unique key) and filter
    an equality or due-time filter, whichever statistics autovacuum left. Asked
    again with plain index scans off too, it must build a bitmap. The bitmap
    must pass :func:`index_served_verdict` with the same named partial indexes.
    When range bounds exist, every input must additionally narrow those columns,
    either by naming it in its ``Index Cond`` (outside string literals) or by
    being a named partial index (whose Filter the verdict already checked).
    Arms of a ``BitmapAnd`` narrow together; each arm of a ``BitmapOr`` is read
    on its own, so each must narrow every bounded column itself. A bitmap over
    a state index that still filters the due time reads the whole index, and
    is not narrowing.
    """
    unnarrowed = [
        str(node["Index Cond"])
        for scan in iter_plan_nodes(walked)
        if scan.get("Relation Name") == table
        for node in iter_plan_nodes(scan)
        if "Index Cond" in node
        and CATALOG_INDEX in node
        and _leading_key_left_open(node) is not None
        and not _borrowed_from_a_join(node, _own_names(scan))
    ]
    filters = _expressions(walked, table, "Filter")
    bounded = _range_bounded_columns(filters + unnarrowed)
    # A scan narrowed only by a join has no local predicate to excuse: changing
    # join strategy must not hide a full child-table walk.
    # A local equality can be printed as an Index Cond on the wrong key,
    # leaving no heap Filter or range bound. It still asks for a narrowed
    # selection; the alternative must independently prove that narrowing.
    if not bounded and not filters and not unnarrowed:
        return False
    # Equality-only selections can also favor an unrelated index after ANALYZE
    # on an empty table. The bitmap must still genuinely narrow the selection;
    # when range bounds exist, every arm must additionally narrow those bounds.
    if index_served_verdict(bitmap, table=table, predicate_indexes=predicate_indexes) is not None:
        return False
    constrained = _constrained_columns(predicate_indexes)
    scans = [node for node in iter_plan_nodes(bitmap) if node.get("Relation Name") == table]
    return all(bounded <= _narrowed(node, bounded, constrained) for node in scans)


def _narrowed(node: dict[str, Any], bounded: set[str], constrained: Mapping[str, Collection[str]]) -> set[str]:
    """Which of the ``bounded`` columns an index narrows for everything this scan or bitmap node reads."""
    if node.get("Index Name") in constrained:
        return set(bounded)
    inputs = [child for child in node.get("Plans", ()) if child.get("Node Type") in _BITMAP_INPUTS]
    arms = [_narrowed(child, bounded, constrained) for child in inputs]
    if node.get("Node Type") == "BitmapOr":
        return set.intersection(*arms) if arms else set()
    return referenced_columns(str(node.get("Index Cond", "")), bounded).union(*arms)


_BITMAP_INPUTS = frozenset({"Bitmap Index Scan", "BitmapAnd", "BitmapOr"})


def _bitmap_index_inputs(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Walk this bitmap's inputs, excluding separately executed SubPlan/InitPlan scans."""
    for child in node.get("Plans", ()):
        if child.get("Node Type") == "Bitmap Index Scan":
            yield child
        elif child.get("Node Type") in _BITMAP_INPUTS:
            yield from _bitmap_index_inputs(child)


def _expressions(plan: dict[str, Any], table: str, key: str) -> list[str]:
    """``key`` expressions of every scan on ``table``."""
    return [str(node[key]) for node in iter_plan_nodes(plan) if node.get("Relation Name") == table and key in node]


def _range_bounded_columns(expressions: list[str]) -> set[str]:
    """The columns compared by a range operator, on either side, outside string literals and casts."""
    found: set[str] = set()
    for expression in expressions:
        text = _CAST.sub("", blank_literals_and_comments(expression))
        for match in _RANGE.finditer(text):
            operands = [match.group("left")] + ([] if match.group("call") else [match.group("right")])
            found.update(operand.strip('"') for operand in operands if operand and operand.upper() not in _NOT_COLUMNS)
    return found


def assert_plan_is_index_served(
    *, name: str, plan: dict[str, Any], table: str, predicate_indexes: PredicateIndexes = ()
) -> None:
    """
    The plan-shape verdict behind profile A's invariant 5, on an already-captured plan.

    A pure function of a plan tree, so the harness self-tests pin it against
    canned plans — including real plan shapes that once slipped past it —
    without needing a database or an adopter.

    Three false negatives motivated the current form, all found by pointing the
    proof at further adopters rather than by reasoning about it:

    1. *Absence of ``Seq Scan`` is not enough.* PostgreSQL will satisfy an
       unindexed predicate by walking an unrelated index end to end and
       filtering every row — a full scan wearing an index scan's name::

           Index Scan using unique_attempt_number_per_job
             Filter: ((updated_at <= ...) AND ((status = ANY (...)) OR ...))

    2. *A pruning marker anywhere in the tree is not enough.* In a join, the
       inner side's key lookup supplies an ``Index Cond`` while the driving scan
       still walks its whole table::

           Nested Loop Anti Join
             ->  Index Scan using orders_pkey                <- prunes nothing
                   Filter: (...)
             ->  Index Scan using shipments_order_id_idx     <- join key only
                   Index Cond: (order_id = orders.id)

    3. *A ``Recheck Cond`` is not a pruning key.* A bitmap heap node carries one
       unconditionally, whatever built the bitmap, so accepting it lets through a
       bitmap assembled by reading an entire index::

           Bitmap Heap Scan on job_attempts
             Recheck Cond: ...                     <- present for every bitmap
             Filter: (...)
             ->  Bitmap Index Scan using unique_attempt_number_per_job
                                                   <- no Index Cond: whole index

       It is the worst of the three, because the planner only chooses a bitmap
       once the table has rows — so the *same code* passed or failed depending
       on whether an earlier test in the same process had inserted any, and the
       order-dependent direction was toward green.

    And one false *positive*, found by writing a fix rather than an adopter:

    4. *A partial index carries no ``Index Cond`` for its own predicate.* When
       the index's WHERE clause subsumes the query's conditions, the plan is an
       index scan with no pruning key and no ``Filter`` — the narrowing lives in
       the index definition, invisible to the plan tree. Requiring a pruning key
       there rejects the best possible plan. A scan with no ``Filter`` discards
       nothing, so it is accepted: the waste this proof hunts is rows walked and
       then thrown away. A condition on a later B-tree key can also discard rows inside the index scan.

    5. *A later B-tree key cannot position the scan.* An index on
       ``(campaign_id, state)`` with only ``state = 'UNKNOWN'`` in its Index Cond
       can still read the whole index on PostgreSQL 16. Capture key order and
       predicates under ``CATALOG_INDEX`` with ``explain_index_eligibility``.
       Bare index conditions without catalog facts are unevaluable. A partial
       index narrows by its predicate; a bitmap of one without a condition is
       accepted only when no Filter or other relation can discard its rows.

    Three more false negatives came from an adopter audit that mutated real
    selections and watched the verdict stay green:

    6. *A join key is not the selection's condition.* A selection that filters
       an unindexed time column and joins its parent reaches the table through
       the foreign-key index, once per parent row::

           Nested Loop
             ->  Index Scan using parent_pkey on parent p
                   Filter: (scope = 's1')
             ->  Index Scan using child_parent_ix on child c
                   Index Cond: (parent_id = p.id)          <- join key only
                   Filter: (due_at <= now())               <- the selection's own condition

       The leading key is constrained, but by the join: each parent reads all of
       its children, which over realistic data is every row. An index condition
       counts only when one of its clauses is the selection's own (a literal, a
       parameter, ``now()``); ``(parent_id, due_at)`` with both clauses passes.
       So does a join key that fixes every key column of a full unique btree
       index by equality: an identity probe (an anti-join on a one-to-one
       dependency) reads at most one row per driving row.

    7. *A partial index read whole is not narrowed when a join discards.* With
       no Filter on the table, a scan of a partial index looks like case 4, but
       a hash join on a filtered parent then drops most of what it read. Plain
       scans now follow the bitmap rule: accepted alone, or when named in
       ``partial_indexes``.

    8. *No condition at all is a full read.* A scan of a non-partial index with
       neither an Index Cond nor a Filter reads every entry: the selection's
       narrowing is elsewhere (a join) or gone (a condition deleted from the
       query). Case 4 is now accepted only with catalog evidence that the index
       is partial.

    So the verdict inspects only the nodes scanning the selection's own table,
    requires each to be a non-sequential scan narrowed by the selection's own
    index condition or by a partial index's predicate, and — for a bitmap heap
    node — looks past its Recheck Cond to the Bitmap Index Scan that actually
    built the bitmap.
    """
    verdict = index_served_verdict(plan, table=table, predicate_indexes=predicate_indexes)
    assert verdict is None, f"{name}: {verdict}"


def scan_counts(plan: dict[str, Any]) -> tuple[float, float]:
    """
    ``(rows returned, rows discarded by filters)`` from an ``EXPLAIN ANALYZE`` plan.

    Returned is the largest ``Actual Rows`` of any node — the rows the selection
    actually produced before any limit; discarded is every ``Rows Removed by
    Filter`` and ``Rows Removed by Index Recheck`` in the tree, the rows read
    only to be thrown away. PostgreSQL reports each per loop, so a node run in a
    nested loop counts once per loop; a bitmap that reads a whole index and then
    rechecks it away shows up only as the recheck.
    """
    nodes = list(iter_plan_nodes(plan))
    returned = max(float(node.get("Actual Rows", 0) or 0) for node in nodes)
    discarded = sum(_removed(node) for node in nodes)
    return returned, discarded


def _loops(node: dict[str, Any]) -> float:
    return float(node.get("Actual Loops", 1) or 1)


def _removed_per_loop(node: dict[str, Any]) -> float:
    return float(node.get("Rows Removed by Filter", 0) or 0) + float(node.get("Rows Removed by Index Recheck", 0) or 0)


def _removed(node: dict[str, Any]) -> float:
    return _removed_per_loop(node) * _loops(node)


def read_cost(plan: dict[str, Any], *, table: str) -> ReadCost:
    """
    What the read cost, from the root of an ``EXPLAIN (ANALYZE, BUFFERS)`` plan.

    ``blocks`` is the root's inclusive shared-buffer count, so each block is
    counted once however many nodes touched it. ``visited`` is every row the
    scans of ``table`` produced or discarded, over all their loops: the work an
    index that reads its whole range and filters it leaves behind, which
    ``blocks`` alone would blur on a small table.
    """
    scans = [node for node in iter_plan_nodes(plan) if node.get("Relation Name") == table]
    assert scans, f"the read never scanned {table!r}, so its cost says nothing about that table"
    visited = sum((float(node.get("Actual Rows", 0) or 0) + _removed_per_loop(node)) * _loops(node) for node in scans)
    return ReadCost(
        blocks=int(plan.get("Shared Hit Blocks", 0)) + int(plan.get("Shared Read Blocks", 0)),
        visited=visited,
        sequential=any("Seq Scan" in node.get("Node Type", "") for node in scans),
    )


_KEY_CONDITION = re.compile(r"(\w+)\)?(?:::[\w ]+?)?\s*(?:~[<>]=?~|<=|>=|=|<|>|IS (?:NOT )?NULL\b)")


def _leading_key_left_open(access: dict[str, Any]) -> str | None:
    """
    The B-tree leading key column ``access``'s Index Cond leaves unconstrained, or ``None`` when the condition narrows.

    A B-tree is ordered by its leading column first. A condition on a later key
    column alone cannot position the scan, so PostgreSQL 16 reads every entry of
    the index and tests the condition on each: the read grows with the table.
    A partial index bounds the read by its own predicate, which the planner only
    uses when the selection implies it, so any condition on one narrows. Other
    access methods have no leading-column rule, and an expression key prints
    differently in the catalog and the plan, so both keep the condition as
    evidence.
    """
    catalog = access[CATALOG_INDEX]
    if catalog["Predicate"] is not None or catalog["Access Method"] != "btree":
        return None
    leading = bare_identifiers(catalog["Key Columns"][0]).strip()
    if not leading.isidentifier():
        return None
    return (
        None
        if leading in set(_KEY_CONDITION.findall(_CAST.sub("", bare_identifiers(str(access["Index Cond"])))))
        else leading
    )


def _index_condition_failure(access: dict[str, Any], table: str, plan: dict[str, Any]) -> str | None:
    """Refuse an unevaluable or unbounded condition, for plain and bitmap scans."""
    index = access.get("Index Name")
    if CATALOG_INDEX not in access:
        return (
            f"the plan names index {index!r} on {table!r} without its catalog definition; "
            f"capture it with explain_index_eligibility so key order can be judged.\n{_rendered(plan)}"
        )
    leading = _leading_key_left_open(access)
    if leading is not None:
        return (
            f"index {index!r} on {table!r} has Index Cond {access['Index Cond']} but leaves its "
            f"leading key column {leading!r} unconstrained. A B-tree reads the whole index when "
            f"only a later key is constrained; add a leading key or a partial predicate.\n{_rendered(plan)}"
        )
    return None
