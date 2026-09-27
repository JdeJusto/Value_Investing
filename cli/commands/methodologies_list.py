"""`methodologies list` — which methodologies are registered."""

from __future__ import annotations

from cli.formatters import dim, print_header


def register(subparsers):
    p = subparsers.add_parser(
        "list",
        help="List registered methodologies",
        description="Shows the name, version, family and source of every registered methodology.",
    )
    p.set_defaults(func=_run)


def _run(args):
    from backend.methodologies.registry import discover, registry

    discover()
    names = registry.list()

    print_header("Registered methodologies")
    if not names:
        print(dim("  No methodologies registered yet."))
        return

    print(f"  {'name':<16} {'version':<10} {'family':<22} source")
    print(f"  {'-' * 16} {'-' * 10} {'-' * 22} {'-' * 30}")
    for name in names:
        m = registry.get(name)
        meta = m.metadata()
        print(f"  {name:<16} {m.version:<10} {m.family:<22} {meta.get('source', '—')}")
    print()
    print(dim("  Use 'methodologies show <name>' for rules and limitations."))
