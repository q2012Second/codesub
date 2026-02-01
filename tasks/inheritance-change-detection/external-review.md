Here’s a critical review of your plan against what’s actually in chat-context.txt, with the biggest correctness + integration risks called out.

⸻

0) Big plan-to-code mismatches you should fix before writing code

A) _check_semantic() does not return Trigger | None

In the current detector, scan() expects _check_semantic() to return a tuple (trigger, proposal) and appends both when present. If you implement the plan as “return a Trigger or None”, you’ll break the scan loop.

B) construct_cache is keyed by (path, language) only

construct_cache is shared across the scan and caches constructs for the target ref only (it’s populated by indexing the target version of files). It is not ref-aware, so you can’t reuse it to compare parent constructs between base_ref and target_ref without introducing a second cache keyed by ref (or a structure like cache[(ref, path, language)]).

This matters because inheritance-aware detection must diff parent members between two refs.

C) You already embed inheritance text into the class interface_hash

Python: _parse_class_container() uses the superclasses node text (bases_text) as the “annotation” fed into compute_interface_hash(). So class inheritance header changes already trigger subscriptions on the class itself.

Java: _extract_class() builds annotation from extends + implements text and feeds that into compute_interface_hash().

So the “missing trigger” problem you’re solving is specifically parent/member changes, not “child base list changes”. Your inherited-change design should be member-diff driven, not container-hash driven.

⸻

1) Override detection: _get_member_base_name() is a correctness trap (especially for Java)

The core issue

Your plan proposes: strip params from Java qualnames and compare only method name. That’s not how Java overriding works.

In your codebase, Java method qualnames intentionally include the parameter types:
User.setName(String) etc.

That is also how container tracking keys members: baseline keys are relative IDs derived from the member qualname suffix (after User.).

So:
	•	Overload ≠ override in Java.
	•	If you strip params, then any same-name overload in the child would “count as override” and suppress inherited triggers incorrectly.

Example (real Java semantics):
	•	Parent has process(Order, User)
	•	Child defines process(Order)
This is not overriding; child still inherits parent’s process(Order,User).

Your plan’s test “child process(Order) overrides parent process(Order,User)” is therefore a false model and will bake in incorrect behavior.

What you should do instead (high-confidence improvement)

Use signature-aware member IDs for Java methods:
	•	For Java methods: override/hide if name + normalized parameter list matches.
	•	You already normalize param type text by removing spaces.
	•	For Java fields: hide by field name only.
	•	For Java constructors: do not treat as inherited at all (constructors are not inherited in Java).
	•	For Python: name-only is reasonable (no overloading), but still treat any attribute definition (method/field/property) as hiding.

If you want a helper like _get_member_base_name, make it language/kind-aware and don’t use it for Java method override detection.

Another subtlety you’re currently missing

Your Java get_container_members() docstring explicitly says you don’t parse Java visibility and “all members are always included”.  ￼

Even though JavaIndexer does collect modifiers internally, the container-member API doesn’t filter. That means your inherited logic must decide:
	•	Do private parent members “propagate”? (In Java: they don’t.)
	•	Do static methods/fields propagate? (They’re inherited but not overridden; they can be hidden.)

If you don’t implement visibility rules, you’ll generate a lot of noisy inherited triggers.

⸻

2) Import parsing via Tree-sitter: good direction, but your proposed extraction logic is likely wrong

Python import parsing risks

Your proposed Tree-sitter traversal logic is very likely to miss common cases because Tree-sitter Python represents aliases and import lists in structured nodes (e.g., aliased_import) rather than token patterns.

You also said “Tree-sitter handles all edge cases” — it helps, but you still need correct node-type handling. The plan’s “look for ‘as’ tokens at child+1” style is exactly the kind of brittle approach Tree-sitter is meant to avoid.

Concrete missing Python cases your plan doesn’t handle well:
	•	from x import (A as B, C)  (nested lists / aliased nodes)
	•	import x.y as z  (alias structured node)
	•	class Child(Base[T]) where base is a subscript node (your _extract_base_classes only handles identifier + attribute)
	•	class Child(Base, metaclass=Meta) where the argument_list contains keyword arguments — you must not treat metaclass as a base class.

