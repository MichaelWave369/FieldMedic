from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _bool(value: str) -> bool:
    return value.strip().lower() == "true"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--wheel", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--bundle", required=True)
    p.add_argument("--install-root", required=True)
    p.add_argument("--data-root", required=True)
    p.add_argument("--install-receipt-sha256", default="")
    p.add_argument("--discover-pass", required=True)
    p.add_argument("--dashboard-pass", required=True)
    p.add_argument("--release-receipt-pass", required=True)
    p.add_argument("--default-uninstall-pass", required=True)
    p.add_argument("--data-preserved", required=True)
    p.add_argument("--sentinel-preserved", required=True)
    args = p.parse_args()

    sys.path.insert(0, str(Path(args.wheel).resolve()))
    from fieldmedic.install_smoke import write_install_smoke_receipt

    receipt = write_install_smoke_receipt(
        output=Path(args.output),
        bundle=Path(args.bundle),
        install_root=Path(args.install_root),
        data_root=Path(args.data_root),
        install_receipt_sha256=args.install_receipt_sha256,
        discover_pass=_bool(args.discover_pass),
        dashboard_pass=_bool(args.dashboard_pass),
        release_receipt_pass=_bool(args.release_receipt_pass),
        default_uninstall_pass=_bool(args.default_uninstall_pass),
        data_preserved=_bool(args.data_preserved),
        sentinel_preserved=_bool(args.sentinel_preserved),
    )
    print(receipt["status"])
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
