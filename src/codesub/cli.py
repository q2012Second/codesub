"""Command-line interface for codesub."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config_store import ConfigStore
from .errors import CodesubError
from .git_repo import GitRepo
from .models import Anchor, SemanticTarget, Subscription
from .utils import (
    LineTarget,
    SemanticTargetSpec,
    extract_anchors,
    format_subscription,
    parse_target_spec,
)
from .project_store import ProjectStore
from .scan_history import ScanHistory


def get_store_and_repo() -> tuple[ConfigStore, GitRepo]:
    """Get ConfigStore and GitRepo for the current directory."""
    repo = GitRepo()
    store = ConfigStore(repo.root)
    return store, repo


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize codesub in the current repository."""
    try:
        repo = GitRepo()
        store = ConfigStore(repo.root)

        # Resolve baseline ref
        baseline = args.baseline or "HEAD"
        baseline_hash = repo.resolve_ref(baseline)

        config = store.init(baseline_hash, force=args.force)

        print(f"Initialized codesub at {store.config_dir}")
        print(f"Baseline: {baseline_hash[:12]} ({baseline})")
        return 0

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_add(args: argparse.Namespace) -> int:
    """Add a new subscription."""
    try:
        store, repo = get_store_and_repo()
        config = store.load()
        baseline = config.repo.baseline_ref

        # Parse target specification
        target = parse_target_spec(args.location)

        if isinstance(target, SemanticTargetSpec):
            # Semantic subscription
            return _add_semantic_subscription(
                store, repo, baseline, target, args
            )
        else:
            # Line-based subscription
            return _add_line_subscription(
                store, repo, baseline, target, args
            )

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _add_line_subscription(
    store: ConfigStore,
    repo: GitRepo,
    baseline: str,
    target: LineTarget,
    args: argparse.Namespace,
) -> int:
    """Add a line-based subscription."""
    lines = repo.show_file(baseline, target.path)

    # Validate line range
    if target.end_line > len(lines):
        print(
            f"Error: Line range {target.start_line}-{target.end_line} exceeds "
            f"file length ({len(lines)} lines)",
            file=sys.stderr,
        )
        return 1

    # Extract anchors
    context_before, watched_lines, context_after = extract_anchors(
        lines, target.start_line, target.end_line, context=args.context
    )
    anchors = Anchor(
        context_before=context_before,
        lines=watched_lines,
        context_after=context_after,
    )

    # Create subscription
    sub = Subscription.create(
        path=target.path,
        start_line=target.start_line,
        end_line=target.end_line,
        label=args.label,
        description=args.desc,
        anchors=anchors,
    )

    store.add_subscription(sub)

    location = (
        f"{target.path}:{target.start_line}"
        if target.start_line == target.end_line
        else f"{target.path}:{target.start_line}-{target.end_line}"
    )
    print(f"Added subscription: {sub.id[:8]}")
    print(f"  Location: {location}")
    if args.label:
        print(f"  Label: {args.label}")
    print(f"  Watching {target.end_line - target.start_line + 1} line(s)")

    return 0


