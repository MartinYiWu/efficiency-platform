"""精确范围的试用证据采集；默认仅 GET，原文只落被 Git 忽略目录。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import quote

import httpx

CATEGORIES = ("事实错误", "引用错误", "遗漏", "延迟")
ANSWER_MODES = ("COMPANY_KNOWLEDGE", "MIXED", "GENERAL_ADVICE", "INSUFFICIENT_EVIDENCE")


def validate_case(case):
    for key in ("caseNo", "question"):
        if not isinstance(case.get(key), str) or not case[key].strip():
            raise ValueError("题号和问题必须是非空字符串")
    if case.get("expectedAnswerMode") not in ANSWER_MODES:
        raise ValueError("期望回答模式无效")
    for key in ("expectedFacts", "prohibitedFacts", "expectedDocumentTitles", "expectedDocumentVersionIds", "tags"):
        values = case.get(key)
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError("评测数组必须只含非空字符串")
    if not case["expectedFacts"]:
        raise ValueError("期望事实不能为空")
    count = case.get("minCitationCount")
    if type(count) is not int or count < 0:
        raise ValueError("最少引用数必须是非负整数")


def private_path(path):
    path = path.resolve()
    result = subprocess.run(["git", "check-ignore", "--quiet", str(path)], capture_output=True)
    if result.returncode != 0 or ".local-acceptance" not in path.parts:
        raise ValueError("原文及人工标注必须位于被 Git 忽略的 .local-acceptance 目录")
    return path


def read(path):
    return json.loads(private_path(Path(path)).read_text(encoding="utf-8"))


def save(path, data):
    path = private_path(Path(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def data(response):
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") not in (None, "SUCCESS"):
        raise ValueError("业务 API 返回失败状态")
    return payload["data"]


def collect(client, run_ids, feedback_ids, page_size=100):
    run_ids = list(dict.fromkeys(run_ids))
    if not run_ids:
        raise ValueError("必须精确指定 Run ID")
    wanted = set(feedback_ids)
    found = {}
    # API 无 runId 过滤器；逐页仅在内存检查，未选反馈不落盘。
    page = 1
    while wanted and not wanted.issubset(found):
        payload = data(client.get("/api/aihub/feedback", params={"page": page, "pageSize": page_size}))
        for item in payload["items"]:
            if item["id"] in wanted:
                if item["runId"] not in run_ids:
                    raise ValueError("指定反馈不属于指定 Run")
                found[item["id"]] = item
        if page * page_size >= payload["total"] or not payload["items"]:
            break
        page += 1
    if wanted - found.keys():
        raise ValueError("指定反馈未全部找到；不生成不完整证据")
    replays = []
    for run_id in run_ids:
        replay = data(client.get(f"/api/aihub/runs/{quote(run_id, safe='')}/replay"))
        if replay["run"]["id"] != run_id:
            raise ValueError("回放 Run ID 不匹配")
        # replay 内嵌反馈也必须受精确 ID 范围限制。
        replay["feedback"] = found.get((replay.get("feedback") or {}).get("id"))
        replays.append(replay)
    return {"schemaVersion": 1, "collectedAt": datetime.now(timezone.utc).isoformat(),
            "feedback": list(found.values()), "replays": replays}


def frozen(replay):
    return {"agentReleaseId": replay["run"].get("agentReleaseId"),
            "citations": [{key: c.get(key) for key in ("documentId", "documentVersionId", "indexReleaseId", "chunkId", "contentHash")} for c in replay.get("citations", [])]}


def review(raw):
    items = []
    for replay in raw["replays"]:
        run = replay["run"]
        duration = None
        if run.get("startedAt") and run.get("finishedAt"):
            duration = int((datetime.fromisoformat(run["finishedAt"].replace("Z", "+00:00")) - datetime.fromisoformat(run["startedAt"].replace("Z", "+00:00"))).total_seconds() * 1000)
        items.append({"runId": run["id"], "status": run.get("status"), "failureCode": run.get("failureCode"), "frozen": frozen(replay),
                      "feedback": [{key: f.get(key) for key in ("id", "rating", "reasonCode")} for f in raw["feedback"] if f["runId"] == run["id"]],
                      "totalDurationMs": duration, "ttftMs": None,
                      "latencySource": "persisted run timestamps; historical replay cannot establish SSE TTFT",
                      "humanReview": {category: "待人工审阅" for category in CATEGORIES}})
    return {"cohort": raw.get("cohort", "unconfirmed"), "confirmedEmployeeCount": raw.get("confirmedEmployeeCount", 0),
            "participationStatus": "仅采集证据，不代表员工完成试用", "items": items}


def export_cases(raw, annotations):
    replays = {r["run"]["id"]: r for r in raw["replays"]}
    cases, sources = [], []
    seen = set()
    for a in annotations:
        if a.get("approved") is not True or not a.get("reviewer") or a.get("category") not in CATEGORIES:
            raise ValueError("每题须人工批准、审阅人及有效分类")
        rid = a["runId"]
        if rid in seen:
            raise ValueError("同一 Run 请合并人工标注，禁止重复导入")
        seen.add(rid)
        replay = replays[rid]
        source = frozen(replay)
        if not source["agentReleaseId"] or any(not c.get("documentVersionId") or not c.get("indexReleaseId") or not c.get("contentHash") for c in source["citations"]):
            raise ValueError("来源缺少冻结发布/文档/索引/内容哈希")
        versions = {c["documentVersionId"] for c in source["citations"]}
        expected_versions = a.get("expectedDocumentVersionIds", [])
        if not set(expected_versions).issubset(versions):
            raise ValueError("期望文档版本不在已采集证据中")
        if not a.get("question") or not a.get("expectedFacts") or a.get("expectedAnswerMode") not in ANSWER_MODES:
            raise ValueError("须提供人工脱敏问题、期望事实及回答模式")
        case_no = "pilot-" + hashlib.sha256(rid.encode()).hexdigest()[:16]
        cases.append({"caseNo": case_no, "question": a["question"], "expectedAnswerMode": a["expectedAnswerMode"],
                      "expectedFacts": a["expectedFacts"], "prohibitedFacts": a.get("prohibitedFacts", []),
                      "expectedDocumentTitles": [], "expectedDocumentVersionIds": expected_versions,
                      "minCitationCount": a.get("minCitationCount", len(expected_versions)),
                      "tags": ["pilot", raw.get("cohort", "unconfirmed"), a["category"], "run:" + rid, "release:" + source["agentReleaseId"]], "enabled": True})
        validate_case(cases[-1])
        sources.append({"caseNo": case_no, "runId": rid, "feedbackIds": [f["id"] for f in raw["feedback"] if f["runId"] == rid],
                        "reviewer": a["reviewer"], "category": a["category"], "frozen": source,
                        "reviewNote": a.get("reviewNote"), "sourceDocuments": a.get("sourceDocuments", [])})
    if not cases:
        raise ValueError("没有人工批准的评测题")
    return {"schemaVersion": 1, "cohort": raw.get("cohort", "unconfirmed"), "cases": cases, "sources": sources,
            "sourceSha256": hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()}


def import_cases(client, bundle, name, confirm_write):
    if not confirm_write:
        raise ValueError("写入必须显式指定 --confirm-write")
    if not name.startswith("pilot-") or not bundle.get("cases") or len(bundle["cases"]) != len(bundle.get("sources", [])) or not bundle.get("sourceSha256"):
        raise ValueError("必须使用 pilot- 前缀新独立集且保留完整来源")
    for case in bundle["cases"]:
        validate_case(case)
    existing = data(client.get("/api/aihub/rag-evaluations/datasets"))
    if any(item["name"] == name for item in existing):
        raise ValueError("目标名称已存在；禁止向已有评测集写入")
    dataset = data(client.post("/api/aihub/rag-evaluations/datasets", json={"name": name,
        "description": "人工批准的独立试用回归集；sourceSha256=" + bundle["sourceSha256"], "agentKey": "customer-service", "status": "DRAFT"}))
    # 分两步写入；失败保留新建集供人工检查，绝不删除业务数据。
    result = data(client.post(f"/api/aihub/rag-evaluations/datasets/{quote(dataset['id'], safe='')}/cases/import", json=bundle["cases"]))
    return {"datasetId": dataset["id"], "result": result, "sourceSha256": bundle["sourceSha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("collect")
    c.add_argument("--run-id", action="append", required=True)
    c.add_argument("--feedback-id", action="append", default=[])
    c.add_argument("--cohort", choices=("developer", "employee", "unconfirmed"), default="unconfirmed")
    c.add_argument("--confirmed-employee-count", type=int, default=0)
    c.add_argument("--page-size", type=int, default=100)
    c.add_argument("--out", required=True)
    for name in ("review", "export", "import"):
        sub = commands.add_parser(name)
        sub.add_argument("--input", required=True)
        sub.add_argument("--out", required=True)
        if name == "export":
            sub.add_argument("--annotations", required=True)
        if name == "import":
            sub.add_argument("--dataset-name", required=True)
            sub.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args()
    private_path(Path(args.out))
    if Path(args.out).exists():
        raise ValueError("输出已存在，拒绝覆盖")
    # 凭据只从环境读取，错误不打印响应正文或请求头。
    headers = {"Authorization": os.environ["PILOT_AUTHORIZATION"]} if os.environ.get("PILOT_AUTHORIZATION") else {}
    with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=30, follow_redirects=False) as client:
        if args.command == "collect":
            if not 1 <= args.page_size <= 100 or args.confirmed_employee_count < 0 or (args.cohort != "employee" and args.confirmed_employee_count):
                raise ValueError("分页大小或员工人数与分组不一致")
            result = collect(client, args.run_id, args.feedback_id, args.page_size)
            result.update(cohort=args.cohort, confirmedEmployeeCount=args.confirmed_employee_count)
        elif args.command == "review":
            result = review(read(args.input))
        elif args.command == "export":
            result = export_cases(read(args.input), read(args.annotations))
        else:
            result = import_cases(client, read(args.input), args.dataset_name, args.confirm_write)
        save(args.out, result)
    print("完成；证据已保存，未输出原文或凭据。")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, httpx.HTTPError) as error:
        # HTTP 异常可能包含敏感 URL，不打印原始异常。
        raise SystemExit("失败：" + (str(error) if isinstance(error, ValueError) else type(error).__name__)) from None
