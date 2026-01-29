￼

Implementation Plan: Frontend Semantic Subscription Management

Overview

The backend already models “semantic subscriptions” via a semantic target (language/kind/qualname/role + hashes) and emits scan-time semantic metadata such as Trigger.change_type/details and Proposal.new_qualname/new_kind. The frontend currently treats every subscription as line-based (path:start-end) and needs to be updated to:
	•	Represent semantic targets in TypeScript types
	•	Display semantic subscriptions distinctly in list + detail views
	•	Accept semantic subscription input (file.py::Qual.Name) in the form
	•	Style scan results by semantic change type and show details
	•	Show semantic rename suggestions in the apply-updates modal

All changes below follow the existing React patterns in this codebase (plain TS interfaces + inline style={{...}} objects, not Tailwind). For example, the current list/table + badge styling is inline, and scan results are rendered with inline “alert-like” boxes.

⸻

Prerequisites
	•	Confirm the backend API responses include the semantic fields you intend to use:
	•	Subscription.semantic should be present for semantic subscriptions (backend dataclass supports it) ￼ ￼
	•	Scan results already serialize trigger.change_type/trigger.details and proposal.new_qualname/proposal.new_kind when present ￼ ￼
	•	Optional but recommended: add 1–2 example semantic subscriptions in your dev environment so you can visually verify [S] vs [L] badges and scan styling.

⸻

Implementation Steps

Step 1: Extend frontend TypeScript models for semantic fields

File: frontend/src/types.ts
Why: Subscription, Trigger, and Proposal types are currently missing semantic-related fields.

Changes:
	1.	Add a SemanticTarget interface matching the backend SemanticTarget.to_dict() shape. The backend includes language, kind, qualname, optional role, hashes, and fingerprint_version. ￼
	2.	Add semantic?: SemanticTarget | null to Subscription. (Backend stores semantic: SemanticTarget | None.) ￼
	3.	Add change_type?: ChangeType and details?: unknown to Trigger. (Backend describes change_type and details.) ￼
	4.	Add new_qualname?: string | null and new_kind?: string | null to Proposal. (Backend adds these for semantic rename/move proposals.) ￼ ￼

Suggested code snippet:

// frontend/src/types.ts

export interface SemanticTarget {
  language: string;   // e.g. "python"
  kind: string;       // e.g. "method" | "class" | "variable" ...
  qualname: string;   // e.g. "User.validate" | "API_VERSION"
  role?: string | null; // e.g. "const"
  interface_hash?: string;
  body_hash?: string;
  fingerprint_version?: number;
}

// Backend can emit: "STRUCTURAL"|"CONTENT"|"MISSING"|"AMBIGUOUS"|"PARSE_ERROR"
export type ChangeType =
  | 'STRUCTURAL'
  | 'CONTENT'
  | 'MISSING'
  | 'AMBIGUOUS'
  | 'PARSE_ERROR'
  // defensive: tolerate older/newer backend casing
  | 'structural'
  | 'content'
  | 'missing';

export interface Subscription {
  // existing fields...
  semantic?: SemanticTarget | null;
}

export interface Trigger {
  // existing fields...
  change_type?: ChangeType;
  details?: unknown;
}

export interface Proposal {
  // existing fields...
  new_qualname?: string | null;
  new_kind?: string | null;
}

Edge-compatibility note: Scan history may contain older entries without change_type / details / new_qualname / new_kind, so keep them optional (as above). The backend serializer already makes them conditional.  ￼ ￼

⸻

Step 2: Add semantic vs line-based badge + semantic summary in the subscription list

File: frontend/src/components/SubscriptionList.tsx
Current behavior: The “Location” column shows only path:start-end.

Desired behavior: Show [S] vs [L] and, if semantic, show qualname + (kind) and optionally role if "const", while still showing the line range.

Changes:
	1.	Compute const isSemantic = !!sub.semantic;
	2.	Prepend a badge:
	•	Semantic: S
	•	Line: L
	3.	If semantic: show qualname (kind) before the path:start-end portion.

Suggested code snippet (minimal change, inline styles like existing badges):

// inside SubscriptionList row render

const lineLoc = sub.start_line === sub.end_line
  ? `${sub.path}:${sub.start_line}`
  : `${sub.path}:${sub.start_line}-${sub.end_line}`;

const isSemantic = !!sub.semantic;

const badgeStyle = (semantic: boolean) => ({
  display: 'inline-block',
  minWidth: 18,
  textAlign: 'center' as const,
  padding: '2px 6px',
  borderRadius: 4,
  fontSize: 12,
  fontWeight: 600,
  marginRight: 8,
  background: semantic ? '#d1ecf1' : '#e9ecef',  // info vs neutral
  color: semantic ? '#0c5460' : '#6c757d',
});

