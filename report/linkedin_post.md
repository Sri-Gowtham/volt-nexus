Spent the last day and a half on a data analytics hackathon with Gradient Learnings — 18 months of battery-swap data from a fictional EV network, VoltRelay Energy. 3.9 million swap attempts across 6 cities. No answer key, no target to predict, just: figure out what's actually going on.

The brief was straightforward on paper: swaps and revenue were growing, but so were failures, and leadership wanted to know why. The honest answer took longer than I expected.

A few things that held up:

Growth and reliability are two separate stories. Contribution margin per swap went from -₹6.48 to +₹12.43 over the 18 months — genuinely more profitable, not just bigger. But failure rate spiked twice in that same window with basically zero correlation to swap volume, revenue, or margin (checked it directly, not just eyeballed). Whatever's causing the failures isn't a scale problem.

One battery cohort is a real outlier. Three specific manufacturing lots were degrading roughly 6.7x faster than every other cohort in the fleet — not a supplier-wide issue, three lots. Ran a sensitivity check to make sure it wasn't sensor noise skewing the numbers. It wasn't.

The pricing pilot earned its keep. A peak/off-peak pricing test in two cities showed up as a ~₹5.3 lift in revenue per swap, and it held independently in both cities rather than being one city carrying an average. Ran a placebo test on the pre-pilot period too, since that's the kind of thing that's easy to skip and easy to get wrong — found a small effect in the opposite direction, which if anything makes the real result more credible, not less.

And the part I'm most glad I didn't skip: an early retention finding didn't survive scrutiny. First-pass analysis suggested queue wait time on a rider's first swap predicted whether they'd come back. Looked real at first — but once I corrected for testing multiple factors at once, it fell apart completely. So I pulled it. What actually held up was narrower: vehicle type and how a rider was acquired predict how often they keep swapping, not whether they disappear entirely. Less dramatic than the first version. Also the version that's actually true.

That last one is the real takeaway. It's easy to find a pattern in 3.9 million rows — nearly everything looks "significant" at that scale. The harder and more useful skill is knowing when a finding doesn't hold up, and being willing to say so instead of keeping the better story.

Built the full pipeline myself — cleaning, stats, visualization, writeup — for the Gradient Learnings Data Analytics Hackathon 2026.

#DataAnalytics #Hackathon #EV #GradientLearnings #BatterySwapping
