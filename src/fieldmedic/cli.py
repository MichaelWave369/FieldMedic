from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

from .case_portable import export_case, import_case
from .dashboard import write_dashboard
from .discovery import discover_engines
from .envelope import wrap_evidence
from .experiment_runner import GovernedExperimentRunner
from .experiments import (
    create_approval,
    load_json,
    load_proposal,
    propose_experiment,
    save_json,
)
from .installation import write_install_receipt
from .ledger import EvidenceLedger
from .local_models import discover_local_models
from .models import ClaimClass, Source
from .nbg_memory import (
    DiagnosticMemoryStore,
    VERIFIED_OUTCOMES,
    case_to_inferred_memory,
    derive_verified_outcome,
)
from .orchestrator import AgentMedic
from .repair_executors import get_executor, list_repair_actions
from .repair_governance import (
    create_repair_grant,
    load_json as load_repair_json,
    load_proposal as load_repair_proposal,
    prepare_repair,
    propose_repair,
    save_json as save_repair_json,
)
from .repair_runner import RepairRunner
from .release_receipt import build_release_receipt
from .router import route
from .settings import default_home, load_engine_config, write_engine_config
from .specialists import list_specialists
from .windows_bundle import build_windows_bundle
from .windows_qualification import run_windows_repair_qualification


def _home() -> Path:
    return default_home()


def _memory_store() -> DiagnosticMemoryStore:
    return DiagnosticMemoryStore(_home() / "memory" / "nbg")


def _case_dir(case_id: str) -> Path:
    return _home() / "cases" / case_id


