# local-jev

> A local Jev-style decision API for typed yes, choice, and score questions.

**Run the Jev/System One pattern locally, without a hosted model call.**

Jev made a useful idea feel obvious: many agent and workflow decisions do not
need a chat response. They need a typed answer. Is this true? Which option
fits? How severe is it?

local-jev packages that pattern for local machines. It installs a small
runtime, downloads an open GGUF model, and exposes a System One-shaped
`/v1/systemone` API for:

- yes or no decisions (`noul`)
- multiple-choice routing (`choice`)
- ordered ratings (`score`)

It is not official TypeSafe Jev, does not include TypeSafe weights, and is not
endorsed by TypeSafe. It is a practical local approximation of the Jev-style
interface, using llama.cpp and direct next-token logits over declared answer
options. It does not ask a model to write JSON and then parse the text.

The appeal is speed, privacy, and simple integration: install the package, run
setup once, then ask local typed questions over HTTP.

## Why It Is Interesting

Jev-style models are exciting because they turn language-model work into
cheap, structured decisions. That is useful for agents, automation, and
backend services where the desired output is not prose.

local-jev gives you a local version of that workflow:

- Route support tickets without sending text to a hosted API.
- Ask an agent guardrail question before a tool call.
- Classify whether a document matches a declared topic.
- Score urgency, severity, relevance, or policy fit.
- Replace fragile prompt-to-JSON flows with fixed answer options.

It is deliberately small. The default model is good for trying the workflow,
and the larger preset is there when you want better local behavior.

## What It Does

- Downloads a small GGUF model on first setup.
- Creates an isolated runtime venv under `~/.local/share/local-jev`.
- Starts a local HTTP API on `127.0.0.1:8010`.
- Accepts System One-style `POST /v1/systemone` requests.
- Scores declared options directly from model logits instead of generating
  prose or JSON.
- Keeps the installed `.deb` small. Model files are downloaded by
  `local-jev setup`.

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

From a source checkout:

```bash
git clone https://github.com/ra-yavuz/local-jev
cd local-jev
bin/local-jev setup
bin/local-jev serve
```

From a release `.deb`:

```bash
sudo dpkg -i ./local-jev_*.deb
local-jev setup
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

## Relationship To Jev

local-jev is Jev-style, not Jev.

- It follows the typed-decision shape popularized by TypeSafe Jev and System
  One style APIs.
- It uses local open GGUF models, not TypeSafe Jev weights.
- It is meant for experimentation, local tools, and agent-side checks.
- It should be validated before production use, especially in high-impact
  workflows.

## How It Works

local-jev renders each decision as evidence, a criterion, and a short option
list labelled `A` through `P`. It evaluates the prompt with `llama-cpp-python`
and reads the model logits for the allowed answer letters. A softmax over
those letters becomes the option distribution.

This is useful for routing, triage, and relevance checks where the question can
be expressed as a small set of explicit choices.

### What Logits Mean Here

A language model does not begin by writing words. At each position, it produces
one raw score for every token in its vocabulary. Those raw scores are logits.
Higher logits mean the model considers that token more likely as the next
token.

A normal wrapper often does this:

```text
prompt -> model writes text -> parse text into JSON
```

local-jev does this instead:

```text
prompt -> read only the A/B/C option logits -> return structured JSON
```

For a `choice` question with three options, local-jev builds a prompt whose
answer must be `A`, `B`, or `C`. It runs one forward pass, looks only at the
logits for those letters, and applies softmax so the selected scores sum to
1.0. The returned probabilities are the normalized scores for the declared
options.

That is why the model never needs to write output like this:

```json
{"choice": "billing"}
```

It only has to make `A` more likely than `B` or `C` at the answer position.
local-jev maps the winning letter back to your option id.

### Why This Is Useful

Direct option-logit scoring has practical benefits:

- The response shape is controlled by code, not by text parsing.
- The model cannot add an unexpected key, sentence, apology, or markdown block.
- Each question returns an option distribution, not only a final label.
- The local server can answer small decision questions without a hosted API
  call.

It also has limits:

- The probabilities are not automatically calibrated accuracy estimates.
- A general GGUF model was not trained specifically for System One decisions.
- Option wording and option order can affect the result.
- Long or confusing evidence can still make a small model fail.

So local-jev is best understood as a local decision scorer. It is closer to a
Jev-style readout than prompt-to-JSON generation, but it is still using normal
open LLM weights underneath.

## Kev And local-jev

[Kev](https://github.com/jaredpalmer/kev) is an open Jev-like family of
decision models built on Qwen3.5. It includes trained weights, evaluation data,
training code, a playground, and a System One-compatible server. Kev is closer
to the Jev idea because it trains adapters and a decision readout for this
task.

local-jev is smaller and simpler. It does not train a new model. It uses a
regular local GGUF model and reads the answer-letter logits directly. That
makes it easy to install and useful for experimentation, but it should not be
confused with a trained Kev or Jev model.

You can compare both APIs with the helper script:

```bash
# terminal 1: start local-jev
local-jev serve

# terminal 2: clone Kev, install its serving dependencies, and start Kev-0.8B
scripts/try-kev.sh serve

# terminal 3: send the same sample request to both servers
scripts/try-kev.sh compare
```

By default, the script uses Kev on `127.0.0.1:8009` and local-jev on
`127.0.0.1:8010`. Set `KEV_RUN=jaredpalmer/kev-4b` if you want to try the
larger Kev model. In the Debian package, the same helper is installed as
`/usr/share/doc/local-jev/examples/try-kev.sh`.

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