def _add_semantic_subscription(
    store: ConfigStore,
    repo: GitRepo,
    baseline: str,
    target: SemanticTargetSpec,
    args: argparse.Namespace,
) -> int:
    """Add a semantic subscription."""
    from .semantic import PythonIndexer

    indexer = PythonIndexer()

    lines = repo.show_file(baseline, target.path)
    source = "\n".join(lines)

    construct = indexer.find_construct(
        source, target.path, target.qualname, target.kind
    )
    if construct is None:
        print(f"Error: Construct '{target.qualname}' not found in {target.path}")
        print("Use 'codesub symbols' to discover valid targets.")
        return 1

    # Extract anchors from construct lines
    context_before, watched_lines, context_after = extract_anchors(
        lines, construct.start_line, construct.end_line, context=args.context
    )
    anchors = Anchor(
        context_before=context_before,
        lines=watched_lines,
        context_after=context_after,
    )

    # Create semantic target
    semantic = SemanticTarget(
        language="python",
        kind=construct.kind,
        qualname=construct.qualname,
        role=construct.role,
        interface_hash=construct.interface_hash,
        body_hash=construct.body_hash,
    )

    sub = Subscription.create(
        path=target.path,
        start_line=construct.start_line,
        end_line=construct.end_line,
        label=args.label,
        description=args.desc,
        anchors=anchors,
        semantic=semantic,
    )

    store.add_subscription(sub)

    print(f"Added semantic subscription: {sub.id[:8]}")
    print(f"  Target: {construct.kind} {construct.qualname}")
    print(f"  Location: {target.path}:{construct.start_line}-{construct.end_line}")
    if args.label:
        print(f"  Label: {args.label}")

    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all subscriptions."""
    try:
        store, _ = get_store_and_repo()
        config = store.load()

        subs = config.subscriptions
        if not args.all:
            subs = [s for s in subs if s.active]

        if not subs:
            print("No subscriptions found.")
            return 0

        if args.json:
            data = [s.to_dict() for s in subs]
            print(json.dumps(data, indent=2))
        else:
            print(f"Subscriptions ({len(subs)}):")
            print(f"Baseline: {config.repo.baseline_ref[:12]}")
            print()
            for sub in subs:
                print(format_subscription(sub, verbose=args.verbose))

        return 0

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_remove(args: argparse.Namespace) -> int:
    """Remove a subscription."""
    try:
        store, _ = get_store_and_repo()

        sub = store.remove_subscription(args.subscription_id, hard=args.hard)

        action = "Removed" if args.hard else "Deactivated"
        print(f"{action} subscription: {sub.id[:8]}")
        if sub.label:
            print(f"  Label: {sub.label}")

        return 0

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan for changes and report triggered subscriptions."""
    try:
        store, repo = get_store_and_repo()
        config = store.load()

        # Import detector here to avoid circular imports during module load
        from .detector import Detector

        # Resolve refs
        base_ref = args.base or config.repo.baseline_ref
        target_ref = repo.resolve_ref(args.target or "HEAD")
        base_ref = repo.resolve_ref(base_ref)

        if base_ref == target_ref:
            print("Base and target refs are the same. No changes to scan.")
            return 0

        # Run detection
        detector = Detector(repo)
        result = detector.scan(config.subscriptions, base_ref, target_ref)

        # Output results
        if args.json:
            from .update_doc import result_to_dict
            data = result_to_dict(result)
            print(json.dumps(data, indent=2))
        else:
            print(f"Scan: {base_ref[:12]} -> {target_ref[:12]}")
            print()

            if result.triggers:
                print(f"TRIGGERED ({len(result.triggers)}):")
                for trigger in result.triggers:
                    sub = trigger.subscription
                    label = f" [{sub.label}]" if sub.label else ""
                    location = f"{trigger.path}:{trigger.start_line}-{trigger.end_line}"
                    reasons = ", ".join(trigger.reasons)
                    print(f"  {sub.id[:8]}{label}")
                    print(f"    Location: {location}")
                    print(f"    Reason: {reasons}")
                print()

            if result.proposals:
                print(f"PROPOSED UPDATES ({len(result.proposals)}):")
                for prop in result.proposals:
                    sub = prop.subscription
                    label = f" [{sub.label}]" if sub.label else ""
                    old_loc = f"{prop.old_path}:{prop.old_start}-{prop.old_end}"
                    new_loc = f"{prop.new_path}:{prop.new_start}-{prop.new_end}"
                    reasons = ", ".join(prop.reasons)
                    print(f"  {sub.id[:8]}{label}")
                    print(f"    {old_loc} -> {new_loc}")
                    print(f"    Reason: {reasons}")
                    if prop.shift:
                        print(f"    Shift: {prop.shift:+d}")
                print()

            if result.unchanged:
                print(f"UNCHANGED ({len(result.unchanged)}):")
                for sub in result.unchanged:
                    label = f" [{sub.label}]" if sub.label else ""
                    print(f"  {sub.id[:8]}{label}")
                print()

        # Write update documents if requested
        if args.write_updates:
            from .update_doc import write_update_doc
            write_update_doc(result, args.write_updates)
            print(f"Wrote update document: {args.write_updates}")

        if args.write_md:
            from .update_doc import write_markdown_doc
            write_markdown_doc(result, args.write_md)
            print(f"Wrote markdown summary: {args.write_md}")

        # Exit code
        if args.fail_on_trigger and result.triggers:
            return 2

        return 0

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_apply_updates(args: argparse.Namespace) -> int:
    """Apply update proposals from an update document."""
    try:
        store, repo = get_store_and_repo()

        from .updater import Updater

        updater = Updater(store, repo)

        # Load update document
        with open(args.update_doc, "r", encoding="utf-8") as f:
            update_data = json.load(f)

        if args.dry_run:
            print("Dry run - no changes will be made")
            print()

        applied, warnings = updater.apply(update_data, dry_run=args.dry_run)

        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"  {warning}")
            print()

        if applied:
            print(f"Applied {len(applied)} update(s):")
            for sub_id in applied:
                print(f"  {sub_id[:8]}")
        else:
            print("No updates applied.")

        if not args.dry_run and applied:
            target_ref = update_data.get("target_ref", "")
            print(f"\nBaseline updated to: {target_ref[:12]}")

        return 0

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"Error: Update document not found: {args.update_doc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in update document: {e}", file=sys.stderr)
        return 1


