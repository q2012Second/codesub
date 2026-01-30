￼

Overall Assessment

NEEDS REVISION

The plan is directionally solid and fits the product goal, but there are a few correctness and “works end-to-end” gaps (especially around large files / pagination and a couple of concrete bugs) that should be fixed before implementation so you don’t end up with a partially-working browser or performance regressions.

⸻

Strengths
	•	Correct conceptual alignment with codesub’s model: using git-tracked files and targeting the baseline ref matches how subscriptions are evaluated (diffs, baseline vs target). This is consistent with how project endpoints already work (they load config + use baseline_ref). ￼
	•	Leverages existing backend error model: The codebase already has centralized error-to-status mapping for CodesubError (e.g., UnsupportedLanguageError → 400, FileNotFoundAtRefError → 404, etc.). Your new endpoints can reuse that and stay consistent with frontend ApiError handling.
	•	Good integration posture: keeping the manual location input and adding a “Browse…” button is low-risk and matches how SubscriptionForm currently builds/display semantic locations (path::qualname).
	•	Frontend concurrency awareness: You explicitly call out race conditions and reference the request-id pattern already used in FileBrowserModal (good sign you’re aligning with existing patterns). ￼
	•	Pragmatic graceful degradation: Promise.allSettled so symbols failing doesn’t block line selection is the right UX for unsupported languages / parse errors.

⸻

Issues Found

Critical
	1.	Large-file + pagination is not actually implemented end-to-end (blocks “browse visually” for many real files)
	•	Backend content endpoint is paginated (start_line, limit), but the frontend CodeViewerPanel in the plan always calls getProjectFileContent(projectId, filePath) with defaults (meaning it only loads the first N lines).
	•	The UI spec requires users to “browse files and select code visually”; if they can’t scroll beyond the initial chunk, they can’t select most of a large file.
	•	The “Large File Warning” in Step 10 doesn’t change the fetch behavior (no “load next chunk”, no “load full file”).
Status: Blocks implementation unless you adjust the plan to either load full files (with virtualization) or implement chunk loading/infinite scroll.
Related code reality: GitRepo.show_file() returns the entire file as a list of lines; there is no streaming/range support today, so “pagination” currently means “read everything then slice”, unless you rework it. ￼
	2.	Backend content endpoint plan has a concrete bug: missing exception import
In Step 2 you do:

try:
    language = detect_language(path)
    supports_semantic = True
except UnsupportedLanguageError:
    pass

but UnsupportedLanguageError isn’t imported in the snippet. That will raise NameError if an unsupported file is requested.
Status: Blocks implementation (easy fix, but must be fixed).
Grounding: UnsupportedLanguageError exists and is part of the global error mapping; you should import it from codesub.errors (or wherever it lives).

⸻

Major
	3.	Construct highlighting map logic is accidentally O(total_lines_in_constructs)
In the plan’s lineConstructMap you iterate from start_line to end_line for every construct, but only set the map on the first line. That loop is unnecessary and can get expensive for big constructs (classes spanning hundreds/thousands of lines).
Fix: just map.set(construct.start_line, construct) without the inner loop.
Status: Should fix before implementation (performance + avoid UI jank).
	4.	Path encoding in frontend likely wrong for FastAPI {path:path} segments
The plan uses:

`${API_BASE}/projects/${projectId}/files/${encodeURIComponent(path)}/content`

encodeURIComponent will encode / into %2F. Some servers/proxies reject encoded slashes; even if it works locally, it’s a common deployment footgun.
Better approaches:
	•	Encode each segment but keep slashes: path.split('/').map(encodeURIComponent).join('/')
	•	Or change API to accept path as a query parameter instead of a path segment.
Status: Should fix before implementation (avoids flaky routing / env-specific failures).

	5.	File list “pagination” is specified but FileListPanel doesn’t implement it
The plan mentions offset/limit and “Load more / pagination”, but the sample loadFiles() always requests the first page and overwrites state. That will fail for large repos.
Status: Can be addressed during implementation, but be explicit in plan: you need offset state + append behavior.
	6.	“Server-side filtering” is only half true (and may be expensive at scale)
The backend lists all files via git ls-tree and then filters in Python for every request. This still avoids sending 10k paths to the client, but repeated requests on every keystroke will repeatedly re-run ls-tree.
Mitigations (pick one):
	•	Cache the file list per (project_id, baseline_ref) for a short TTL.
	•	Add a search_prefix mode and use git pathspecs when possible (better than substring).
	•	Consider returning directory-aware results or doing “typeahead” search behavior.
