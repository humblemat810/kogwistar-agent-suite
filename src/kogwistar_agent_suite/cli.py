"""Small local-first CLI for the Developer Pack."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .profiles import developer_profile
from .tools import ToolCall


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kogwistar-agent-suite")
    parser.add_argument("--workspace", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)
    search = subparsers.add_parser("search", help="search installed capabilities")
    search.add_argument("query")
    search.add_argument("--capability", action="append", default=[])
    search.add_argument("--mode", choices=("lexical", "bm25", "semantic"), default="lexical")
    search.add_argument("--ranked", action="store_true")
    subparsers.add_parser("profile", help="print the core AgentProfile")
    read = subparsers.add_parser("read", help="read bounded workspace text")
    read.add_argument("path")
    read.add_argument("--max-bytes", type=int, default=65536)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pack = developer_profile(args.workspace)
    if args.command == "search":
        if args.ranked:
            values = [
                {"capability": result.descriptor.__dict__, "match": result.match, "score": result.score}
                for result in pack.search_ranked(
                    args.query,
                    allowed_capabilities=frozenset(args.capability),
                    mode=args.mode,
                )
            ]
        else:
            values = [item.__dict__ for item in pack.search(
                args.query,
                allowed_capabilities=frozenset(args.capability),
                mode=args.mode,
            )]
        print(json.dumps(
            values,
            default=str,
            sort_keys=True,
        ))
        return 0
    if args.command == "profile":
        print(pack.agent_profile().stable_json())
        return 0
    if args.command == "read":
        text = pack.tools.call(
            ToolCall("workspace.read_text", {"relative_path": args.path, "max_bytes": args.max_bytes}),
            allowed_capabilities=frozenset({"workspace.read"}),
        )
        print(text, end="")
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
