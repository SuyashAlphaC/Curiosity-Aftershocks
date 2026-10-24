import { useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Check,
  Clock3,
  Database,
  LoaderCircle,
  Play,
  Radio,
  Square,
  Waves,
} from "lucide-react";
import "./live.css";

type LivePoint = { hour: string; views: number | null; baseline: boolean };
type Candidate = {
  id: string;
  title: string;
  views: number;
  baseline: number;
  lift: number;
  z: number;
  excess: number;
  baselineSamples: number;
  series: LivePoint[];
};
type LiveEdge = {
  source: string;
  target: string;
  correlation: number;
  samples: number;
};
export type LiveState = {
  active: boolean;
  phase: string;
  message: string;
  config?: { name: string; occurred_at: string; exclude_terms: string[] };
  topics: Candidate[];
  edges: LiveEdge[];
  timeline: { hour: string; candidates: number; scannedArticles: number }[];
  log: { time: string; message: string }[];
  baselineReady?: number;
  baselineHours?: number;
  processedHours?: number;
  sourceRecords?: number;
  scannedArticles?: number;
  candidateCount?: number;
  latestHour?: string;
  updatedAt?: string;
  nextCheckAt?: string;
  processingHour?: string;
  limitations?: string[];
  method?: string;
};
const compact = (n?: number) =>
  n === undefined
    ? "—"
    : Intl.NumberFormat("en", {
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(n);
const number = (n: number) => Intl.NumberFormat("en").format(n);
const stamp = (s?: string) =>
  s
    ? new Date(s).toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "UTC",
      }) + " UTC"
    : "Awaiting observations";
function localInput(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
async function request(path: string, body?: unknown, signal?: AbortSignal) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : data.detail?.[0]?.msg || "The monitor request failed.",
    );
  return data as LiveState;
}

function DiscoveryGraph({
  state,
  selected,
  select,
}: {
  state: LiveState;
  selected: string;
  select: (id: string) => void;
}) {
  const ordered = [...state.topics].sort((a, b) => a.id.localeCompare(b.id));
  const nodes = ordered.map((t, i) => {
    const angle = (i / Math.max(ordered.length, 1)) * Math.PI * 2 - Math.PI / 2;
    const radius = i % 2 ? 155 : 207;
    return {
      ...t,
      x: 380 + Math.cos(angle) * radius * 1.35,
      y: 228 + Math.sin(angle) * radius * 0.82,
    };
  });
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return (
    <svg
      className="discovery-graph"
      viewBox="0 0 760 460"
      role="group"
      aria-label="Automatically discovered topic graph"
    >
      <defs>
        <radialGradient id="live-field">
          <stop stopColor="#c3f967" stopOpacity=".075" />
          <stop offset="1" stopColor="#c3f967" stopOpacity="0" />
        </radialGradient>
        <pattern
          id="live-dots"
          width="22"
          height="22"
          patternUnits="userSpaceOnUse"
        >
          <circle cx="1" cy="1" r=".65" fill="#7d9481" opacity=".24" />
        </pattern>
      </defs>
      <rect width="760" height="460" fill="url(#live-dots)" />
      <ellipse cx="380" cy="228" rx="330" ry="210" fill="url(#live-field)" />
      {[95, 155, 207].map((r) => (
        <ellipse
          key={r}
          cx="380"
          cy="228"
          rx={r * 1.35}
          ry={r * 0.82}
          fill="none"
          stroke="#345039"
          strokeDasharray="3 7"
          opacity=".45"
        />
      ))}
      {state.edges.map((e, i) => {
        const a = byId.get(e.source),
          b = byId.get(e.target);
        if (!a || !b) return null;
        const highlight = a.id === selected || b.id === selected;
        return (
          <path
            key={i}
            d={`M${a.x},${a.y} Q380,228 ${b.x},${b.y}`}
            stroke={highlight ? "#c3f967" : "#809f97"}
            strokeOpacity={highlight ? 0.65 : 0.17}
            strokeWidth={highlight ? 1.4 : 0.7}
            fill="none"
          >
            <title>
              {e.correlation.toFixed(2)} correlation across {e.samples} observed
              hours
            </title>
          </path>
        );
      })}
      <text
        x="380"
        y="222"
        textAnchor="middle"
        fill="#dcebcf"
        fontSize="28"
        fontFamily="Space Grotesk"
      >
        {state.topics.length}
      </text>
      <text
        x="380"
        y="242"
        textAnchor="middle"
        fill="#91a490"
        fontSize="9"
        letterSpacing="1.5"
      >
        CANDIDATE SIGNALS
      </text>
      {nodes.map((n) => {
        const radius = Math.min(20, 6 + Math.log2(n.lift) * 2);
        const isSelected = n.id === selected;
        return (
          <g
            key={n.id}
            transform={`translate(${n.x},${n.y})`}
            className="topic-node"
            role="button"
            tabIndex={0}
            aria-label={`Inspect live topic ${n.title}`}
            aria-pressed={isSelected}
            onClick={() => select(n.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                select(n.id);
              }
            }}
          >
            <title>
              {n.title}: {number(n.views)} views, {n.lift.toFixed(1)}× baseline
            </title>
            {isSelected && (
              <circle
                r={radius + 9}
                fill="none"
                stroke="#c3f967"
                opacity=".35"
              />
            )}
            <circle
              r={radius}
              fill={isSelected ? "#c3f967" : "#c3f96722"}
              stroke="#a8d96b"
            />
            <circle r="2.5" fill={isSelected ? "#12200b" : "#c3f967"} />
            <text
              y={radius + 17}
              textAnchor="middle"
              fill={isSelected ? "#e5f4d7" : "#a7b5bd"}
              fontSize="10"
            >
              {n.title.length > 24 ? n.title.slice(0, 22) + "…" : n.title}
            </text>
          </g>
        );
      })}
      <text x="18" y="440" fill="#82948b" fontSize="8">
        Size: current lift · Links: observed co-movement
      </text>
    </svg>
  );
}

