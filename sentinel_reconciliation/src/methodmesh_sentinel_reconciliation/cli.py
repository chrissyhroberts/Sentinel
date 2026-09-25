from __future__ import annotations

import argparse
from pathlib import Path

from .reconcile import reconcile_csv, write_csv, write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile MethodMesh NFC credential evidence against Sentinel study registries.")
    parser.add_argument("--submissions", required=True, help="ODK Central submission CSV export")
    parser.add_argument("--provisioning-devices", required=True, help="Provisioning-device registry CSV")
    parser.add_argument("--issued-credentials", required=True, help="Issued-credential registry CSV")
    parser.add_argument("--out", required=True, help="Derived reconciliation CSV")
    parser.add_argument("--events-jsonl", help="Optional append-oriented reconciliation events JSONL")
    args = parser.parse_args()

    results = reconcile_csv(args.submissions, args.provisioning_devices, args.issued_credentials)
    write_csv(results, args.out)
    if args.events_jsonl:
        write_jsonl(results, args.events_jsonl)

    counts: dict[str, int] = {}
    for result in results:
        counts[result.study_credential_status] = counts.get(result.study_credential_status, 0) + 1
    print(f"Reconciled {len(results)} submission(s).")
    for status in sorted(counts):
        print(f"  {status}: {counts[status]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
