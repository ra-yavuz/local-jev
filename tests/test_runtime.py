#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "lib" / "local-jev" / "local_jev_runtime.py"


def load_runtime():
    spec = importlib.util.spec_from_file_location("local_jev_runtime", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_softmax():
    runtime = load_runtime()
    values = runtime.softmax([0.0, 0.0])
    assert len(values) == 2
    assert abs(values[0] - 0.5) < 1e-9
    assert abs(values[1] - 0.5) < 1e-9


def test_request_shape():
    runtime = load_runtime()
    rows, specs = runtime.request_to_rows(
        {
            "state": "The sky is blue.",
            "questions": {
                "blue": {
                    "type": "noul",
                    "instructions": "Is the sky blue?",
                },
                "route": {
                    "type": "choice",
                    "instructions": "Pick a route.",
                    "criteria": {"a": "Route A", "b": "Route B"},
                },
            },
        }
    )
    assert len(rows) == 2
    assert specs["blue"][0] == "noul"
    assert specs["route"][0] == "choice"


if __name__ == "__main__":
    test_softmax()
    test_request_shape()
