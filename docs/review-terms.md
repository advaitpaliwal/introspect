# Review Terms

Introspect wakes from direct user messages scored by the local intent classifier and a local repetition-pressure layer over review-tier classifier events.

The optional `~/.introspect/trigger-words.txt` file adds review metadata. It can tag events with exact lowercase terms when the user deliberately creates the file. Reflector wake decisions come from the classifier and repetition-pressure layer.

The normal wake path is:

1. Ignore assistant messages, Codex file/context wrappers, control messages, pasted context, and duplicate hook/scanner observations.
2. Score the direct user message with `~/.introspect/models/wake-logreg-v2-round4.json`.
3. Compute the effective wake threshold from the installed sensitivity setting. The bundled model threshold is `0.64`; the live `sensitive` setting maps to `0.40`.
4. Queue the event when the score meets the effective wake threshold.
5. Keep scores from the review threshold, currently `0.30`, up to the effective wake threshold as review-only local signal data.
6. Queue a review-tier event with `wake_reason=repetition_pressure` when a similar complaint repeats across chats in the same project within the local repetition window.
7. Record optional review metadata when `trigger-words.txt` exists.

The repetition layer stores bounded hashed local features in `feedback/repetition-state.json`. It scopes pressure by project. Session/message identity suppresses duplicate hook/scanner observations. It filters low-score prompts, assistant messages, Codex file/context wrappers, control phrases, pasted context, and install backfill.

Codex Desktop still has a scanner backstop because changed command hooks can be skipped until the hook definition is trusted or the app session reloads config. The scanner reads recent `~/.codex/sessions/**/rollout-*.jsonl` files, ignores Codex control/context records, dedupes transcript lines, and queues missed classifier-triggered or repeated-pressure prompts through the same single-worker cooldown path.
