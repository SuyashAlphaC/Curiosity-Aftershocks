import LiveMonitor from "./LiveMonitor";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Atom,
  Check,
  ChevronDown,
  CircleHelp,
  Database,
  ExternalLink,
  Focus,
  GitBranch,
  Globe2,
  Layers3,
  LoaderCircle,
  Pause,
  Play,
  Radio,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Telescope,
  X,
} from "lucide-react";
import type { Pipeline, Study, Topic } from "./types";

const palette = [
  "#c3f967",
  "#8dbaff",
  "#c1a2f9",
  "#ffb77b",
  "#6dd9ce",
  "#f193b6",
];
const fmt = (n: number) =>
  Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
const full = (n: number) => Intl.NumberFormat("en").format(Math.round(n));
const dayLabel = (day: number) =>
  day === 0 ? "Event day" : `Day ${day > 0 ? "+" : ""}${day}`;
const dateLabel = (date: string) =>
  new Date(date + "T12:00:00Z").toLocaleDateString("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function Constellation({
  study,
  day,
  selected,
  onSelect,
  query,
  threshold,
}: {
  study: Study;
  day: number;
  selected: string;
  onSelect: (id: string) => void;
  query: string;
  threshold: number;
}) {
  const categories = [...new Set(study.topics.map((t) => t.category))];
  const color = (t: Topic) =>
    t.category === "Control"
      ? "#78838c"
      : palette[categories.indexOf(t.category) % palette.length];
  const nodes = useMemo(() => {
    const others = study.topics.filter((t) => t.id !== study.seed);
    return study.topics.map((t) => {
      if (t.id === study.seed) return { ...t, x: 420, y: 241 };
      const index = others.findIndex((o) => o.id === t.id);
      const angle = index * 2.399963229728653 + 0.3;
      const ring = index < 6 ? 115 : index < 12 ? 190 : 258;
      return {
        ...t,
        x: 420 + Math.cos(angle) * ring * 1.23,
        y: 241 + Math.sin(angle) * ring * 0.74,
      };
    });
  }, [study]);
  const visible = new Set(
    nodes
      .filter((t) => t.title.toLowerCase().includes(query.toLowerCase()))
      .map((t) => t.id),
  );
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return (
    <div className="constellation-wrap">
      <div className="orbit-caption">
        <span className="live-dot" /> OBSERVATION FIELD{" "}
        <span>EN.WIKIPEDIA</span>
      </div>
      <svg
        className="constellation"
        viewBox="0 0 840 500"
        role="group"
        aria-label="Interactive topic constellation; select a topic to inspect its traffic"
      >
        <defs>
          <radialGradient id="field">
            <stop offset="0" stopColor="#b8e578" stopOpacity=".08" />
            <stop offset="1" stopColor="#b8e578" stopOpacity="0" />
          </radialGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="4" />
          </filter>
          <pattern
            id="dots"
            width="24"
            height="24"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="1" cy="1" r=".7" fill="#71818b" opacity=".22" />
          </pattern>
        </defs>
        <rect width="840" height="500" fill="url(#dots)" />
        <ellipse cx="420" cy="241" rx="360" ry="235" fill="url(#field)" />
        {[95, 170, 245].map((r) => (
          <ellipse
            key={r}
            cx="420"
            cy="241"
            rx={r * 1.23}
            ry={r * 0.74}
            fill="none"
            stroke="#34422f"
            strokeDasharray="3 8"
            opacity=".45"
          />
        ))}
        <path
          d="M420 15V467M35 241H805"
          stroke="#526144"
          strokeDasharray="2 9"
          opacity=".23"
        />
        {study.edges
          .filter((e) => e.correlation >= threshold)
          .map((edge, i) => {
            const a = byId.get(edge.source)!,
              b = byId.get(edge.target)!;
            const active = edge.source === selected || edge.target === selected;
            const shown = visible.has(a.id) && visible.has(b.id);
            return (
              <path
                key={i}
                d={`M${a.x},${a.y} Q420,241 ${b.x},${b.y}`}
                fill="none"
                stroke={active ? "#c3f967" : "#8bafa2"}
                strokeWidth={active ? 1.3 : 0.65}
                opacity={!shown ? 0.025 : active ? 0.55 : 0.12}
                className={active ? "active-link" : ""}
              />
            );
          })}
        {nodes.map((node) => {
          const point = node.series.find((p) => p.day === day)!;
          const radius = Math.min(24, 5 + Math.log2(1 + point.lift) * 3);
          const isSeed = node.id === study.seed,
            isSelected = node.id === selected;
          const title =
            node.title.length > 25 ? node.title.slice(0, 23) + "…" : node.title;
          return (
            <g
              key={node.id}
              transform={`translate(${node.x},${node.y})`}
              className="topic-node"
              role="button"
              tabIndex={visible.has(node.id) ? 0 : -1}
              aria-label={`Inspect ${node.title}`}
              aria-pressed={isSelected}
              onClick={() => onSelect(node.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(node.id);
                }
              }}
              opacity={visible.has(node.id) ? 1 : 0.1}
            >
              <title>
                {node.title}: {full(point.views)} views ·{" "}
                {point.lift.toFixed(1)}× baseline
              </title>
              {(isSeed || isSelected) && (
                <circle
                  r={radius + 12}
                  fill="none"
                  stroke={color(node)}
                  strokeOpacity=".35"
                  strokeDasharray={isSelected ? "none" : "3 5"}
                />
              )}
              <circle
                r={radius + 5}
                fill={color(node)}
                opacity=".12"
                filter="url(#glow)"
              />
              <circle
                r={radius}
                fill={color(node)}
                fillOpacity={isSelected ? ".95" : ".18"}
                stroke={color(node)}
                strokeWidth={isSelected ? 2 : 1}
              />
              <circle
                r={isSeed ? 4 : 2.5}
                fill={isSelected ? "#182114" : color(node)}
              />
              <text
                y={radius + 24}
                textAnchor="middle"
                fill={isSelected ? "#e6f3db" : "#a6b1ba"}
                fontSize={isSeed ? 12 : 10.5}
                fontWeight={isSeed ? 600 : 400}
              >
                {title}
              </text>
              {(isSeed || isSelected) && (
                <text
                  y={radius + 39}
                  textAnchor="middle"
                  fill={color(node)}
                  fontSize="10"
                  fontFamily="monospace"
                >
                  {point.lift.toFixed(1)}× BASELINE
                </text>
              )}
            </g>
          );
        })}
        <text x="22" y="478" fill="#74818a" fontSize="9" fontFamily="monospace">
          NODE SIZE = ATTENTION LIFT
        </text>
        <text
          x="817"
          y="478"
          textAnchor="end"
          fill="#74818a"
          fontSize="9"
          fontFamily="monospace"
        >
          EDGES = LAGGED CORRELATION
        </text>
      </svg>
      <div className="legend">
        {categories.map((c, i) => (
          <span key={c}>
            <i
              style={{
                background:
                  c === "Control" ? "#78838c" : palette[i % palette.length],
              }}
            />
            {c}
          </span>
        ))}
      </div>
    </div>
  );
}

