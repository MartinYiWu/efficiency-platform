import hashlib
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime

from unit.persistence.test_task_authorization_chain import binding, prepared, reserve

from scripts.authorize_task_continuation import main


def test_cli_preview_is_byte_read_only_and_confirm_idempotent(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "true")
    ledger, prices = prepared(tmp_path)
    result = reserve(ledger, "root", binding())
    ledger.finish(result.reservation_id)
    ledger.stop("root", "test")
    price_file = tmp_path / "prices.json"
    price_file.write_text(json.dumps([asdict(p) for p in prices]), encoding="utf-8")
    expiry = datetime.fromtimestamp(time.time() + 60, UTC).isoformat()
    args = [
        "--task-id",
        "task",
        "--continuation-of",
        "root",
        "--max-total-cost-cny",
        "0.000040",
        "--max-total-http",
        "4",
        "--max-input-tokens",
        "1000",
        "--max-output-tokens",
        "1000",
        "--max-reasoning-tokens",
        "1000",
        "--expires-at",
        expiry,
        "--price-limit-file",
        str(price_file),
    ]
    before = hashlib.sha256(ledger.path.read_bytes()).hexdigest()
    assert main(args, ledger_path=ledger.path) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "preview"
    assert hashlib.sha256(ledger.path.read_bytes()).hexdigest() == before
    assert main([*args, "--confirm"], ledger_path=ledger.path) == 0
    created = json.loads(capsys.readouterr().out)
    assert main([*args, "--confirm"], ledger_path=ledger.path) == 0
    assert json.loads(capsys.readouterr().out) == created
