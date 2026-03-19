from __future__ import annotations

import argparse
from pathlib import Path

from naive_fin_data.fetcher import (
    export_a_share_code_list,
    export_hk_code_list,
    fetch_all_a_share,
    fetch_all_hk,
    fetch_single_a_share,
    fetch_single_hk,
)


def _add_common_single_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--type", default="stock", help="target type")
    parser.add_argument("--code", required=True, help="symbol code")
    parser.add_argument("--period", default="1d", help="period: 1m/5m/15m/30m/60m/1d")
    parser.add_argument("--adjust", default="", help="adjust type")
    parser.add_argument("--output-root", default="data", help="data root directory")


def _add_common_full_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--type", default="stock", help="target type")
    parser.add_argument("--period", default="1d", help="period: 1m/5m/15m/30m/60m/1d")
    parser.add_argument("--adjust", default="", help="adjust type")
    parser.add_argument("--output-root", default="data", help="data root directory")
    parser.add_argument("--limit", type=int, default=None, help="optional symbol count cap")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Naive financial data fetcher")
    sub = parser.add_subparsers(dest="command", required=True)

    single_a = sub.add_parser("single-a", help="fetch a single A-share symbol")
    _add_common_single_args(single_a)
    single_a.set_defaults(adjust="qfq")

    full_a = sub.add_parser("full-a", help="fetch all A-share symbols")
    _add_common_full_args(full_a)
    full_a.set_defaults(adjust="qfq")

    single_hk = sub.add_parser("single-hk", help="fetch a single HK symbol")
    _add_common_single_args(single_hk)

    full_hk = sub.add_parser("full-hk", help="fetch all HK symbols")
    _add_common_full_args(full_hk)

    codes_a = sub.add_parser("codes-a", help="export all A-share stock codes")
    codes_a.add_argument("--type", default="stock", help="target type")
    codes_a.add_argument("--output-root", default="data", help="data root directory")

    codes_hk = sub.add_parser("codes-hk", help="export all HK stock codes")
    codes_hk.add_argument("--type", default="stock", help="target type")
    codes_hk.add_argument("--output-root", default="data", help="data root directory")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    output_root = Path(args.output_root)

    if args.command == "single-a":
        output_file = fetch_single_a_share(
            code=args.code,
            period=args.period,
            output_root=output_root,
            adjust=args.adjust,
            type_name=args.type,
            market="cn",
        )
        if output_file is None:
            print(f"no new data for {args.code}")
        else:
            print(f"saved: {output_file}")
        return 0

    if args.command == "single-hk":
        output_file = fetch_single_hk(
            code=args.code,
            period=args.period,
            output_root=output_root,
            adjust=args.adjust,
            type_name=args.type,
            market="hk",
        )
        if output_file is None:
            print(f"no new data for {args.code}")
        else:
            print(f"saved: {output_file}")
        return 0

    if args.command == "codes-a":
        output_file = export_a_share_code_list(
            output_root=output_root,
            type_name=args.type,
            market="cn",
        )
        print(f"saved: {output_file}")
        return 0

    if args.command == "codes-hk":
        output_file = export_hk_code_list(
            output_root=output_root,
            type_name=args.type,
            market="hk",
        )
        print(f"saved: {output_file}")
        return 0

    if args.command == "full-a":
        result = fetch_all_a_share(
            period=args.period,
            output_root=output_root,
            adjust=args.adjust,
            type_name=args.type,
            market="cn",
            limit=args.limit,
        )
    else:
        result = fetch_all_hk(
            period=args.period,
            output_root=output_root,
            adjust=args.adjust,
            type_name=args.type,
            market="hk",
            limit=args.limit,
        )

    print(f"success: {len(result['success'])}")
    print(f"failed: {len(result['failed'])}")
    if result["failed"]:
        print("failed codes:", ",".join(result["failed"][:20]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