Given that your current Python indexer already pulls bases_text from the superclasses node without inspecting its internal children, it’s very plausible the superclasses node is itself the argument_list.

Your plan’s _extract_base_classes() expects an argument_list child inside superclasses_node, which could return empty for the most common case.

Java import parsing risks

Big missing piece: package resolution.

Your JavaIndexer builds class annotation from extends/implements, but there is no package-aware symbol resolution in the current code.

If you rely only on import_declaration, you will fail to resolve bases that are:
	•	in the same package (no import needed),
	•	referenced with a qualified name,
	•	reachable only via wildcard imports.

Also: mapping com.example.User → a file path requires knowing the project’s source roots (e.g., src/main/java, src/test/java, multi-module layouts). Your plan doesn’t address this, and it’s a common failure mode in real repos.

⸻

3) “Index files from subscription imports, not just diff” — correct motivation, but too broad in implementation

You’re right that for a chain like C extends B, B extends A, if only A changed, you still need to parse B (unchanged) to discover A and reach it. You won’t get that from diff-only indexing.

But indexing “all files reachable from subscription imports” is likely overkill and will explode scan time on real codebases.

Better approach: resolve only the inheritance chain, on demand

Instead of “index import closure”, do:
	1.	Parse the child file (already done in _check_semantic stage 1/2/3).
	2.	From the child class construct, read base_classes (or parse from the existing annotation).
	3.	Resolve just those bases to files/classes.
	4.	Parse each resolved parent file to get that parent’s base list, repeat to depth limit.

This is dramatically cheaper than recursively crawling every import.

⸻

4) Inheritance semantics are underspecified (and your current edge-case list misses a major one)

Major missing edge case: Python multiple inheritance and MRO

Your edge case says “diamond inheritance: each path visited once, all changes collected”.

That’s not correct for Python method resolution.

If class C(A, B) and both A and B define foo, then only one is actually inherited (A.foo under standard MRO). If B.foo changes, C’s behavior does not change.

If your resolver “collects all changes from all parents”, you will generate false positives.

To be correct, you must incorporate:
	•	MRO ordering (C3 linearization) at least for in-repo resolvable classes,
	•	“first definition wins” logic for inherited member provenance.

Intermediate overrides matter too

Your plan filters “where the child overrides the member”.

But for C extends B extends A, if B overrides A.foo, then changes in A.foo shouldn’t trigger C, even if C doesn’t override.

So the override/hide filter must consider all descendants between ancestor and child, not just the leaf.

⸻

5) Detector integration: where to hook inheritance checks without breaking existing behavior

How _check_semantic currently decides trigger type

When a semantic target is found cross-file, _search_cross_file() returns either:
	•	_check_container_members(...) if include_members is true and the kind is in CONTAINER_KINDS, or
	•	_classify_semantic_change(...) otherwise.

For container subscriptions, triggers are AGGREGATE and have a detailed schema (member_changes, etc.).

Integration implication

You cannot “just add inheritance triggers” without deciding:
	•	If a direct trigger exists, do you also compute and attach inherited changes?
	•	If yes, you must merge into the existing trigger details. Your plan says “don’t mutate triggers”, but the current model returns one trigger per subscription; returning multiple triggers for the same subscription would be a behavioral change.
	•	If no direct trigger exists, you can return a new trigger based only on inherited changes — but you still must return (trigger, proposal) correctly.

Change type selection for inherited changes

Your plan says: “use STRUCTURAL/CONTENT with source=inherited metadata”.

But container mode already uses AGGREGATE. If you add inherited changes to a container subscription trigger, you likely want to keep it AGGREGATE and add a details["inherited_changes"] section.

For non-container semantic subscriptions, you can set:
	•	STRUCTURAL if any inherited member had interface change / added / removed,
	•	else CONTENT.

⸻

6) Missing implementation pieces (these will bite you mid-build)

A) You need a “diff parent members between refs” helper

Right now, _check_container_members() compares baseline captured at subscription time vs current. It does not diff two arbitrary refs.

Inherited detection needs something like:
	•	diff_container(container_qualname, path, base_ref, target_ref) → member changes.