<td style={{ padding: '12px 8px' }}>
  <span style={badgeStyle(isSemantic)}>{isSemantic ? 'S' : 'L'}</span>

  {isSemantic && sub.semantic ? (
    <span style={{ marginRight: 8 }}>
      {sub.semantic.qualname}{' '}
      <span style={{ color: '#666' }}>({sub.semantic.kind})</span>
      {sub.semantic.role === 'const' && (
        <span style={{
          marginLeft: 6,
          padding: '1px 6px',
          borderRadius: 10,
          fontSize: 11,
          background: '#fff3cd',
          color: '#856404',
        }}>
          const
        </span>
      )}
    </span>
  ) : null}

  <span style={{ fontFamily: 'monospace', color: '#666' }}>
    {lineLoc}
  </span>
</td>

Edge cases handled:
	•	semantic missing/null → treated as line-based.
	•	semantic present but missing role/hashes → display still works (optional fields).

⸻

Step 3: Add a “Semantic Target” section on Subscription detail

File: frontend/src/components/SubscriptionDetail.tsx
Current behavior: Displays Location computed from path + start_line/end_line and other metadata.

Desired behavior: For semantic subscriptions, show an additional section with language/kind/qualname + hashes.

Changes:
	1.	Keep the existing location string as-is (still useful).
	2.	If sub.semantic exists, render a new dl block under the existing “Location/Label/Description…” area.

Suggested code snippet:

// after existing "Location" row(s) in the <dl> section:
{sub.semantic && (
  <>
    <h3 style={{ marginTop: 24, marginBottom: 8 }}>Semantic Target</h3>
    <dl style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 8 }}>
      <dt style={{ color: '#666' }}>Language</dt>
      <dd>{sub.semantic.language}</dd>

      <dt style={{ color: '#666' }}>Kind</dt>
      <dd>{sub.semantic.kind}</dd>

      <dt style={{ color: '#666' }}>Qualified Name</dt>
      <dd style={{ fontFamily: 'monospace' }}>{sub.semantic.qualname}</dd>

      <dt style={{ color: '#666' }}>Interface Hash</dt>
      <dd style={{ fontFamily: 'monospace' }}>
        {sub.semantic.interface_hash || <span style={{ color: '#999' }}>-</span>}
      </dd>

      <dt style={{ color: '#666' }}>Body Hash</dt>
      <dd style={{ fontFamily: 'monospace' }}>
        {sub.semantic.body_hash || <span style={{ color: '#999' }}>-</span>}
      </dd>
    </dl>
  </>
)}

Edge cases handled:
	•	Semantic exists but hashes are empty strings → show - placeholder.
	•	Non-semantic subscriptions → no new section.

⸻

Step 4: Update “Add Subscription” form to accept semantic input format

File: frontend/src/components/SubscriptionForm.tsx
Current behavior: Placeholder and help text only describe path:line / path:start-end.

Desired behavior: Support both:
	•	Line: file.py:10-20
	•	Semantic: file.py::ClassName.method

Auto-detect presence of ::.

Changes (minimal):
	1.	Update placeholder text to include semantic example.
	2.	Update help text (the small gray text) to mention both formats.
	3.	Add a small “Detected format” hint based on location.includes('::').

Suggested code snippet:

// near the location input in SubscriptionForm.tsx:

const isSemantic = location.includes('::');

<input
  type="text"
  value={location}
  onChange={(e) => setLocation(e.target.value)}
  placeholder="path/to/file.py:42-50 or path/to/file.py::ClassName.method"
  style={{ width: '100%', padding: 8, border: '1px solid #ddd', borderRadius: 4 }}
/>

<div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
  Format:
  {' '}
  <span style={{ fontFamily: 'monospace' }}>path:line</span>,
  {' '}
  <span style={{ fontFamily: 'monospace' }}>path:start-end</span>,
  {' '}
  or
  {' '}
  <span style={{ fontFamily: 'monospace' }}>path::Qualified.Name</span>
  {' '}
  (repo-relative path).
</div>

{location.trim().length > 0 && (
  <div style={{
    fontSize: 12,
    marginTop: 6,
    color: isSemantic ? '#0c5460' : '#6c757d',
  }}>
    Detected: {isSemantic ? 'semantic subscription' : 'line-based subscription'}
  </div>
)}

Important note / risk to flag: In the provided backend snippet, the create-subscription endpoint’s description still mentions only path:line / path:start-end. Your task statement says backend is already updated; if that’s true in your actual branch, you’re fine. If not, semantic form submission will 400 until backend parsing is updated.

⸻

Step 5: Enhance Scan results view to style by change_type + show details

File: frontend/src/components/ScanView.tsx
Current behavior:
	•	Has a small REASON_LABELS mapping for line-based reasons only.
	•	Renders triggers with a fixed “danger/red” style, and proposals with fixed “warning/yellow” style.