def cmd_projects_list(args: argparse.Namespace) -> int:
    """List registered projects."""
    try:
        store = ProjectStore()
        projects = store.list_projects()

        if not projects:
            print("No projects registered.")
            print("Add a project with: codesub projects add <path>")
            return 0

        if args.json:
            data = [p.to_dict() for p in projects]
            print(json.dumps(data, indent=2))
        else:
            print(f"Projects ({len(projects)}):")
            print()
            for p in projects:
                print(f"  {p.id[:8]}  {p.name}")
                print(f"           {p.path}")
                print()

        return 0

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_projects_add(args: argparse.Namespace) -> int:
    """Add a project."""
    try:
        store = ProjectStore()
        project = store.add_project(path=args.path, name=args.name)

        print(f"Added project: {project.id[:8]}")
        print(f"  Name: {project.name}")
        print(f"  Path: {project.path}")

        return 0

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_projects_remove(args: argparse.Namespace) -> int:
    """Remove a project."""
    try:
        store = ProjectStore()
        project = store.remove_project(args.project_id)

        print(f"Removed project: {project.id[:8]} ({project.name})")

        return 0

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_scan_history_clear(args: argparse.Namespace) -> int:
    """Clear scan history."""
    try:
        history = ScanHistory()

        if args.project:
            count = history.clear_project_history(args.project)
            print(f"Cleared {count} scan(s) for project {args.project[:8]}")
        else:
            count = history.clear_all_history()
            print(f"Cleared {count} scan(s) from all projects")

        return 0

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_symbols(args: argparse.Namespace) -> int:
    """List discoverable code constructs in a file."""
    try:
        store, repo = get_store_and_repo()
        config = store.load()

        ref = args.ref or config.repo.baseline_ref
        lines = repo.show_file(ref, args.path)
        source = "\n".join(lines)

        from .semantic import PythonIndexer

        indexer = PythonIndexer()
        constructs = indexer.index_file(source, args.path)

        # Filter by kind if specified
        if args.kind:
            constructs = [c for c in constructs if c.kind == args.kind]

        # Filter by grep pattern if specified
        if args.grep:
            constructs = [c for c in constructs if args.grep in c.qualname]

        if args.json:
            data = [
                {
                    "path": c.path,
                    "kind": c.kind,
                    "qualname": c.qualname,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "role": c.role,
                }
                for c in constructs
            ]
            print(json.dumps(data, indent=2))
        else:
            if not constructs:
                print(f"No constructs found in {args.path}")
                return 0

            print(f"Constructs in {args.path} ({len(constructs)}):")
            print()
            for c in constructs:
                fqn = f"{c.path}::{c.qualname}"
                role_str = f" ({c.role})" if c.role else ""
                lines_str = (
                    f"{c.start_line}"
                    if c.start_line == c.end_line
                    else f"{c.start_line}-{c.end_line}"
                )
                print(f"  {c.kind:<10} {c.qualname}{role_str}")
                print(f"             Lines: {lines_str}")
                print(f"             FQN:   {fqn}")
                print()

        return 0

    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the API server."""
    try:
        import uvicorn

        # Verify we're in a git repo
        repo = GitRepo()
        store = ConfigStore(repo.root)

        if not store.exists():
            print("Warning: codesub not initialized. Run 'codesub init' first.", file=sys.stderr)
            print("Starting server anyway...", file=sys.stderr)

        print("Starting codesub API server...")
        print(f"Repository: {repo.root}")
        print(f"API docs: http://{args.host}:{args.port}/docs")
        print()

        # When reload is enabled, uvicorn requires the app as an import string
        app_target = "codesub.api:app" if args.reload else None
        if app_target is None:
            from .api import app
            app_target = app

        uvicorn.run(
            app_target,
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=1,  # Single worker to avoid concurrent write issues
        )
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="codesub",
        description="Subscribe to file line ranges and detect changes via git diff.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize codesub in the repository")
    init_parser.add_argument(
        "--baseline", "-b", help="Baseline ref (default: HEAD)"
    )
    init_parser.add_argument(
        "--force", "-f", action="store_true", help="Overwrite existing config"
    )

    # add
    add_parser = subparsers.add_parser("add", help="Add a new subscription")
    add_parser.add_argument(
        "location",
        help="Location to subscribe to. Line-based: 'path:line' or 'path:start-end'. "
        "Semantic: 'path::QualName' or 'path::kind:QualName'",
    )
    add_parser.add_argument("--label", "-l", help="Label for the subscription")
    add_parser.add_argument("--desc", "-d", help="Description")
    add_parser.add_argument(
        "--context", "-c", type=int, default=2,
        help="Number of context lines for anchors (default: 2)"
    )

    # list
    list_parser = subparsers.add_parser("list", help="List subscriptions")
    list_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    list_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed info including anchors"
    )
    list_parser.add_argument(
        "--all", "-a", action="store_true", help="Include inactive subscriptions"
    )

    # remove
    remove_parser = subparsers.add_parser("remove", help="Remove a subscription")
    remove_parser.add_argument("subscription_id", help="Subscription ID (or prefix)")
    remove_parser.add_argument(
        "--hard", action="store_true", help="Delete entirely (default: deactivate)"
    )

    # symbols
    symbols_parser = subparsers.add_parser(
        "symbols", help="List discoverable code constructs in a file"
    )
    symbols_parser.add_argument("path", help="File path to analyze")
    symbols_parser.add_argument("--ref", help="Git ref (default: baseline)")
    symbols_parser.add_argument(
        "--kind",
        choices=["variable", "field", "method"],
        help="Filter by construct kind",
    )
    symbols_parser.add_argument("--grep", help="Filter by name pattern")
    symbols_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # scan
    scan_parser = subparsers.add_parser(
        "scan", help="Scan for changes and report triggered subscriptions"
    )
    scan_parser.add_argument(
        "--base", "-b", help="Base ref (default: config baseline)"
    )
    scan_parser.add_argument(
        "--target", "-t", help="Target ref (default: HEAD)"
    )
    scan_parser.add_argument(
        "--write-updates", "-w", help="Write JSON update document to path"
    )
    scan_parser.add_argument(
        "--write-md", "-m", help="Write markdown summary to path"
    )
    scan_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    scan_parser.add_argument(
        "--fail-on-trigger", action="store_true",
        help="Exit with code 2 if any subscriptions are triggered"
    )

    # apply-updates
    apply_parser = subparsers.add_parser(
        "apply-updates", help="Apply update proposals from an update document"
    )
    apply_parser.add_argument("update_doc", help="Path to update document JSON")
    apply_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without applying"
    )

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    serve_parser.add_argument(
        "--port", "-p", type=int, default=8000, help="Port to bind to (default: 8000)"
    )
    serve_parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )

    # projects (subcommand group)
    projects_parser = subparsers.add_parser("projects", help="Manage registered projects")
    projects_subparsers = projects_parser.add_subparsers(dest="projects_command")

    # projects list
    projects_list_parser = projects_subparsers.add_parser("list", help="List registered projects")
    projects_list_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # projects add
    projects_add_parser = projects_subparsers.add_parser("add", help="Add a project")
    projects_add_parser.add_argument("path", help="Path to git repository")
    projects_add_parser.add_argument("--name", "-n", help="Display name (defaults to dir name)")

    # projects remove
    projects_remove_parser = projects_subparsers.add_parser("remove", help="Remove a project")
    projects_remove_parser.add_argument("project_id", help="Project ID")

    # scan-history
    scan_history_parser = subparsers.add_parser("scan-history", help="Manage scan history")
    scan_history_subparsers = scan_history_parser.add_subparsers(dest="scan_history_command")

    # scan-history clear
    scan_history_clear_parser = scan_history_subparsers.add_parser("clear", help="Clear scan history")
    scan_history_clear_parser.add_argument(
        "--project", "-p", help="Clear only for specific project ID"
    )

    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Handle projects subcommands
    if args.command == "projects":
        if not hasattr(args, "projects_command") or not args.projects_command:
            parser.parse_args(["projects", "--help"])
            return 0
        if args.projects_command == "list":
            return cmd_projects_list(args)
        elif args.projects_command == "add":
            return cmd_projects_add(args)
        elif args.projects_command == "remove":
            return cmd_projects_remove(args)

    # Handle scan-history subcommands
    if args.command == "scan-history":
        if not hasattr(args, "scan_history_command") or not args.scan_history_command:
            parser.parse_args(["scan-history", "--help"])
            return 0
        if args.scan_history_command == "clear":
            return cmd_scan_history_clear(args)

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "list": cmd_list,
        "remove": cmd_remove,
        "symbols": cmd_symbols,
        "scan": cmd_scan,
        "apply-updates": cmd_apply_updates,
        "serve": cmd_serve,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        return cmd_func(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
