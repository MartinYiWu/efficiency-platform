"""离线验收准备；不访问账本、不授权、不执行模型。"""

import argparse
import hashlib
import importlib.util
import json
from dataclasses import asdict
from pathlib import Path

spec = importlib.util.spec_from_file_location("paid_readiness_manage", Path(__file__).with_name("manage.py"))
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)
from efficiency_platform_agent.core.paid_budget import PaidUsage, calculate_paid_cost


def build_report(plan_path, cases_path, account_limit_confirmed=False):
    report = {
        "status": "BLOCKED", "executable": False, "blockers": [],
        "manual_review": ["核验官方价格来源、版本及账户实际消费上限", "逐题核验完整业务链路的最大HTTP尝试数（含重试、Embedding、rerank）", "真实执行需另经用户明确授权；此报告不授予预算"],
    }
    if account_limit_confirmed is not True:
        report["blockers"].append("ACCOUNT_LIMIT_NOT_CONFIRMED")
    plan = None
    try:
        plan, prices = manage.load_plan(Path(plan_path))
        for price in prices:
            worst_cost = max(
                calculate_paid_cost(PaidUsage(price.max_input_tokens, price.max_output_tokens), price),
                calculate_paid_cost(PaidUsage(price.max_input_tokens, price.max_output_tokens, cached_tokens=price.max_input_tokens), price),
            )
            if worst_cost > price.max_cost_microunits_per_attempt:
                raise ValueError("price cap below worst cost")
        report["plan_sha256"] = hashlib.sha256(Path(plan_path).read_bytes()).hexdigest()
        report["limits"] = {key: value for key, value in asdict(plan).items() if key != "budget_id"}
        report["price_versions"] = [{"provider": p.provider, "model": p.model, "pricing_version": p.pricing_version} for p in prices]
    except (ValueError, TypeError, OSError, manage.PaidBudgetError):
        report["blockers"].append("INVALID_PLAN")
        plan = None
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate field")
                result[key] = value
            return result

        cases = json.loads(Path(cases_path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique)
        if not isinstance(cases, list) or not 1 <= len(cases) <= 3:
            raise ValueError("case count")
        keys, questions, safe = set(), set(), []
        for case in cases:
            if not isinstance(case, dict) or set(case) != {"key", "question", "category", "description", "expected_max_attempts"}:
                raise ValueError("case fields")
            if any(not isinstance(case[n], str) or not case[n].strip() for n in ("key", "question", "category", "description")):
                raise ValueError("empty case")
            key, question = case["key"].strip(), " ".join(case["question"].split()).casefold()
            if len(key) > 256 or key in keys or question in questions or case["category"] not in {"公司", "混合", "通用"}:
                raise ValueError("duplicate or invalid category")
            attempts = case["expected_max_attempts"]
            if type(attempts) is not int or not 1 <= attempts <= 2**63 - 1:
                raise ValueError("attempts")
            keys.add(key)
            questions.add(question)
            safe.append({"key": key, "category": case["category"], "expected_max_attempts": attempts})
        report["cases"] = safe
        if plan:
            worst = max(p.max_cost_microunits_per_attempt for p in prices)
            total = sum(c["expected_max_attempts"] for c in cases)
            if total > plan.max_calls or worst * total > plan.max_cost_microunits or any(c["expected_max_attempts"] > plan.max_run_calls or worst * c["expected_max_attempts"] > plan.max_run_cost_microunits for c in cases):
                report["blockers"].append("ATTEMPTS_EXCEED_BUDGET")
            report["declared_attempts"] = total
            report["conservative_cost_microunits"] = worst * total
            input_cap = max(p.max_input_tokens for p in prices)
            output_cap = max(p.max_output_tokens for p in prices)
            reasoning_cap = max((p.max_output_tokens if p.provider == "deepseek" else 0) for p in prices)
            if (input_cap * total > plan.max_input_tokens
                or output_cap * total > plan.max_output_tokens
                or reasoning_cap * total > plan.max_reasoning_tokens
                or any(input_cap * c["expected_max_attempts"] > plan.max_run_input_tokens
                       or output_cap * c["expected_max_attempts"] > plan.max_run_output_tokens
                       or reasoning_cap * c["expected_max_attempts"] > plan.max_run_reasoning_tokens for c in cases)):
                report["blockers"].append("ATTEMPT_TOKENS_EXCEED_BUDGET")
    except (ValueError, TypeError, OSError):
        report["blockers"].append("INVALID_CASES")
    if not report["blockers"]:
        report["status"] = "READY_FOR_REVIEW"
    return report


def write_report(path, report):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--account-limit-confirmed", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_report(args.plan, args.cases, args.account_limit_confirmed)
    try:
        if ".local-acceptance" not in args.out.resolve().parts:
            raise ValueError("local evidence only")
        write_report(args.out, report)
    except (OSError, ValueError):
        print(json.dumps({"error": "REPORT_NOT_WRITTEN", "message": "输出须为.local-acceptance内已存在目录下的新文件。"}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": report["status"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["status"] == "READY_FOR_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
