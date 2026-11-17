"""跨语言fixture先用本机socket自检，不访问外部模型。"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest


@pytest.fixture(scope="module")
def fixture_server(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    work = tmp_path_factory.mktemp("business-budget")
    log = (work / "agent.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).with_name("paid_budget_agent_fixture.py")),
            "--port",
            str(port),
            "--workdir",
            str(work),
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        stdout=log,
        stderr=log,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=20, trust_env=False
        ) as client:
            for _ in range(150):
                if process.poll() is not None:
                    raise AssertionError(
                        (work / "agent.log").read_text(encoding="utf-8")
                    )
                try:
                    if client.get("/health/ready").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("fixture startup timeout")
            yield client
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()


def request(client, scenario):
    conv = str(uuid4())
    r = client.post(
        f"/{scenario}/v1/customer-service/conversations/{conv}/messages",
        json={
            "contract_version": "customer-service-run/1",
            "request_id": uuid4().hex,
            "conversation_id": conv,
            "tenant_id": "dev",
            "user_id": "synthetic",
            "agent_release_id": "00000000-0000-0000-0000-000000000001",
            "message": "synthetic question",
            "history": [],
        },
    )
    r.raise_for_status()
    run = r.json()["run_id"]
    events = []
    with client.stream(
        "GET", f"/{scenario}/v1/customer-service/runs/{run}/events"
    ) as stream:
        for line in stream.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


@pytest.mark.parametrize(
    "scenario,terminal,attempts",
    [
        ("success", "answer.completed", 2),
        ("exhaust", "run.failed", 1),
        ("tokens", "run.failed", 1),
        ("money", "run.failed", 1),
        ("retry", "answer.completed", 3),
        ("unauthorized", "run.failed", 0),
    ],
)
def test_fixture_actual_loopback_budget_chain(
    fixture_server, scenario, terminal, attempts
):
    events = request(fixture_server, scenario)
    assert events[-1]["event_type"] == terminal
    data = fixture_server.get("/test/observations/" + scenario).json()
    assert data["upstream_requests"] == attempts
    assert data["snapshot"].get("calls", 0) == attempts
    if terminal == "run.failed":
        assert events[-1]["payload"]["error_code"] in [
            "BUDGET_EXHAUSTED",
            "RUN_EXHAUSTED",
            "NO_BUDGET",
        ]
    else:
        assert data["snapshot"]["accounting"]["actual_cost_microunits"] == 2
