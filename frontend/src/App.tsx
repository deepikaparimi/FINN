import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  Search,
  Settings2,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import priceFixture from "../../fixtures/prices.json";
import announcementFixture from "../../fixtures/announcements.json";
import researchDemo from "../../config/research_demo.json";

type Screen = "digest" | "alerts" | "research";
type Decision = "watch" | "dismiss";
type PriceRow = { ticker: string; date: string; close: number; volume: number; source?: string };
type Announcement = {
  id?: string;
  ticker: string;
  company: string;
  time: string;
  subject: string;
  category?: string;
  level?: number;
  attachment_link?: string;
  source?: string;
  headline?: string;
  filing_text?: string;
  why_it_matters?: string;
  results_metrics?: Array<{ label: string; value: number | null; qoq_percent: number | null; yoy_percent: number | null }>;
  verdict?: "Strong" | "Mixed" | "Weak" | "Unclear";
  verdict_reason?: string;
  market_context?: { volume_ratio: number | null; price_change_pct: number | null } | null;
};
type TopItem = Pick<Announcement, "id" | "ticker" | "category" | "level" | "time" | "verdict" | "results_metrics" | "market_context">;
type AlertItem = {
  id?: string;
  ticker: string;
  company_name?: string;
  company?: string;
  date: string;
  type: "price_move" | "volume_spike" | string;
  value: number;
  threshold: number;
  average_volume_20d?: number;
  summary: string;
};
type Rules = { volume_multiplier: number; price_change_percent: number };
type DecisionMap = Record<string, Decision>;
type FixturePrices = { prices: Record<string, Array<{ date: string; close: number; volume: number }>> };
type TrendMetrics = {
  periods: string[];
  trajectory: {
    revenue: Array<number | null>;
    profit: Array<number | null>;
    revenue_growth_percent: Array<number | null>;
    profit_growth_percent: Array<number | null>;
  };
  snapshot: {
    period?: string | null;
    revenue?: number | null;
    profit?: number | null;
    revenue_growth_percent?: number | null;
    profit_growth_percent?: number | null;
    net_margin_percent?: number | null;
    operating_margin_percent?: number | null;
  };
  balance_sheet: { period?: string | null; borrowings?: number | null; equity?: number | null; debt_to_equity?: number | null };
  cash_quality: {
    period?: string | null;
    operating_cash_flow?: number | null;
    profit_after_tax?: number | null;
    cash_conversion?: number | null;
    free_cash_flow?: number | null;
    free_cash_flow_method?: string;
  };
};
type ResearchPayload = {
  found: boolean;
  ticker: string;
  company_name?: string;
  price?: number | null;
  source_url?: string;
  saved_at?: string;
  metrics?: TrendMetrics;
  message?: string;
};

const rulesKey = "finn-push-alert-rules-v1";
const decisionsKey = "finn-push-decisions-v1";
const fixturePriceData = priceFixture as FixturePrices;
const fixtureAnnouncements = announcementFixture as Announcement[];
const defaultRules: Rules = { volume_multiplier: 2, price_change_percent: 3 };
const periods = [
  { label: "6H", hours: 6 },
  { label: "24H", hours: 24 },
  { label: "3D", hours: 72 },
  { label: "7D", hours: 168 },
];

