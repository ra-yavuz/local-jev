# local-jev

**Run a local Jev-shaped decision API over small GGUF models.**

local-jev gives you a tiny local service for typed decisions: yes or no
(`noul`), multiple choice (`choice`), and ordered ratings (`score`). It is
not official TypeSafe Jev, and it does not include any TypeSafe model
weights. It is a practical local wrapper around GGUF models and direct
next-token logits.

The goal is simple: install the package, run setup once, then start a local
`/v1/systemone` API.

## What it does

- Downloads a small GGUF model on first setup.
- Creates an isolated runtime venv under `~/.local/share/local-jev`.
- Starts a local HTTP API on `127.0.0.1:8010`.
- Accepts Kev-style `POST /v1/systemone` requests.
- Scores declared options directly from model logits. It does not generate
  prose.

Default model:

- `qwen3-0.6b-q4`: `bartowski/Qwen_Qwen3-0.6B-GGUF`,
  `Qwen_Qwen3-0.6B-Q4_K_M.gguf`

Optional larger model:

- `qwen3.5-4b-q4`: `bartowski/Qwen_Qwen3.5-4B-GGUF`,
  `Qwen_Qwen3.5-4B-Q4_K_M.gguf`

## Quickstart

```bash
local-jev setup
local-jev serve
```

Then test it:

```bash
curl -s http://127.0.0.1:8010/v1/systemone \
  -H 'content-type: application/json' \
  -d '{
    "state": "Shoes arrived two weeks late and in the wrong size. I also see two charges on my card.",
    "questions": {
      "department": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {
          "returns": "Exchanges, refunds, wrong or damaged items",
          "shipping": "Delivery status, delays, lost packages",
          "billing": "Charges, invoices, payment problems"
        }
      },
      "escalate": {
        "type": "noul",
        "instructions": "Does this need urgent human attention?"
      },
      "frustration": {
        "type": "score",
        "instructions": "How frustrated is the customer?",
        "criteria": ["Calm", "Frustrated", "Very angry"]
      }
    }
  }'
```

One-shot local scoring also works:

```bash
local-jev ask \
  --state "The deployment completed and health checks passed." \
  --question "Did the deployment succeed?" \
  --option yes="The deployment succeeded" \
  --option no="The deployment did not succeed"
```

## <a name="install"></a>Install

From a release `.deb`:

```bash
sudo apt install ./local-jev_*.deb
local-jev setup
```

From the signed apt repository, after this project is published:

```bash
sudo bash -c 'set -e; install -m 0755 -d /etc/apt/keyrings && curl -fsSL https://ra-yavuz.github.io/apt/pubkey.gpg -o /etc/apt/keyrings/ra-yavuz.gpg && echo "deb [signed-by=/etc/apt/keyrings/ra-yavuz.gpg] https://ra-yavuz.github.io/apt stable main" > /etc/apt/sources.list.d/ra-yavuz.list && apt update && apt install -y local-jev'
```

## Commands

```bash
local-jev --help
local-jev setup
local-jev status
local-jev serve --host 127.0.0.1 --port 8010
local-jev ask --state "text" --question "question" --option a="first" --option b="second"
```

Useful environment variables:

| Variable | Meaning |
|---|---|
| `LOCAL_JEV_HOME` | Runtime venv and model directory |
| `LOCAL_JEV_HOST` | Default server host |
| `LOCAL_JEV_PORT` | Default server port |
| `HF_HOME` | Hugging Face cache directory |
| `HF_HUB_DISABLE_XET` | Set to `1` to use plain HTTP downloads |

## API

### `GET /v1/models`

Returns the loaded local model metadata.

### `POST /v1/systemone`

Request:

```json
{
  "state": "text, object, or array",
  "questions": {
    "id": {
      "type": "noul",
      "instructions": "Is this true?",
      "criteria": {
        "true": "The answer is yes.",
        "false": "The answer is no."
      }
    }
  }
}
```

Question types:

| Type | Criteria | Result |
|---|---|---|
| `noul` | optional `true` and `false` descriptions | probability of yes |
| `choice` | object of option id to description | winning option plus probabilities |
| `score` | ordered list of level descriptions | weighted score plus probabilities |

local-jev supports 2 to 16 options per scored question.

## How it works

local-jev renders each decision as evidence, a criterion, and a short option
list labelled `A` through `P`. It evaluates the prompt with `llama-cpp-python`
and reads the model logits for the allowed answer letters. A softmax over
those letters becomes the option distribution.

This is useful for routing, triage, and entity-resolution checks where the
question can be expressed as a small set of explicit choices.

## Limits

- The default model is small and can be overconfident.
- Probabilities are option scores, not measured accuracy.
- Long input can exceed the configured context window.
- A local model can still be wrong, especially on ambiguous or high-stakes
  decisions.
- This project is not official Jev and is not a substitute for validation.

## Disclaimer / no warranty

local-jev downloads and runs third-party model files and uses model output to
score decisions. It is provided **as is, without warranty of any kind**,
express or implied, including but not limited to merchantability, fitness for
a particular purpose, and noninfringement.

By installing or running this software you accept that:

- You alone are responsible for any damage to your hardware, data, network,
  or system.
- You alone are responsible for any decision, workflow, or automation that
  uses local-jev output.
- The author and contributors are **not liable** for any harm, data loss,
  security incident, model output, model download, classification result, or
  other damages, however caused.
- Model output is unreliable. Do not rely on local-jev for safety-critical,
  legal, medical, financial, employment, law-enforcement, or similarly
  sensitive decisions without independent review.
- Third-party models and Hugging Face downloads are outside this project's
  control.

If you do not accept these terms, do not install or run this software.

Full legal license: see [`LICENSE`](LICENSE) (MIT).

## Author

[Ramazan Yavuz](https://ramazan-yavuz.tr). Part of a set of independent,
open-source tools published at [ra-yavuz.github.io](https://ra-yavuz.github.io/).
