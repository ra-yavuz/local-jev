#!/usr/bin/env python3
"""local-jev runtime and bootstrapper."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any


VERSION = "0.1.0"
LETTERS = "ABCDEFGHIJKLMNOP"
DISCLAIMER = (
    "DISCLAIMER: local-jev is provided AS IS, without warranty. Model output "
    "is unreliable. You accept all risk for installing, running, and acting on "
    "its results."
)
RUNTIME_DEPS = [
    "huggingface-hub==1.31.0",
    "llama-cpp-python==0.3.35",
    "numpy==2.2.6",
]
MODEL_PRESETS = {
    "qwen3-0.6b-q4": {
        "repo": "bartowski/Qwen_Qwen3-0.6B-GGUF",
        "file": "Qwen_Qwen3-0.6B-Q4_K_M.gguf",
        "label": "Qwen3 0.6B Q4_K_M",
    },
    "qwen3.5-4b-q4": {
        "repo": "bartowski/Qwen_Qwen3.5-4B-GGUF",
        "file": "Qwen_Qwen3.5-4B-Q4_K_M.gguf",
        "label": "Qwen3.5 4B Q4_K_M",
    },
}
DEFAULT_PRESET = "qwen3-0.6b-q4"


def data_home(custom: str | None) -> Path:
    if custom:
        return Path(custom).expanduser()
    if os.environ.get("LOCAL_JEV_HOME"):
        return Path(os.environ["LOCAL_JEV_HOME"]).expanduser()
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "local-jev"


def runtime_python(home: Path) -> Path:
    return home / "venv" / "bin" / "python"


def running_in_runtime(home: Path) -> bool:
    return Path(sys.executable).resolve() == runtime_python(home).resolve()


def run_checked(command: list[str], env: dict[str, str] | None = None) -> None:
    shown = " ".join(command)
    print(f"+ {shown}", flush=True)
    subprocess.check_call(command, env=env)


def install_runtime(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    py = runtime_python(home)
    if not py.exists():
        run_checked([sys.executable, "-m", "venv", str(home / "venv")])
    run_checked([str(py), "-m", "pip", "install", "--upgrade", "pip", "wheel"])
    run_checked([str(py), "-m", "pip", "install", *RUNTIME_DEPS])


def ensure_runtime(home: Path, original_argv: list[str], auto_setup: bool) -> None:
    if running_in_runtime(home):
        return
    py = runtime_python(home)
    if not py.exists():
        if not auto_setup:
            raise SystemExit("runtime is missing. Run: local-jev setup")
        print("local-jev runtime is missing, setting it up now.", flush=True)
        install_runtime(home)
    os.execv(str(py), [str(py), __file__, *original_argv])


def model_dir(home: Path, preset: str) -> Path:
    return home / "models" / preset


def model_path(home: Path, preset: str) -> Path:
    spec = MODEL_PRESETS[preset]
    return model_dir(home, preset) / spec["file"]


def download_model(home: Path, preset: str) -> Path:
    if preset not in MODEL_PRESETS:
        raise SystemExit(f"unknown preset: {preset}")
    spec = MODEL_PRESETS[preset]
    target = model_path(home, preset)
    if target.exists():
        print(f"model already present: {target}")
        return target

    from huggingface_hub import hf_hub_download

    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    model_dir(home, preset).mkdir(parents=True, exist_ok=True)
    print(f"downloading {spec['label']} from {spec['repo']}", flush=True)
    path = hf_hub_download(
        repo_id=spec["repo"],
        filename=spec["file"],
        local_dir=str(model_dir(home, preset)),
    )
    print(f"model ready: {path}")
    return Path(path)


def as_text(value: Any) -> str:
    if isinstance(value, str):
        if not value:
            raise ValueError("value must be nonempty")
        return value
    if isinstance(value, (dict, list)) and value:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        raise ValueError("value is required")
    return str(value)


def softmax(values: list[float]) -> list[float]:
    peak = max(values)
    weights = [math.exp(value - peak) for value in values]
    total = sum(weights)
    return [weight / total for weight in weights]


def confidence(probabilities: list[float]) -> float:
    if len(probabilities) == 1:
        return 1.0
    base = 1.0 / len(probabilities)
    return max(0.0, min(1.0, (max(probabilities) - base) / (1.0 - base)))


def render_prompt(row: dict[str, Any]) -> str:
    state = as_text(row["state"])
    options = []
    for index, option in enumerate(row["options"]):
        letter = LETTERS[index]
        options.append(f"{letter}. {as_text(option['description'])}")
    return (
        "You are a local decision model.\n"
        "Choose exactly one listed option. Reply with only its uppercase letter.\n\n"
        f"Evidence:\n{state}\n\n"
        f"Criterion:\n{as_text(row['question'])}\n\n"
        "Options:\n"
        + "\n".join(options)
        + "\n\nAnswer:\n"
    )


class LocalJevModel:
    def __init__(self, path: Path, preset: str, threads: int, ctx: int) -> None:
        from llama_cpp import Llama

        self.path = path
        self.preset = preset
        self.ctx = ctx
        self.lock = threading.Lock()
        self.llm = Llama(
            model_path=str(path),
            n_ctx=ctx,
            n_threads=threads,
            n_gpu_layers=0,
            logits_all=True,
            verbose=False,
        )
        self.answer_tokens = []
        for letter in LETTERS:
            tokens = self.llm.tokenize(letter.encode("utf-8"), add_bos=False, special=True)
            if len(tokens) != 1:
                raise RuntimeError(f"answer slot {letter} is not one token")
            self.answer_tokens.append(tokens[0])

    def score_row(self, row: dict[str, Any]) -> dict[str, Any]:
        import numpy

        if not 2 <= len(row["options"]) <= len(LETTERS):
            raise ValueError("local-jev supports 2 to 16 options")
        prompt = render_prompt(row)
        tokens = self.llm.tokenize(prompt.encode("utf-8"), add_bos=False, special=True)
        if not tokens:
            raise ValueError("empty prompt")
        if len(tokens) > self.ctx:
            raise ValueError(f"input has {len(tokens)} tokens, above context {self.ctx}")
        slots = self.answer_tokens[: len(row["options"])]
        started = time.perf_counter()
        with self.lock:
            self.llm.reset()
            self.llm.eval(tokens)
            logits = numpy.asarray(self.llm.eval_logits[-1], dtype=numpy.float64)
        selected = [float(logits[token]) for token in slots]
        probabilities = softmax(selected)
        return {
            "id": row["id"],
            "option_ids": [option["id"] for option in row["options"]],
            "probabilities": probabilities,
            "option_logits": selected,
            "input_tokens": len(tokens),
            "forward_seconds": time.perf_counter() - started,
            "readout": "last-position GGUF logits restricted to declared answer letters",
        }


def request_to_rows(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, tuple[str, list[str], list[str]]]]:
    questions = payload.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a nonempty object")
    rows = []
    specs = {}
    for qid, question in questions.items():
        if not isinstance(qid, str) or not qid:
            raise ValueError("question ids must be nonempty strings")
        if not isinstance(question, dict):
            raise ValueError(f"{qid}: question must be an object")
        qtype = question.get("type")
        instructions = as_text(question.get("instructions"))
        criteria = question.get("criteria")
        if qtype == "noul":
            labels = ["true", "false"]
            true_desc = "The answer is yes."
            false_desc = "The answer is no."
            if isinstance(criteria, dict):
                true_desc = as_text(criteria.get("true", true_desc))
                false_desc = as_text(criteria.get("false", false_desc))
            descriptions = [true_desc, false_desc]
        elif qtype == "choice":
            if not isinstance(criteria, dict) or not criteria:
                raise ValueError(f"{qid}: choice criteria must be a nonempty object")
            labels = list(criteria.keys())
            descriptions = [
                str(description) if description is not None else str(label)
                for label, description in criteria.items()
            ]
        elif qtype == "score":
            if not isinstance(criteria, list) or len(criteria) < 2:
                raise ValueError(f"{qid}: score criteria must have at least 2 levels")
            labels = [str(index) for index in range(len(criteria))]
            descriptions = [as_text(item) for item in criteria]
        else:
            raise ValueError(f"{qid}: type must be noul, choice, or score")

        if len(labels) == 1:
            specs[qid] = (qtype, labels, descriptions)
            continue
        if not 2 <= len(labels) <= 16:
            raise ValueError(f"{qid}: local-jev supports 2 to 16 options")
        specs[qid] = (qtype, labels, descriptions)
        rows.append(
            {
                "id": qid,
                "state": payload.get("state"),
                "question": instructions,
                "options": [
                    {"id": label, "description": description}
                    for label, description in zip(labels, descriptions)
                ],
            }
        )
    return rows, specs


def answer_from_result(qtype: str, labels: list[str], descriptions: list[str], result: dict[str, Any] | None) -> dict[str, Any]:
    if result is None:
        only = labels[0]
        return {
            "type": "choice",
            "choice": only,
            "confidence": 1.0,
            "probabilities": {only: 1.0},
        }
    option_ids = list(result["option_ids"])
    probabilities = [float(value) for value in result["probabilities"]]
    pairs = dict(zip(option_ids, probabilities))
    if qtype == "noul":
        return {"type": "noul", "noul": pairs["true"]}
    if qtype == "choice":
        return {
            "type": "choice",
            "choice": max(pairs, key=pairs.get),
            "confidence": confidence(probabilities),
            "probabilities": pairs,
        }
    score = sum(int(label) * pairs[label] for label in option_ids)
    return {
        "type": "score",
        "score": score,
        "confidence": confidence(probabilities),
        "legend": {str(index): descriptions[index] for index in range(len(descriptions))},
        "probabilities": pairs,
    }


class Api:
    def __init__(self, model: LocalJevModel) -> None:
        self.model = model

    def systemone(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        rows, specs = request_to_rows(payload)
        results = {row["id"]: self.model.score_row(row) for row in rows}
        answers = {}
        total_input_tokens = 0
        for qid, (qtype, labels, descriptions) in specs.items():
            result = results.get(qid)
            if result is not None:
                total_input_tokens += int(result["input_tokens"])
            answers[qid] = answer_from_result(qtype, labels, descriptions, result)
        output_text = json.dumps(answers, ensure_ascii=False)
        return {
            "model": f"local-jev-{self.model.preset}",
            "answers": answers,
            "usage": {
                "input_tokens": total_input_tokens,
                "output_tokens": len(output_text),
            },
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "backend": {
                "engine": "llama-cpp-python direct logits",
                "preset": self.model.preset,
                "model_path": str(self.model.path),
                "context_tokens": self.model.ctx,
            },
        }


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self.send_json(200, {"status": "ok"})
                return
            if self.path == "/v1/models":
                self.send_json(
                    200,
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": f"local-jev-{api.model.preset}",
                                "object": "model",
                                "owned_by": "local",
                                "backend": "llama-cpp-python",
                                "model_path": str(api.model.path),
                            }
                        ],
                    },
                )
                return
            self.send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/v1/systemone":
                self.send_json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                self.send_json(200, api.systemone(payload))
            except Exception as error:
                self.send_json(422, {"error": str(error)})

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    return Handler


def cmd_setup(args: argparse.Namespace, original_argv: list[str]) -> None:
    home = data_home(args.home)
    print(DISCLAIMER)
    install_runtime(home)
    if not running_in_runtime(home):
        py = runtime_python(home)
        subprocess.check_call([str(py), __file__, "_download", "--home", str(home), "--preset", args.preset])
    else:
        download_model(home, args.preset)


def cmd_download(args: argparse.Namespace) -> None:
    download_model(data_home(args.home), args.preset)


def load_model_for_command(args: argparse.Namespace, original_argv: list[str]) -> LocalJevModel:
    home = data_home(args.home)
    ensure_runtime(home, original_argv, args.auto_setup)
    path = model_path(home, args.preset)
    if not path.exists():
        if not args.auto_setup:
            raise SystemExit("model is missing. Run: local-jev setup")
        download_model(home, args.preset)
    return LocalJevModel(path, args.preset, args.threads, args.ctx)


def cmd_serve(args: argparse.Namespace, original_argv: list[str]) -> None:
    model = load_model_for_command(args, original_argv)
    print(DISCLAIMER, flush=True)
    api = Api(model)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(api))
    print(f"local-jev listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("local-jev stopped.", flush=True)
    finally:
        server.server_close()


def parse_option(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("options must look like id=description")
    key, value = raw.split("=", 1)
    if not key or not value:
        raise argparse.ArgumentTypeError("options must look like id=description")
    return key, value


def cmd_ask(args: argparse.Namespace, original_argv: list[str]) -> None:
    model = load_model_for_command(args, original_argv)
    criteria = dict(args.option)
    payload = {
        "state": args.state,
        "questions": {
            "answer": {
                "type": "choice",
                "instructions": args.question,
                "criteria": criteria,
            }
        },
    }
    print(json.dumps(Api(model).systemone(payload), ensure_ascii=False, indent=2))


def cmd_status(args: argparse.Namespace) -> None:
    home = data_home(args.home)
    rows = {
        "home": str(home),
        "runtime": str(runtime_python(home)),
        "runtime_ready": runtime_python(home).exists(),
        "models": {
            name: {
                "label": spec["label"],
                "path": str(model_path(home, name)),
                "ready": model_path(home, name).exists(),
            }
            for name, spec in MODEL_PRESETS.items()
        },
    }
    print(json.dumps(rows, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="local-jev",
        description="Run a local Jev-shaped decision API over GGUF models.",
        epilog=DISCLAIMER,
    )
    parser.add_argument("--home", help="data directory for runtime venv and models")
    parser.add_argument("--version", action="version", version=f"local-jev {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="install runtime dependencies and download a model", epilog=DISCLAIMER)
    setup.add_argument("--preset", choices=sorted(MODEL_PRESETS), default=DEFAULT_PRESET)
    setup.set_defaults(func=cmd_setup)

    serve = sub.add_parser("serve", help="start the /v1/systemone HTTP API", epilog=DISCLAIMER)
    serve.add_argument("--preset", choices=sorted(MODEL_PRESETS), default=DEFAULT_PRESET)
    serve.add_argument("--host", default=os.environ.get("LOCAL_JEV_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("LOCAL_JEV_PORT", "8010")))
    serve.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    serve.add_argument("--ctx", type=int, default=2048)
    serve.add_argument("--no-auto-setup", dest="auto_setup", action="store_false")
    serve.set_defaults(func=cmd_serve, auto_setup=True)

    ask = sub.add_parser("ask", help="score one local choice question", epilog=DISCLAIMER)
    ask.add_argument("--preset", choices=sorted(MODEL_PRESETS), default=DEFAULT_PRESET)
    ask.add_argument("--state", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--option", type=parse_option, action="append", required=True)
    ask.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    ask.add_argument("--ctx", type=int, default=2048)
    ask.add_argument("--no-auto-setup", dest="auto_setup", action="store_false")
    ask.set_defaults(func=cmd_ask, auto_setup=True)

    status = sub.add_parser("status", help="show runtime and model paths", epilog=DISCLAIMER)
    status.set_defaults(func=lambda args, argv: cmd_status(args))
    return parser


def main(argv: list[str] | None = None) -> None:
    original_argv = list(sys.argv[1:] if argv is None else argv)
    if original_argv and original_argv[0] == "_download":
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--home")
        parser.add_argument("--preset", choices=sorted(MODEL_PRESETS), default=DEFAULT_PRESET)
        cmd_download(parser.parse_args(original_argv[1:]))
        return
    parser = build_parser()
    args = parser.parse_args(original_argv)
    args.func(args, original_argv)


if __name__ == "__main__":
    main()