export default function App() {
  const [screen, setScreen] = useState<Screen>("digest");
  const [hours, setHours] = useState(24);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [topItems, setTopItems] = useState<TopItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [prices, setPrices] = useState<PriceRow[]>([]);
  const [rules, setRules] = useState<Rules>(() => readStoredRules());
  const [ruleDraft, setRuleDraft] = useState<Rules>(() => readStoredRules());
  const [decisions, setDecisions] = useState<DecisionMap>(() => readDecisions());
  const [loading, setLoading] = useState(true);
  const [rulesSaving, setRulesSaving] = useState(false);
  const [routineExpanded, setRoutineExpanded] = useState(false);
  const [toast, setToast] = useState("");
  const [dataNote, setDataNote] = useState("Connecting to FINN");
  const [researchTicker, setResearchTicker] = useState("");
  const [researchQuery, setResearchQuery] = useState("");
  const [researchData, setResearchData] = useState<ResearchPayload | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);
  const [researchUnavailable, setResearchUnavailable] = useState(false);

  useEffect(() => {
    let current = true;
    setLoading(true);
    async function loadPush() {
      const [digestResponse, alertsResponse, rulesResponse, pricesResponse] = await Promise.all([
        getJson<{ announcements?: Announcement[]; top_items?: TopItem[] }>(`/api/digest?hours=${hours}`),
        getJson<{ alerts?: AlertItem[] }>("/api/alerts"),
        getJson<Rules>("/api/alert-rules"),
        getJson<{ prices?: PriceRow[] }>("/api/prices"),
      ]);
      if (!current) return;

      const priceRows = pricesResponse?.prices?.length
        ? normalizePriceRows(pricesResponse.prices)
        : fixtureRows();
      const loadedRules = rulesResponse && isValidRules(rulesResponse)
        ? rulesResponse
        : readStoredRules();
      const digestItems = digestResponse?.announcements
        ? digestResponse.announcements
        : fallbackDigest(fixtureAnnouncements, hours);
      const alertItems = alertsResponse?.alerts
        ? alertsResponse.alerts
        : calculateFixtureAlerts(priceRows, loadedRules);

      setPrices(priceRows);
      setRules({ volume_multiplier: loadedRules.volume_multiplier, price_change_percent: loadedRules.price_change_percent });
      setRuleDraft({ volume_multiplier: loadedRules.volume_multiplier, price_change_percent: loadedRules.price_change_percent });
      setAnnouncements(digestItems);
      setTopItems(digestResponse?.top_items ?? []);
      setAlerts(alertItems);
      const fixtureOnly = !digestResponse || !alertsResponse || !pricesResponse || !rulesResponse;
      const hasLivePriceRows = priceRows.some((row) => row.source === "yfinance");
      const hasSampleData = digestItems.some((item) => item.source === "sample")
        || priceRows.some((row) => row.source === "saved_sample" || row.source === "sample")
        || fixtureOnly;
      setDataNote(hasSampleData ? "Showing saved sample data" : hasLivePriceRows ? "FINN API · live prices" : "FINN API · saved data");
      setLoading(false);
    }
    void loadPush();
    return () => { current = false; };
  }, [hours]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 1900);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (screen !== "research" || !researchTicker) return;
    let current = true;
    setResearchLoading(true);
    setResearchData(null);
    setResearchUnavailable(false);
    void getJson<ResearchPayload>(`/api/research/${encodeURIComponent(researchTicker)}`)
      .then((result) => {
        if (!current) return;
        if (result) setResearchData(result);
        else setResearchUnavailable(true);
      })
      .finally(() => { if (current) setResearchLoading(false); });
    return () => { current = false; };
  }, [screen, researchTicker]);

  const visibleAnnouncements = useMemo(
    () => announcements.filter((item) => decisions[announcementId(item)] !== "dismiss"),
    [announcements, decisions],
  );
  const levelOne = visibleAnnouncements.filter((item) => item.level === 1);
  const levelTwo = visibleAnnouncements.filter((item) => item.level === 2);
  const levelThree = visibleAnnouncements.filter((item) => item.level !== 1 && item.level !== 2);
  const visibleAlerts = alerts.filter((item) => decisions[alertId(item)] !== "dismiss");

  function decide(id: string, value: Decision) {
    setDecisions((current) => {
      const next = { ...current, [id]: value };
      try { window.localStorage.setItem(decisionsKey, JSON.stringify(next)); } catch { /* Storage may be disabled. */ }
      return next;
    });
    setToast(value === "watch" ? "Added to Watch" : "Dismissed from your feed");
  }

  async function saveRules() {
    if (!isValidRules(ruleDraft)) return;
    setRulesSaving(true);
    let saved = false;
    try {
      const response = await fetch("/api/alert-rules", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ruleDraft),
      });
      if (response.ok) {
        const body = await response.json() as Rules;
        setRules({ volume_multiplier: body.volume_multiplier, price_change_percent: body.price_change_percent });
        saved = true;
      }
    } catch { /* Keep the edit locally if the API is unavailable. */ }
    if (!saved) {
      setRules(ruleDraft);
      setToast("Saved on this device · API unavailable");
    } else {
      setToast("Alert limits saved");
    }
    try { window.localStorage.setItem(rulesKey, JSON.stringify(ruleDraft)); } catch { /* Storage may be disabled. */ }
    const refreshedAlerts = await getJson<{ alerts?: AlertItem[] }>("/api/alerts");
    setAlerts(refreshedAlerts?.alerts ?? calculateFixtureAlerts(prices, ruleDraft));
    setRulesSaving(false);
  }

  function openResearch(ticker: string) {
    const symbol = ticker.trim().toUpperCase();
    setResearchTicker(symbol);
    setResearchQuery(symbol);
    setScreen("research");
  }

  function submitResearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const symbol = researchQuery.trim().toUpperCase();
    if (!symbol) return;
    setResearchTicker(symbol);
    setResearchQuery(symbol);
  }

  return (
    <main className="phone-shell">
      <header className="topbar">
        <a className="brand-mark" href="#digest" onClick={(event) => { event.preventDefault(); setScreen("digest"); }} aria-label="FINN Digest">
          <span className="brand-glyph">F</span><span>FINN<span className="brand-period">.</span></span>
        </a>
        <div className="topbar-right"><span className="sync-dot" /><span>{dataNote}</span><button className="icon-button" aria-label="Notifications"><Bell size={17} /></button></div>
      </header>

      <div className="content-wrap">
        {screen === "digest" && (
          <section aria-labelledby="digest-title">
            <div className="section-kicker"><span>DAILY BRIEFING</span><span className="kicker-rule" /></div>
            <div className="title-row"><div><h1 id="digest-title">The Digest</h1><p className="subhead">Signal across your portfolio.</p></div><div className="date-stamp"><Clock3 size={13} /> {dateStamp()}</div></div>

            <div className="period-control" role="tablist" aria-label="Digest time window">
              {periods.map((period) => <button key={period.hours} role="tab" aria-selected={hours === period.hours} className={hours === period.hours ? "period-option active" : "period-option"} onClick={() => { setRoutineExpanded(false); setHours(period.hours); }}>{period.label}</button>)}
            </div>

            {loading ? <DigestSkeleton /> : (
              <>
                <div className="digest-meta"><span>{visibleAnnouncements.length} filings</span><span className="meta-separator">/</span><span>{levelOne.length} priority</span></div>
                {topItems.length > 0 && <section className="top-three" aria-label="Top 3 right now"><div className="top-three-heading">TOP 3 RIGHT NOW</div>{topItems.map((item) => <button key={item.id || `${item.ticker}:${item.time}`} className="top-three-line" onClick={() => document.getElementById(`digest-${item.id || ""}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}><span>{item.ticker}: {topItemSummary(item)}</span><ChevronRight size={14} /></button>)}</section>}
                {visibleAnnouncements.length === 0 ? <EmptyState title="Nothing moved into focus." copy="No announcements in this window. Your quiet is intentional." /> : (
                  <div className="digest-list">
                    {levelOne.map((item) => {
                      const id = announcementId(item);
                      return <SwipeRow key={id} id={id} anchorId={`digest-${id}`} decision={decisions[id]} onDecide={decide} className="level-one-card">
                        <div className="item-overline"><span className="level-chip">01 <i /></span><span>{item.ticker}</span><span className="item-time">{relativeTime(item.time)}</span></div>
                        <div className="digest-headline-row"><h2>{item.headline || shortHeadline(item.subject, item.category)}</h2>{item.verdict && <span className={`verdict-chip verdict-${item.verdict.toLowerCase()}`}>{item.verdict}</span>}</div>
                        {item.verdict_reason && <p className="verdict-reason">{item.verdict_reason}</p>}
                        {item.market_context && <p className="market-context">{formatMarketContext(item.market_context)}</p>}
                        {item.why_it_matters && <p className="why-it-matters">{item.why_it_matters}</p>}
                        {item.results_metrics && item.results_metrics.some((metric) => metric.value !== null) && <ResultsTable metrics={item.results_metrics} />}
                        <FilingDisclosure text={item.filing_text || item.subject} />
                        <div className="item-foot"><span>{item.company}</span><button className="deep-link" onClick={() => openResearch(item.ticker)}>Dig deeper <ArrowRight size={13} /></button></div>
                        {item.attachment_link && <a className="source-link" href={item.attachment_link} target="_blank" rel="noreferrer">Open exchange filing <ArrowRight size={12} /></a>}
                      </SwipeRow>;
                    })}
                    {levelTwo.length > 0 && <div className="level-two-list"><div className="group-label">ALSO IN WINDOW <span>{String(levelTwo.length).padStart(2, "0")}</span></div>
                      {levelTwo.map((item) => {
                        const id = announcementId(item);
                        return <SwipeRow key={id} id={id} anchorId={`digest-${id}`} decision={decisions[id]} onDecide={decide} className="level-two-row">
                          <span className="level-two-marker" />
                          <div className="level-two-copy"><span className="ticker-tag">{item.ticker}</span><span className="level-two-subject">{item.headline || shortHeadline(item.subject, item.category)}</span><span className="item-time">{relativeTime(item.time)}</span>
                            {item.market_context && <span className="market-context">{formatMarketContext(item.market_context)}</span>}
                            {item.why_it_matters && <span className="why-it-matters">{item.why_it_matters}</span>}
                            <FilingDisclosure text={item.filing_text || item.subject} />
                          </div>
                          <button className="row-deep" aria-label={`Dig deeper into ${item.ticker}`} onClick={() => openResearch(item.ticker)}><ChevronRight size={16} /></button>
                        </SwipeRow>;
                      })}
                    </div>}
                    {levelThree.length > 0 && <div className="routine-block">
                      <button className="routine-toggle" aria-expanded={routineExpanded} onClick={() => setRoutineExpanded((value) => !value)}>
                        <span className="routine-count">{levelThree.length}</span><span>routine filings</span><span className="routine-hint">low relevance</span>{routineExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                      </button>
                      {routineExpanded && <div className="routine-items">{levelThree.map((item) => {
                        const id = announcementId(item);
                        return <SwipeRow key={id} id={id} decision={decisions[id]} onDecide={decide} className="routine-row"><span className="ticker-tag">{item.ticker}</span><span>{item.subject}</span><span className="item-time">{relativeTime(item.time)}</span></SwipeRow>;
                      })}</div>}
                    </div>}
                  </div>
                )}
              </>
            )}
          </section>
        )}

        {screen === "alerts" && (
          <section aria-labelledby="alerts-title">
            <div className="section-kicker"><span>WATCH THE TAPE</span><span className="kicker-rule" /></div>
            <div className="title-row"><div><h1 id="alerts-title">Alerts</h1><p className="subhead">Moves outside your comfort zone.</p></div><span className="alert-total">{loading ? "—" : String(visibleAlerts.length).padStart(2, "0")}</span></div>
            {loading ? <AlertSkeleton /> : visibleAlerts.length === 0 ? <EmptyState title="No thresholds crossed." copy="We’ll surface a signal when volume or price moves past your limits." /> : (
              <div className="alert-list">{visibleAlerts.map((item) => {
                const id = alertId(item);
                const history = prices.filter((price) => price.ticker === item.ticker).sort((a, b) => a.date.localeCompare(b.date));
                const isVolume = item.type === "volume_spike";
                const up = !isVolume && item.value >= 0;
                return <SwipeRow key={id} id={id} decision={decisions[id]} onDecide={decide} className="alert-row">
                  <div className="alert-card-head"><div className={isVolume ? "alert-icon volume-icon" : `alert-icon ${up ? "up-icon" : "down-icon"}`}>{isVolume ? <TrendingUp size={16} /> : up ? <ArrowUpRight size={17} /> : <ArrowDownRight size={17} />}</div><div className="alert-heading"><span>{item.ticker}<small>{(item.company_name || item.company || item.ticker).replace(/ Limited$/, "")}</small></span><span className="alert-date">{item.date}</span></div></div>
                  <div className="alert-metric-row"><div><span className="metric-label">{isVolume ? "VOLUME VS 20D AVG" : "ONE-DAY PRICE MOVE"}</span><strong className={isVolume ? "metric-value volume-value" : `metric-value ${up ? "positive-value" : "negative-value"}`}>{isVolume ? `${item.value.toFixed(2)}×` : `${item.value > 0 ? "+" : "−"}${Math.abs(item.value).toFixed(2)}%`}</strong></div><MiniChart rows={history} positive={isVolume || up} metric={isVolume ? "volume" : "close"} /></div>
                  <div className="alert-rule-line"><span>{isVolume ? `Limit ${rules.volume_multiplier}× · avg ${compactNumber(item.average_volume_20d ?? 0)}` : `Limit ±${rules.price_change_percent}%`}</span><button className="deep-link" onClick={() => openResearch(item.ticker)}>Dig deeper <ArrowRight size={13} /></button></div>
                </SwipeRow>;
              })}</div>
            )}

            <div className="settings-panel">
              <div className="settings-title"><div className="settings-icon"><Settings2 size={16} /></div><div><h2>Alert limits</h2><p>Make “unusual” your call.</p></div></div>
              <label className="rule-setting"><span><strong>Volume spike</strong><small>vs previous 20 sessions</small></span><span className="number-input-wrap"><input aria-label="Volume alert multiplier" type="number" min="0.1" max="100" step="0.1" value={ruleDraft.volume_multiplier} onChange={(event) => setRuleDraft({ ...ruleDraft, volume_multiplier: Number(event.target.value) })} /><b>×</b></span></label>
              <label className="rule-setting"><span><strong>Price move</strong><small>in one session, either direction</small></span><span className="number-input-wrap"><input aria-label="Price alert percent" type="number" min="0.1" max="100" step="0.1" value={ruleDraft.price_change_percent} onChange={(event) => setRuleDraft({ ...ruleDraft, price_change_percent: Number(event.target.value) })} /><b>%</b></span></label>
              <button className="save-rules" disabled={rulesSaving || !isValidRules(ruleDraft)} onClick={() => void saveRules()}>{rulesSaving ? "Saving…" : "Save limits"}<Check size={15} /></button>
              <p className="settings-footnote">Changes apply to the next alert refresh.</p>
            </div>
          </section>
        )}

        {screen === "research" && (
          <ResearchPage
            ticker={researchTicker}
            query={researchQuery}
            onQueryChange={setResearchQuery}
            onSubmit={submitResearch}
            onBack={() => setScreen("digest")}
            loading={researchLoading}
            unavailable={researchUnavailable}
            data={researchData}
            demoCompanies={researchDemo}
            onSelectDemo={openResearch}
          />
        )}
      </div>

      <nav className="bottom-nav" aria-label="Main navigation">
        <NavItem active={screen === "digest"} onClick={() => setScreen("digest")} icon={<Sparkles size={17} />} label="Digest" />
        <NavItem active={screen === "alerts"} onClick={() => setScreen("alerts")} icon={<Bell size={17} />} label="Alerts" badge={!loading && visibleAlerts.length > 0 ? visibleAlerts.length : undefined} />
        <NavItem active={screen === "research"} onClick={() => setScreen("research")} icon={<Search size={17} />} label="Research" />
      </nav>
      {toast && <div role="status" className="toast"><Check size={14} /> {toast}</div>}
    </main>
  );
}

function SwipeRow({ id, anchorId, decision, onDecide, className, children }: {
  id: string; anchorId?: string; decision?: Decision; onDecide: (id: string, value: Decision) => void; className: string; children: ReactNode;
}) {
  const startX = useRef<number | null>(null);
  return <div
    className={`swipe-row ${className} ${decision === "watch" ? "is-watched" : ""}`}
    id={anchorId}
    tabIndex={0}
    role="group"
    aria-label="Swipe right to watch, swipe left to dismiss"
    onTouchStart={(event) => { startX.current = event.touches[0]?.clientX ?? null; }}
    onTouchEnd={(event) => {
      if (startX.current === null) return;
      const delta = (event.changedTouches[0]?.clientX ?? startX.current) - startX.current;
      if (delta > 64) onDecide(id, "watch");
      if (delta < -64) onDecide(id, "dismiss");
      startX.current = null;
    }}
    onKeyDown={(event) => {
      if (event.key === "ArrowRight") { event.preventDefault(); onDecide(id, "watch"); }
      if (event.key === "ArrowLeft") { event.preventDefault(); onDecide(id, "dismiss"); }
    }}
  >
    {decision === "watch" && <span className="watch-ribbon"><Check size={10} /> WATCHING</span>}
    {children}
  </div>;
}

function MiniChart({ rows, positive, metric }: { rows: PriceRow[]; positive: boolean; metric: "close" | "volume" }) {
  const values = rows.slice(-18).map((row) => row[metric]);
  if (values.length < 2) return <div className="chart-empty" aria-label="Trend data unavailable">NO TREND</div>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const yValues = values.map((value) => 30 - ((value - min) / range) * 25);
  const points = values.map((_, index) => `${(index / (values.length - 1)) * 100},${yValues[index]}`).join(" ");
  const color = positive ? "#a7d96c" : "#ff8178";
  return <svg className="mini-chart" viewBox="0 0 100 34" role="img" aria-label={`Recent ${metric === "volume" ? "volume" : "price"} trend`} preserveAspectRatio="none"><polyline points={points} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /><circle cx="100" cy={yValues[yValues.length - 1]} r="2.5" fill={color} /></svg>;
}

function NavItem({ active, onClick, icon, label, badge }: { active: boolean; onClick: () => void; icon: ReactNode; label: string; badge?: number }) {
  return <button className={`nav-item ${active ? "active" : ""}`} onClick={onClick} aria-current={active ? "page" : undefined}>{icon}<span>{label}</span>{badge !== undefined && <b className="nav-badge">{badge}</b>}</button>;
}

function DigestSkeleton() {
  return <div className="skeleton-stack" aria-label="Loading digest"><div className="skeleton-line short" /><div className="skeleton-card"><div className="skeleton-line tiny" /><div className="skeleton-line wide" /><div className="skeleton-line medium" /></div><div className="skeleton-card compact"><div className="skeleton-line wide" /></div><div className="skeleton-card compact"><div className="skeleton-line medium" /></div></div>;
}

function AlertSkeleton() {
  return <div className="skeleton-stack" aria-label="Loading alerts"><div className="skeleton-card alert-skeleton"><div className="skeleton-line medium" /><div className="skeleton-chart" /><div className="skeleton-line short" /></div><div className="skeleton-card alert-skeleton"><div className="skeleton-line medium" /><div className="skeleton-chart" /><div className="skeleton-line short" /></div></div>;
}

function EmptyState({ title, copy }: { title: string; copy: string }) {
  return <div className="empty-state"><div className="empty-mark"><span /><span /><span /></div><h2>{title}</h2><p>{copy}</p></div>;
}

function ResearchPage({
  ticker, query, onQueryChange, onSubmit, onBack, loading, unavailable, data, demoCompanies, onSelectDemo,
}: {
  ticker: string;
  query: string;
  onQueryChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onBack: () => void;
  loading: boolean;
  unavailable: boolean;
  data: ResearchPayload | null;
  demoCompanies: Array<{ ticker: string; company_name: string }>;
  onSelectDemo: (ticker: string) => void;
}) {
  const metrics = data?.metrics;
  const snapshot = metrics?.snapshot;
  return <section aria-labelledby="research-title" className="research-page">
    <button className="back-link" onClick={onBack}><ArrowLeft size={15} /> Back to Digest</button>
    <div className="section-kicker"><span>PULL · COMPANY FUNDAMENTALS</span><span className="kicker-rule" /></div>
    <form className="research-search" onSubmit={onSubmit}>
      <label className="sr-only" htmlFor="research-symbol">NSE ticker</label>
      <Search size={15} />
      <input id="research-symbol" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Any NSE ticker" autoCapitalize="characters" />
      <button type="submit">Open</button>
    </form>
    <div className="research-demo-chips" aria-label="Demo companies">{demoCompanies.map((company) => <button key={company.ticker} onClick={() => onSelectDemo(company.ticker)}>{company.ticker}</button>)}</div>

    {ticker && <div className="research-company-head">
      <div><span className="research-symbol-label">NSE · {ticker}</span><h1 id="research-title">{data?.found ? data.company_name : ticker}</h1></div>
      <div className="research-price">{data?.found && data.price !== null && data.price !== undefined ? formatPrice(data.price) : "—"}<small>LAST SAVED CLOSE</small></div>
    </div>}

    {loading && <ResearchSkeleton />}
    {!loading && !ticker && <div className="research-empty"><div className="research-orbit"><Sparkles size={19} /></div><h2>Start with a ticker.</h2><p>Look up any NSE symbol. Pull reads the saved multi-year financial tables and calculates the headline metrics in plain Python.</p></div>}
    {!loading && ticker && unavailable && <div className="research-empty"><h2>Research data could not be loaded.</h2><p>Start the FINN backend and try this ticker again.</p></div>}
    {!loading && ticker && data && !data.found && <div className="research-empty no-data"><h2>No saved financial tables for {ticker}.</h2><p>{data.message || "Ingest Screener's tables to build this company page."}</p><code>python scripts/ingest.py {ticker}</code></div>}

    {!loading && data?.found && metrics && <div className="research-sections">
      <div className="research-source-line">
        <span className="source-dot" /> Saved from screener.in · {formatSavedDate(data.saved_at)}
        {data.source_url && <a href={data.source_url} target="_blank" rel="noreferrer">Source <ArrowRight size={11} /></a>}
      </div>

      <section className="research-section" aria-labelledby="snapshot-heading">
        <div className="research-section-heading"><span className="section-index">01</span><h2 id="snapshot-heading">Financial snapshot</h2><span>{snapshot?.period || "Latest saved period"}</span></div>
        <div className="snapshot-ledger">
          <MetricLine label="Revenue" value={formatCrore(snapshot?.revenue)} change={formatPercent(snapshot?.revenue_growth_percent)} />
          <MetricLine label="Net profit" value={formatCrore(snapshot?.profit)} change={formatPercent(snapshot?.profit_growth_percent)} />
          <MetricLine label="Net margin" value={formatPercent(snapshot?.net_margin_percent)} />
          <MetricLine label="Operating margin" value={formatPercent(snapshot?.operating_margin_percent)} />
        </div>
        <p className="metric-source-note">Growth is latest period versus previous saved period · P&amp;L table</p>
      </section>

      <section className="research-section" aria-labelledby="trajectory-heading">
        <div className="research-section-heading"><span className="section-index">02</span><h2 id="trajectory-heading">Trajectory</h2><span>₹ crore</span></div>
        <TrendPlot label="Revenue" periods={metrics.periods} values={metrics.trajectory.revenue} color="#b7db7a" />
        <TrendPlot label="Net profit" periods={metrics.periods} values={metrics.trajectory.profit} color="#72b6a2" />
      </section>

      <section className="research-section" aria-labelledby="balance-heading">
        <div className="research-section-heading"><span className="section-index">03</span><h2 id="balance-heading">Balance sheet</h2><span>{metrics.balance_sheet.period || "Latest"}</span></div>
        <div className="snapshot-ledger">
          <MetricLine label="Borrowings" value={formatCrore(metrics.balance_sheet.borrowings)} />
          <MetricLine label="Equity" value={formatCrore(metrics.balance_sheet.equity)} />
          <MetricLine label="Debt / equity" value={formatRatio(metrics.balance_sheet.debt_to_equity)} />
        </div>
        <p className="metric-source-note">Borrowings ÷ shareholders’ equity · Balance sheet table</p>
      </section>

      <section className="research-section" aria-labelledby="cash-heading">
        <div className="research-section-heading"><span className="section-index">04</span><h2 id="cash-heading">Cash quality</h2><span>{metrics.cash_quality.period || "Latest"}</span></div>
        <div className="snapshot-ledger">
          <MetricLine label="Operating cash flow" value={formatCrore(metrics.cash_quality.operating_cash_flow)} />
          <MetricLine label="Cash conversion" value={formatRatio(metrics.cash_quality.cash_conversion)} />
          <MetricLine label="Free cash flow" value={formatCrore(metrics.cash_quality.free_cash_flow)} />
        </div>
        <p className="metric-source-note">Cash conversion = operating cash flow ÷ PAT · {metrics.cash_quality.free_cash_flow_method || "cash flow table"}</p>
      </section>
      <p className="research-disclaimer">Calculated from saved Screener.in tables. Values are shown for the reported period; no forecast or outside analysis is included.</p>
    </div>}
  </section>;
}

function ResultsTable({ metrics }: { metrics: NonNullable<Announcement["results_metrics"]> }) {
  const percent = (value: number | null) => value === null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
  return <div className="results-table-wrap"><table className="results-table"><thead><tr><th>₹ cr</th><th>This quarter</th><th>QoQ %</th><th>YoY %</th></tr></thead><tbody>{metrics.map((metric) => <tr key={metric.label}><th>{metric.label}</th><td>{metric.value === null ? "—" : Math.round(metric.value).toLocaleString("en-IN")}</td><td className={metric.qoq_percent === null ? "" : metric.qoq_percent > 0 ? "result-up" : metric.qoq_percent < 0 ? "result-down" : ""}>{percent(metric.qoq_percent)}</td><td className={metric.yoy_percent === null ? "" : metric.yoy_percent > 0 ? "result-up" : metric.yoy_percent < 0 ? "result-down" : ""}>{percent(metric.yoy_percent)}</td></tr>)}</tbody></table></div>;
}

function FilingDisclosure({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return <div className="filing-disclosure"><button aria-expanded={open} onClick={() => setOpen((value) => !value)}>{open ? "Hide filing" : "Show filing"}</button>{open && <p>{text}</p>}</div>;
}

function shortHeadline(subject: string, category?: string) {
  const quarter = subject.match(/Q[1-4]\s+FY\s?\d{2,4}/i)?.[0]?.replace(/\s+/g, " ").toUpperCase();
  if (category === "results" || /results/i.test(subject)) return `${quarter || "Latest"} results`;
  const clean = subject.replace(/^SAMPLE ONLY\s*[—-]\s*/i, "").split(/[.;]/, 1)[0].trim();
  return clean.length > 72 ? `${clean.slice(0, 69).replace(/\s+\S*$/, "")}…` : clean;
}

function MetricLine({ label, value, change }: { label: string; value: string; change?: string }) {
  return <div className="metric-line"><span>{label}</span><strong>{value}</strong>{change && <small className={change.startsWith("−") ? "change-negative" : "change-positive"}>{change}</small>}</div>;
}

function TrendPlot({ label, periods, values, color }: { label: string; periods: string[]; values: Array<number | null>; color: string }) {
  const points = values.map((value, index) => ({ value, period: periods[index] ?? `P${index + 1}` })).filter((item): item is { value: number; period: string } => item.value !== null && Number.isFinite(item.value));
  if (points.length < 2) return <div className="trend-row"><span className="trend-label">{label}</span><span className="trend-empty">Not enough saved periods</span></div>;
  const min = Math.min(...points.map((point) => point.value));
  const max = Math.max(...points.map((point) => point.value));
  const range = max - min || 1;
  const coords = points.map((point, index) => ({
    x: 2 + (index / (points.length - 1)) * 96,
    y: 26 - ((point.value - min) / range) * 21,
  }));
  const path = coords.map((point) => `${point.x},${point.y}`).join(" ");
  const latest = points[points.length - 1];
  return <div className="trend-row">
    <div className="trend-head"><span className="trend-label">{label}</span><span className="trend-latest">₹{compactNumber(latest.value)} Cr <small>{latest.period}</small></span></div>
    <svg className="trend-svg" viewBox="0 0 100 30" preserveAspectRatio="none" role="img" aria-label={`${label} multi-year trend`}><polyline points={path} fill="none" stroke={color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /><circle cx={coords[coords.length - 1].x} cy={coords[coords.length - 1].y} r="1.7" fill={color} /></svg>
    <div className="trend-years"><span>{points[0].period}</span><span>{points[points.length - 1].period}</span></div>
  </div>;
}

function ResearchSkeleton() {
  return <div className="research-skeleton" aria-label="Loading company fundamentals"><div className="skeleton-line short" /><div className="skeleton-line wide" /><div className="skeleton-ledger" /><div className="skeleton-ledger" /><div className="skeleton-ledger" /></div>;
}

async function getJson<T>(url: string): Promise<T | null> {
  try {
    const response = await fetch(url);
    if (!response.ok) return null;
    return await response.json() as T;
  } catch { return null; }
}

function fallbackDigest(items: Announcement[], hours: number): Announcement[] {
  const now = Date.now();
  const cutoff = now - hours * 60 * 60 * 1000;
  return items.filter((item) => {
    const time = Date.parse(item.time);
    return Number.isFinite(time) && time >= cutoff && time <= now;
  }).map((item) => ({ ...item, level: item.level ?? levelFor(item.category ?? "unclassified") }))
    .sort((a, b) => (a.level ?? 3) - (b.level ?? 3) || Date.parse(b.time) - Date.parse(a.time));
}

function fixtureRows(): PriceRow[] {
  return Object.entries(fixturePriceData.prices).flatMap(([ticker, history]) => history.map((row) => ({ ...row, ticker, source: "saved_sample" })));
}

function normalizePriceRows(rows: PriceRow[]): PriceRow[] {
  return rows.filter((row) => Number.isFinite(row.close) && Number.isFinite(row.volume));
}

function calculateFixtureAlerts(rows: PriceRow[], currentRules: Rules): AlertItem[] {
  const byTicker = new Map<string, PriceRow[]>();
  for (const row of rows) byTicker.set(row.ticker, [...(byTicker.get(row.ticker) ?? []), row]);
  const result: AlertItem[] = [];
  for (const [ticker, history] of byTicker) {
    const ordered = [...history].sort((a, b) => a.date.localeCompare(b.date));
    if (ordered.length < 2) continue;
    const current = ordered[ordered.length - 1];
    const previous = ordered[ordered.length - 2];
    const change = ((current.close - previous.close) / previous.close) * 100;
    if (Math.abs(change) > currentRules.price_change_percent) result.push({
      ticker, date: current.date, type: "price_move", value: Number(change.toFixed(2)),
      threshold: currentRules.price_change_percent, summary: `Price moved ${change.toFixed(2)}% in one session.`,
    });
    const baseline = ordered.slice(-21, -1);
    if (baseline.length === 20) {
      const average = baseline.reduce((sum, row) => sum + row.volume, 0) / baseline.length;
      const multiple = current.volume / average;
      if (multiple > currentRules.volume_multiplier) result.push({
        ticker, date: current.date, type: "volume_spike", value: Number(multiple.toFixed(2)),
        threshold: currentRules.volume_multiplier, average_volume_20d: Math.round(average),
        summary: `Volume is ${multiple.toFixed(2)}x its 20-session average.`,
      });
    }
  }
  return result;
}

function levelFor(category: string): number {
  if (["results", "M&A", "management_change", "litigation", "credit_rating", "fund_raise", "pledging"].includes(category)) return 1;
  if (["dividend", "capex", "bonus_split", "earnings_call", "press_release", "insider_trading"].includes(category)) return 2;
  return 3;
}

function announcementId(item: Announcement): string {
  return item.id ?? `${item.ticker}:${item.time}:${item.subject}`;
}

function alertId(item: AlertItem): string {
  return item.id ?? `${item.ticker}:${item.type}:${item.date}`;
}

function isValidRules(value: Rules): boolean {
  return Number.isFinite(value.volume_multiplier) && value.volume_multiplier > 0
    && Number.isFinite(value.price_change_percent) && value.price_change_percent > 0;
}

function readStoredRules(): Rules {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(rulesKey) ?? "null") as Rules | null;
    if (parsed && isValidRules(parsed)) return parsed;
  } catch { /* Use defaults when storage is unavailable. */ }
  return defaultRules;
}

function readDecisions(): DecisionMap {
  try { return JSON.parse(window.localStorage.getItem(decisionsKey) ?? "{}") as DecisionMap; }
  catch { return {}; }
}

function dateStamp(): string {
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short" }).format(new Date()).toUpperCase();
}

function relativeTime(value: string): string {
  const deltaMinutes = Math.max(0, Math.round((Date.now() - Date.parse(value)) / 60000));
  if (!Number.isFinite(deltaMinutes)) return "—";
  if (deltaMinutes < 60) return `${deltaMinutes}m`;
  const hours = Math.floor(deltaMinutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function compactNumber(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return String(value);
}

function formatCrore(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `₹${compactNumber(value)} Cr`;
}

function formatSavedDate(value?: string): string {
  if (!value) return "date unavailable";
  const date = new Date(value.replace(" ", "T"));
  if (!Number.isFinite(date.getTime())) return "date unavailable";
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function formatPercent(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value < 0 ? "−" : "+"}${Math.abs(value).toFixed(1)}%`;
}

function formatRatio(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(2)}×`;
}

function formatPrice(value: number): string {
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function formatMarketContext(context: NonNullable<Announcement["market_context"]>): string {
  const details = [];
  if (context.volume_ratio !== null) details.push(`Volume ${context.volume_ratio.toFixed(1)}× average`);
  if (context.price_change_pct !== null) details.push(`price ${formatPercent(context.price_change_pct)}`);
  return details.join(", ");
}

function topItemSummary(item: TopItem): string {
  const category = (item.category || "filing").replace(/_/g, " ").toLowerCase();
  if (category === "results") {
    const pat = item.results_metrics?.find((metric) => metric.label.toUpperCase() === "PAT");
    if (pat?.qoq_percent !== null && pat?.qoq_percent !== undefined) {
      return `results, PAT ${formatPercent(pat.qoq_percent)} QoQ`;
    }
  }
  return category;
}
