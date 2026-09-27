"""`methodologies show` — full metadata for one methodology."""

from __future__ import annotations

from cli.formatters import (
    dim,
    green,
    print_header,
    print_key_value,
    print_section,
    red,
)

_KIND_COLOR = {"EXPLICIT": green, "INFERRED": lambda t: t, "EXCEPTION": red}


def register(subparsers):
    p = subparsers.add_parser(
        "show",
        help="Show metadata, rules and limitations for a methodology",
        description="Renders the rules, verdict logic and known limitations of one methodology.",
    )
    p.add_argument("name", help="Methodology name (e.g. graham)")
    p.set_defaults(func=_run)


def _run(args):
    from backend.methodologies.registry import discover, registry

    discover()
    methodology = registry.get(args.name)
    if methodology is None:
        print(red(f"ERROR: unknown methodology '{args.name}'."))
        print(dim(f"  Registered: {', '.join(registry.list())}"))
        return

    meta = methodology.metadata()
    print_header(f"Methodology: {methodology.name} v{methodology.version}")
    print_key_value("Family", methodology.family)
    print_key_value("Source", meta.get("source", "—"))
    print_key_value("Era", meta.get("era", "—"))
    print()

    print_section("Rules")
    for rule in methodology.rules():
        color = _KIND_COLOR.get(rule.kind, lambda t: t)
        page = f" [{rule.source.page}]" if rule.source and rule.source.page else ""
        print(f"  {color(rule.kind):<10} {rule.id:<38} {rule.name}{page}")
        print(f"  {'':<10} {dim(rule.description)}")
    print()

    print_section("Verdict logic")
    print(dim(f"  {meta.get('verdict_logic', '—')}"))
    print()

    print_section("Known limitations")
    for limitation in meta.get("known_limitations", []):
        print(f"  • {limitation}")
    print()

    print_section("Era adjustment")
    print_key_value("Supported", "yes" if meta.get("era_adjustment") else "no")
    print(dim(f"  {meta.get('era_adjustment_caveat', '—')}"))
