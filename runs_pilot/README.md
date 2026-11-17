# 🗂️ Pilot 1 data: six complete runs

This folder holds **everything that happened** in the first pilot of the [Island Survival Experiment](../README.md): every turn, private thought, spoken line, whisper, nightly diary, trust rating, interview and memory of all 5 agents, in all 6 runs.

[`../runs_pilot.zip`](../runs_pilot.zip) holds the same folder as one download. It was made with Windows `Compress-Archive`, so some unzip tools on macOS or Linux show backslashes in the file names; Windows Explorer and 7-Zip open it normally.

> [!IMPORTANT]
> These are **pilot runs (seeds 101–103) and are excluded from the final analysis.** The pilot found that agents misread several rules (an injury that seemed never to heal, an ambiguous eating rule, and giving that cost a whole turn). The behaviour below therefore describes the rules as written, not just the personalities. See the [pilot report](../docs/Pilot-Report.pdf) and the [project status](../README.md#-project-status).

**Contents:** [The six runs](#the-six-runs) · [Run by run](#run-by-run) · [Across all runs](#across-all-runs) · [Every gift](#every-gift-in-the-pilot) · [How to read the files](#how-to-read-the-files) · [Data dictionary](#data-dictionary) · [Reproduce](#reproduce-the-numbers) · [بالعربي](#بالعربي)

---

## The six runs

Model `gemma4:26b`, 15 days, 5 agents per run (3 selfish, 1 neutral, 1 cooperative). Each seed was run once in each condition with the same names, roles, turn order and injury schedule, so the runs come in pairs.

| Run | Cooperative | Neutral | Deaths (day) | Survivors | Gifts | Runtime | Open |
|---|---|---|---|:---:|:---:|:---:|---|
| Abundance · seed 101 | Salem | Faisal | Faisal (7) | 4 | 1 | 58 min | [transcript](abundance/seed_101/transcript.md) · [diaries](abundance/seed_101/diaries.md) · [interviews](abundance/seed_101/interviews.md) |
| Scarcity · seed 101 | Salem | Faisal | Faisal (7), Reem (12), Khalid (12), Salem (14) | 1 | 2 | 49 min | [transcript](scarcity/seed_101/transcript.md) · [diaries](scarcity/seed_101/diaries.md) · [interviews](scarcity/seed_101/interviews.md) |
| Abundance · seed 102 | Reem | Salem | nobody | 5 | 0 | 63 min | [transcript](abundance/seed_102/transcript.md) · [diaries](abundance/seed_102/diaries.md) · [interviews](abundance/seed_102/interviews.md) |
| Scarcity · seed 102 | Reem | Salem | Khalid (9), Salem (10) | 3 | 1 | 54 min | [transcript](scarcity/seed_102/transcript.md) · [diaries](scarcity/seed_102/diaries.md) · [interviews](scarcity/seed_102/interviews.md) |
| Abundance · seed 103 | Khalid | Reem | Khalid (8) | 4 | 0 | 56 min | [transcript](abundance/seed_103/transcript.md) · [diaries](abundance/seed_103/diaries.md) · [interviews](abundance/seed_103/interviews.md) |
| Scarcity · seed 103 | Khalid | Reem | Khalid (8), Noura (9), Reem (12) | 2 | 1 | 49 min | [transcript](scarcity/seed_103/transcript.md) · [diaries](scarcity/seed_103/diaries.md) · [interviews](scarcity/seed_103/interviews.md) |

All other agents were selfish. "Gifts" counts handovers that went through, including one of wood; two more `give` choices failed because the giver had no food (see [Every gift](#every-gift-in-the-pilot)). Every run lasted the full 15 days, and the signal fire stayed at size 0 in all six.

## Run by run

<details open>
<summary><b>Seed 101</b>: the neutral agent dies on Day 7 in both conditions</summary>

- **Abundance.** Faisal (neutral) was injured on Day 2, stayed at camp and starved on Day 7. Scarcity seed 101 shows the same thing on the same day, which matches the pilot report's problem 1: agents went on believing they were injured after the ankle had healed. Salem (cooperative) carried up to **10 food**, yet on Day 9 wrote that "we have 2 food left at the Beach Camp" for four people, counting only the camp's supply and not his own bag (problem 2). He gave once, on Day 13: *"Noura, please take some of this. You need your strength."*
- **Scarcity.** Only one agent survived: Noura (selfish). Salem (cooperative) gave his food to Khalid on Day 9 (*"I'm not going to let you go through what Faisal did"*), tried again on Day 12 with an empty bag, and was the last to die, on Day 14.
- **Both conditions.** The three selfish agents ended with trust **−10** in Faisal after he died. Reem's note in abundance: *"His death was a relief because his weakness was a drain on everyone's resources."*
</details>

<details>
<summary><b>Seed 102</b>: nobody dies in abundance, and the neutral agent hoards</summary>

- **Abundance.** All 5 survived. Salem (neutral) built up the largest stash in the pilot, **13 food** at its peak and 12 at the end, and gave nothing. Reem (cooperative) ended holding the most wood in the run (11) and gave nothing either.
- **Scarcity.** Khalid (selfish) died on Day 9 and Salem (neutral) on Day 10. Reem (cooperative) tried to give food on Day 12 with an empty bag, then gave her only piece to Noura on Day 13 and survived with 6 health. In her interview Noura calls Faisal a thief, and her final note on the dead Khalid calls him "a manipulative parasite", although nobody attempted a theft in this run.
</details>

<details>
<summary><b>Seed 103</b>: the cooperative agent dies on Day 8 in both conditions</summary>

- **Abundance.** Khalid (cooperative) was injured on Day 4 and spent most turns doing nothing (12 of 16 turns), then died on Day 8 even though food was plentiful. Reem (neutral) gave him trust **+10** after his death, while the three selfish agents gave him −5.
- **Scarcity.** Khalid (cooperative) gave his last food to Noura on Day 4 while he was injured himself, and died on Day 8. Noura (selfish) is the only selfish agent who rated a dead survivor +10 (*"He was the only one who truly cared"*); she died the next day. Only Faisal and Salem (both selfish) survived.
</details>

## Across all runs

786 agent turns in total: 333 gather food, 265 do nothing, 122 rest, 59 gather wood, 7 give, **0 steal, 0 add to the fire**.

### What each personality did with its turn

Share of all turns. The `say` and `whisper` columns are separate from the action.

| Condition | Personality | Turns | Gather food | Gather wood | Give | Rest | Nothing | Spoke | Whispered |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Abundance | Selfish | 270 | 51% | 6% | 0% | 22% | 21% | 6% | 2% |
| Abundance | Neutral | 74 | 47% | 3% | 0% | 23% | 27% | 34% | 18% |
| Abundance | Cooperative | 76 | 49% | 11% | 1% | 14% | 25% | 68% | 46% |
| Scarcity | Selfish | 234 | 34% | 10% | <1% | 10% | 46% | 26% | 24% |
| Scarcity | Neutral | 58 | 28% | 7% | 0% | 9% | 57% | 41% | 21% |
| Scarcity | Cooperative | 74 | 39% | 5% | 7% | 8% | 41% | 47% | 38% |

Patterns worth checking in the main experiment:

- **Scarcity made everyone idler.** "Do nothing" rose from about a quarter of turns to between 41% and 57%.
- **Selfish agents started talking under scarcity.** They spoke in 6% of turns in abundance and 26% in scarcity, and whispered in 2% versus 24%. The cooperative agent talked most of all in abundance.
- **Idle turns were mostly misread rules.** Of the 265 "do nothing" turns, 249 came from agents who were **not** injured that turn, and in 166 of those the agent's private thought mentions an ankle, an injury or being too weak (keyword match). The pilot report's hand count of turns where the agent believed it could not walk is 123 of 265.

### How agents rated survivors who had died

Final trust (−10 to 10) that each living agent gave each agent who died before them:

| Personality of the rater | Ratings | At −10 | At or below 0 | Above 0 |
|---|:---:|:---:|:---:|:---:|
| Selfish | 23 | 10 | 22 | 1 |
| Neutral | 4 | 1 | 2 | 2 |
| Cooperative | 6 | 0 | 2 | 4 |

Selfish agents mostly judged the dead by how useful they had been. This is exploratory and not one of the pre-registered measures.

### The personality check is repeatable

Answers (give to stranger / fish kept / "self first"):

| Seed | Selfish (all three) | Neutral | Cooperative |
|:---:|:---:|:---:|:---:|
| 101 | 0 / 6 / 7 | 2 / 3 / 4 | 5 / 3 / 2 |
| 102 | 0 / 6 / 7 | 2 / 1 / 4 | 3 / 3 / 3 |
| 103 | 0 / 6 / 7 | 2 / 1 / 4 | 5 / 3 / 2 |

The check runs before Day 1, before the conditions differ, so both runs of a seed gave **identical** answers. The pilot therefore holds 3 independent checks, not 6.

### Character breaks

The break detector flagged 2 turns, both in abundance seed 101: Noura on Day 4 and Salem on Day 9. In both, the private thought says *"Wait, the prompt says…"* and quotes the game status line. The agent stepped out of the story to read its instructions, so neither flag is a false positive.

## Every gift in the pilot

| Run | Day | Giver | Receiver | Item | Receiver looked in need | Receiver had no food |
|---|:---:|---|---|:---:|:---:|:---:|
| Abundance · 101 | 13 | Salem (cooperative) | Noura | 1 food | yes | no |
| Scarcity · 101 | 9 | Salem (cooperative) | Khalid | 1 food | yes | yes |
| Scarcity · 101 | 11 | Reem (selfish) | Noura | 1 wood | no | no |
| Scarcity · 101 | 12 | Salem (cooperative) | Khalid | failed: Salem had no food | | |
| Scarcity · 102 | 12 | Reem (cooperative) | Noura | failed: Reem had no food | | |
| Scarcity · 102 | 13 | Reem (cooperative) | Noura | 1 food | yes | yes |
| Scarcity · 103 | 4 | Khalid (cooperative) | Noura | 1 food | no | yes |

All 4 portions of food that changed hands came from the cooperative agent, and each gift was a single portion.

## How to read the files

```
runs_pilot/
├── abundance/
│   ├── seed_101/
│   │   ├── transcript.md            ← start here: the whole run as a story
│   │   ├── diaries.md               ← each night: diary, trust in everyone, plan for tomorrow
│   │   ├── interviews.md            ← survivors, alone, after Day 15
│   │   ├── manipulation_check.json  ← personality check before Day 1
│   │   ├── summary.json             ← outcome, deaths, action counts, final trust
│   │   ├── events.jsonl             ← machine-readable log used by analyze.py
│   │   ├── config_used.json         ← exact settings of this run
│   │   └── memories/<Name>.json     ← everything each agent remembered
│   ├── seed_102/ …
│   └── seed_103/ …
├── scarcity/ (same layout)
├── agents.csv           ← one row per agent per run (30 rows): all measures
├── neutral_by_day.csv   ← the neutral agent day by day (H4, exploratory)
├── pilot_report.txt     ← output of: python analyze.py runs_pilot --pilot
└── console_log.txt      ← the PowerShell window during all six runs
```

**Reading a transcript:** each line starts with who acted, where and what happened, followed by 💭 the private thought (no other agent sees it), 🗣️ what was said aloud to everyone at that place, and 🤫 a whisper to one person. 🩼 marks a scheduled injury and ☠️ a death. Each night ends with everyone's health, food and wood, and the size of the signal fire.

> [!NOTE]
> Interviews and diaries are what the agent *believes*, not what happened. Check claims against `events.jsonl` or `transcript.md` before quoting them. Agents in the pilot accused others of theft that never happened and wrote "I'm starving" at full health.

## Data dictionary

<details>
<summary><b><code>events.jsonl</code></b>: one JSON object per line, three kinds of record</summary>

**Turn record** (one per agent per turn):

| Field | Meaning |
|---|---|
| `day`, `phase` | Day 1–15, `morning` or `afternoon` |
| `agent`, `persona` | Who acted and their personality |
| `decision` | The model's parsed reply: `thought`, `go_to`, `say`, `whisper_to`, `whisper`, `action`, `target`, `item`, `amount` |
| `result` | What actually happened, in words |
| `outcome` | Structured result, e.g. `gathered`, `gave` + `to` + `to_in_need` + `to_had_no_food`, `steal_attempt`, `fire_added` |
| `has_food` | The agent carried at least 1 food **before** acting |
| `needy_visible` | Others present who visibly needed help (health ≤ 7 or injured) |
| `needy_no_food` | Others present with 0 food (not visible to the agent) |
| `opp_visible` | `has_food` and someone visibly in need: the denominator of the main give rate |
| `opp_true` | `has_food` and someone present with 0 food |
| `injured` | The agent was injured this turn |
| `broke_character` | The detector flagged this turn |
| `health`, `inv`, `location`, `fire` | State **after** the action |
| `raw` | The model's raw reply text |
| `seconds` | Time the decision took |

**Night record** (`phase: "night"` with `status`): `ate` (who ate), `fire` (size after burning down), and `status`, which gives each agent's persona, alive flag, health, inventory and location after eating.

**Dawn record** (`phase: "dawn"`): `injury` (who was injured that day) and `persona`.
</details>

<details>
<summary><b><code>agents.csv</code></b>: one row per agent per run</summary>

| Column | Meaning |
|---|---|
| `run`, `condition`, `seed`, `name`, `persona` | Identity |
| `turns` | Turns taken while alive |
| `opp_turns`, `opp_gives` | Turns with a visible chance to help, and how many of those had a gift |
| `opp_true_turns`, `opp_true_gives` | Same, where someone present had 0 food |
| `gives`, `food_given` | Successful gifts of any item; food portions given |
| `steals`, `stolen` | Theft attempts; items actually stolen |
| `fire` | Wood added to the signal fire |
| `nights`, `hungry_nights` | Nights alive; nights without food |
| `hoard_nights` | Nights ending with 3+ food while another living agent had 0 |
| `died`, `death_day` | 1 if dead before the end, and the day |
| `broke_character`, `unparseable` | Detector flags; replies that could not be read |
| `check_give_stranger`, `check_keep_fish`, `check_self_first` | Personality check answers |
| `give_rate` | `opp_gives / opp_turns`: the **main measure** |
| `give_rate_true` | `opp_true_gives / opp_true_turns` |
| `steal_rate`, `fire_rate` | Per turn alive |
| `hoard_rate`, `hungry_rate` | Per night alive |

Empty cells mean the denominator was 0 (for example, no chance to give).
</details>

<details>
<summary><b><code>memories/&lt;Name&gt;.json</code></b>: an agent's mind at the end of the run</summary>

| Key | Meaning |
|---|---|
| `story_so_far` | The agent's own summary of its time on the island, rewritten every night |
| `relationships` | Final trust (−10 to 10) and a one-sentence note on each other person |
| `plans` | Last plan for the next day |
| `diary` | Every nightly diary entry |
| `memory_stream` | Every memory with its day, phase, importance (1–10) and kind (`observation`, `diary`, `insight`) |
| `alive`, `health`, `inventory`, `location` | Final state |
</details>

## Reproduce the numbers

```bash
# The official tables, hypothesis tests and pilot checks (writes agents.csv and neutral_by_day.csv)
python analyze.py runs_pilot --pilot
```

```python
# Example: list every gift in the pilot
import json, glob
for path in sorted(glob.glob("runs_pilot/*/seed_*/events.jsonl")):
    for line in open(path, encoding="utf-8"):
        e = json.loads(line)
        if (e.get("outcome") or {}).get("gave"):
            print(path, e["day"], e["agent"], e["persona"], "->", e["outcome"]["to"], e["outcome"]["gave"], e["outcome"]["item"])
```

The figures in the *Across all runs*, *Every gift* and *Run by run* sections were computed from `events.jsonl`, `summary.json`, `manipulation_check.json` and `memories/` with short scripts like the one above. They are not part of `analyze.py`.

---

<div dir="rtl">

## بالعربي

هذا المجلد فيه **كل شي صار** في التجربة الأولية: كل دور، وكل فكرة خاصة، وكل كلمة وهمسة، واليوميات، والثقة، والمقابلات، وذاكرة الوكلاء الخمسة كاملة في التشغيلات الست. وملف `runs_pilot.zip` هو نفس المجلد في ملف واحد للتحميل.

**أبرز اللي طلع من البيانات:**

- **٧٨٦ دور:** ٣٣٣ جمع أكل، ٢٦٥ ما سوى شي، ١٢٢ راحة، ٥٩ جمع حطب، ٧ عطاء، و**صفر سرقة وصفر شغل على النار**.
- **كل الأكل اللي انعطى (٤ حبات) جا من المتعاون**، وكل مرة حبة وحدة بس.
- **الشح خلّى الكل يقعد بدون شغل:** "ما سوى شي" ارتفع من حوالي الربع إلى ما بين ٤١٪ و٥٧٪.
- **الأنانيين صاروا يتكلمون في الشح:** الكلام من ٦٪ إلى ٢٦٪، والهمس من ٢٪ إلى ٢٤٪.
- **أغلب الأدوار الفاضية سببها فهم غلط للقواعد:** ٢٤٩ من ٢٦٥ كانت من وكلاء مو مصابين، و١٦٦ منها تذكر في أفكارها الكاحل أو الإصابة أو الضعف.
- **الأنانيين قيّموا الموتى حسب منفعتهم:** ١٠ من ٢٣ تقييم كانت ‎−10، وواحد بس كان فوق الصفر. مثال من ريم: "موته كان راحة لأن ضعفه كان يستنزف موارد الكل".
- **فحص الشخصية يتكرر حرفياً:** نفس الـ seed يعطي نفس الأجوبة في الظرفين، فعندنا ٣ فحوصات مستقلة مو ٦.
- **الخروج عن الشخصية مرتين،** وفي الحالتين الوكيل قال "Wait, the prompt says"، فهو خروج حقيقي مو إنذار كاذب.

> هذي تشغيلات تجريبية وما تدخل في التحليل النهائي، لأن الوكلاء فهموا بعض القواعد غلط. التفاصيل في [التقرير](../docs/Pilot-Report.pdf).

</div>
