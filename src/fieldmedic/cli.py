from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

from .local_models import discover_local_models
from .orchestrator import AgentMedic
from .router import route
from .specialists import list_specialists


def _home() -> Path:
    return Path(
        os.environ.get("FIELDMEDIC_HOME", str(Path.home() / ".fieldmedic"))
    ).expanduser()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fieldmedic")
    p.add_argument(
        "--brainc",
        default=os.environ.get("BRAINC_ROUTER_BIN"),
        help="optional BrainC-compatible router executable",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("health", help="check available diagnostic engines")
    h.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    h.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))
    h.add_argument("--no-model-discovery", action="store_true")

    r = sub.add_parser("route", help="deterministically route a symptom")
    r.add_argument("symptom")

    sub.add_parser("models", help="discover local-first reasoning models")
    sub.add_parser("specialists", help="list Agent Medic specialist capabilities")

    d = sub.add_parser("doctor", help="open a governed diagnostic case")
    d.add_argument("symptom")
    d.add_argument("--case-id")
    d.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    d.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))
    d.add_argument("--no-model-discovery", action="store_true")
    d.add_argument(
        "--local-reasoning",
        action="store_true",
        help="allow the selected local Ollama model to refine the evidence-cited synthesis",
    )

    args = p.parse_args(argv)
    agent = AgentMedic(_home(), brainc_binary=args.brainc)

    if args.cmd == "health":
        result = agent.health(
            args.drivemedic,
            args.netmedic,
            discover_models=not args.no_model_discovery,
        )
    elif args.cmd == "route":
        result = route(args.symptom).to_dict()
    elif args.cmd == "models":
        result = {"models": [item.to_dict() for item in discover_local_models()]}
    elif args.cmd == "specialists":
        result = {"specialists": list_specialists()}
    else:
        result = agent.doctor(
            args.symptom,
            args.drivemedic,
            args.netmedic,
            args.case_id,
            discover_models=not args.no_model_discovery,
            local_reasoning=args.local_reasoning,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