export default function LiveMonitor() {
  const [state, setState] = useState<LiveState | null>(null),
    [error, setError] = useState(""),
    [pollError, setPollError] = useState(""),
    [busy, setBusy] = useState(false);
  const [name, setName] = useState(""),
    [when, setWhen] = useState(localInput(new Date(Date.now() - 4 * 3600000))),
    [terms, setTerms] = useState(""),
    [selected, setSelected] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false,
      first = true;
    const refresh = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const next = await request(
          "/api/monitor",
          undefined,
          controller.signal,
        );
        setState(next);
        setPollError("");
        if (first && next.config) {
          setName(next.config.name);
          setWhen(localInput(new Date(next.config.occurred_at)));
          setTerms(next.config.exclude_terms.join(", "));
        }
        first = false;
      } catch (e) {
        if (e instanceof Error && e.name !== "AbortError")
          setPollError(e.message);
      } finally {
        inFlight = false;
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, []);
  async function start(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setState(
        await request("/api/monitor/start", {
          name,
          occurred_at: new Date(when).toISOString(),
          exclude_terms: terms
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean),
        }),
      );
      setSelected("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start monitoring");
    } finally {
      setBusy(false);
    }
  }
  async function stop() {
    setBusy(true);
    try {
      setState(await request("/api/monitor/stop", {}));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not stop monitoring");
    } finally {
      setBusy(false);
    }
  }
  const topic =
    state?.topics.find((t) => t.id === selected) || state?.topics[0];
  const active = !!state?.active;
  const lag = state?.latestHour
    ? Math.max(
        0,
        Math.round(
          (Date.now() - new Date(state.latestHour).getTime() - 3600000) / 60000,
        ),
      )
    : null;
  const baselineReady = state?.baselineReady || 0;
  return (
    <section className="live-monitor">
      <div className="live-title">
        <div>
          <div className="section-kicker">
            RECENT EVENTS / AUTOMATIC DISCOVERY
          </div>
          <h2>The unexpected, as it emerges.</h2>
          <p>
            Scan English Wikipedia for sudden attention spikes. No hand-picked
            topic list.
          </p>
        </div>
        <span className={`monitor-badge ${active ? "is-active" : ""}`}>
          <span className="live-dot" />
          {active
            ? "MONITOR RUNNING"
            : state?.phase === "idle" || !state
              ? "READY TO OBSERVE"
              : "LAST OBSERVATIONS"}
        </span>
      </div>
      <form className="monitor-form" onSubmit={start}>
        <label>
          Event name
          <input
            required
            minLength={3}
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={active || busy}
            placeholder="The recent event you want to investigate"
          />
        </label>
        <label>
          Event occurred · your local time
          <input
            required
            type="datetime-local"
            value={when}
            onChange={(e) => setWhen(e.target.value)}
            max={localInput(new Date())}
            min={localInput(new Date(Date.now() - 24 * 3600000))}
            disabled={active || busy}
          />
        </label>
        <label>
          Headline terms to exclude <span>Optional · comma separated</span>
          <input
            value={terms}
            onChange={(e) => setTerms(e.target.value)}
            disabled={active || busy}
            placeholder="eclipse, solar"
          />
        </label>
        <div className="monitor-form-actions">
          {active ? (
            <button
              type="button"
              className="outline-button"
              onClick={stop}
              disabled={busy}
            >
              {busy ? (
                <LoaderCircle className="spin" size={14} />
              ) : (
                <Square size={13} />
              )}{" "}
              Stop monitoring
            </button>
          ) : (
            <button type="submit" className="primary-button" disabled={busy}>
              {busy ? (
                <LoaderCircle className="spin" size={14} />
              ) : (
                <Play size={14} />
              )}{" "}
              Start monitoring
            </button>
          )}
        </div>
      </form>
      <p className="monitor-disclosure">
        <Clock3 size={13} /> Hourly public data, with publication and processing
        delay. First run downloads full dumps and can take several minutes. This
        is real monitoring, not a simulated stream.
      </p>
      {(error || pollError) && (
        <div className="monitor-error" role="alert">
          {error || pollError}
        </div>
      )}
      <div
        className={`monitor-status phase-${state?.phase || "idle"}`}
        role="status"
      >
        <span>
          {active ? (
            <LoaderCircle className="spin" size={17} />
          ) : (
            <Radio size={17} />
          )}
        </span>
        <div>
          <strong>
            {state?.config?.name || "Your next observation starts here"}
          </strong>
          <p>{state?.message || "Connecting to the monitor…"}</p>
        </div>
        <span className="phase-label">
          {state?.phase?.replaceAll("_", " ") || "connecting"}
        </span>
      </div>
      <div className="monitor-stages">
        {[
          [
            Database,
            "Build baseline",
            `${baselineReady}/3 prior hours`,
            baselineReady === 3,
          ],
          [
            Activity,
            "Scan all eligible articles",
            state?.scannedArticles
              ? `${number(state.scannedArticles)} in latest hour`
              : "Waiting for event data",
            !!state?.scannedArticles,
          ],
          [
            Waves,
            "Discover the unexpected",
            `${state?.candidateCount || 0} candidate spikes`,
            !!state?.latestHour,
          ],
        ].map(([Icon, title, detail, ready], i) => {
          const C = Icon as typeof Database;
          return (
            <div key={i} className={ready ? "stage-ready" : ""}>
              {ready ? <Check size={17} /> : <C size={17} />}
              <span>
                <strong>{title as string}</strong>
                <small>{detail as string}</small>
              </span>
            </div>
          );
        })}
      </div>
      <section
        className="metrics live-metrics"
        aria-label="Live ingestion metrics"
      >
        <article>
          <span>SOURCE ROWS COVERED</span>
          <div>
            {compact(state?.sourceRecords)}
            <small>{state?.processedHours || 0} completed hours</small>
          </div>
        </article>
        <article>
          <span>LATEST OBSERVATION</span>
          <div className="watermark">
            {state?.latestHour
              ? new Date(state.latestHour).toLocaleTimeString("en-GB", {
                  hour: "2-digit",
                  minute: "2-digit",
                  timeZone: "UTC",
                }) + " UTC"
              : "—"}
            <small>
              hour beginning ·{" "}
              {state?.latestHour
                ? new Date(state.latestHour).toLocaleDateString("en", {
                    month: "short",
                    day: "numeric",
                    timeZone: "UTC",
                  })
                : "waiting"}
            </small>
          </div>
        </article>
        <article>
          <span>DATA AGE AFTER HOUR END</span>
          <div>
            {lag === null ? "—" : lag}
            <small>
              {lag === null
                ? "not yet available"
                : "minutes · includes processing"}
            </small>
          </div>
        </article>
        <article>
          <span>DISCOVERED SPIKES</span>
          <div>
            {state?.candidateCount ?? "—"}
            <small>strongest 24 visualized</small>
          </div>
        </article>
      </section>
      {state && state.timeline.length > 0 && (
        <div className="live-arrivals" aria-label="Observed post-event hours">
          <span className="eyebrow">OBSERVED HOURS</span>
          {state.timeline.map((frame) => (
            <div key={frame.hour}>
              <time>
                {new Date(frame.hour).toLocaleTimeString("en-GB", {
                  hour: "2-digit",
                  minute: "2-digit",
                  timeZone: "UTC",
                })}{" "}
                UTC
              </time>
              <strong>{frame.candidates}</strong>
              <span>spike candidates</span>
            </div>
          ))}
        </div>
      )}
      {state && state.topics.length > 0 ? (
        <>
          <div className="observation-panel live-field-panel">
            <div className="panel-head">
              <div>
                <h3>Discovery constellation</h3>
                <span>
                  Automatically selected from the latest observed hour. Not
                  attributed to the event.
                </span>
              </div>
              <span className="micro">
                {state.edges.length} co-movement links
              </span>
            </div>
            <div className="live-discovery-layout">
              <div>
                <DiscoveryGraph
                  state={state}
                  selected={topic?.id || ""}
                  select={setSelected}
                />
                <p className="graph-evidence-note">
                  Links require at least five shared hourly observations and
                  correlation ≥ 0.85. An empty graph is a valid result; the app
                  never invents connections.
                </p>
              </div>
              {topic && (
                <aside className="inspector live-inspector">
                  <div className="eyebrow">AUTOMATICALLY DISCOVERED</div>
                  <h3>{topic.title}</h3>
                  <div className="inspector-value">
                    {compact(topic.views)}
                    <span>views in the latest hour</span>
                  </div>
                  <div
                    className="sparkbars"
                    role="img"
                    aria-label="Observed hourly traffic; dark bars are the baseline"
                  >
                    {topic.series.map((p) => (
                      <span
                        key={p.hour}
                        title={`${p.hour}: ${p.views === null ? "missing" : number(p.views)} views`}
                        style={{
                          height:
                            p.views === null
                              ? "0%"
                              : `${Math.max(2, (p.views / Math.max(...topic.series.map((q) => q.views || 0), 1)) * 100)}%`,
                          background: p.baseline ? "#52644b" : "#c3f967",
                        }}
                      />
                    ))}
                  </div>
                  <dl className="signal-stats">
                    <div>
                      <dt>Current lift</dt>
                      <dd className="lime">{topic.lift.toFixed(1)}×</dd>
                    </div>
                    <div>
                      <dt>Baseline per hour</dt>
                      <dd>{number(topic.baseline)}</dd>
                    </div>
                    <div>
                      <dt>Burst score</dt>
                      <dd>{topic.z.toFixed(1)}</dd>
                    </div>
                    <div>
                      <dt>Excess views</dt>
                      <dd>{number(topic.excess)}</dd>
                    </div>
                  </dl>
                  <a
                    className="article-link"
                    href={`https://en.wikipedia.org/wiki/${topic.id}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Investigate this topic <ArrowUpRight size={14} />
                  </a>
                  <p className="micro">
                    Could reflect your event, other news, daily cycles, or
                    automated traffic. Investigate before attributing it.
                  </p>
                </aside>
              )}
            </div>
          </div>
          <div className="live-candidates">
            <div className="signals-heading">
              <h3>The newly detected trail</h3>
              <span className="micro">
                Sorted by excess attention · {stamp(state.latestHour)}
              </span>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>DISCOVERED TOPIC</th>
                    <th>CURRENT VIEWS</th>
                    <th>BASELINE / HOUR</th>
                    <th>LIFT</th>
                    <th>BURST SCORE</th>
                  </tr>
                </thead>
                <tbody>
                  {state.topics.map((t) => (
                    <tr
                      key={t.id}
                      className={topic?.id === t.id ? "selected-row" : ""}
                    >
                      <td>
                        <button
                          className="topic-table-button"
                          onClick={() => setSelected(t.id)}
                        >
                          {t.title}
                        </button>
                      </td>
                      <td className="numeric">{number(t.views)}</td>
                      <td className="numeric">{number(t.baseline)}</td>
                      <td className="numeric lime">{t.lift.toFixed(1)}×</td>
                      <td className="numeric">{t.z.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <div className="live-empty">
          <div className="radar-rings">
            <Radio size={32} />
          </div>
          <h3>
            {state?.latestHour
              ? "No spikes meet the detection threshold."
              : "Waiting for the first discovery."}
          </h3>
          <p>
            {state?.latestHour
              ? "This is an observed result, not an error. The monitor will keep checking for newly published hours."
              : "Three pre-event hourly files establish the baseline. As post-event files arrive, Spark scans the broad article universe and the graph grows from observed evidence."}
          </p>
        </div>
      )}
      <div className="monitor-bottom">
        <section className="monitor-log">
          <div className="eyebrow">INGESTION JOURNAL</div>
          {state?.log?.length ? (
            state.log
              .slice(-8)
              .reverse()
              .map((entry, i) => (
                <div key={`${entry.time}-${i}`}>
                  <time>
                    {new Date(entry.time).toLocaleTimeString("en-GB", {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </time>
                  <p>{entry.message}</p>
                </div>
              ))
          ) : (
            <p className="muted">
              No background job is running. Start a monitor to see each
              ingestion step.
            </p>
          )}
        </section>
        <section className="monitor-method">
          <div className="eyebrow">WHAT “UNEXPECTED” MEANS HERE</div>
          <p>
            At least 200 hourly views, 3× the pre-event mean, 100 excess views,
            and a burst score of 4 or more. A title must appear in all three
            baseline hours.
          </p>
          <p>
            Headline exclusions are literal text filters. They do not establish
            semantic unrelatedness, and co-movement does not establish cause.
          </p>
          <p>
            The short baseline makes this an exploratory demo, sensitive to
            daily cycles and other news. It observes for up to 24 hours while
            the server runs.
          </p>
          {state?.nextCheckAt && active && (
            <span className="micro">
              Next source check: {stamp(state.nextCheckAt)}
            </span>
          )}
        </section>
      </div>
    </section>
  );
}
