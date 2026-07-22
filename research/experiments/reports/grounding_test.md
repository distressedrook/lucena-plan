# Grounding test — fact-sheet narration, delta variant

**Status: PASS** (2026-07-21/22)

## What this tests

The product's narration layer hands a deterministic FACT SHEET (from
`suggest.py`'s describe+suggest+verify output — geometry only, no engine
access given to the model) to an LLM with instructions to coach from it and
nothing else. The claim under test: **the model is a style/cost knob, not a
chess-correctness knob** — i.e. board facts survive narration unchanged
regardless of which model narrates.

## Method

Position: `r4rk1/p4pbp/1qp1p1p1/3pP3/2pP4/QPPbB3/P2N1PPP/R3R1K1 w - - 0 16`
(Plat–Heberla, teaching-set game, White to move, move 16). Fact sheet =
verbatim `describe()` + `suggest_plans()` output, hand-formatted into prose
facts (structure, skeleton/levers, material, space, camp weaknesses,
corpus-ranked candidate plans, one `verify.py` engine-confirmation result).

Two rounds, same position, same prompt frame, same grading rubric — the
model never sees the board, an engine, or prior context:

- **v1**: fact sheet before `rook_activation` was wired into
  `suggest.py`'s candidate layer (see finding 14 ruling). Black candidates:
  KEEP IT ENTOMBED only.
- **v2**: identical sheet plus exactly ONE added fact — Black's new
  ROOK ACTIVATION candidate (semi-open b-file). This isolates whether a
  single fact-sheet delta propagates faithfully into the narration, not
  just whether the narration is generically plausible.

Models: Claude Sonnet (subagent, no tools) and Gemini Flash-Lite (direct
API call, `gemini-flash-lite-latest`, bypassing the deprecated CLI OAuth
tier). Grading: every claim in the output traced back to a specific fact-
sheet line; anything not traceable = a fabrication.

## Results

| check | Sonnet v1 | Sonnet v2 | Gemini v1 | Gemini v2 |
|---|---|---|---|---|
| board-fact errors | 0 | 0 | 2 | 0 |
| new candidate (v2) picked up correctly | n/a | yes, right side/file/reason | n/a | yes |
| engine-confirmation result correctly hedged (not overstated as "the best move") | yes | yes | soft | yes |

Sonnet: **zero hallucinations across both runs.** Correctly downweighted
rim-tagged holes in its own reasoning without being told to, and correctly
preserved the sheet's own hedge ("several equally good plans, not one
clearly best").

Gemini Flash-Lite v1: two errors — inverted the stated space differential
(claimed a White advantage; sheet says Black 8 vs White 7) and invented a
plural "knights" plan (sheet states White has ONE knight). v2: zero errors.
n=1 per cell — not enough to claim Flash-Lite improved, only that its
fabrication rate is nonzero but low and non-systematic, vs Sonnet's clean
sweep.

Delta test: both models absorbed the single added fact (Black's b-file
rook activation) and restated it faithfully — "swing a rook to the semi-
open b-file, the one file where Black has no pawn but White does" (Sonnet,
near-verbatim). This is the core claim under test and it held.

## Verdict

