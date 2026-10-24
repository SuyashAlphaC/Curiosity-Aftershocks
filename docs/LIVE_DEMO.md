# Demonstrating the recent-event monitor

## Prepare before class

1. Start the updated application with `make serve` and open http://127.0.0.1:8000.
2. Open **Live monitor**. Choose a real event from the past 24 hours whose occurrence time you can cite. An event several hours old is more likely to have published hourly observations than one that just happened.
3. Enter the event's actual name and local time. Optionally enter obvious headline words to hide direct title matches. Do not supply article lists: discovery is automatic.
4. Click **Start monitoring** well before presenting. The first run downloads and processes three full baseline dumps plus available post-event dumps. Depending on network and hardware, warm-up can take 15–20 minutes or more. Completed hourly inputs are cached for reuse.
5. Check **Latest observation**, **Data age**, the baseline indicator, and the ingestion journal. Keep the server running. New public source files are checked every five minutes.

## The demonstration story (3–5 minutes)

- **Configuration:** “I supplied an event time and optional headline terms, not a list of interesting articles.”
- **Ingestion:** Point to real source rows, completed hours, and the latest source timestamp. “These counts come from complete public Wikimedia dumps processed by Spark Structured Streaming.”
- **Discovery:** Point to the broad article count and detected candidates. “The system compares the latest hourly count against a fixed pre-event baseline and ranks unusual increases.”
- **Graph:** Click an automatically discovered topic. Explain its absolute views, baseline, lift, and burst score. “Links show observed co-movement across at least five shared hours, not users moving between pages.”
- **Automatic updates:** Show the observed-hours strip and journal. New file arrival triggers processing and a new candidate graph; the interface polls status automatically. Do not claim an update occurred if the source has not published a new file.
- **Research question:** Open a candidate's Wikipedia article and discuss whether an independent explanation connects it to the event or to other news. “Detection generates a hypothesis; it does not prove causality.”

## Honest answers to likely questions

**Is it actually live?** It monitors newly published files automatically. The underlying source is hourly, with publication and local processing delay. It is not a second-by-second stream or a replay disguised as live.

**Does “unexpected” mean unrelated?** No. The candidate was discovered outside a manually curated topic list. Literal headline exclusion can remove obvious title matches, but semantic unrelatedness and event attribution need investigation.

**Why no graph edges yet?** Three baseline hours plus only one post-event hour give four observations. Links require at least five shared observations, so another observed hour is needed. The system does not invent edges for presentation.

**Why are some topics missing?** Titles must appear in all three baseline hours and pass minimum traffic, lift, excess, and burst-score thresholds. New or sparse articles may be excluded. Only the strongest 24 candidates are drawn.

**Can we replay the saved validation?** Last results remain visible when stopped, explicitly labeled **Last observations**. They must not be presented as a currently running monitor. The validation watch is an engineering test time window, not a claim about a specific news event.

**What are the limits?** Three hours is a short baseline. Daily rhythms, automated traffic, other simultaneous events, and selection effects can produce apparent bursts and correlations. This is an exploratory signal detector.