Desired behavior:
	•	Style triggers by change_type:
	•	STRUCTURAL → warning/orange
	•	CONTENT → info/blue
	•	MISSING → error/red
	•	Show details (if present) as extra context
	•	Expand reason labels for semantic reasons (e.g., interface_changed, body_changed, semantic_target_missing, semantic_location)—these are emitted by the detector.

Changes:
	1.	Expand REASON_LABELS:

const REASON_LABELS: Record<string, string> = {
  // existing...
  overlap_hunk: 'Lines in range were modified',
  insert_inside_range: 'New lines inserted inside range',
  file_deleted: 'File was deleted',
  line_shift: 'Lines shifted due to changes above',
  rename: 'File was renamed or moved',

  // semantic reasons
  interface_changed: 'Interface/signature changed',
  body_changed: 'Implementation/value changed',
  semantic_location: 'Semantic target moved/renamed',
  semantic_target_missing: 'Semantic target not found',
  // optional future-proof
  ambiguous: 'Multiple possible semantic matches',
  parse_error: 'Parser error while analyzing target',
};

	2.	Add helper functions near the top of the component:

function normalizeChangeType(ct?: string): string | undefined {
  if (!ct) return undefined;
  return ct.toUpperCase();
}

function triggerStyleForChangeType(ct?: string) {
  const t = normalizeChangeType(ct);

  if (t === 'CONTENT') {
    return { background: '#d1ecf1', borderColor: '#bee5eb', color: '#0c5460' }; // info
  }
  if (t === 'STRUCTURAL') {
    return { background: '#fff3cd', borderColor: '#ffeeba', color: '#856404' }; // warning
  }
  if (t === 'MISSING') {
    return { background: '#f8d7da', borderColor: '#f5c6cb', color: '#721c24' }; // danger
  }
  if (t === 'AMBIGUOUS' || t === 'PARSE_ERROR') {
    return { background: '#e2e3e5', borderColor: '#d6d8db', color: '#383d41' }; // neutral/gray
  }
  // fallback to existing trigger style
  return { background: '#f8d7da', borderColor: '#f5c6cb', color: '#721c24' };
}

function formatDetails(details: unknown): string {
  if (details == null) return '';
  if (typeof details === 'string') return details;
  try { return JSON.stringify(details, null, 2); } catch { return String(details); }
}

	3.	Update the trigger card rendering to:

	•	Use triggerStyleForChangeType(t.change_type)
	•	Prefix header with [CHANGE_TYPE] if present
	•	Render t.details if present

Patch-style snippet (conceptual):

{result.triggers.map((t: Trigger, idx: number) => {
  const style = triggerStyleForChangeType(t.change_type);
  const ct = normalizeChangeType(t.change_type);

  return (
    <div
      key={idx}
      style={{
        marginBottom: 12,
        padding: 12,
        border: `1px solid ${style.borderColor}`,
        borderRadius: 6,
        background: style.background,
        color: style.color,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 4 }}>
        {ct ? `[${ct}] ` : ''}
        {t.label || t.subscription_id}
      </div>

      <div style={{ fontFamily: 'monospace', fontSize: 12, marginBottom: 6 }}>
        {t.path}:{t.start_line}-{t.end_line}
      </div>

      <div style={{ fontSize: 12 }}>
        {formatReasons(t.reasons)}
      </div>

      {t.details != null && (
        <pre style={{
          marginTop: 8,
          padding: 8,
          background: 'rgba(255,255,255,0.6)',
          borderRadius: 4,
          overflowX: 'auto',
          fontSize: 12,
        }}>
          {formatDetails(t.details)}
        </pre>
      )}
    </div>
  );
})}

This plugs into the existing rendering pattern where triggers are already mapped into alert-like boxes.

Edge cases handled:
	•	change_type missing (older scans) → fallback style.
	•	Unknown change_type values → fallback style.
	•	details is dict vs string → formatDetails handles both.

⸻

Step 6: Show semantic rename suggestions in ApplyUpdatesModal

File: frontend/src/components/ApplyUpdatesModal.tsx
Current behavior: Displays label + old_path:old_start-old_end -> new_path:new_start-new_end.

Desired behavior: If new_qualname is present, show rename suggestion (and new_kind if present).

Changes:
	1.	After the existing location line, add:

{(p.new_qualname || p.new_kind) && (
  <div style={{ fontSize: 12, fontFamily: 'monospace', color: '#666', marginTop: 4 }}>
    Semantic:{' '}
    {p.new_qualname ?? <span style={{ color: '#999' }}>-</span>}
    {p.new_kind ? ` (${p.new_kind})` : ''}
  </div>
)}

Why it works: Backend emits these fields only when applicable (semantic move/rename proposal). ￼

⸻

Step 7: (Optional but recommended) Show semantic rename hints in ScanView proposals list too