That function must:
	•	read file at base_ref and target_ref,
	•	index both,
	•	find the container construct in both,
	•	list their direct members in both,
	•	compare interface/body hashes per relative_id.

This is conceptually similar to _check_container_members, but the inputs differ.

B) Your caching strategy must become ref-aware

If you diff parent members for multiple children/subscriptions, you will re-parse the same ancestor files repeatedly unless you cache (ref, path, language) → constructs. Current construct_cache won’t help because it’s not ref-aware.

C) Java inheritance needs package + source root handling

Without this, the feature will appear “randomly broken” on many Java repos.

At minimum:
	•	parse the package declaration,
	•	attempt resolution in:
	1.	same package,
	2.	explicit imports,
	3.	java.lang (treat as external/skip),
	4.	wildcard imports (probably skip or best-effort).

And you’ll need a strategy for mapping package paths to actual filesystem paths.

⸻

7) Test plan review: strong coverage intent, but some tests are wrong / missing key cases

The “Java overload override” test is incorrect

“child process(Order) overrides parent process(Order,User) – no trigger”

That’s not overriding. Replace with tests that reflect real conditions:
	•	Parent has both overloads, child overrides one:
	•	Parent: process(Order) and process(Order,User)
	•	Child: process(Order)
Change process(Order,User) in parent → should trigger child, because it’s still inherited.
	•	Parent changes method signature:
	•	Parent changes process(Order) → process(Order,User) (remove old)
Child still has process(Order) → should trigger (override relationship breaks).

Missing tests you should add

Python:
	•	class Child(Base[T]) / Base[User] base extraction (subscript base)
	•	class Child(Base, metaclass=Meta) ensure metaclass isn’t treated as base
	•	Multiple inheritance MRO correctness:
	•	C(A,B) where both define foo; change B.foo should not trigger C
	•	Intermediate override suppression:
	•	C(B), B(A), B defines foo, A.foo changes → should not trigger C for foo

Java:
	•	Same-package base class resolution without import
	•	Private method changes in parent should not trigger child (if you implement real inheritance visibility)
	•	Interface method changes:
	•	adding abstract method should trigger implementing classes
	•	default method body change should trigger implementing classes only if they don’t implement it

Also: align tests with your current container semantics

Java container tracking currently includes all members even with include_private=False.  ￼
So if inherited detection does filter by visibility, you must decide whether to keep that inconsistency or update Java container behavior too.

⸻

8) Risk assessment (what’s most likely to go wrong)

High risk: false negatives or false positives from override logic
	•	Base-name matching will produce false negatives (miss inherited changes) by treating overloads as overrides.
	•	Ignoring intermediate overrides produces false positives and false negatives depending on chain shape.

High risk: performance regression

Indexing an entire import closure per subscription can turn O(subscriptions × imports × file_size) quickly.
Mitigation: on-demand chain traversal + ref-aware caching.

Medium risk: Java resolution brittleness

Package/source-root resolution is hard. If it’s wrong, users will see “sometimes it works, sometimes it doesn’t.”
Mitigation: start with best-effort same-directory heuristic + explicit imports, and document limits.

Medium risk: schema/UX drift

You’re adding new trigger details. Ensure:
	•	update doc serialization remains stable,
	•	CLI output stays readable,
	•	existing tests for aggregate trigger serialization still pass (you already have tests around this).

⸻

Practical recommendations to tighten the plan
	1.	Drop _get_member_base_name() for Java override detection.
Use signature-aware IDs (relative_id style) for Java methods, name-only for Java fields, ignore constructors.
	2.	Implement parent-member diff as a first-class helper (base_ref vs target_ref), rather than trying to reuse subscription-baseline logic.
	3.	Resolve inheritance chain on-demand, not via full import graph indexing.
	4.	Handle intermediate overrides (not only child) by walking from child upward and maintaining a “already defined” set of member IDs.
	5.	For Python multiple inheritance, either:
	•	implement MRO-aware provenance (best), or
	•	explicitly document that you will over-trigger in multiple inheritance and add a guard to avoid claiming correctness.

If you want, I can sketch a concrete “minimal correct” algorithm that matches your current data model (SemanticTarget, baseline_members, AGGREGATE trigger shape) and avoids the major semantic traps—without rewriting your detector architecture.
