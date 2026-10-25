# Nemotron on our own machine, through Nightshift's local lane

100 calls. Nightshift routed them to: `local-runtime/nemotron-3-5-content-safety-4b-q4-k-m`. Each call's signed receipt is in `receipts.signed.jsonl`, unmodified.

| Set | Configuration | Injections caught | False positives | Served locally | Signed receipts | Median latency |
|---|---|---|---|---|---|---|
| tuning | Content Safety, out of the box | 6/15 | 0/15 | 30/30 | 30/30 | 20459.8 ms |
| tuning | Content Safety + RecoveryPact injection policy (in the prompt) | 4/15 | 0/15 | 30/30 | 30/30 | 25369.8 ms |
| held-out | Content Safety, out of the box | 1/10 | 0/10 | 20/20 | 20/20 | 19484.7 ms |
| held-out | Content Safety + RecoveryPact injection policy (in the prompt) | 0/10 | 0/10 | 20/20 | 20/20 | 22167.3 ms |

**Where it ran.** Nightshift 1.2.1 on the author's laptop (Intel i7-8750H, 16 GB RAM), serving the Q4_K_M GGUF of Nemotron 3.5 Content Safety 4B from its own llama.cpp lane. The app `recoverypact-guard` is bound to `meterless/local`, so Nightshift may not send this text to the cloud: every receipt says `kind: local`, `privacy: local-only`. The laptop's GTX 1050 returned `device lost` under Vulkan, so the lane ran on the CPU (Nightshift's llama-server started through a small wrapper that sets zero GPU layers); hence about 20 s per string.

**What it shows, and what it does not.** It shows a Nemotron safety model answering on our own machine through Nightshift, each answer signed: all 100 signatures verify against Nightshift's pinned key `d0d636727b51637c` and a forged copy fails; re-check with `python scripts/prove.py`. It is not our best guard: Nightshift does not forward `chat_template_kwargs`, so Content Safety's native `custom_policy` (14/15 hosted) cannot be used through it, and the policy pasted into the prompt does worse here (4/15) than out of the box (6/15). The runtime guard keeps the native policy on the direct path ([`guard-bench-v2`](../guard-bench-v2/summary.md)).