File: frontend/src/components/ScanView.tsx
Why: Users often decide whether to apply updates while looking at ScanView; adding the semantic rename hint here reduces clicks.

Where: In the proposals map, right under the old->new location line (similar to ApplyUpdatesModal). The proposals section is currently rendered in a yellow box.

Snippet:

{p.new_qualname && (
  <div style={{ fontFamily: 'monospace', fontSize: 12, color: '#666', marginTop: 4 }}>
    Semantic: {p.new_qualname}{p.new_kind ? ` (${p.new_kind})` : ''}
  </div>
)}


⸻

Testing Strategy

Even if you don’t currently have a test harness wired up, defining test cases keeps the implementation honest. Here are concrete test cases you can implement with React Testing Library (or use as manual QA steps).

Component-level tests (React Testing Library)
	•	SubscriptionList renders [L] for line-based subs
	•	Given a Subscription with semantic: undefined, expect badge text L and no qualname shown.
	•	Baseline reference for current rendering: list shows path:start-end in the Location cell.
	•	SubscriptionList renders [S] and semantic summary
	•	Given Subscription.semantic = { qualname: 'User.validate', kind: 'method' }, expect badge S, “User.validate (method)”, and also line location.
	•	SubscriptionList shows const badge when role is const
	•	Given semantic.role = 'const', expect a “const” pill.
	•	SubscriptionDetail shows Semantic Target section only when semantic exists
	•	With semantic: null → section not present.
	•	With semantic populated → section includes Language, Kind, Qualified Name, Interface Hash, Body Hash. (Location row still present.)
	•	SubscriptionForm “Detected” hint switches on ::
	•	Set location input to auth.py::User.validate → expect “Detected: semantic subscription”.
	•	Set to auth.py:10-20 → expect “Detected: line-based subscription”.
	•	Verify placeholder/help text updated from current line-only hint.
	•	ScanView trigger styling changes with change_type
	•	Render triggers with change_type: 'STRUCTURAL' and confirm the warning background/border are applied.
	•	Render with change_type: 'CONTENT' and confirm info style.
	•	Render with change_type: 'MISSING' and confirm danger style (same as current trigger style).
	•	Current trigger render uses fixed danger styles.
	•	ScanView renders details
	•	Given details: { from: "str", to: "str | None" }, expect a <pre> with JSON string.
	•	ApplyUpdatesModal shows semantic rename when new_qualname exists
	•	Given Proposal.new_qualname = 'NewClass.method', expect “Semantic: NewClass.method”.
	•	Current modal does not show anything except location.

Manual QA (fast, high-value)
	•	Create a semantic subscription via the form (file.py::Class.method) and confirm it appears in the list with [S] badge.
	•	Run a scan where a semantic target changes and verify:
	•	[STRUCTURAL] or [CONTENT] appears in the trigger header
	•	the trigger box color matches the change type
	•	details are visible if provided
	•	Run a scan where a semantic target is renamed/moved and confirm:
	•	Proposal shows new_qualname/new_kind in ApplyUpdatesModal
	•	Applying updates works and subscription metadata updates accordingly

⸻

Edge Cases
	•	Subscription has semantic: null or missing: Treat as line-based; show [L] badge and existing UI. (Type uses optional/nullable.)
	•	Old scan history entries missing change_type/details: Keep UI backward compatible by making fields optional and rendering conditionally. Serializer only adds them “if present.” ￼
	•	Unknown change_type value: Normalize to uppercase and use fallback style (current danger style or a gray neutral).
	•	details not a string: Render JSON safely; if stringify fails, show String(details).
	•	Semantic proposals without new_kind: Display just new_qualname.
	•	Input contains :: but is malformed: Backend should reject; frontend should show the returned error via existing showMessage('error', ...) behavior (already used throughout).

⸻

Risks & Mitigations
	•	Risk: Backend subscription endpoints may not yet return semantic even if the model supports it.
Evidence: The dataclass supports semantic and to_dict() includes it ￼, but the Pydantic subscription_to_schema() shown does not include semantic (it only maps anchors + core fields). ￼
Mitigation: Before finalizing the frontend, verify actual /subscriptions responses. If semantic is missing, you’ll need a backend schema update (or a separate endpoint) before the semantic UI can populate.
	•	Risk: Casing mismatch (STRUCTURAL vs structural) between environments.
Mitigation: Use normalizeChangeType() and accept both in the union type.
	•	Risk: Styling consistency (Tailwind vs inline styles).
Mitigation: Keep the existing inline style approach used by SubscriptionList, ScanView, and ApplyUpdatesModal to minimize change footprint and maintain consistency.

⸻

If you want, I can also include a “diff-style” checklist of exact insertion points (e.g., “after line X in ScanView.tsx, insert helper Y”), but the steps above should map cleanly onto the current component structure shown in chat-context.txt.
