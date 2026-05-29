#!/usr/bin/env python3
"""Upload flat Markdown docs to TOS, then import them into Viking Knowledge Base.

Required environment variables:
  VOLC_ACCESSKEY
  VOLC_SECRETKEY

Required packages:
  pip install tos volcengine
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


KB_DOMAIN = "api-knowledgebase.mlp.cn-beijing.volces.com"
KB_SIGN_REGION = "cn-north-1"
KB_SIGN_SERVICE = "air"
KB_ADD_PATH = "/api/knowledge/doc/v2/add"


def require_imports():
    try:
        import tos  # noqa: F401
        from volcengine.auth.SignerV4 import SignerV4  # noqa: F401
        from volcengine.base.Request import Request  # noqa: F401
        from volcengine.Credentials import Credentials  # noqa: F401
    except Exception as exc:
        raise SystemExit(
            "Missing dependency. Install with: python3 -m pip install --user tos volcengine\n"
            f"Original error: {type(exc).__name__}: {exc}"
        )


def safe_doc_id(filename: str) -> str:
    stem = Path(filename).stem
    digest = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:10]
    ascii_part = re.sub(r"[^A-Za-z0-9_]+", "_", stem)
    ascii_part = re.sub(r"_+", "_", ascii_part).strip("_")
    if not ascii_part or not re.match(r"[A-Za-z_]", ascii_part):
        ascii_part = "doc"
    value = f"{ascii_part}_{digest}"
    return value[:128]


def iter_markdown_files(source_dir: Path) -> list[Path]:
    files = sorted(
        p for p in source_dir.glob("BSH_*.md")
        if re.match(r"BSH_.*(_index|_F\d{2}_)", p.name)
    )
    if not files:
        raise SystemExit(f"No BSH Markdown files found in {source_dir}")
    return files


def put_to_tos(client, bucket: str, object_key: str, file_path: Path, dry_run: bool) -> None:
    if dry_run:
        return
    client.put_object_from_file(bucket, object_key, str(file_path))


def prepare_kb_request(method: str, path: str, ak: str, sk: str, data: dict):
    from volcengine.auth.SignerV4 import SignerV4
    from volcengine.base.Request import Request
    from volcengine.Credentials import Credentials

    req = Request()
    req.set_shema("https")
    req.set_method(method)
    req.set_host(KB_DOMAIN)
    req.set_path(path)
    req.set_headers({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Host": KB_DOMAIN,
    })
    req.set_body(json.dumps(data, ensure_ascii=False))
    credentials = Credentials(ak, sk, KB_SIGN_SERVICE, KB_SIGN_REGION)
    SignerV4.sign(req, credentials)
    return req


def signed_post(ak: str, sk: str, path: str, data: dict, dry_run: bool) -> dict:
    if dry_run:
        return {"dry_run": True, "request": data}
    req = prepare_kb_request("POST", path, ak, sk, data)
    request = urllib.request.Request(
        f"https://{KB_DOMAIN}{path}",
        headers=req.headers,
        data=req.body.encode("utf-8") if isinstance(req.body, str) else req.body,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {"raw": raw}
    payload["_http_status"] = status
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("/Users/mac/Documents/故障树 v0.1/outputs/bsh-flow-knowledge-flat"),
    )
    parser.add_argument("--bucket", required=True, help="TOS bucket name")
    parser.add_argument("--tos-region", default="cn-beijing")
    parser.add_argument("--tos-endpoint", default="tos-cn-beijing.volces.com")
    parser.add_argument("--tos-prefix", default="bsh-flow-knowledge-flat")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--collection-name")
    target.add_argument("--resource-id")
    parser.add_argument("--project", default="default")
    parser.add_argument("--limit", type=int, default=0, help="Import only first N docs for testing")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between KB add calls")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    ak = os.environ.get("VOLC_ACCESSKEY")
    sk = os.environ.get("VOLC_SECRETKEY")
    if not ak or not sk:
        raise SystemExit("Set VOLC_ACCESSKEY and VOLC_SECRETKEY in the environment first.")

    if args.dry_run:
        tos_client = None
    else:
        require_imports()
        import tos
        tos_client = tos.TosClientV2(ak, sk, args.tos_endpoint, args.tos_region)

    source_dir = args.source_dir.resolve()
    files = iter_markdown_files(source_dir)
    if args.limit:
        files = files[:args.limit]

    results_path = source_dir / "volcengine_import_results.jsonl"
    ok = 0
    failed = 0

    with results_path.open("a", encoding="utf-8") as results:
        for idx, file_path in enumerate(files, start=1):
            object_key = f"{args.tos_prefix.rstrip('/')}/{file_path.name}"
            tos_uri = f"tos://{args.bucket}/{object_key}"
            doc_id = safe_doc_id(file_path.name)
            put_to_tos(tos_client, args.bucket, object_key, file_path, args.dry_run)

            payload = {
                "doc_id": doc_id,
                "doc_name": file_path.name,
                "doc_type": "markdown",
                "uri": tos_uri,
            }
            if args.resource_id:
                payload["resource_id"] = args.resource_id
            else:
                payload["collection_name"] = args.collection_name
                payload["project"] = args.project

            response = signed_post(ak, sk, KB_ADD_PATH, payload, args.dry_run)
            success = bool(
                args.dry_run
                or response.get("code") in (0, "0", None) and response.get("_http_status", 200) < 400
            )
            if success:
                ok += 1
            else:
                failed += 1
            record = {
                "idx": idx,
                "filename": file_path.name,
                "doc_id": doc_id,
                "tos_uri": tos_uri,
                "success": success,
                "response": response,
            }
            results.write(json.dumps(record, ensure_ascii=False) + "\n")
            results.flush()
            print(f"[{idx}/{len(files)}] {'OK' if success else 'FAIL'} {file_path.name}")
            if args.sleep and not args.dry_run:
                time.sleep(args.sleep)

    print(json.dumps({"total": len(files), "ok": ok, "failed": failed, "results": str(results_path)}, ensure_ascii=False))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