function Timeline({
  study,
  day,
  setDay,
}: {
  study: Study;
  day: number;
  setDay: (day: number) => void;
}) {
  const max = Math.max(...study.timeline.map((p) => p.views), 1);
  const x = (i: number) => 30 + (i / 49) * 760;
  const y = (v: number) => 132 - (v / max) * 112;
  const path = study.timeline
    .map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.views)}`)
    .join(" ");
  return (
    <div className="timeline-wrap">
      <svg
        viewBox="0 0 820 164"
        role="img"
        aria-label="Daily pageviews over 28 days before and 21 days after the event"
      >
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#c3f967" stopOpacity=".25" />
            <stop offset="1" stopColor="#c3f967" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line
              x1="30"
              x2="790"
              y1={y(max * f)}
              y2={y(max * f)}
              stroke="#222d35"
              strokeDasharray="3 5"
            />
            <text
              x="785"
              y={y(max * f) - 5}
              fill="#78848c"
              textAnchor="end"
              fontSize="9"
            >
              {fmt(max * f)}
            </text>
          </g>
        ))}
        <path d={`${path} L790,132 L30,132 Z`} fill="url(#area)" />
        <path d={path} fill="none" stroke="#c3f967" strokeWidth="2" />
        <line
          x1="30"
          x2="790"
          y1={y(study.timeline[0].baseline)}
          y2={y(study.timeline[0].baseline)}
          stroke="#8dbaff"
          strokeDasharray="5 5"
          opacity=".7"
        />
        <line
          x1={x(28)}
          x2={x(28)}
          y1="12"
          y2="135"
          stroke="#c3f967"
          strokeDasharray="3 4"
          opacity=".45"
        />
        <text x={x(28) + 6} y="12" fill="#c3f967" fontSize="9">
          EVENT
        </text>
        <line
          x1={x(day + 28)}
          x2={x(day + 28)}
          y1="18"
          y2="135"
          stroke="#fff"
          opacity=".5"
        />
        <circle
          cx={x(day + 28)}
          cy={y(study.timeline[day + 28].views)}
          r="4"
          fill="#c3f967"
          stroke="#0b1014"
          strokeWidth="2"
        />
        {[-28, -21, -14, -7, 0, 7, 14, 21].map((d) => (
          <text
            key={d}
            x={x(d + 28)}
            y="154"
            textAnchor="middle"
            fill="#7e8c96"
            fontSize="10"
          >
            {d > 0 ? "+" : ""}
            {d}d
          </text>
        ))}
      </svg>
      <input
        className="timeline-slider"
        type="range"
        min="-28"
        max="21"
        value={day}
        onChange={(e) => setDay(+e.target.value)}
        aria-label="Replay day"
      />
    </div>
  );
}

function Inspector({ topic, day }: { topic: Topic; day: number }) {
  const p = topic.series.find((v) => v.day === day)!;
  const peak = Math.max(...topic.series.map((s) => s.views), 1);
  return (
    <aside className="inspector">
      <div className="eyebrow">
        <span className="live-dot" /> SIGNAL INSPECTOR
      </div>
      <div className="topic-chip">{topic.category}</div>
      <h3>{topic.title}</h3>
      <p className="muted">
        A closer look at this topic’s attention signature.
      </p>
      <div className="inspector-value">
        {fmt(p.views)}
        <span>views · {dayLabel(day).toLowerCase()}</span>
      </div>
      <div
        className="sparkbars"
        role="img"
        aria-label="50-day traffic sparkline"
      >
        {topic.series.map((s) => (
          <span
            key={s.day}
            style={{
              height: `${Math.max(3, (s.views / peak) * 100)}%`,
              background:
                s.day === day ? "#eaffca" : s.day >= 0 ? "#a2d55b" : "#3a4c35",
            }}
          />
        ))}
      </div>
      <dl className="signal-stats">
        <div>
          <dt>Current lift</dt>
          <dd className="lime">{p.lift.toFixed(1)}×</dd>
        </div>
        <div>
          <dt>Peak lift</dt>
          <dd>{topic.peakLift.toFixed(1)}×</dd>
        </div>
        <div>
          <dt>Peak delay</dt>
          <dd>+{topic.peakDay} days</dd>
        </div>
        <div>
          <dt>Burst days · z ≥ 3</dt>
          <dd>{topic.burstDays}</dd>
        </div>
        <div>
          <dt>Temporal cluster</dt>
          <dd>C{topic.cluster + 1}</dd>
        </div>
        <div>
          <dt>Daily baseline</dt>
          <dd>{full(topic.baseline)}</dd>
        </div>
      </dl>
      <a
        className="article-link"
        href={`https://en.wikipedia.org/wiki/${encodeURIComponent(topic.id)}`}
        target="_blank"
        rel="noreferrer"
      >
        Explore on Wikipedia <ArrowUpRight size={15} />
      </a>
      <p className="micro">
        Aggregate pageviews. A connection does not imply that readers moved
        between articles.
      </p>
    </aside>
  );
}

