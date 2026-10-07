from __future__ import annotations
import argparse, json, os
from pathlib import Path
from .orchestrator import AgentMedic
from .router import route


def _home() -> Path:
    return Path(os.environ.get("FIELDMEDIC_HOME", str(Path.home() / ".fieldmedic"))).expanduser()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fieldmedic")
    sub = p.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("health", help="check available diagnostic engines")
    h.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    h.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))

    r = sub.add_parser("route", help="deterministically route a symptom")
    r.add_argument("symptom")

    d = sub.add_parser("doctor", help="open a governed diagnostic case")
    d.add_argument("symptom")
    d.add_argument("--case-id")
    d.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    d.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))

    args = p.parse_args(argv)
    agent = AgentMedic(_home())
    if args.cmd == "health":
        result = agent.health(args.drivemedic, args.netmedic)
    elif args.cmd == "route":
        result = route(args.symptom).to_dict()
    else:
        result = agent.doctor(args.symptom, args.drivemedic, args.netmedic, args.case_id)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
