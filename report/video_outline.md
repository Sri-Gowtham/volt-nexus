# 3-Minute Video Outline
### Presenting to VoltRelay's operations & CX leadership

**Format:** 6 beats, ~25-30 seconds each. Every number below is sourced
from `FINAL_FINDINGS.md` — do not quote a figure that isn't in that file.
Uses 5 charts total (not all 14) so the video stays focused and doesn't
turn into a notebook walkthrough.

---

### 1. Title / business problem (0:00-0:25)
- "VoltRelay's battery-swap network grew 3x in swaps and revenue over 18
  months -- but service failures rose faster, retention looked flat, and
  per-swap profitability was in question. Leadership needed to know what's
  actually driving each of those, separately -- not assumed."
- Scope: 6 cities, 3.87M swap attempts, 18 months, no answer key -- an
  open diagnostic investigation, not a prediction task.

### 2. Network growth + operational performance (0:25-0:50)
**Chart: `q1_network_performance.png`**
- "Completed swaps and revenue both tripled, moving together. Contribution
  margin per swap improved from -Rs.6.48 to +Rs.12.43 -- the network is
  genuinely more profitable per swap, not just bigger."
- "But failure rate spiked twice in that same window, with essentially
  zero correlation to the growth and margin trend -- we checked directly,
  not just eyeballed it. Whatever's driving failures isn't a scale
  problem."

### 3. Where service failures concentrate (0:50-1:20)
**Chart: `q2b_high_risk_segment.png`**
- "On their own, station, time of day, season, and vehicle class each
  explain only a little of the failure pattern. But one specific
  combination stands out: 3-wheelers, in summer and monsoon, during
  evening and night hours -- that segment fails at roughly 2x the network
  rate."
- "That's a precise, targetable segment -- more useful than a generic
  'improve service quality' directive."

### 4. Station + battery signals (1:20-1:50)
**Charts: `q3_station_ranking.png`, `q4_battery_degradation.png`**
- "Station age is the one station attribute that holds up under rigorous
  testing -- older, Gen1 launch-wave stations fail more often."
- "On the battery side, three specific manufacturing lots from one
  supplier -- Kyron -- are degrading roughly 4 to 6 times faster than
  every other cohort in the fleet. Confirmed stable even after we checked
  for sensor-drift noise. This is a three-lot problem, not a supplier-wide
  one."

### 5. Pricing + partner economics (1:50-2:20)
**Chart: `q5_pricing_pilot_did.png`**
- "The peak/off-peak pricing pilot is associated with about Rs.5.35 more
  revenue per completed swap, and that holds up independently in both
  pilot cities. We also ran a placebo test on the pre-pilot period as a
  gut-check -- it came back small and in the opposite direction, which
  supports rather than undercuts the main result."
- "On the partner side: the largest fleet partner by revenue is barely
  profitable per swap, while two of the three largest partners are
  actually losing money on every swap. Volume doesn't equal value here."

### 6. Retention findings + actions (2:20-3:00)
**Chart: `q6b_activity_drivers.png`**
- "Here's the part I want to be upfront about: our first pass suggested
  queue wait time on a rider's first swap predicted whether they'd come
  back. Once we corrected for testing multiple factors at once, that
  finding did not hold up -- so we withdrew it rather than keep it in the
  final numbers."
- "What does hold up: vehicle class and how a rider was signed up predict
  how *actively* an engaged rider keeps swapping -- 3-wheeler riders swap
  about 30% less often; riders brought on by a field agent or partner
  swap 18 to 25% more often. That's a real, usable signal for engagement
  campaigns -- just not a proven churn-prevention lever."
- **Close, recommendations:** "Refresh Gen1 station hardware. Investigate
  the three Kyron lots. Roll out peak/off-peak pricing network-wide --
  the strongest evidence-backed option of the four we considered. Review
  contract terms with the two underperforming large fleet partners. And
  target engagement campaigns at 3-wheeler and organically-signed-up
  riders, since that's what the data actually supports."

---

**Production notes:** 5 charts total across 6 beats (beat 4 uses two).
Keep the Rs.5.35 pricing figure and the "6x Kyron" figure on screen as
text overlays — the two most quotable stats. The retention beat (6) should
be delivered plainly, not apologetically — a withdrawn finding presented
as evidence of rigor lands better on a business audience than either
hiding it or over-explaining it.
