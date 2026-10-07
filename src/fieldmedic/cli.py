from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

from .experiment_runner import GovernedExperimentRunner
from .experiments import (
    create_approval,
    load_json,
    load_proposal,
    propose_experiment,
    save_json,
)
from .local_models import discover_local_models
from .orchestrator import AgentMedic
from .router import route
from .specialists import list_specialists


def _home() -> Path:
    return Path(
        os.environ.get("FIELDMEDIC_HOME", str(Path.home() / ".fieldmedic"))
    ).expanduser()


def _controls(values: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise SystemExit(f"--control requires KEY=VALUE, got: {value}")
        key, item = value.split("=", 1)
        if not key.strip():
            raise SystemExit("--control key may not be empty")
        result[key.strip()] = item
    return result


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
    d.add_argument(
        "--netmedic-case",
        help="existing/local NetMedic case path used only for experiment proposals",
    )
    d.add_argument("--no-model-discovery", action="store_true")
    d.add_argument(
        "--local-reasoning",
        action="store_true",
        help="allow the selected local Ollama model to refine the evidence-cited synthesis",
    )

    ep = sub.add_parser("experiment-propose", help="create an immutable experiment proposal")
    ep.add_argument("--case-id", required=True)
    ep.add_argument("--netmedic-case", required=True)
    ep.add_argument("--name", required=True)
    ep.add_argument("--design-key", required=True)
    ep.add_argument("--arm-a", required=True)
    ep.add_argument("--arm-b", required=True)
    ep.add_argument("--test-label", required=True)
    ep.add_argument("--trials", type=int, default=6)
    ep.add_argument("--window-minutes", type=int, default=5)
    ep.add_argument("--control", action="append")
    ep.add_argument("--evidence-id", action="append", default=[])
    ep.add_argument("--output", default="fieldmedic-experiment-proposal.json")

    ea = sub.add_parser("experiment-approve", help="explicitly approve bounded experiment scopes")
    ea.add_argument("proposal")
    ea.add_argument("--operator", required=True)
    ea.add_argument("--scope", action="append", required=True)
    ea.add_argument("--ttl-minutes", type=int, default=30)
    ea.add_argument("--confirm-arm", action="store_true")
    ea.add_argument("--confirm-machine-stable", action="store_true")
    ea.add_argument("--confirm-test-context", action="store_true")
    ea.add_argument("--confirm-control", action="append", default=[])
    ea.add_argument("--output")

    ef = sub.add_parser("experiment-freeze", help="freeze an approved proposal in NetMedic")
    ef.add_argument("proposal")
    ef.add_argument("approval")
    ef.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"), required=False)

    ec = sub.add_parser("experiment-capture", help="run one approved frozen-protocol capture")
    ec.add_argument("proposal")
    ec.add_argument("approval")
    ec.add_argument("--protocol", required=True)
    ec.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"), required=False)
    ec.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))

    em = sub.add_parser("experiment-matched", help="run approved matched analysis")
    em.add_argument("proposal")
    em.add_argument("approval")
    em.add_argument("--protocol", required=True)
    em.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"), required=False)

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
    elif args.cmd == "doctor":
        result = agent.doctor(
            args.symptom,
            args.drivemedic,
            args.netmedic,
            args.case_id,
            discover_models=not args.no_model_discovery,
            local_reasoning=args.local_reasoning,
            netmedic_case=args.netmedic_case,
        )
    elif args.cmd == "experiment-propose":
        proposal = propose_experiment(
            case_id=args.case_id,
            netmedic_case=args.netmedic_case,
            name=args.name,
            design_key=args.design_key,
            arm_a=args.arm_a,
            arm_b=args.arm_b,
            test_label=args.test_label,
            trials=args.trials,
            window_minutes=args.window_minutes,
            controls=_controls(args.control),
            evidence_ids=args.evidence_id,
        )
        output = Path(args.output)
        save_json(output, proposal.to_dict())
        result = {
            "proposal": proposal.to_dict(),
            "proposal_sha256": proposal.sha256,
            "path": str(output),
            "status": "PROPOSED_NOT_AUTHORIZED",
        }
    elif args.cmd == "experiment-approve":
        proposal_path = Path(args.proposal)
        proposal = load_proposal(proposal_path)
        approval = create_approval(
            proposal,
            operator_label=args.operator,
            scopes=args.scope,
            ttl_minutes=args.ttl_minutes,
            confirmations={
                "arm": args.confirm_arm,
                "machine_stable": args.confirm_machine_stable,
                "test_context": args.confirm_test_context,
                "controls": args.confirm_control,
            },
        )
        output = Path(args.output) if args.output else proposal_path.with_name(
            proposal_path.stem + "-approval.json"
        )
        save_json(output, approval)
        result = {"approval": approval, "path": str(output)}
    else:
        if not args.netmedic:
            raise SystemExit("--netmedic or NETMEDIC_BIN is required")
        proposal = load_proposal(Path(args.proposal))
        approval = load_json(Path(args.approval))
        runner = GovernedExperimentRunner(
            home=_home(),
            drivemedic=getattr(args, "drivemedic", None),
            netmedic=args.netmedic,
        )
        if args.cmd == "experiment-freeze":
            result = runner.freeze(proposal, approval)
        elif args.cmd == "experiment-capture":
            result = runner.capture(
                proposal,
                approval,
                protocol_fingerprint=args.protocol,
            )
        else:
            result = runner.matched(
                proposal,
                approval,
                protocol_fingerprint=args.protocol,
            )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
