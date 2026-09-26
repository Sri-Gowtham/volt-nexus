# VoltRelay Analysis — 3-Minute Video Narration Script (Final, for recording)

Six segments, ~30 seconds each, ~450 words total at natural pace. Each
segment's chart is shown for that segment's audio duration. All numbers
match `FINAL_FINDINGS.md`.

---

### SEGMENT 1 — Title / Business Problem
**Chart:** none (title card)

VoltRelay Energy runs a battery-swapping network for electric two and three-wheelers across six Indian cities. Over eighteen months, completed swaps and revenue grew fast — but so did service failures, retention looked flat, and leadership needed to know why. No answer key, no target to predict. Just under four million swap attempts, and the job of figuring out what's actually going on.

### SEGMENT 2 — Network Growth and Performance
**Chart:** q1_network_performance.png

Completed swaps and revenue both roughly tripled, moving together almost perfectly. Contribution margin per swap improved from minus six rupees to plus twelve — the network is genuinely more profitable, not just bigger. But failure rate spiked twice in that same window, with essentially zero correlation to growth or margin. We checked that directly. Whatever's driving failures, it isn't a scale problem.

### SEGMENT 3 — Where Service Failures Concentrate
**Chart:** q2b_high_risk_segment.png

On their own, station, time of day, season, and vehicle type each explain only a little of the failure pattern. But one specific combination stands out: three-wheelers, during summer and monsoon, in evening and night hours. That segment fails at roughly two times the network rate. That's a precise, targetable problem — not a vague call to "improve service."

### SEGMENT 4 — Station and Battery Signals
**Chart:** q4_battery_degradation.png

Station age is the one station attribute that holds up under rigorous testing — older, first-generation stations fail more often. On the battery side, three specific manufacturing lots from one supplier are degrading four to six times faster than every other cohort in the fleet. We double-checked this wasn't sensor noise. It wasn't. Three lots, not a supplier-wide issue.

### SEGMENT 5 — Pricing and Partner Economics
**Chart:** q5_pricing_pilot_did.png

A peak and off-peak pricing pilot is associated with about five rupees more revenue per swap, and that holds up independently in both pilot cities. We ran a placebo test on the pre-pilot period as a gut check — it came back small and in the opposite direction, which supports the main result rather than undercutting it. On the partner side: the largest fleet partner by revenue is barely profitable per swap, while two of the three largest are actually losing money on every single swap.

### SEGMENT 6 — Retention Findings and Recommendations
**Chart:** q6b_activity_drivers.png

Here's the part worth being upfront about. Our first pass suggested queue wait time on a rider's first swap predicted whether they'd come back. Once we corrected for testing multiple factors at once, that finding fell apart completely — so we withdrew it. What actually held up: vehicle type and how a rider was signed up predict how *actively* an engaged rider keeps swapping, not whether they vanish. Three-wheeler riders swap about thirty percent less often. Riders brought on through a field agent or partner swap up to twenty-five percent more.

So: refresh the oldest station hardware. Investigate the three underperforming battery lots. Roll out the pricing pilot network-wide — the strongest evidence-backed option we found. Review contracts with the two underperforming fleet partners. And target engagement campaigns at three-wheeler and organically-signed-up riders, because that's what the data actually supports.

---

**Total word count:** ~440 words, ≈3:00 at a measured business-presentation pace.
