# callscore · Call quality with a model that doesn't write

*Léelo en [español](README.es.md).*

Every call-center recording comes out catalogued with agent, team, date, quality score, critical failures and KPIs, in a SQLite database that feeds progress per agent and team, coaching sessions ranked by severity and a feedback report between teams. The model, Jev (TypeSafe, via OpenRouter), doesn't write a single word: it only picks between closed options. Code measures, computes the scores and copies every quote from the transcript.

> AI carries risk. Code bounds it. The standard answers for what remains.

**Demo** with artificial calls, declared as such: no data from any real call center.

[Design philosophy](#design-philosophy) · [The five steps](#the-five-steps-in-this-project) · [Try it](#try-it) · [Results](#results) · [Measured](#measured) · [Limitations](#limitations) · [Security & regulation](#security--regulation)

---

## Design philosophy

Every AI application has five steps. Only step 4 invokes a model; the other four are code: reproducible, testable, offline. Step 5 never patches: it flags and degrades. Full text at [epifaneia.dev](https://epifaneia.dev).

```
 1 CLEANING      2 CONTEXT       3 INPUT GUARDRAIL   4 PROCESS        5 OUTPUT GUARDRAIL
 ■ code          ■ code          ■ code              ▲ model          ■ code
```

## The scenario

A quality team listens to a sample of calls by hand and scores them with a form: greeting, verification, listening, solution, closing. They hear few calls, it takes time, and two reviewers don't score alike. The goal is the same thing for every call: each failure with the turn that proves it, KPIs as averages against the service target, and knowing which agent needs a coaching session, and on what.

## Where AI adds value

Reading a conversation and answering closed questions about it: does the agent verify identity? how well does it probe the need, from 0 to 2? which turn shows it best? That is all Jev does. Scores come from a formula, meters (duration, silence, interruptions) come from the audio timings, and every coaching tip is written beforehand in the form, with its source. When Jev isn't sure, the line is flagged as doubtful and goes to review: it counts neither as a failure nor as a pass.

---

## The five steps in this project

★ marks where this project improves on the baseline: a **model that only decides** and an **output guardrail** that checks its decisions against what was measured.

| Step | What it does here | |
|---|---|---|
| 1 · Cleaning | `pipeline/s1_limpieza.py`: stereo audio (agent left, customer right, as a phone system records it) → numbered turns with faster-whisper large-v3-turbo, locally, word by word and per channel. Who speaks comes from the channel, not from a model. Date and agent are recording labels. | |
| 2 · Context | `pipeline/s2_contexto.py`: the team comes from the roster; duration, silence, talk share and interruptions (overlap of 0.3 s or more) come from the timings. The text Jev reads marks the turns that talk over the other speaker, because an overlap doesn't show in text. | |
| 3 · Input guardrail | `pipeline/s3_guardarrail_in.py`: the form (`config/formulario.json`) becomes closed questions: yes/no with explicit criteria, 0-1-2 scales, and for evidence, only the agent's turns as options. No free text. | |
| 4 · Process | `pipeline/s4_proceso.py` and `clients/jev.py`: three Jev passes per call (quality, KPIs, evidence of the failures). The default engine is simulated, offline; spending requires `JEV_MOTOR=openrouter` and has a cumulative cap. | ★ |
| 5 · Output guardrail | `pipeline/s5_guardarrail_out.py`: a decision with probability between 0.35 and 0.65, or with low confidence, is **doubtful**. A doubtful critical failure doesn't zero the call: it sends it to review. Listening judged good with three or more measured interruptions becomes doubtful. The quality score comes from a formula weighted by severity; KPIs are stored as measurements and judged as averages. The quote is the turn's text, copied by code. | ★ |

## Try it

Offline and free, with the simulated engine (it decides at random, so it only tests the plumbing) and the three sample transcripts:

```bash
python -m venv .venv && .venv\Scripts\activate          # on Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                    # CUSTODIA_ACTOR; the OpenRouter key, only here
python run.py                           # → data/prueba/: jev.db, coaching.md, estadistica.html
JEV_MOTOR=seco python run.py            # writes what would be sent to data/peticiones/, without sending it
```

With the real Jev (spends money; cumulative cap in dollars with `JEV_TOPE_USD`, 0.25 by default):

```bash
JEV_MOTOR=openrouter python run.py
python run.py data/voz/*/*_telefono.wav     # from audio: each X.wav with its X.etiquetas.json
```

The full sample, day by day, with voices generated locally (see `requirements-voz.txt`):

```bash
python tools/muestra/avanzar.py --hasta 20     # builds, transcribes and processes the 20 days
python tools/muestra/ejemplos.py               # North Team quotes for the feedback report
python tools/muestra/desvio.py                 # deviation from the design, written into README.es.md
python tools/verificar_citas.py                # checks that every quote in the form is verbatim in its source
```

## Results

The full sample, processed with the real Jev (120 calls, $0.018). The reports are in Spanish:

- [`data/estadistica.html`](data/estadistica.html): weekly progress of the quality score and KPIs per team, each agent against their team's average, and the table of calls, eliminated calls and calls under review per week. A page with no dependencies: download it and open it in a browser.
- [`data/coaching.md`](data/coaching.md): agents ranked by the severity of their failures, each with the tip from the form and the turn that proves it. Doubtful ones are listed apart, pending review.
- [`data/feedback.md`](data/feedback.md): what the North Team does better than the South Team up to the feedback day, line by line, with calls to action (the tip from the form, the North's figure as target, how the North does it and where the South fails, with quotes) and whether the gap closed afterwards.
- [`data/jev.db`](data/jev.db): the SQLite database with calls, quality lines and KPIs.

**Quality per call, KPIs as averages.** A missing verification is a failure with no further context, and a critical failure sets the call to 0. KPIs are different: per call only the measurement is stored, and the average per week, agent and team is judged against the service target. **The best call in the sample is a long one**: profile P03 (complex fault: asks permission before the hold, books a technician with a date, isn't resolved in the call because a technician is needed) scores 10 out of 10 and is the longest in the catalogue. The best calls are the hard ones and need more time; duration is only bad on average.

---

## Where the form comes from

No quality line is made up. Each one quotes the public document it comes from, with section and page, and declares separately what is our own decision (weights, thresholds, what counts as critical). `tools/verificar_citas.py` downloads the originals and checks that every quote is verbatim in its source.

| Source | What it contributes |
|---|---|
| ICA (Colombia), *Protocolo de atención canal telefónico* | The skeleton of the call: greeting, verification, listening, hold, solution with a deadline, closing |
| Lanbide (Basque Government), phone service tender, §6.2 | Indicators: average talk time, resolved calls, satisfaction |
| support-lead-kit (MIT), `scorecards/default.yaml` | The 0-1-2 scale and the idea of a critical failure (auto_fail) |
| Talkdesk, *Call Scoring Evaluation Form Items* | Cross-check by section; reference only, no verbatim quote (all rights reserved) |

Details and links in `config/fuentes.json`.

## The calls are artificial, and it says so

There is no public Spanish call-center audio with a licence that allows publishing it and with known agent, date and failures. So the calls are built, and declared:

- **Scripts** written by hand, with failures planted on purpose (`muestras/guiones/`). Each call carries its labels: date and agent. No model decides who the agent is.
- **Voice** from [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache 2.0), locally. Fixed scheme: one voice for the agent (`ef_dora`) and another for the customer (`em_alex`), always the same.
- **Mix** in stereo, agent left and customer right. Pauses and interruptions come from the script, so they are known truth. Two versions: clean (16 kHz) and phone (8 kHz, 300-3400 Hz band, noise at 25 dB).

## The sample, day by day

120 calls over four weeks, Monday to Friday, one per agent per day, assigned by hand in `diseno/reparto.json` (nothing random). `python tools/muestra/plan.py` expands them into `diseno/plan.json` and `diseno/plan.html`, and checks the design:

- all twelve profiles in the catalogue (`diseno/catalogo.html`) appear, so the sample covers every level;
- the North Team leads in expected score every week (9.0-9.7 against 6.9-9.0);
- the South Team gets feedback on the Friday of week 2 and improves in weeks 3 and 4 in probing, listening, solution and language, the lines where the North was ahead; no other line drops more than 15 points.

`tools/muestra/avanzar.py` processes the next day: it puts the agent's name into the profile's script, generates the audio with Kokoro, runs it through the pipeline from the `.wav` and rebuilds coaching, statistics, feedback and deviation with the data up to that day. `--reiniciar` goes back to day 0. A script turn can carry `pausa`, seconds of silence before it, or `interrumpe`, seconds it overlaps the previous one. Talk share is not designed: each call gets what it needs and it is reported as is.

The North quotes in the feedback report come from `tools/muestra/ejemplos.py`, one more Jev pass: for each line that calls for action, which turn of a North call that meets it shows it best. If Jev sees no clear turn, there is no quote.

---

## Measured

### Transcription

On the three sample calls (371 words), with `tools/voz/medir_wer.py`:

| condition | total WER | word errors (excluding numbers) | turns |
|---|---|---|---|
| clean | 12.7 % | 0.5 % | 29/29 |
| phone | 9.4 % | 0.5 % | 29/29 |

Almost all of the WER is numbers: Whisper writes "4" where the script says "cuatro", and a dictated ID number comes out joined. It counts as an error because that is how it reaches Jev. Duration and interruptions measured from the audio match the mix's truth (±0.3 s); silence comes out 3 to 8 points higher, because it counts the air Kokoro leaves around each sentence. Before choosing Kokoro, Qwen3-TTS 0.6B and Chatterbox Multilingual were tested: 3.8 % and 3.2 % word errors, and both slower than real time on an RTX 2060.

### Jev's deviation from the design

The truth is the design: every call in the sample comes from a catalogue profile that fixes what passes and what fails. That design was written by a large model and reviewed by hand; Jev never sees it. `tools/muestra/desvio.py` compares Jev's decisions with the design and rewrites the table in `README.es.md`; this is a translated copy.

120 calls with a profile · engine: openrouter · mean error in the quality score: 0.37 points out of 10 · critical failures detected: 3 of 3 · critical failures not in the design: 0 eliminated the call, 3 went to review

| line | agreement with the design | disagreements flagged as doubtful | unflagged disagreements |
|---|---|---|---|
| E1 Identity verification | 100 % (120/120) | 0 | 0 |
| E2 Respectful treatment | 100 % (120/120) | 0 | 0 |
| E3 No unauthorised promises | 98 % (117/120) | 3 | 0 |
| G1 Greeting and introduction | 89 % (107/120) | 10 | 3 |
| G2 Probing the need | 90 % (108/120) | 10 | 2 |
| G3 Active listening | 90 % (108/120) | 9 | 3 |
| G4 Empathy | 70 % (84/120) | 5 | 31 |
| G5 Solution and next steps | 99 % (119/120) | 0 | 1 |
| G6 Closing | 99 % (119/120) | 1 | 0 |
| G7 Plain language | 99 % (119/120) | 1 | 0 |
| N1 Hold with permission | 100 % (120/120) | 0 | 0 |
| Resolved (KPI) | 86 % (103/120) | 5 | 12 |
| Satisfaction (KPI) | 90 % (108/120) | 5 | 7 |

Of the three designed critical failures, two eliminate the call (the disrespect and the unauthorised promise) and the third, a missing verification, goes to review because Jev wasn't sure. The three flagged without being in the design are the same sentence in one script ("in 5 minutes you should have the speed you pay for"), which Jev reads as taking for granted something that doesn't depend on the agent: a defensible reading, and it went to review.

**What the first measurement uncovered (day 1, 6 calls).** The first version of E3 asked with a double negative. Jev read as an unauthorised promise exactly what the form asks for, processing a refund with a deadline, confidently eliminated the model call, and the mean score error was 3.01 points. Jev also couldn't see interruptions and passed the listening of an agent who interrupted three times. Guardrails were changed, not results: E3 now asks in positive terms with yes and no criteria, the text marks the turns that talk over the other speaker, and good listening with three measured interruptions becomes doubtful. With the same day rerun, the error fell to 0.43 points.

### Cost

The full sample (120 calls, three passes per call, plus the feedback examples pass): **$0.018**. The custody ledger records it call by call.

---

## Limitations

- **The calls aren't real.** There are 21 hand-written scripts, two fixed synthetic voices and no emotion, accent or office noise. Nothing measured here carries over to real calls as is.
- **The truth is a design, not an independent annotation.** The profiles were written by a large model and reviewed by hand, but nobody else annotated the calls. The deviation measures how far Jev agrees with that design. Where the design is debatable, like the P11 promise Jev reads as a guarantee, there is no third party to decide.
- **The sample is small and repetitive.** There are 120 calls, but they come from 12 profiles and 21 scripts, so Jev reads nearly the same text several times. Agreement has less variety than 120 suggests.
- **The North's lead and the South's improvement are planted.** The statistics and the feedback report show that the pipeline recovers what was designed, not that those patterns exist in a call center.
- **Empathy (G4).** Jev's weak spot: 70 % agreement with the design, and the 31 disagreements it doesn't flag all go the same way, with Jev more generous. It is left measured, not corrected.
- **What is judged from text.** "Resolved" and "satisfied" are estimated by Jev from the transcript, while the Lanbide tender measures satisfaction with surveys. Jev doesn't hear tone: interruptions exist only because code marks the overlaps in the text.
- **Transcription.** Whisper gets numbers wrong and sometimes writes «a Dios» where the agent says «adiós». In three calls the agent channel had to be transcribed without the voice filter because of a known faster-whisper bug, and it is noted in the warnings. Measured silence comes out 3 to 8 points high because of the air Kokoro leaves, which is why the North exceeds the silence target.
- **Quotes are Jev's choice.** The turn it picks as proof isn't always the clearest. For listening it often quotes «Me da el DNI…», the turn that talks over the customer, but the interruption mark isn't stored with the quote, so the report doesn't show it. For plain language it finds no North example, because what is good there is the absence of jargon. Example quotes are lost if the call is reprocessed.
- **The thresholds are ours.** The doubtful band (0.35-0.65), the 15-point gap that calls for action, the listening check at three interruptions and every line's target are design decisions, declared in `config/` or in the code, not standards.
- **Jev changes.** Everything was measured with `typesafe/jev-1.14-20261014` through OpenRouter's alpha decisions API. Another version may give another deviation.
- **No automated tests.** The check is the sample itself: the plan is validated with `plan.py`, the scripts with `guiones.py` and the result with `desvio.py`.

---

## Security & regulation

The same four headings as in every other repository. **Today** rows are what the code does; **next** rows, what is missing.

| | | |
|---|---|---|
| **Confidentiality** | Audio, transcription, meters, scores and reports stay local. The only thing that leaves the machine is the transcript text, to OpenRouter and TypeSafe, and only with `JEV_MOTOR=openrouter`: the default engine is simulated and offline. A request over 30 KB is not sent. `.env`, audio, raw responses and the custody ledger are out of git. | **today** |
| | With real calls, remove ID numbers, phone numbers and customer names in step 1, before the text leaves, and agree with the provider where it is processed. | **next** |
| **Traceability** | Custody ledger per Jev call (`logs/custody.jsonl`): who launched it (`CUSTODIA_ACTOR`, without it nothing runs), step, cost, tokens and served model, never the text. Every raw response is saved in `data/respuestas/`. Every coaching failure carries the call and the turn that prove it. | **today** |
| **Leak prevention** | The key lives only in `.env`. Having it spends nothing: it has to be requested with `JEV_MOTOR=openrouter`, and a cumulative cap (`JEV_TOPE_USD`), summed from the ledger's real cost, stops before overspending. `JEV_MOTOR=seco` shows every request without sending it. | **today** |
| **Human in the loop** | Doubtful decisions don't count: they go to review, and a doubtful critical failure doesn't zero the call. Coaching lists pending reviews apart, and feedback only quotes confident failures. Nothing is silently corrected: changes go into the questions and the guardrails, not the results. | **today** |
| | Evaluating workers' performance is a high-risk use under the AI Act (Annex III, point 4). In real use, no score would affect a person until someone has listened to the call, and the agent could see and contest their evaluation. | **next** |

Written with reference to the EU AI Act (2024/1689), the GDPR and ISO/IEC 27001. No certification or conformity is claimed: the table says which part the code covers and which part belongs to the company.

---

## Structure

```
config/       plantilla.json · formulario.json · kpis.json · fuentes.json
diseno/       catalogo.json/.html · reparto.json · plan.json/.html
pipeline/     s1_limpieza · s2_contexto · s3_guardarrail_in · s4_proceso · s5_guardarrail_out
clients/      jev.py (OpenRouter, dry run and simulated)
base/         db.py (SQLite) · coaching.py · estadistica.py · feedback.py
tools/        verificar_citas.py · voz/ (sintetizar, mezclar, medir_wer) · muestra/ (catalogo, plan, guiones, avanzar, ejemplos, desvio)
kit/          toolkit pieces: custody (identity, ledger), cleaning (text_norm)
muestras/     guiones/ for the twelve profiles · llamadas/ transcribed by hand for testing
data/         sample results: jev.db · coaching.md · feedback.md · estadistica.html
```

The code, configuration and reports are in Spanish.

Daniel Martín · [epifaneia.dev](https://epifaneia.dev) · Apache-2.0