Status: Can be addressed during implementation, but call it out explicitly in plan as a perf risk.
	7.	Binary files are not actually handled
The plan mentions skipping binary files, but the listing endpoint returns all tracked files. And GitRepo.show_file() runs subprocess.run(..., text=True) which can choke on binary/non-UTF8 content. ￼
Fix options:
	•	Filter file list by “likely text” extensions (default to common code/text).
	•	Or detect binary in backend (e.g., git cat-file -p and heuristic) and return a 415/400 with a clear message.
Status: Can be addressed during implementation, but without it users will hit confusing errors.

⸻

Minor
	8.	FastAPI request schema FileListRequest isn’t used
You define it, but the endpoint uses explicit query params. Either remove it or use it via Depends() to keep code clean.
	9.	supports_semantic detection could use existing registry helper
You already have get_indexer_for_path() in the semantic registry, which is used elsewhere and throws consistent errors.
Minor, but it avoids drift between “detect” and “get indexer”.
	10.	Syntax highlighting is described but not planned concretely
The plan says “syntax highlighting” but doesn’t specify a library or implementation detail. Not a blocker, but you’ll want to decide early because it affects rendering strategy with virtualization.

⸻

Recommendations

Backend
	•	Make “baseline ref missing” behavior explicit
Existing project status exposes baseline_ref: string | null on the frontend types. ￼
If baseline can be null, new endpoints should return a consistent error (likely 409 ConfigNotInitialized or 400) rather than an unhandled git error.
	•	Return a more payload-efficient content format (optional improvement)
Instead of {number, content} per line, consider:

{ "start_line": 1, "lines": ["...", "..."], "total_lines": 1234 }

The client can compute numbers. This reduces JSON size substantially for large chunks.

	•	Consider caching list_files(ref) per baseline. This is the highest-impact perf win for large repos (it avoids rerunning ls-tree for every search keystroke).
	•	Filter out submodules (optional)
git ls-tree can surface submodule entries; if those appear, show_file may behave oddly. Consider using git ls-tree -r (not --name-only) and filtering mode 160000.

Frontend
	•	Decide on one large-file strategy now
	•	Option A: Fetch full file (set limit large, maybe capped), and use virtualization.
	•	Option B: Chunked fetching + virtualization (recommended): fetch start_line chunks as the user scrolls.
	•	Option C: Hard cap with “Open externally” style fallback (least preferred).
	•	Reuse modal patterns from FileBrowserModal
	•	requestIdRef to prevent stale update
	•	Escape-to-close
	•	focus on mount
These are already implemented and will keep UX consistent. ￼
	•	Fix the construct map performance bug (remove the inner line loop).
	•	Path encoding: switch from encodeURIComponent(path) to segment-wise encoding, or refactor API to accept path in query.
	•	Error state UX
	•	FileListPanel should show error UI (like FileBrowserModal does) instead of // Handle error. ￼
	•	CodeViewerPanel should handle the “content fetch failed” case (right now it can end up blank).

Implementation order tweaks

Your step ordering is broadly good, but I’d adjust slightly:
	1.	Backend endpoints + tests (list/content/symbols)
	2.	Frontend API + types
	3.	Implement FileListPanel with real pagination + cancellation
	4.	Implement CodeViewerPanel with finalized large-file strategy
	5.	Wire CodeBrowserModal + SubscriptionForm integration
	6.	Frontend tests

This avoids building UI assumptions (like “we always have the whole file”) before the data-loading model is decided.

⸻

Questions
	1.	Do you want users to browse “baseline snapshot” only, or optionally browse the working tree / a selected ref?
The plan uses baseline, which is consistent, but it’s worth confirming because it affects user expectations (“why doesn’t this show my latest changes?”).
	2.	What’s the intended “large file” UX contract?
Should users be able to select lines anywhere in a 20k-line file? If yes, chunking + virtualization needs to be in the plan explicitly (not as a future consideration).
	3.	Should semantic selection ever include kind in the location string?
Today the UI displays semantic locations as path::qualname (no kind).
The CLI pipeline supports kind internally (it calls find_construct(..., kind=target.kind)), but it’s unclear if that’s user-exposed or only derived after lookup. ￼
	4.	Do you want to exclude non-text files by default?
If yes, define a default extension allowlist and only show “All files” behind an advanced toggle.

⸻

If you want, I can rewrite the plan’s “Step 7 CodeViewerPanel” section into a concrete chunk-loading + virtualization approach that fits your existing API style and avoids the big-file blockers.
