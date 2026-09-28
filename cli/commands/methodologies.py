"""Registration point for the methodology CLI commands.

Command surface (see ``docs/methodology_decisions.md``):

    main.py methodologies list
    main.py methodologies show <name>
    main.py analyze-graham <ticker> [--era-adjustment]
    main.py compare-methodologies <ticker> [--methodologies a,b,c]

``methodologies`` is a command *group*: this module creates the group and
hands its subparsers to the individual command modules, which register
themselves. Adding a command never touches ``cli/main.py``.
"""

from __future__ import annotations

from cli.commands import (
    analyze_buffett_clark,
    analyze_graham,
    analyze_graham_dodd,
    compare_methodologies,
    methodologies_list,
    methodologies_show,
)


def register(subparsers) -> None:
    """Register the ``methodologies`` group and its children."""
    group = subparsers.add_parser(
        "methodologies",
        help="Multi-methodology engine commands",
        description="List, show and compare registered investment methodologies.",
    )
    group_sub = group.add_subparsers(dest="methodology_command", title="Methodologies")
    methodologies_list.register(group_sub)
    methodologies_show.register(group_sub)

    analyze_graham.register(subparsers)
    analyze_buffett_clark.register(subparsers)
    analyze_graham_dodd.register(subparsers)
    compare_methodologies.register(subparsers)