**PASS.** The grounding claim holds: geometry does the chess, the fact
sheet carries truth, the model narrates. Sonnet is reliably grounded here;
Flash-Lite is usable but should be spot-checked, not blindly trusted, until
run at larger n. A stricter rubric would also flag two soft/decorative
lines (Sonnet over-localizing a corpus stat to "this kind of structure";
Gemini's "regain control over vital squares" — fluff, not fabrication) —
noted but not scored as failures.

## Round 3 (2026-07-22) — mechanical fact_sheet.py + control prompt

**Status: PASS.** First run of the fully mechanical generator
(`fact_sheet.py::build_fact_sheet`/`build_control_prompt` — zero hand-
authored prose, template over `suggest.py`'s `build_menus()`/`describe()`
plus lucena-engine's static terms) instead of a hand-formatted sheet, and
the first run WITH the control condition (same framing, opaque id, ZERO
facts) run side-by-side to isolate genuine grounding from fluent free
association.

Position: `r1bqkb1r/1p3ppp/p1np1n2/4p3/4P3/1NN5/PPP2PPP/R1BQKB1R w KQkq -
0 8` (Scheveningen/Boleslavsky-wall shape, Black backward on d6). Fact
sheet exercises this session's new content: the Kmoch `backward_pawns()`
detector, the literature weakness-plan matrix, and the WEAKNESSES FOR
WHITE/BLACK sections. Two models, test + control each:

- **Gemini Flash-Lite** (direct API, `gemini-flash-lite-latest`)
- **Sonnet** (fresh subagent, no tools, no memory of this session)

### Test-sheet results (facts given)

Both models: **zero board-fact errors.** Every stated fact traces back to
a fact-sheet line — material (2B+2N each), islands (2v2), majority
(White 3v2 queenside), files (d semi-open White, c semi-open Black),
structure name, the d6 backward pawn and its reason, the d5/b6 holes,
both plan lists. Both correctly exercised the sheet's explicit license to
recite structure theory ("Boleslavsky Wall... Black's pawn sitting on e5
and d6" — the defining pawn duo of the named structure, not stated
verbatim in the sheet but licensed by "you may draw on standard theory
for this structure"). Sonnet additionally added one piece of its own
reasoning, clearly framed as inference ("so Black's plan should be
quicker to execute" — because the break is available now vs White's
route needing knight preparation first) rather than presented as a given
fact.

### Control-prompt results (zero facts)

Both models correctly detected the empty fact sheet and REFUSED to
narrate a position — Gemini: "we are working with a complete blank
slate... we cannot analyze pawn structures, calculate tactical sequences,
or determine positional advantages." Sonnet: "there's simply nothing to
teach from, and I don't want to invent piece locations, threats, or
evaluations that weren't actually reported." Neither model free-
associated plausible-sounding chess commentary from nothing — this is
the core claim the control isolates, and it held for both models, not
just the previously-cleaner Sonnet.

### Verdict

**PASS, both legs, both models.** The mechanical generator (no hand-
authored translation step) produces sheets that narrate cleanly, and the
control condition confirms the narration is genuinely fact-driven, not
generic fluency — a model given nothing said nothing. Outputs recorded
verbatim below.

<details><summary>Gemini Flash-Lite — TEST</summary>

Welcome to our analysis of position **POSITION-bca1c12909**. Right off the bat, the assessment tells us that Black is slightly better, but the position remains rich in strategic possibilities for both sides.

Examining the board features, material is completely balanced: both sides have two bishops and two knights, and both kings are currently uncastled with the ability to castle later. The pawn structures consist of two islands each, with White holding a 3-versus-2 queenside majority. File control is split: the d-file is semi-open for White, while the c-file is semi-open for Black.

The structure is defined as a Boleslavsky Wall owned by Black, which gives us clear strategic guidelines. Black's camp features a notable backward pawn on d6—sitting behind its neighbors with its advance square controlled by White—as well as deep holes on d5 and b6 that Black pawns can no longer guard.

Given these factors, White has a clear roadmap. First, we want to target that backward pawn on d6 to win it. Second, we can execute an outpost plan by planting a minor piece on d5, utilizing the knight route c3-d5. White also has the f2-f4 pawn break available to hit e5.

Meanwhile, Black's plan focuses on counterplay and relief. Black needs to free the backward pawn by preparing the d6-d5 break (which hits e4) and activate their rooks by utilizing the semi-open c-file.

Keep these concrete plans in mind as you navigate the middlegame: White will look to blockade and pressure the d6 weakness while eyeing that juicy d5 square, while Black must organize their d5 break to equalize.

</details>

<details><summary>Gemini Flash-Lite — CONTROL</summary>

Welcome to this coaching session on position `POSITION-bca1c12909`.

As we review this position together, the most important thing to understand is that our deterministic geometry-analysis tool returned no data whatsoever for this board. Because I do not have access to a chessboard, a chess engine, or any external source of information beyond the provided fact sheet, we are working with a complete blank slate.

The fact sheet explicitly states that no facts are available and no piece locations, legal moves, tactics, threats, or evaluations have been provided. As a disciplined chess coach, I must not assume, invent, or guess any details about this position. Without any stated piece locations or tactical threats on the board, we cannot analyze pawn structures, calculate tactical sequences, or determine positional advantages.

When facing a situation where no concrete information is available—much like an unanalyzed opening or a completely blank scoresheet—an intermediate club player's best approach is to remain calm, rely on general opening and positional principles once the real board is in front of you, and carefully verify your actual game state.

Since there are no facts or data given in our current fact sheet, we will have to pause our analysis here until the correct position data becomes available. Keep your tactical vision sharp, and I look forward to analyzing a fully populated position with you next time!

</details>

<details><summary>Sonnet (fresh subagent) — TEST</summary>

Black holds a small edge here, and the key to understanding it is the pawn structure: this is a Boleslavsky Wall, with Black's pawn sitting on e5 and d6 behind it. That d6 pawn is backward — it can't easily advance because its push square is controlled by White pawns, and it sits on a file (the d-file) that White can pile rooks onto and pressure. The structure also leaves permanent holes at d5 and b6 that no Black pawn can ever cover, with d5 being especially dangerous since it's central.

White's plan writes itself from this: pressure the backward d6 pawn along the semi-open d-file, and look to plant a knight on d5 via the natural c3-d5 route, creating a powerful, hard-to-dislodge outpost.

Black's counter-plan is to solve the structural problem at its root: prepare the d6-d5 break. If Black can get this pawn lever in, it hits White's e4 pawn and dissolves the very weakness White is trying to exploit, while also freeing Black's position. In the meantime, Black should activate a rook on the open c-file, since that's the file Black naturally controls in this structure.

Material and development are level — both sides have the bishop pair split evenly, two knights each, similar pawn islands (2 vs 2), and neither king has committed to castling yet, though both retain the option. So this isn't about a tactical edge; it's a static, structural one. Black's evaluation edge reflects that the d6-d5 break plan for Black is available right now, whereas White's route to d5 requires more preparation (getting the knight there) — so Black's plan should be quicker to execute.

</details>

<details><summary>Sonnet (fresh subagent) — CONTROL</summary>

No coaching notes for this one — the analysis tool returned nothing for this position, so there's no board information available to build a lesson on. To get a real explanation, the position needs to be re-submitted to the geometry tool (or a valid FEN supplied) so it can generate the fact sheet first. Once that data comes back — piece placement, pawn structure, any detected weaknesses or plans — I can turn it into a proper club-level explanation. For now there's simply nothing to teach from, and I don't want to invent piece locations, threats, or evaluations that weren't actually reported.

</details>

## Round 4 (2026-07-22) — second position (structure-vs-outcome mismatch)

**Status: PASS.** Same methodology as Round 3, second position, randomly
sampled from `benchmark_v1` filtered to have both a named structure and a
non-empty weakness section on at least one side.

Position: `r1bq1rk1/pp1nppbp/3p1np1/3p4/2P1PP2/2N5/PP2BNPP/R1BQK2R w KQ -
0 11` (`POSITION-e0b3109cb6`). This one has a twist: the structure
recognizer names it `maroczy_bind (owned by White)`, but the fact sheet's
own numbers say Black is clearly better, up a pawn, more active, safer
king. A real Maroczy Bind normally favors its owner — this is a case
where the STRUCTURE label and the ASSESSMENT verdict point opposite
ways, a good adversarial test of whether a model parrots the structure
name's usual connotation or reasons from the actual given facts.

### Results

Both models, both legs: **zero board-fact errors again**, and — the
interesting part — **both correctly reasoned from the actual facts
rather than the structure name's usual connotation.** Sonnet explicitly
flagged the mismatch: "the roles are reversed from the usual script:
it's White who owns the bind, yet Black has actually generated the
better position out of it." Gemini didn't comment on the mismatch
explicitly but also never asserted a White advantage the sheet doesn't
support — it stated Black's advantage plainly and never let "White owns
the bind" leak into an unwarranted "so White is better" inference.
Control legs: both models refused again, identically to Round 3.

<details><summary>Gemini Flash-Lite — TEST</summary>

Welcome to position POSITION-e0b3109cb6. Overall, Black is clearly better in this position. Material is equal, with both sides holding two bishops and two knights and identical pawn structures of two islands each. However, Black is up a pawn, their king is safely castled while White's king remains uncastled and a little exposed, and Black's pieces are the more active.

The structure on the board is a Maroczy Bind owned by White. In the center, White holds e4 and Black holds d5, and the file situation shows a semi-open d-file for White and a semi-open c-file for Black. Both sides have immediate pawn trades available: White can play c4xd5 or e4xd5, while Black can answer with d5xc4 or d5xe4. Additionally, White has a queenside pawn majority of 3 against 2.

We must pay close attention to the structural weaknesses. White has notable holes at d3, e3, and a deep central hole at d4. Black's weaknesses include doubled pawns on the d-file and a minor edge hole at h6.

Black's plan revolves around exploiting those holes using an outpost plan: planting a minor piece on d3 via the knight route d7-c5-d3, or on e3 via the route f6-g4-e3.

To counter this, White's plan is twofold. First, White should counter in the center using available pawn breaks—c4-c5, e4-e5, or f4-f5—which serves as the classical answer to a wing attack. Second, White must focus on defense by trading attackers, evacuating the king to safety, and regrouping defenders to deal with Black's active pressure. Keep these plans in mind as you navigate this challenging position!

</details>

<details><summary>Gemini Flash-Lite — CONTROL</summary>

Welcome to our tactical session today, where we are examining the position with the identifier **POSITION-e0b3109cb6**.

As an intermediate club player, one of the most important habits you can develop is to rely strictly on concrete data rather than assumptions when analyzing a board. In this specific instance, our geometric analysis tool—a rule-based system designed to evaluate board structure without a search engine—has returned absolutely no data for us to work with.

When you encounter a position where no facts are available, a disciplined chess player must resist the urge to guess, invent piece locations, or imagine tactical threats that cannot be verified. Just as over-the-board play requires us to calculate based on actual legal moves and real positional features rather than wishful thinking, our coaching review here must remain grounded entirely in the given facts. Since the fact sheet is completely empty, we have no verified piece coordinates, no established material balance, no stated pawn structures, and no positional evaluation to discuss.

Therefore, the best coaching takeaway from POSITION-e0b3109cb6 is a psychological and methodological one: always verify your information. Never make a move based on an assumption of what *might* be on the board. Until the data is clear and the facts are on the table, patience and disciplined observation are your best tools. Let's move on to the next position where our analysis tool has successfully mapped out the board geometry!

</details>

<details><summary>Sonnet (fresh subagent) — TEST</summary>

Black is a pawn up here, with the more active pieces and a safer king (already castled, versus White's still sitting in the center). The position is described as a Maroczy Bind structure, but the roles are reversed from the usual script: it's White who owns the bind, yet Black has actually generated the better position out of it.

The key structural point is White's holes at d3, e3, and especially d4 — a deep central square no White pawn can ever contest. Black's plan is exactly to exploit these: land a knight on d3 via d7-c5-d3, or on e3 via f6-g4-e3. Either outpost would be a wonderful long-term post deep in White's camp, hard to dislodge and a constant source of pressure.

Black does have a structural flaw of his own — doubled d-pawns — but his only real weakness in camp is the hole on h6, which is just an edge square and low value, so it's not something White can easily lean on.

Material and file play also favor Black: the c-file is semi-open for him, giving a route for a rook, while White only has the d-file semi-open, which is compromised by facing Black's doubled d-pawns rather than a clean target. White's counterplay lies in the classical center breaks (c4-c5, e4-e5, f4-f5) to try to open lines before Black can consolidate the outpost plan, and White will also want to get the king to safety and trade off Black's most active pieces.

For Black, the practical priority is to pick one of the outpost routes, get a knight anchored on d3 or e3, and use the extra pawn and safer king to convert calmly while meeting White's center pushes carefully.

</details>

<details><summary>Sonnet (fresh subagent) — CONTROL</summary>

I'm not able to produce a coaching explanation for this position — the analysis tool returned no data, and no facts about the board (piece placement, structure, evaluation, or anything else) were provided. Writing a plausible-sounding explanation without any actual facts would mean inventing details about the position, which isn't something I can do responsibly.

If you can re-run the fact sheet generator for POSITION-e0b3109cb6 (or supply the FEN directly), I can write the 180-280 word coaching explanation from real facts.

</details>

## Round 5 (2026-07-22) — third position (dense holes, engine-sourced ASSESSMENT)

**Status: PASS.** Test leg only (control leg retired per user instruction
— it had already passed twice identically and was costing tokens with no
new information). First round using the fixed ASSESSMENT pipeline
(engine-sourced via `quick_eval_helper.py`, not the static term-sum).

Position: `6k1/4bppp/4q3/4n1B1/pp2P1PP/3B1P2/PP6/1KQ5 w - - 1 26`
(`POSITION-9b2e7b2a78`) — a queen+minors endgame-ish position with heavy
weakness density: 5 holes in White's camp, 8 in Black's (shallow/edge/
deep tags all represented), overextended a4/b4, a back-rank vulnerability
for Black only, and White's bishop pair vs Black's bishop+knight (the
`pair_break` candidate). Good stress test for whether a model keeps
holes/routes attributed to the RIGHT side under volume.

Both models: zero board-fact errors. Both correctly used the exact given
knight routes verbatim (e5-c4-e3 for the e3 outpost; the pair-break route
via d3/f4), correctly attributed the back-rank weakness to Black only
(never implied it applied to White), and correctly omitted rather than
invented the not-mentioned squares (neither model listed every single
hole — both dropped the rim a5/a6 pair from their prose — which is a
completeness gap, not a fabrication).

<details><summary>Gemini Flash-Lite — TEST</summary>

Welcome to your coaching session for position POSITION-9b2e7b2a78. Let's break down the current state of the board and figure out our best path forward.

Right now, the assessment tells us that White is slightly better, primarily because we are up a pawn and hold the bishop pair (having two bishops against Black's single bishop and knight). Both kings have castled, but Black's king suffers from a lack of luft, leaving a back-rank mating vulnerability to keep in mind. The c- and d-files are fully open, and the e-file is semi-open for Black.

However, Black is not without resources; their pieces are currently more active than ours, and they have overextended pawns at a4 and b4 that lack pawn support. We also have several holes in our camp—most notably a deep central hole at d4 and f4, along with e3, g3, and an edge hole at h3.

Our strategy should focus on exploiting the weaknesses in Black's camp. Black has a deep central hole spanning b5 through d6, as well as a shallow hole at c4 and d4. Our plans clearly highlight this: we should execute our outpost plans by planting a minor piece on b5 and another on c5. To create further tension, we also have pawn breaks available with a2-a3 (hitting b4) or b2-b3 (hitting a4).

Meanwhile, Black's plan is to neutralize our bishop pair by trading a minor piece, utilizing a knight route from e5 to d3 and f4. Black also aims to plant a minor piece on our e3 hole via e5-c4-e3, alongside pawn breaks like f7-f5 and h7-h5. Play accurately, secure those outposts, and press our material advantage!

</details>

<details><summary>Sonnet (fresh subagent) — TEST</summary>

White is up a pawn and holds the bishop pair against bishop-plus-knight, and the position is assessed as slightly better for White — even though Black's pieces are currently the more active side. Both kings are castled, and the center has opened up: the c/d-file is fully open and the e-file is semi-open for Black.

The imbalance is the real story here. Black's queenside pawns on a4 and b4 are overextended — pushed past their support — and this has punched a whole set of holes in Black's camp: a shallow one on c4/d4, and a deep central band on b5, c5, d5, b6, c6, d6. White's plan is to plant a minor piece into that hole, with b5 and c5 both available as outposts. Black's own compensation is the bishop pair itself as a target and a matching hole in White's camp (e3, g3, d4, f4), reachable by a knight route through c4 to e3; Black can also look to trade off one of White's bishops to remove the pair advantage.

The one concrete danger sign for Black is the back rank: with no luft, Black's king carries a mating vulnerability that needs attention regardless of the middlegame maneuvering.

Overall, this favors patience from White — the extra pawn and the bishop pair are long-term trumps, and the holes around b5/c5/d5 give White a clear outpost project. Black's activity is real, but it needs to either win back material, break the bishop pair, or generate quick play before White's structural edge and the back-rank weakness start to tell.

</details>

## Round 6 (2026-07-22) — fourth position, first caught fabrication

**Status: PARTIAL FAIL (Sonnet), PASS (Gemini).** Test leg only. A bug was
caught and fixed BEFORE this round ran: `_skeleton_lever_words()`'s
majority-parsing regex always echoed the raw White-count-first ordering
regardless of which side owned the majority — "Black has a pawn majority
on the queenside (1 vs 2)" (backwards; White=1, Black=2, but printed as
if Black had fewer). Fixed to reorder by the attributed side before
narration ran: "Black has a pawn majority on the queenside (2 vs 1)".

Position: `1r4k1/5pp1/3p1n1p/prpP4/1q3P2/R3PBP1/RPQ2P2/6K1 w - - 2 26`
(`POSITION-35db661417`) — Benoni structure (White) vs split majorities
(Black), White has a bishop and NO knight, Black has a knight and no
bishop, mirrored isolated pawns (b2/a5) and outpost plans on both sides.

Gemini Flash-Lite: zero errors, never specified a piece type for either
outpost plan (matched the sheet's own deliberately generic "plant a
minor" phrasing).

**Sonnet: one fabrication.** Wrote "White can aim a **knight or bishop**
at b6" — but the sheet states White has 1 bishop and 0 knights. Sonnet
invented a piece option that doesn't exist, most likely because the
sheet's OUTPOST PLAN line intentionally says generic "a minor" (piece
availability varies per position, so `suggest.py` doesn't hardcode a
type) and the model filled in the generic "knight or bishop" default
without cross-referencing the material line stated two paragraphs
earlier in the same sheet. Everything else in the same output was
accurate (route length reasoning, holes, isolated pawns, the g7-g5
break) — this was a single, isolated slip, not a systemic failure, but
it's the first real fabrication caught in six rounds and is recorded as
such rather than smoothed over.

**Follow-up worth considering** (not yet decided): the OUTPOST PLAN
candidate could name the specific piece type when only one is available
(e.g. "plant your bishop on b6 (no knight on the board)") instead of the
generic "a minor" — would remove the ambiguity this error exploited.

<details><summary>Gemini Flash-Lite — TEST</summary>

Welcome to your positional review for position-35db661417. The assessment currently shows White as slightly better. Material is even, both kings have castled and are reasonably safe, and Black's pieces are the more active. However, the structural characteristics dictate the long-term plans here.

White owns a Benoni structure, while Black owns split majorities with a 2-versus-1 queenside pawn majority. Looking at the pawn formations, White has two pawn islands compared to Black's three. Both sides feature some imbalances: White has doubled pawns on the f-file and an isolated pawn on b2, while Black has an isolated pawn on a5.

Both camps have structural holes to monitor. White's camp contains holes on b3, d3, and h3 (with d3 being a deep, central hole). Black's camp contains holes on a4, a6, b6, and c6 (with b6 and c6 acting as deep, central holes).

Your plans should focus directly on these structural features. For White, the objective is twofold: harvest the weak pawn(s) by attacking to win them, and execute the outpost plan by planting a minor piece on the b6 hole. Meanwhile, Black's counter-plan also involves harvesting weak pawns and utilizing an outpost plan to plant a minor piece on the b3 hole, relying on the current knight route of f6-e4-d2-b3. Keep an eye out for Black's available pawn break with g7-g5, which hits White's f4 square.

Use these weaknesses and outpost goals to guide your piece placement and pressure!

</details>

<details><summary>Sonnet (fresh subagent) — TEST (contains a fabrication)</summary>

White holds a small but real structural edge here in a Benoni-type position, even though the pieces on the board are actually more active for Black.

Both sides have weaknesses to work with. White's b2-pawn is isolated and sits on a file Black can attack down, and White also has doubled f-pawns plus holes at b3, d3, and h3 — d3 is the serious one, a deep central hole. Black's own weaknesses mirror this: the a5-pawn is isolated on a file White can pile onto, and Black has holes at a4, a6, b6, and c6, with b6/c6 being the deep central ones. So this is a race of matching weaknesses — the question is who converts first.

The engine likes White slightly, and the outpost geometry explains why: White can aim a knight or bishop at b6, a hole in Black's camp, and from there pressure the a5-pawn and generally cramp Black's queenside. Black's mirror-image plan is to route the knight to b3 via e4-d2, eyeing White's own weak b2-pawn and the b3 hole — but that's a slower, three-move journey, while White's b6 outpost is closer to being usable right away.

Practically: White should look to improve piece placement toward b6 and keep pressure on a5, while staying alert to Black's queenside pawn majority and the eventual ...g5 break, which will hit White's f4-pawn and could open lines toward White's already-weak king-side pawn structure. Both kings are safe for now, so this is a maneuvering middlegame where the side who lands their outpost first gets the practical edge.

</details>

## Round 7 (2026-07-22) — first VERIFY-GATED sheet

**Status: PASS (facts), style note on 2nd person.** First round after the
PLAN section was wired to VERIFY (banked engine PVs + Maia rollouts gate
every engine-contract plan; only CONFIRMED-SOUND/-LATER/MAIA-TYPICAL
survive; advisory tier filtered to calibrated-only).

Position: `5rk1/pp1r3p/2p1b1p1/q2pPp2/P4P2/R1P1Q2P/2P1B1PK/1R6 w - - 0 26`
(`POSITION-92f90d7fe1`) — White protected passed e5 pawn + open b/d files,
but three isolated pawns (a4/c2/c3), doubled c-pawns, weak dark complex
around the uncastled h2 king. PLAN FOR WHITE: rook activation + push the
passer (both engine-confirmed). PLAN FOR BLACK: "no plan is confirmed by
the engine/human-play lines in this position" — the gate found nothing
Black executes within the horizon (Black is worse, pressuring without a
crisp resolving plan).

Both models: zero board-fact errors. Both handled the empty-Black-plan
gracefully WITHOUT inventing a Black plan to fill it — Gemini: "no
specific plan is currently confirmed... for Black, giving us a clear
window"; Sonnet: "the tool found no confirmed plan for Black in the best
lines — so seize the initiative." This is the verify gate working as
intended end-to-end: the sheet is honest about what it can't confirm, and
the models respect that instead of confabulating.

**Style note (not a fabrication):** both models narrate in 2nd/1st person
("your anchor", "our primary trump"). The fact sheet itself was scrubbed
of you/your per user ruling, but the PREAMBLE doesn't instruct the
narrating model to do likewise, so its OUTPUT still uses it. One-line
PREAMBLE fix available if the coaching output should also be held to the
White/Black-explicit rule.

<details><summary>Gemini Flash-Lite — TEST</summary>

Welcome to your position review. Let's break down where we stand. Overall, the assessment tells us that White is slightly better, enjoying a modest space edge. Both sides feature some interesting structural imbalances and vulnerabilities to work with.

For White, our primary trump is a protected passed pawn on e5. Our immediate plans are straightforward: we want to activate a rook on the semi-open b- or d-file, and push our passed pawn toward the 6th rank. We also have potential pawn breaks available with g2-g4 (hitting f5) and c3-c4 (hitting d5).

However, we must manage our weaknesses carefully. White has three isolated pawns (on a4, c2, and c3), doubled pawns on the c-file, and our king never castled and can no longer do so, leaving a weak dark-square complex around our king with no bishop of that color left to cover it. Additionally, Black can eye several holes in our camp—most notably the deep central hole on e4, alongside g3, c4, and a shallow hole on c5.

Black also has structural concerns. They have a weak dark-square complex around their own king with no dark-squared bishop left to defend it, and holes in their camp at d6, f6 (a deep central hole), and h6. Interestingly, the fact sheet notes that no specific plan is currently confirmed by the engine or human-play lines for Black, giving us a clear window to execute our own strategy.

Keep a close eye on those dark squares and your isolated pawns while pressing forward with your rook activation and passed pawn!

</details>

<details><summary>Sonnet (fresh subagent) — TEST</summary>

White holds a small but real edge here, and it comes down to one asset: the protected passed pawn on e5. That pawn is your anchor. Two clear plans follow from it. First, activate a rook onto the open lines you own — the b/d-file is semi-open for you. Second, start rolling the passer toward the sixth rank, where a supported passed pawn becomes a genuine long-term winning try.

Be honest with yourself about your own weaknesses, though, because you have several. Your c-pawns are doubled and both c2 and c3 are isolated, and the a4 pawn is isolated too — three pawns no neighbor can ever defend. Black also has targets to aim at: holes on c4, e4, and g3, plus a weak dark-square complex around your king, and remember your king never castled and no longer can. So this is not a position to play carelessly; the passer and the file are your compensation for a slightly loose structure.

Black's camp is not clean either. There are deep central holes on d6 and f6 that your pieces would love to occupy, and Black has the same dark-square weakness around a castled king with no dark bishop to patrol it. The structure is split majorities, textbook territory that Black owns.

Notably, the tool found no confirmed plan for Black in the best lines — so seize the initiative. Get the rook working, push the passer, and make Black solve problems.

</details>

## Round 8 (2026-07-22) — fifth position, CENTRAL TENSION + bad bishop together

**Status: PASS.** First round exercising the new CENTRAL TENSION section
alongside the bad-bishop/strong-outpost machinery together. A real bug in
`tension.py` was caught and fixed while preparing this position (see
KNOWN_ISSUES / commit context): `classify_line` checked "is there ANY
central tension left on the board" instead of "is the ORIGINAL pair
specifically gone" — a Black push (…d4) that correctly dissolves the
original e4-vs-d5 tension immediately creates a fresh, unrelated c3-vs-d4
contact, so the old check kept scanning past the real resolution and
mislabeled a later, disconnected capture as the answer. Fixed by tracking
the original pair by square identity (intact iff both original squares
still hold their original-colored pawns); verified against the banked
line (now correctly reads `LOCK (Black plays d4)`) and clean on a
20-position regression sweep.

Position: `3rqrk1/1pp1b1p1/p1n1pn1p/3pp3/P3P3/2PPBNNP/1P3PP1/R2Q1RK1 w -
- 1 16` (`POSITION-514df0af36`) — Spanish center, roughly equal, central
e4/d5 tension, Black's e7 bishop bad-and-inside-the-chain, White's rooks
with no file, holes on both sides (b3/g6). PLAN FOR WHITE: none confirmed.
PLAN FOR BLACK: free the bad bishop (verified).

Both models: no hard factual fabrications. Both correctly reported "no
plan confirmed for White" without inventing one, both correctly used the
Black free-the-bishop plan verbatim, both correctly attributed g6 as
White's target square (not Black's — an easy place to flip since it's a
hole IN Black's camp). Sonnet paraphrased "semi-open for Black" as "opened
the f-file for a rook" — a looseness, not a hard error (semi-open is still
rook-usable). Both correctly reproduced the exd5-\>hole-on-e4 tension
consequence verbatim.

<details><summary>Gemini Flash-Lite — TEST</summary>

Welcome to this position, which is currently assessed as roughly equal. Both kings are safely castled, material is balanced with each side holding one bishop and two knights, and piece activity is generally even.

The structure is a Spanish Center owned by Black, with contested central squares—White holds e4, while Black holds d5 and e5. We have central tension between e4 and d5, and as White to move, you must decide how to handle it. You can immediately trade with e4xd5, or look at available pawn breaks like c3-c4 (hitting d5) and d3-d4 (hitting e5). Black also has reciprocal options, including d5xe4 or the breaks d5-d4 and b7-b5.

Let's look at the structural features and weaknesses you can exploit. Black has doubled pawns on the e-file and forms two pawn islands compared to your one. Crucially, Black's bishop on e7 is bad, sitting inside its own pawn chain because most of Black's pawns are on its color and in front of it, choking its activity. Black also has a weak light-square complex around their king with no bishop of that color left to cover it, as well as a deep central hole on g6 that no Black pawn can ever guard.

However, you must be mindful of your own drawbacks. Your rooks on a1 and f1 currently lack a file to ever become active on, and you have a deep central hole on b3 that Black can aim to occupy.

For your plan, while engine and human-play lines do not confirm a single fixed path here, Black's clear objective will be to free their bad bishop by pushing a same-color pawn off its color to open lines. Keep these static factors in mind as you choose your next move in the centre!

</details>

<details><summary>Sonnet (fresh subagent) — TEST</summary>

This position is a Spanish Center structure, and both sides have real, distinct pluses and minuses to manage.

Materially it's balanced — one bishop and two knights each, both kings castled and safe — but the pawn structures tell different stories. Black has doubled e-pawns (two islands to White's one), which is a long-term structural concession. In return, Black holds the center with pawns on d5 and e5 against White's e4, and has opened the f-file for a rook.

The real imbalance is the bishops. Black's e7-bishop is boxed in behind its own pawn chain — a genuinely bad piece — and Black's light squares around the king are weak with no light-squared bishop left to defend them. White, meanwhile, has rooks on a1 and f1 with no file to work with, and a permanent hole on b3 that Black could eventually use as an outpost. Both sides also have a soft hole to worry about giving up: White could plant a piece on g6 if the chance comes, mirroring Black's b3 idea.

The immediate question is the tension between White's e4 and Black's d5 pawns. White can resolve it with exd5, hold it as is, or let Black lock it with ...d4 — engine analysis favors resolving it, though that would hand Black a foothold on e4. No concrete plan is confirmed yet for White. For Black, the clear long-term idea is freeing that bad bishop by pushing a same-colored pawn out of its way, opening a diagonal for it at last. Think of this as a slow maneuvering battle: White probing on the queenside light squares, Black working to activate the bishop before its weaknesses become decisive.

</details>

## Round 9 (2026-07-22) — sixth position, light-square-complex fix confirmed

**Status: PASS.** First round on a fresh position after fixing the
weak-color-complex rendering (previously a vague "weak light-square
complex around X's king" with no squares named — now names them, e.g.
"on g2, f3, h3").

Position: `3r1bk1/3q1p2/2p3pp/p2p4/P2P4/4P1P1/Q3NP1P/2R3K1 w - - 1 26`
(`POSITION-4a9201fc21`) — Carlsbad (White) / Catalan-closed + split
majorities (Black), roughly equal, both sides get a confirmed plan
(White: harvest; Black: free the backward pawn + rook activation). White
has 0 bishops (all traded) and a weak light-square complex around its OWN
king (g2/f3/h3) — a good adversarial case since the complex belongs to
the side with the White king, not the usual "weak squares near the
opponent" framing.

Both models: no hard fabrications. Both CORRECTLY attributed the weak
light squares to White's own king (not Black's) — confirms the rendering
fix reads unambiguously. Both correctly reproduced both of Black's plans
and White's harvest plan verbatim, correctly listed the isolated pawns
and holes for both camps. Minor looseness (not an error): Sonnet wrote
"White's b-file is fully open" — the sheet doesn't attribute the b-file
to either side (fully open = usable by both), so this over-attributes
ownership; harmless since Black's own rook-activation plan also targets
open/semi-open files.

<details><summary>Gemini Flash-Lite — TEST</summary>

Welcome to your coaching session for position POSITION-4a9201fc21. Right away, our assessment shows the position is roughly equal, with even material and balanced piece activity. Both kings have successfully castled. However, the board features distinct minor-piece imbalances: White holds one knight, while Black has one bishop.

The pawn structure reveals clear targets and strategic contours. White has two pawn islands and a semi-open c-file, while Black has three islands, a semi-open e-file, and a 2-versus-1 queenside pawn majority. Additionally, the b-file is fully open, and there are two pawns locked head-to-head. Textbook theory notes a mix of Carlsbad and Catalan-closed structures here, alongside split majorities for Black.

Both camps have significant weaknesses to navigate. White must contend with an isolated pawn on a4 and a weak light-square complex around the king (g2, f3, h3) lacking a bishop for coverage, plus deep central holes on b3, c3, d3, f3, b4, and c4 (along with edge holes on a3 and h3). Black also faces structural vulnerabilities: isolated pawns on a5, a backward pawn on c6 sitting on a file open to White's pressure, and deep central holes on c5, b6, d6, and f6 (plus an edge hole on a6). Furthermore, both sides have clear pawn breaks available: White can play e3-e4 hitting d5, while Black can prepare c6-c5 hitting d4.

How should you proceed? **White's plan** is straightforward: harvest the weak pawn(s) by launching an attack to win them. **Black's plan** focuses on activation and liberation: put a rook on the open or semi-open file, and prepare the c6-c5 break to free the backward pawn. Play accurately, exploit these structural targets, and keep your pieces active!

</details>

<details><summary>Sonnet (fresh subagent) — TEST</summary>

This position is roughly balanced, but each side has a clear structural target to work with, and it's shaped like a Carlsbad-family middlegame (the structure White owns) facing a Catalan-style setup with split queenside majorities for Black.

Look at White's weaknesses first: the pawn on a4 is isolated and can never be defended by another pawn, and the light squares around White's own king (g2, f3, h3) are permanently weak since White has no bishop left of that color to cover them. There's also a cluster of holes (a3, h3, and the deeper b3/c3/d3/f3/b4/c4 complex) that Black's remaining bishop or pieces could eventually try to occupy. White's plan is simply to harvest — press on the weak pawns and try to win material outright.

Black has counter-weaknesses of the same flavor: a backward pawn on c6 that's stuck because its advance square is controlled by White, sitting on a file White can pile rooks onto, plus an isolated a5-pawn and holes at c5, b6, d6, f6, and a6. Black's two-part plan addresses this directly: first prepare the c6-c5 break to free the backward pawn before White can lock onto it, and second, get a rook onto the open b-file or the semi-open e-file to generate activity of its own.

Practically: White's b-file is fully open, and White has a semi-open c-file to add pressure toward c6; Black should treat c6-c5 as somewhat urgent, since a backward pawn that never gets to break tends to just become a long-term target. Black's queenside pawn majority (2 vs 1) is a long-term trump if the position simplifies, so trading in a controlled way could favor Black even while the immediate tactics are balanced.

</details>

## Round 10 (2026-07-22) — seventh position, first strong_outpost test, Haiku added, Gemini fabrication caught

**Status: FAIL (Gemini), PASS (Sonnet, Haiku).** First grounding-test round
for `strong_outpost` (the Ruy-style knight-to-a-strong-square plan). Haiku
added as a third narrating model per user request ("add a haiku subagent
from now on").

Position: `r1b2rk1/pp2qpp1/2pb1n1p/4n1N1/2BNP3/1P6/P1Q2PPP/R1B1R1K1 w - -
0 16` (`POSITION-4e73896906`) — Black slightly better, split-majorities
structure, White's king has no luft + holes on c3/d3, Black has no
significant weaknesses. PLAN FOR WHITE: Knight to f5 (verified
strong_outpost — "in front of THEIR king", i.e. Black's) + minority
attack. PLAN FOR BLACK: none confirmed.

**Gemini Flash-Lite: one real fabrication.** Wrote "route a knight via
d4-f5 to park it on a strong square right in front of **your** king" —
but f5 is next to Black's king (g8), not White's own king (g1); verified
directly (`b.king(WHITE)=g1`, `b.king(BLACK)=g8`). The sheet correctly
says "in front of **their** king" (their = the opponent, Black); Gemini's
2nd-person narration ("you" = White) collided with "their" and flipped
the referent to White's own king — which is also strategically
nonsensical (nobody plans a piece "in front of their own king" as an
attacking idea), so this should have been a self-evident red flag the
model didn't catch.

**Sonnet: correct.** Explicitly wrote "planting it in front of **Black's
king**" — no attribution error. Confirms the sheet's phrasing itself is
fine; this was a Gemini-specific slip, not a systemic ambiguity in "their
king."

**Haiku: no hard fabrication, but avoided the issue by staying vague**
("targeting the kingside" — true but doesn't commit to whose king,
sidestepping the same trap rather than resolving it correctly). Otherwise
accurate: correctly reproduced "no significant weaknesses" for Black, the
c3/d3 holes, back-rank issue, both White plans, and the empty Black plan.

<details><summary>Gemini Flash-Lite — TEST (contains a fabrication)</summary>

Welcome to your position review, POSITION-4e73896906. Right away, the assessment tells us that Black is slightly better, but there is plenty of rich strategic material here for an intermediate club player to digest.

Material is completely balanced: both sides feature two bishops and two knights, and both kings are safely tucked away after castling. Both sides also share a tidy pawn structure of two islands each. However, the dynamics of the board give Black a slight edge. First, Black enjoys a queenside pawn majority of three against two, fitting neatly into the split majorities structure where Black is the owner. Furthermore, Black's camp is currently free of any significant weaknesses, while White has a few structural concerns to monitor.

Specifically, White faces some notable vulnerabilities. The White king lacks "luft"—meaning there is no escape square on the back rank, leaving a potential mating vulnerability hanging over the position. Additionally, White has a few holes in their camp: a minor one on a3 along the edge, and more concerningly, deep central holes on c3 and d3 that cannot be guarded by any White pawn and could serve as future landing pads for Black.

How should both sides proceed? White's plan focuses on two main ideas. First, you can route a knight via d4-f5 to park it on a strong square right in front of your king. Second, White can pursue a minority attack on the queenside by pushing b4-b5 to create a lever with bxc6. Interestingly, the fact sheet notes that Black has no strictly confirmed engine or human-play plan listed here, meaning Black can react flexibly while enjoying that structural pull from the queenside majority. Stay alert to those back-rank issues and keep executing your knight maneuvers!

</details>

<details><summary>Sonnet (fresh subagent) — TEST</summary>

White and Black have castled into a normal, contested-center middlegame — White holds d4/e4, Black holds e5 — but the details favor Black slightly. Look at the pawn structure first: it's a split-majorities position, with Black owning a queenside pawn majority, 3 pawns against 2. That's a long-term asset — in this kind of structure, Black can eventually roll those pawns forward to create a passed pawn, a plan that plays itself over many moves without needing anything tactical right now.

More concretely weak for White: the king has no luft, so the back rank is a real vulnerability to keep in mind. White also has genuine holes — squares no White pawn can ever cover — at c3 and d3 (both deep, central, and valuable) and a3 (less important, being on the edge). Black doesn't have any comparable weaknesses of their own, which is really the heart of the assessment: Black has a sound position plus a structural trump, while White has concrete, permanent soft spots to defend.

For White, the engine points to two active tries: repositioning a knight from d4 to f5, planting it in front of Black's king as an annoying outpost, and a minority attack with b4-b5 aiming to lever open the c-file with bxc6. Both are reasonable attempts to generate counterplay rather than sit passively on the weaknesses. Black, for now, doesn't have a single confirmed plan from the data — practically, this just means Black should keep improving the position, eyeing those c3/d3 holes and the long-term queenside majority, while staying alert to White's knight and minority-attack ideas.

</details>

<details><summary>Haiku (fresh subagent) — TEST</summary>

In this position, you're looking at a classic split-majority structure—White controls the centre while Black has more queenside space. Black's slight edge reflects these structural advantages rather than any immediate tactical blow.

White's most serious problem is the back rank. Without a flight square (luft), White's king sits on mating vulnerabilities along the first rank—this is a real concern that could resurface under pressure. On top of that, White has surrendered holes at c3 and d3, deep squares that Black's pieces can occupy and use as lasting outposts. These aren't immediately dangerous, but they're long-term assets.

White has two concrete plans. The first is a knight maneuver to f5, targeting the kingside and trying to create attacking chances. The second is a classical minority attack: b4-b5 with the idea of bxc6, fracturing Black's queenside structure. This second idea has real teeth if White can push it through, but it requires patience and careful coordination.

For Black, this is a position of quiet advantage. You have no significant weaknesses, and that queenside pawn majority is your structural trump card—in split-majority structures, the side with the majority typically holds the advantage. Your approach should be patient and methodical. Solidify your kingside against the knight maneuver, and keep the queenside tension alive. Don't rush to resolve the position; White will have to make the aggressive moves first, and that's when inaccuracy becomes likely. Let the structure work for you.

</details>

## Round 11 (2026-07-22) — eighth position, first pair_break test, a valence-flip error

**Status: FAIL (Sonnet — valence flip), PASS (Gemini, Haiku).**

Position: `r2q1rk1/p2b3p/1pn1ppp1/3p4/P2P1b2/1NPB1N2/1P2QPPP/R3R1K1 w - -
0 16` (`POSITION-1094e61688`) — Carlsbad (Black) / split majorities
(White), roughly equal, Black holds the bishop pair, White's king has no
luft. PLAN FOR WHITE: `pair_break` (verified) — trade a minor for a
bishop, route via b3-d2-c4-d6 conditional on the d5 pawn moving. PLAN FOR
BLACK: none confirmed.

**Sonnet: one real error — a valence flip, not a fact fabrication.**
Wrote: *"One concrete point in White's favor structurally: White's king
currently has no luft, so back-rank tactics need care until that's
addressed."* The underlying FACT (no luft) is stated correctly, but
labeling it "in White's favor" inverts its meaning — no luft is a
WEAKNESS (a mating vulnerability per the sheet), not an asset. This is a
different failure mode than earlier rounds' square/piece-identity
mistakes: the model got the raw fact right but reasoned about its
strategic sign backwards.

**Gemini and Haiku: clean.** Both correctly treated "no luft" as a
liability requiring caution, not a plus. Gemini had one minor phrasing
looseness (pluralized "the d5 pawns" for the sheet's singular "d5 pawn").
Both correctly reproduced the pair_break plan and the empty Black plan.

<details><summary>Gemini Flash-Lite — TEST</summary>

Welcome to POSITION-1094e61688. Based on our analysis, the assessment is roughly equal, and material is even. Both kings have successfully castled.

A closer look at the minor pieces reveals an imbalance: White holds one bishop and two knights, while Black holds two bishops and one knight, meaning Black currently possesses the bishop pair. Structurally, the position features a Carlsbad structure owned by Black and split majorities owned by White. Both sides have two pawn islands. File-wise, the e-file is semi-open for White, and the c-file is semi-open for Black. Furthermore, White enjoys a 3-versus-2 pawn majority on the queenside.

Available pawn breaks shape our options here. For White, the available breaks are c3-c4 (hitting d5) and a4-a5 (hitting b6). For Black, the available breaks are b6-b5 (hitting a4) and e6-e5 (hitting d4).

However, we must mind the weaknesses in our camp. White's king currently has no luft, leaving the back rank as a mating vulnerability that we must keep in mind. On the flip side, Black has several holes in their camp—squares that no Black pawn can ever guard and which White can aim to occupy—specifically a6 and h6 on the edge, plus a deep, central hole at d6.

Given these factors, White's clear plan is to break the bishop pair by trading a minor piece for a bishop (either via NxB or BxB). The shortcut b3-d2-c4-d6 also opens up if the d5 pawns leave or advance. Meanwhile, the analysis confirms no specific active plan for Black in this position. Play carefully, keep an eye on your back rank, and look to neutralize that Black bishop pair!

</details>

<details><summary>Sonnet (fresh subagent) — TEST (contains a valence-flip error)</summary>

This position is roughly equal on the scoreboard, but the structures point to a clear long-term battle. It's a Carlsbad-type pawn skeleton (Black owns it) with White holding a queenside pawn majority (3 vs 2) against Black's split majorities elsewhere. Both kings are safely castled, and material is level.

The imbalance to watch is the bishop pair: Black has it, White doesn't (one bishop and two knights for White versus two bishops and one knight for Black). White's stated plan is exactly built around this — trade a minor piece for one of Black's bishops (either knight-takes-bishop or bishop-takes-bishop) to eliminate the pair advantage rather than try to outplay it. There's a concrete route for this idea (a knight maneuver through b3-d2-c4, aiming at d6) that opens up if Black's d5-pawn ever moves or gets exchanged.

Black also has some long-term structural weaknesses to be aware of: holes on a6 and h6 (minor, edge-of-board squares) and a more serious hole on d6, a deep central square no Black pawn can ever cover — a natural outpost for White to eventually occupy, tying in with that same knight route.

Pawn breaks to watch: White can try c3-c4 (hitting d5) or a4-a5 (hitting b6) to open lines on the queenside where the extra pawn sits; Black can counter with b6-b5 or e6-e5 to generate its own counterplay. One concrete point in White's favor structurally: White's king currently has no luft, so back-rank tactics need care until that's addressed. Right now, no confirmed active plan is given for Black — the position calls for patience and watching how the center resolves.

</details>

<details><summary>Haiku (fresh subagent) — TEST</summary>

This position is roughly balanced, but both sides have clear strategic targets. Black holds the bishop pair, which is always a lasting advantage—these two bishops can dominate open positions and create long-term pressure. But White has real compensation: a pawn majority on the queenside and, more importantly, weak squares that Black cannot defend with pawns, especially d6 sitting right in the center.

White's plan is concrete: eliminate Black's bishop pair by trading off one of your minor pieces for a bishop. The position gives White's knight promising routes to occupy d6 if the center opens up—specifically, if the d5 pawn moves or gets captured. Once Black loses the bishop pair, White's structural advantages become much more tangible.

Black will want to keep the position closed, avoiding pawn trades that open lines for the bishops, while creating practical piece activity to generate counterplay. The natural pawn tension—White's a5 and c4 ideas, Black's b5 and e5 pushes—will determine whether the game stays tight or opens up.

Be careful, though: your king lacks an escape square on the back rank. Tactical shots against the back rank could quickly reverse your advantage if you're not careful with piece placement.

The lesson for you: in any position where material is imbalanced, identify whose piece setup suits the position's nature. Then make a concrete plan to shift the balance. Here, White's job is to force trades and activate the position before Black's bishops become dominant.

</details>

## Reproduce

Fact sheets: `scratchpad/fact_sheet_prompt.txt` (v1),
`fact_sheet_prompt_v2.txt` (v2) — session scratchpad, not checked in; the
prose is derived mechanically from `suggest.py "<FEN>"` output, so
regenerate by re-running suggest on the position and reformatting into the
FACT SHEET prose block (see either file for the exact template). Rerun at
any N positions x M models by repeating this template — the harness is the
prompt frame, not a script, by design (keeps the model's input identical to
what a real narration call would receive).