function Methods({ study, pipeline }: { study: Study; pipeline: Pipeline }) {
  return (
    <section className="method-view">
      <div className="section-kicker">THE SCIENCE BEHIND THE SIGNAL</div>
      <h2>Curiosity, with receipts.</h2>
      <p className="section-intro">
        Every point is an observed Wikimedia count. Every inference has a
        boundary.
      </p>
      <div className="method-grid">
        {[
          [
            "01",
            "Observe",
            "50 days. 19 articles. One shared moment.",
            "We fetch 28 days before and 21 days after each event, including the event day. Cohorts are manually curated, with three everyday comparison topics. English Wikipedia, all access types, user traffic, daily granularity.",
          ],
          [
            "02",
            "Establish a baseline",
            "Fit the past. Never the aftermath.",
            "For each article, the baseline μ and population standard deviation σ use only the 28 pre-event days. Lift = views / max(μ, 1). Burst z = (views − μ) / max(σ, √μ, 1). A burst day has z ≥ 3.",
          ],
          [
            "03",
            "Find temporal signatures",
            "Similar shapes, different subjects.",
            "Spark MLlib KMeans groups L2-normalized log(1 + lift) vectors across the 22 post-event days. Four clusters, fixed random seed 42. Cluster IDs are arbitrary, not semantic labels.",
          ],
          [
            "04",
            "Explore relationships",
            "A connection is a hypothesis.",
            "For each pair in the curated cohort, we compare log(1 + views) over post-event days at lags from −5 to +5 days. Edges show the strongest positive Pearson correlation ≥ 0.72. This search is exploratory; there is no causal or statistical significance claim.",
          ],
        ].map(([n, t, h, p]) => (
          <article key={n} className="method-card">
            <span className="step-number">{n}</span>
            <div className="eyebrow">{t}</div>
            <h3>{h}</h3>
            <p>{p}</p>
          </article>
        ))}
      </div>
      <div className="evaluation">
        <div>
          <div className="eyebrow">
            HELD-OUT BASELINE CHECK · {study.shortTitle}
          </div>
          <h3>How predictable was ordinary attention?</h3>
          <p>
            Train a constant mean on days −28 through −8. Evaluate on days −7
            through −1. This tests baseline forecasting, not anomaly
            classification accuracy.
          </p>
        </div>
        <div>
          <strong>{full(study.evaluation.mae)}</strong>
          <span>MAE · views/article/day</span>
        </div>
        <div>
          <strong>{(study.evaluation.wape * 100).toFixed(1)}%</strong>
          <span>Weighted absolute error</span>
        </div>
      </div>
      <div className="limits">
        <CircleHelp size={20} />
        <div>
          <h3>Read the signal responsibly</h3>
          <ul>
            {pipeline.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function PipelineView({ pipeline }: { pipeline: Pipeline }) {
  return (
    <section className="pipeline-view">
      <div className="section-kicker">FROM OPEN DATA TO OBSERVATION</div>
      <h2>A real engine underneath.</h2>
      <p className="section-intro">
        Spark SQL transforms the observations. MLlib finds temporal structure.
        Parquet keeps the analytical layers inspectable.
      </p>
      <div className="pipeline-flow">
        {[
          [Globe2, "01 / INGEST", "Wikimedia", "Cached responses + SHA-256"],
          [
            Database,
            "02 / TRANSFORM",
            "Spark SQL",
            "Baselines, bursts, window functions",
          ],
          [
            GitBranch,
            "03 / DISCOVER",
            "Spark MLlib",
            "Temporal KMeans + lag analysis",
          ],
          [Layers3, "04 / SERVE", "Parquet → API", "Atomic published artifact"],
        ].map(([Icon, step, title, desc], i) => {
          const C = Icon as typeof Globe2;
          return (
            <article key={i}>
              <C size={26} />
              <span className="eyebrow">{step as string}</span>
              <h3>{title as string}</h3>
              <p>{desc as string}</p>
              {i < 3 && <ArrowRight className="flow-arrow" size={18} />}
            </article>
          );
        })}
      </div>
      <div className="run-card">
        <div>
          <span className="status-pill">
            <Check size={13} /> COMPLETED RUN
          </span>
          <h3>{pipeline.engine}</h3>
          <p>
            {pipeline.master} · {pipeline.partitions} shuffle partitions ·{" "}
            {pipeline.granularity} study observations
          </p>
          <span className="micro">
            Built {new Date(pipeline.builtAt).toLocaleString()}
          </span>
        </div>
        <div>
          <strong>{full(pipeline.records)}</strong>
          <span>study observations</span>
        </div>
        <div>
          <strong>{pipeline.durationSeconds}s</strong>
          <span>measured runtime</span>
        </div>
        <div>
          <strong>{pipeline.invalidRecords}</strong>
          <span>invalid records</span>
        </div>
      </div>
      {pipeline.bulk ? (
        <div className="bulk-card">
          <div className="eyebrow">
            LARGE-SCALE HOURLY INGESTION · MEASURED, NOT SIMULATED
          </div>
          <h3>{fmt(pipeline.bulk.records)} rows through Apache Spark.</h3>
          <p>
            A separate bulk path reads complete public gzip dumps and writes
            partitioned Parquet. These hourly counts are not mixed into the
            daily user-only studies.
          </p>
          <div className="bulk-metrics">
            <span>
              <strong>{full(pipeline.bulk.records)}</strong>source records
            </span>
            <span>
              <strong>{fmt(pipeline.bulk.recordsPerSecond)}/s</strong>observed
              throughput
            </span>
            <span>
              <strong>
                {(pipeline.bulk.inputBytes / 1024 / 1024).toFixed(1)} MB
              </strong>
              compressed input
            </span>
            <span>
              <strong>{pipeline.bulk.rejectedRecords}</strong>rejected records
            </span>
          </div>
          <details>
            <summary>Inspect hourly input and leading articles</summary>
            <code>{pipeline.bulk.files.join(", ")}</code>
            <div className="bulk-articles">
              {pipeline.bulk.topArticles.slice(0, 10).map((t) => (
                <div key={t.article}>
                  <span>{t.article.replaceAll("_", " ")}</span>
                  <b>{full(t.views)}</b>
                </div>
              ))}
            </div>
            <p className="micro">{pipeline.bulk.note}</p>
          </details>
        </div>
      ) : (
        <div className="bulk-card">
          <h3>Ready for full hourly dumps</h3>
          <p>
            Run <code>make bulk</code> to process a complete Wikimedia hourly
            dump through Spark. Measured scale results will appear here after
            completion.
          </p>
        </div>
      )}
      <div className="provenance">
        <div>
          <div className="eyebrow">DATA PROVENANCE</div>
          <h3>Open data. Traceable results.</h3>
          <p>
            {pipeline.source.source} · {pipeline.source.license}
          </p>
          <p className="micro">
            Fetched {new Date(pipeline.source.retrieved_at).toLocaleString()}
          </p>
          <code className="hash">SHA-256 {pipeline.source.sha256}</code>
        </div>
        <a
          href="https://dumps.wikimedia.org/other/pageviews/readme.html"
          target="_blank"
          rel="noreferrer"
        >
          Wikimedia documentation <ExternalLink size={15} />
        </a>
      </div>
    </section>
  );
}

export default function App() {
  const [studies, setStudies] = useState<Study[]>([]),
    [study, setStudy] = useState<Study | null>(null),
    [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [eventId, setEventId] = useState("eclipse"),
    [tab, setTab] = useState("Observatory"),
    [selected, setSelected] = useState("");
  const [day, setDay] = useState(0),
    [playing, setPlaying] = useState(false),
    [query, setQuery] = useState(""),
    [threshold, setThreshold] = useState(0.8);
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [retry, setRetry] = useState(0),
    [sort, setSort] = useState("excessViews");
  const [showControls, setShowControls] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      get<Study[]>("/api/events", controller.signal),
      get<Pipeline>("/api/pipeline", controller.signal),
    ])
      .then(([s, p]) => {
        setStudies(s);
        setPipeline(p);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [retry]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setPlaying(false);
    get<Study>(`/api/events/${eventId}`, controller.signal)
      .then((s) => {
        setStudy(s);
        setSelected(s.seed);
        setDay(0);
        setQuery("");
        setLoading(false);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [eventId, retry]);
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(
      () =>
        setDay((d) => {
          if (d >= 21) {
            setPlaying(false);
            return 21;
          }
          return d + 1;
        }),
      650,
    );
    return () => clearInterval(timer);
  }, [playing]);
  const topic = study?.topics.find((t) => t.id === selected);
  const topics =
    study?.topics
      .filter(
        (t) =>
          (showControls || t.category !== "Control") &&
          t.title.toLowerCase().includes(query.toLowerCase()),
      )
      .sort((a, b) =>
        sort === "peakDay"
          ? a.peakDay - b.peakDay
          : b[sort as "excessViews" | "peakLift"] -
            a[sort as "excessViews" | "peakLift"],
      ) || [];
  function changeDay(d: number) {
    setDay(d);
    setPlaying(false);
  }
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="app-shell">
        <aside className="rail">
          <a
            href="/"
            className="brand-mark"
            aria-label="Curiosity Aftershocks home"
          >
            <Atom size={27} />
          </a>
          <div className="rail-nav">
            {[
              [Telescope, "Observatory"],
              [Radio, "Live monitor"],
              [Database, "Data pipeline"],
              [CircleHelp, "Methodology"],
            ].map(([Icon, name]) => {
              const C = Icon as typeof Telescope;
              return (
                <button
                  key={name as string}
                  aria-label={name as string}
                  title={name as string}
                  className={tab === name ? "active" : ""}
                  onClick={() => setTab(name as string)}
                >
                  <C size={21} />
                </button>
              );
            })}
          </div>
          <span className="rail-bottom">CA / 01</span>
        </aside>
        <div className="workspace">
          <header className="topbar">
            <div className="wordmark">
              curiosity<span>aftershocks</span>
              <span className="beta">RESEARCH LAB</span>
            </div>
            <div className="top-right">
              <span className="source-badge">
                <span className="live-dot" /> REAL WIKIMEDIA DATA
              </span>
              <a
                href="https://github.com/wikimedia"
                target="_blank"
                rel="noreferrer"
                aria-label="Wikimedia on GitHub"
              >
                <Globe2 size={18} />
              </a>
            </div>
          </header>
          <main id="main">
            <div className="page-title">
              <div>
                <div className="eyebrow">
                  COLLECTIVE ATTENTION / AN EXPLORATORY OBSERVATORY
                </div>
                <h1>
                  The world happens.
                  <br />
                  Curiosity <em>ripples.</em>
                  <span className="title-star">✳</span>
                </h1>
                <p>Trace the unexpected places our questions take us.</p>
              </div>
              <div className="edition">
                <span>OPEN DATA, OPEN QUESTIONS</span>
                <div>
                  03{" "}
                  <span>
                    events.
                    <br />
                    Infinite rabbit holes.
                  </span>
                </div>
                <span className="edition-line" />
              </div>
            </div>
            <nav className="tabs" aria-label="Workspace views">
              {[
                "Observatory",
                "Live monitor",
                "Data pipeline",
                "Methodology",
              ].map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  aria-current={tab === t ? "page" : undefined}
                  className={tab === t ? "selected" : ""}
                >
                  {t === "Observatory" ? (
                    <Focus size={15} />
                  ) : t === "Live monitor" ? (
                    <Radio size={15} />
                  ) : t === "Data pipeline" ? (
                    <Database size={15} />
                  ) : (
                    <Layers3 size={15} />
                  )}{" "}
                  {t}
                </button>
              ))}
              <span className="tabs-note">
                A SMALL WINDOW INTO A VERY CURIOUS WORLD{" "}
                <ArrowDownToLine size={12} />
              </span>
            </nav>
            {tab === "Live monitor" ? (
              <LiveMonitor />
            ) : error ? (
              <section className="error-state" role="alert">
                <Activity size={30} />
                <h2>We couldn’t load the observations.</h2>
                <p>{error}</p>
                <button
                  className="primary-button"
                  onClick={() => setRetry((r) => r + 1)}
                >
                  Retry connection <RotateCcw size={15} />
                </button>
              </section>
            ) : loading || !study || !pipeline ? (
              <section className="loading-state" role="status">
                <LoaderCircle className="spin" size={30} />
                <p>Bringing the observation field into focus…</p>
              </section>
            ) : (
              <>
                <section
                  className="event-selector"
                  aria-label="Select an event"
                >
                  {studies.map((s, i) => (
                    <button
                      key={s.id}
                      className={`event-card ${eventId === s.id ? "chosen" : ""}`}
                      onClick={() => setEventId(s.id)}
                      aria-pressed={eventId === s.id}
                    >
                      <span
                        className={`event-art event-art-${s.id}`}
                        aria-hidden="true"
                      >
                        {s.id === "eclipse" ? (
                          <span className="eclipse-disc" />
                        ) : s.id === "moon" ? (
                          <span className="moon-disc" />
                        ) : (
                          <span className="ocean-lines" />
                        )}
                      </span>
                      <span className="event-card-text">
                        <span className="micro">
                          0{i + 1} / {s.category}
                        </span>
                        <strong>{s.shortTitle}</strong>
                        <span>{dateLabel(s.date)}</span>
                      </span>
                      <ArrowUpRight size={17} />
                    </button>
                  ))}
                </section>
                {tab === "Observatory" ? (
                  <>
                    <div className="study-heading">
                      <div>
                        <span className="section-kicker">
                          THE AFTERSHOCK / {study.location}
                        </span>
                        <h2>{study.title}</h2>
                        <p>{study.description}</p>
                      </div>
                      <a
                        className="outline-button"
                        href={`/api/events/${study.id}/export`}
                        download
                      >
                        <ArrowDownToLine size={15} /> Export data
                      </a>
                    </div>
                    <section className="metrics" aria-label="Event summary">
                      <article>
                        <span>
                          <Activity size={14} /> POST-EVENT PAGEVIEWS
                        </span>
                        <div>
                          {fmt(study.stats.totalViews)}
                          <small>across the cohort</small>
                        </div>
                      </article>
                      <article>
                        <span>
                          <Sparkles size={14} /> EXCESS ATTENTION
                        </span>
                        <div>
                          {fmt(study.stats.excessViews)}
                          <small>above daily baseline</small>
                        </div>
                      </article>
                      <article>
                        <span>
                          <Radio size={14} /> STRONGEST AFTERSHOCK
                        </span>
                        <div>
                          {fmt(study.stats.peakLift)}
                          <b>×</b>
                          <small>peak / baseline</small>
                        </div>
                      </article>
                      <article>
                        <span>
                          <GitBranch size={14} /> TOPICS IN ORBIT
                        </span>
                        <div>
                          {study.stats.topics}
                          <small>including 3 controls</small>
                        </div>
                      </article>
                    </section>
                    <section className="observation-panel">
                      <div className="panel-head">
                        <div>
                          <h3>
                            <span className="tiny-orbit" /> The curiosity
                            constellation
                          </h3>
                          <span>
                            Follow a signal. Find an unexpected connection.
                          </span>
                        </div>
                        <div className="graph-tools">
                          <label className="search-box">
                            <Search size={14} />
                            <input
                              value={query}
                              onChange={(e) => setQuery(e.target.value)}
                              placeholder="Find a topic…"
                              aria-label="Find a topic"
                            />
                            {query && (
                              <button
                                onClick={() => setQuery("")}
                                aria-label="Clear search"
                              >
                                <X size={12} />
                              </button>
                            )}
                          </label>
                          <span title="Inspect topics by clicking a node">
                            <Focus size={16} />
                          </span>
                        </div>
                      </div>
                      <div className="observation-grid">
                        <div className="field">
                          <Constellation
                            study={study}
                            day={day}
                            selected={selected}
                            onSelect={setSelected}
                            query={query}
                            threshold={threshold}
                          />
                          <div className="correlation-control">
                            <SlidersHorizontal size={13} />
                            <label htmlFor="correlation">
                              Minimum correlation
                            </label>
                            <input
                              id="correlation"
                              type="range"
                              min="0.72"
                              max="0.99"
                              step="0.01"
                              value={threshold}
                              onChange={(e) => setThreshold(+e.target.value)}
                            />
                            <output>{threshold.toFixed(2)}</output>
                            <span>
                              {
                                study.edges.filter(
                                  (e) => e.correlation >= threshold,
                                ).length
                              }{" "}
                              connections
                            </span>
                          </div>
                        </div>
                        {topic && <Inspector topic={topic} day={day} />}
                      </div>
                      <div className="replay">
                        <div className="replay-heading">
                          <div>
                            <h3>Replay the ripple</h3>
                            <span>28 days before → 21 days after</span>
                          </div>
                          <div className="replay-actions">
                            <span className="replay-date" aria-live="polite">
                              {dayLabel(day)}{" "}
                              <span>
                                / {dateLabel(study.timeline[day + 28].date)}
                              </span>
                            </span>
                            <button
                              className="reset-button"
                              onClick={() => changeDay(0)}
                              aria-label="Reset to event day"
                            >
                              <RotateCcw size={14} />
                            </button>
                            <button
                              className="play-button"
                              onClick={() => {
                                if (day >= 21) setDay(-28);
                                setPlaying(!playing);
                              }}
                              aria-label={
                                playing ? "Pause replay" : "Play replay"
                              }
                            >
                              {playing ? (
                                <Pause size={13} />
                              ) : (
                                <Play size={13} />
                              )}{" "}
                              {playing ? "Pause" : "Play"}
                            </button>
                          </div>
                        </div>
                        <Timeline study={study} day={day} setDay={changeDay} />
                        <div className="timeline-legend">
                          <span>
                            <i />
                            Observed pageviews
                          </span>
                          <span>
                            <i />
                            Pre-event baseline
                          </span>
                          <span>UTC · Daily observations</span>
                        </div>
                      </div>
                    </section>
                    <section className="signals-section">
                      <div className="signals-heading">
                        <div>
                          <div className="section-kicker">
                            BEYOND THE HEADLINE
                          </div>
                          <h2>
                            The attention trail
                            <span>
                              {topics.length.toString().padStart(2, "0")}
                            </span>
                          </h2>
                        </div>
                        <div className="table-controls">
                          <label className="checkbox-label">
                            <input
                              type="checkbox"
                              checked={showControls}
                              onChange={(e) =>
                                setShowControls(e.target.checked)
                              }
                            />{" "}
                            Show controls
                          </label>
                          <label className="sort-label">
                            <span className="sr-only">Sort topics</span>
                            <select
                              value={sort}
                              onChange={(e) => setSort(e.target.value)}
                            >
                              <option value="excessViews">
                                Excess attention
                              </option>
                              <option value="peakLift">Peak lift</option>
                              <option value="peakDay">Peak delay</option>
                            </select>
                            <ChevronDown size={13} />
                          </label>
                        </div>
                      </div>
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>TOPIC</th>
                              <th>ATTENTION SHAPE</th>
                              <th>PEAK LIFT</th>
                              <th>PEAK DELAY</th>
                              <th>EXCESS VIEWS</th>
                              <th>
                                <span className="sr-only">Inspect</span>
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {topics.map((t, i) => (
                              <tr
                                key={t.id}
                                className={
                                  selected === t.id ? "selected-row" : ""
                                }
                              >
                                <td>
                                  <button
                                    className="topic-table-button"
                                    onClick={() => setSelected(t.id)}
                                  >
                                    <span className="row-index">
                                      {String(i + 1).padStart(2, "0")}
                                    </span>
                                    <span>
                                      <strong>{t.title}</strong>
                                      <small>
                                        {t.category} · Cluster {t.cluster + 1}
                                      </small>
                                    </span>
                                  </button>
                                </td>
                                <td>
                                  <div
                                    className="mini-bars"
                                    aria-label="Attention shape"
                                  >
                                    {t.series
                                      .filter((p) => p.day >= 0)
                                      .map((p) => (
                                        <i
                                          key={p.day}
                                          style={{
                                            height: `${Math.max(4, (p.views / Math.max(...t.series.filter((v) => v.day >= 0).map((v) => v.views), 1)) * 100)}%`,
                                          }}
                                        />
                                      ))}
                                  </div>
                                </td>
                                <td className="lime numeric">
                                  {t.peakLift.toFixed(1)}×
                                </td>
                                <td className="numeric">+{t.peakDay}d</td>
                                <td className="numeric">
                                  {fmt(t.excessViews)}
                                </td>
                                <td>
                                  <button
                                    className="inspect-button"
                                    onClick={() => {
                                      setSelected(t.id);
                                      document
                                        .querySelector(".observation-panel")
                                        ?.scrollIntoView({
                                          behavior: window.matchMedia(
                                            "(prefers-reduced-motion: reduce)",
                                          ).matches
                                            ? "instant"
                                            : "smooth",
                                        });
                                    }}
                                    aria-label={`Show ${t.title} in inspector`}
                                  >
                                    <ArrowUpRight size={16} />
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {!topics.length && (
                          <div className="empty-state">
                            No topics match “{query}”.{" "}
                            <button onClick={() => setQuery("")}>
                              Clear search
                            </button>
                          </div>
                        )}
                      </div>
                    </section>
                    <div className="insight-note">
                      <Atom size={22} />
                      <p>
                        <strong>Attention is a signal, not a journey.</strong>{" "}
                        These connections describe aggregate patterns. They
                        don’t track people, prove causality, or tell us why
                        someone clicked.
                      </p>
                      <button onClick={() => setTab("Methodology")}>
                        Read the methodology <ArrowRight size={15} />
                      </button>
                    </div>
                  </>
                ) : tab === "Methodology" ? (
                  <Methods study={study} pipeline={pipeline} />
                ) : (
                  <PipelineView pipeline={pipeline} />
                )}
              </>
            )}
            <footer>
              <div>
                <Atom size={17} /> curiosity aftershocks{" "}
                <span>AN OPEN-DATA EXPLORATION</span>
              </div>
              <span>
                Built with Apache Spark · Powered by collective curiosity{" "}
                <span className="lime">↗</span>
              </span>
            </footer>
          </main>
        </div>
      </div>
    </>
  );
}