def _load_case(case_id: str) -> dict:
    path = _case_dir(case_id) / "case.json"
    if not path.exists():
        raise SystemExit(f"FieldMedic case not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"FieldMedic case root must be an object: {path}")
    return value


def _key_values(values: list[str] | None, *, flag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise SystemExit(f"{flag} requires KEY=VALUE, got: {value}")
        key, item = value.split("=", 1)
        if not key.strip():
            raise SystemExit(f"{flag} key may not be empty")
        result[key.strip()] = item
    return result


def _controls(values: list[str] | None) -> dict[str, str]:
    return _key_values(values, flag="--control")


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

    disc = sub.add_parser("discover", help="discover and probe DriveMedic + NetMedic")
    disc.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    disc.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))

    cfg = sub.add_parser(
        "configure-engines",
        help="store hash-bound local DriveMedic / NetMedic paths for discovery",
    )
    cfg.add_argument("--drivemedic")
    cfg.add_argument("--netmedic")
    sub.add_parser("engine-config", help="show local engine discovery handoff config")

    ir = sub.add_parser(
        "installation-receipt",
        help="write the current Windows installation handoff receipt",
    )
    ir.add_argument("--install-root", required=True)
    ir.add_argument("--runtime-root", required=True)
    ir.add_argument("--wheel", required=True)
    ir.add_argument("--launcher", required=True)
    ir.add_argument("--dashboard-launcher", required=True)
    ir.add_argument("--uninstaller", required=True)
    ir.add_argument("--path-added", action="store_true")
    ir.add_argument("--output")

    wb = sub.add_parser(
        "build-windows-bundle",
        help="build a deterministic FieldMedic-only Windows release bundle",
    )
    wb.add_argument("--wheel", required=True)
    wb.add_argument("--repository-root", default=".")
    wb.add_argument("--output", required=True)

    ce = sub.add_parser("case-export", help="export one portable hash-attested case bundle")
    ce.add_argument("case_id")
    ce.add_argument("output")

    ci = sub.add_parser("case-import", help="import one portable case bundle without overwrite")
    ci.add_argument("bundle")

    dash = sub.add_parser("dashboard", help="write the read-only operator dashboard")
    dash.add_argument("--output", default="fieldmedic-dashboard.html")
    dash.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    dash.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))

    rr = sub.add_parser("release-receipt", help="write a local product/release receipt")
    rr.add_argument("--output", default="fieldmedic-release-receipt.json")
    rr.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    rr.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))

    wq = sub.add_parser(
        "qualify-windows-repairs",
        help="run live apply/measure/rollback qualification for both Windows repair executors",
    )
    wq.add_argument("--interface-index", required=True, type=int)
    wq.add_argument(
        "--address-family",
        default="IPv4",
        choices=["IPv4", "IPv6"],
    )
    wq.add_argument("--temporary-metric", required=True, type=int)
    wq.add_argument("--operator", required=True)
    wq.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    wq.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))

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

    ma = sub.add_parser("memory-admit", help="admit a case candidate into durable NBG memory")
    ma.add_argument("case_id")
    ma.add_argument("--operator", required=True)
    ma.add_argument("--reason", default="retain diagnostic case")

    mv = sub.add_parser("memory-verify", help="derive a verified outcome from an admitted case memory")
    mv.add_argument("case_id")
    mv.add_argument("--operator", required=True)
    mv.add_argument("--outcome", required=True, choices=sorted(VERIFIED_OUTCOMES))
    mv.add_argument("--details")
    mv.add_argument("--memory-id")

    mq = sub.add_parser("memory-query", help="query diagnostic memory without a model")
    mq.add_argument("symptom")
    mq.add_argument("--domain", default="unknown")
    mq.add_argument("--specialist", action="append", default=[])
    mq.add_argument("--limit", type=int, default=5)

    sub.add_parser("memory-stats", help="summarize the local NBG diagnostic store")

    sub.add_parser(
        "repair-actions",
        help="list the fixed registry of executable bounded repairs",
    )

    rp = sub.add_parser(
        "repair-propose",
        help="create a typed repair proposal from an evidence-backed case",
    )
    rp.add_argument("case_id")
    rp.add_argument(
        "--action",
        required=True,
        choices=[item["action_key"] for item in list_repair_actions()],
    )
    rp.add_argument("--param", action="append", required=True)
    rp.add_argument("--output")

    rprep = sub.add_parser(
        "repair-prepare",
        help="capture target pre-state and exact rollback state",
    )
    rprep.add_argument("proposal")
    rprep.add_argument("--ttl-minutes", type=int, default=10)
    rprep.add_argument("--output")

    rauth = sub.add_parser(
        "repair-authorize",
        help="bind explicit operator authority to one proposal + preflight",
    )
    rauth.add_argument("proposal")
    rauth.add_argument("preflight")
    rauth.add_argument("--operator", required=True)
    rauth.add_argument("--ttl-minutes", type=int, default=15)
    rauth.add_argument("--output")

    rexec = sub.add_parser(
        "repair-execute",
        help="execute one exact bounded repair transaction",
    )
    rexec.add_argument("proposal")
    rexec.add_argument("preflight")
    rexec.add_argument("grant")
    rexec.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    rexec.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))

    rverify = sub.add_parser(
        "repair-verify",
        help="capture independent post-action outcome measurements",
    )
    rverify.add_argument("execution")
    rverify.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    rverify.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))

    rrollback = sub.add_parser(
        "repair-rollback",
        help="restore the exact captured pre-repair target state",
    )
    rrollback.add_argument("execution")
    rrollback.add_argument("--drivemedic", default=os.environ.get("DRIVEMEDIC_BIN"))
    rrollback.add_argument("--netmedic", default=os.environ.get("NETMEDIC_BIN"))

    args = p.parse_args(argv)
    agent = AgentMedic(_home(), brainc_binary=args.brainc)
    exit_code = 0

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
    elif args.cmd == "discover":
        result = discover_engines(
            drivemedic=args.drivemedic,
            netmedic=args.netmedic,
            home=_home(),
        )
    elif args.cmd == "configure-engines":
        result = write_engine_config(
            home=_home(),
            drivemedic=args.drivemedic,
            netmedic=args.netmedic,
        )
    elif args.cmd == "engine-config":
        result = load_engine_config(_home())
    elif args.cmd == "installation-receipt":
        output = (
            Path(args.output)
            if args.output
            else _home() / "installation" / "install.json"
        )
        receipt = write_install_receipt(
            output,
            home=_home(),
            install_root=Path(args.install_root),
            runtime_root=Path(args.runtime_root),
            wheel=Path(args.wheel),
            launcher=Path(args.launcher),
            dashboard_launcher=Path(args.dashboard_launcher),
            uninstaller=Path(args.uninstaller),
            path_added=args.path_added,
        )
        result = {
            "path": str(output),
            "receipt": receipt,
        }
    elif args.cmd == "build-windows-bundle":
        result = build_windows_bundle(
            wheel=Path(args.wheel),
            repository_root=Path(args.repository_root),
            output=Path(args.output),
        )
    elif args.cmd == "case-export":
        result = export_case(
            _case_dir(args.case_id),
            Path(args.output),
        )
    elif args.cmd == "case-import":
        result = import_case(
            Path(args.bundle),
            _home() / "cases",
        )
    elif args.cmd == "dashboard":
        result = write_dashboard(
            Path(args.output),
            home=_home(),
            drivemedic=args.drivemedic,
            netmedic=args.netmedic,
        )
    elif args.cmd == "release-receipt":
        receipt = build_release_receipt(
            home=_home(),
            drivemedic=args.drivemedic,
            netmedic=args.netmedic,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        result = {
            "path": str(output),
            "receipt": receipt,
        }
    elif args.cmd == "qualify-windows-repairs":
        result = run_windows_repair_qualification(
            home=_home(),
            drivemedic=args.drivemedic,
            netmedic=args.netmedic,
            interface_index=args.interface_index,
            address_family=args.address_family,
            temporary_metric=args.temporary_metric,
            operator_label=args.operator,
        )
        if result.get("status") != "PASS":
            exit_code = 2
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
    elif args.cmd == "memory-admit":
        case = _load_case(args.case_id)
        candidate_path = _case_dir(args.case_id) / "nbg-candidate.json"
        if candidate_path.exists():
            candidate_doc = json.loads(candidate_path.read_text(encoding="utf-8"))
            memory = candidate_doc.get("memory") if isinstance(candidate_doc, dict) else None
        else:
            memory = None
        if not isinstance(memory, dict):
            memory = case_to_inferred_memory(case)
        admission = _memory_store().admit(
            memory,
            operator_label=args.operator,
            reason=args.reason,
            case_id=args.case_id,
        )
        result = {
            "memory": memory,
            "admission": admission,
            "store": str(_memory_store().root),
        }
    elif args.cmd == "memory-verify":
        store = _memory_store()
        memory_id = args.memory_id or f"fieldmedic:{args.case_id}:inferred"
        source_memory = store.get(memory_id)
        if source_memory is None:
            raise SystemExit(
                f"source memory is not admitted: {memory_id}; run memory-admit first"
            )
        verification = wrap_evidence(
            case_id=args.case_id,
            source=Source.OPERATOR,
            category="memory.outcome-verification",
            summary=f"Operator verified diagnostic outcome: {args.outcome}",
            payload={
                "outcome": args.outcome,
                "details": args.details,
                "operator_label": args.operator,
                "operator_label_semantics": (
                    "local operator label; not independently verified identity"
                ),
            },
            claim_class=ClaimClass.VERIFICATION,
            provenance={
                "method": "explicit-operator-verification",
                "source_memory_id": memory_id,
            },
        )
        EvidenceLedger(_case_dir(args.case_id) / "evidence.jsonl").append(verification)
        derived, transition = derive_verified_outcome(
            source_memory,
            outcome=args.outcome,
            verification_evidence_id=verification.evidence_id,
            details=args.details,
            source="fieldmedic-explicit-operator-verification",
            known_time=verification.ingested_at,
        )
        admission = store.admit(
            derived,
            operator_label=args.operator,
            reason=f"retain verified diagnostic outcome {args.outcome}",
            case_id=args.case_id,
        )
        store.append_transition(transition)
        result = {
            "verification_evidence": verification.to_dict(),
            "derived_memory": derived,
            "transition": transition,
            "admission": admission,
        }
    elif args.cmd == "memory-query":
        result = _memory_store().routing_hints(
            symptom=args.symptom,
            domain=args.domain,
            specialist_ids=args.specialist,
            limit=args.limit,
        )
    elif args.cmd == "memory-stats":
        result = _memory_store().stats()
    elif args.cmd == "repair-actions":
        result = {"actions": list_repair_actions()}
    elif args.cmd == "repair-propose":
        case = _load_case(args.case_id)
        proposal = propose_repair(
            case,
            action_key=args.action,
            params=_key_values(args.param, flag="--param"),
        )
        output = (
            Path(args.output)
            if args.output
            else _case_dir(args.case_id)
            / "repairs"
            / proposal.proposal_id
            / "proposal.json"
        )
        save_repair_json(output, proposal.to_dict())
        result = {
            "proposal": proposal.to_dict(),
            "proposal_sha256": proposal.sha256,
            "path": str(output),
            "status": "PROPOSED_NOT_AUTHORIZED",
        }
    elif args.cmd == "repair-prepare":
        proposal_path = Path(args.proposal)
        proposal = load_repair_proposal(proposal_path)
        preflight = prepare_repair(
            proposal,
            executor=get_executor(proposal.action_key),
            ttl_minutes=args.ttl_minutes,
        )
        output = (
            Path(args.output)
            if args.output
            else proposal_path.with_name("preflight.json")
        )
        save_repair_json(output, preflight)
        result = {"preflight": preflight, "path": str(output)}
    elif args.cmd == "repair-authorize":
        proposal_path = Path(args.proposal)
        proposal = load_repair_proposal(proposal_path)
        preflight = load_repair_json(Path(args.preflight))
        grant = create_repair_grant(
            proposal,
            preflight,
            operator_label=args.operator,
            ttl_minutes=args.ttl_minutes,
        )
        output = (
            Path(args.output)
            if args.output
            else proposal_path.with_name("grant.json")
        )
        save_repair_json(output, grant)
        result = {"grant": grant, "path": str(output)}
    elif args.cmd in {"repair-execute", "repair-verify", "repair-rollback"}:
        if not args.drivemedic or not args.netmedic:
            raise SystemExit(
                "--drivemedic/DRIVEMEDIC_BIN and --netmedic/NETMEDIC_BIN "
                "are required for bounded repair verification"
            )
        runner = RepairRunner(
            home=_home(),
            drivemedic=args.drivemedic,
            netmedic=args.netmedic,
        )
        if args.cmd == "repair-execute":
            proposal = load_repair_proposal(Path(args.proposal))
            preflight = load_repair_json(Path(args.preflight))
            grant = load_repair_json(Path(args.grant))
            result = runner.execute(proposal, preflight, grant)
        elif args.cmd == "repair-verify":
            result = runner.verify(load_repair_json(Path(args.execution)))
        else:
            result = runner.rollback(load_repair_json(Path(args.execution)))
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
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
