import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { format, subDays } from 'date-fns';
import { useAuth } from '../context/AuthContext';
import { getLocations, createReconciliationSession, listReconciliationSessions,
  getReconciliationSession, reprocessReconciliationSession } from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import DateRangePicker from '../components/DateRangePicker';

const TYPES = { rfid: 'RFID', visual: 'Visual', mixed: 'Mixed' };
const fieldClass = 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm';
const today = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Africa/Nairobi', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());
const initialSetup = () => ({ location_id: '', session_date: today(), input_type: 'rfid', notes: '' });
const message = (error) => typeof error.response?.data?.detail === 'string'
  ? error.response.data.detail : error.message || 'Something went wrong. Please try again.';

// A scan file is a single column, with optional CSV quoting. Never coerce tags to numbers.
function parseTags(text, rfid = false) {
  const entries = [];
  const errors = [];
  text.replace(/^\uFEFF/, '').split(/\r\n|\n|\r/).forEach((line, index) => {
    let value = line.trim();
    if (!value) return;
    if (value.startsWith('"')) {
      if (!/^"(?:[^"]|"")*"$/.test(value)) {
        errors.push(`Line ${index + 1}: expected one quoted value.`);
        return;
      }
      value = value.slice(1, -1).replace(/""/g, '"').trim();
    } else if (/[,"]/.test(value)) {
      errors.push(`Line ${index + 1}: use one tag per line, without a header.`);
      return;
    }
    if (!value || value.length > 100) {
      errors.push(`Line ${index + 1}: tags must contain 1–100 characters.`);
      return;
    }
    const idType = !rfid ? 'visual_tag' : /^\d{15}$/.test(value) ? 'eid'
      : /^[0-9a-f]+$/i.test(value) ? 'reader_code' : null;
    if (!idType) errors.push(`Line ${index + 1}: expected a 15-digit EID or hexadecimal reader code.`);
    else entries.push({ raw_value: value, id_type: idType });
  });
  return { entries, errors };
}

function Coverage({ value }) {
  const color = value >= 90 ? 'bg-green-100 text-green-800' : value >= 70
    ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800';
  return <span className={`inline-block rounded-full px-2 py-1 text-xs font-semibold ${color}`}>{value.toFixed(1)}%</span>;
}

function ResultTable({ headings, children }) {
  return <div className="overflow-x-auto"><table className="w-full text-left text-sm">
    <thead><tr>{headings.map((heading) => <th key={heading} className="p-3 font-medium text-muted-foreground">{heading}</th>)}</tr></thead>
    <tbody className="divide-y">{children}</tbody>
  </table></div>;
}

function Results({ result, admin, busy, onReprocess }) {
  return <div className="space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="text-xl font-semibold">{result.location_name}</h2>
        <p className="text-sm text-muted-foreground">{result.session_date} · {TYPES[result.input_type]} · {result.total_scanned} scanned</p></div>
      {admin && <Button variant="outline" onClick={onReprocess} disabled={busy}>{busy ? 'Reprocessing…' : 'Reprocess'}</Button>}
    </div>
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {[["Coverage", <Coverage value={result.coverage_pct} />], ['Matched', result.matched_count],
        ['Not in system', result.unmatched_scan_count], ['Missing from scan', result.in_system_not_seen_count]].map(([label, value]) =>
        <div key={label} className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">{label}</p><div className="mt-1 text-xl font-semibold">{value}</div></div>)}
    </div>
    <details className="overflow-hidden rounded-lg border">
      <summary className="cursor-pointer bg-green-100 p-3 font-semibold text-green-900">✓ Matched ({result.matched_count})</summary>
      <ResultTable headings={['Tag', 'Animal', 'Species', 'Matched via']}>
        {result.matched.map((row) => <tr key={row.animal_id}>
          <td className="p-3 font-mono">{row.tag_number}</td><td className="p-3"><Link className="text-primary underline" to={`/animals/${row.animal_id}`}>Animal #{row.animal_id}</Link></td>
          <td className="p-3 capitalize">{row.species}</td><td className="p-3">{row.matched_via === 'identifier' ? 'Identifier' : 'Tag number'}</td>
        </tr>)}
      </ResultTable>
    </details>
    <details open={result.unmatched_scan_count > 0} className="overflow-hidden rounded-lg border">
      <summary className="cursor-pointer bg-red-100 p-3 font-semibold text-red-900">⚠ Not in system ({result.unmatched_scan_count})</summary>
      <p className="p-3 text-sm">These animals were scanned but have no system record. Register them in the <Link className="text-primary underline" to="/animals">Animals page</Link>.</p>
      <ResultTable headings={['Raw value', 'Type']}>
        {result.unmatched_scan.map((row, index) => <tr key={index}><td className="p-3 font-mono break-all">{row.raw_value}</td><td className="p-3">{row.id_type}</td></tr>)}
      </ResultTable>
    </details>
    <details open={result.in_system_not_seen_count > 0} className="overflow-hidden rounded-lg border">
      <summary className="cursor-pointer bg-amber-100 p-3 font-semibold text-amber-900">⚠ Missing from scan ({result.in_system_not_seen_count})</summary>
      <p className="p-3 text-sm">These animals are registered at this farm but were not scanned. Verify their status.</p>
      <ResultTable headings={['Tag', 'Species', 'Category']}>
        {result.in_system_not_seen.map((row) => <tr key={row.animal_id}><td className="p-3 font-mono">{row.tag_number}</td><td className="p-3 capitalize">{row.species}</td><td className="p-3">{row.category}</td></tr>)}
      </ResultTable>
    </details>
  </div>;
}

export default function Reconciliation() {
  const { user } = useAuth();
  const canCreate = ['admin', 'data_entry'].includes(user?.role);
  const [locations, setLocations] = useState([]);
  const [locationError, setLocationError] = useState('');
  const [range, setRange] = useState(() => {
    const end = new Date(`${today()}T12:00:00`);
    return { from: subDays(end, 89), to: end };
  });
  const [locationFilter, setLocationFilter] = useState('');
  const [sessions, setSessions] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [mode, setMode] = useState('detail');
  const [result, setResult] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [step, setStep] = useState(1);
  const [setup, setSetup] = useState(initialSetup);
  const [rfidText, setRfidText] = useState('');
  const [visualTags, setVisualTags] = useState([]);
  const [visualInput, setVisualInput] = useState('');
  const request = useRef(0);
  const operation = useRef(false);
  const fileOperation = useRef(false);
  const dateFrom = range?.from ? format(range.from, 'yyyy-MM-dd') : undefined;
  const dateTo = range?.to ? format(range.to, 'yyyy-MM-dd') : undefined;
  const rfid = parseTags(rfidText, true);
  const entries = [ ...(setup.input_type !== 'visual' ? rfid.entries : []),
    ...(setup.input_type !== 'rfid' ? visualTags.map((raw_value) => ({ raw_value, id_type: 'visual_tag' })) : []) ];
  const parseErrors = setup.input_type !== 'visual' ? rfid.errors : [];

  useEffect(() => {
    let active = true;
    setLocationError('');
    getLocations().then(({ data }) => { if (active) setLocations(data); })
      .catch(() => { if (active) setLocationError('Could not load farms. Use Refresh to retry.'); });
    return () => { active = false; };
  }, [refresh]);

  useEffect(() => {
    let active = true;
    setHistoryLoading(true);
    setHistoryError('');
    listReconciliationSessions({ location_id: locationFilter || undefined, date_from: dateFrom, date_to: dateTo })
      .then(({ data }) => { if (active) setSessions(data); })
      .catch(() => { if (active) setHistoryError('Could not load sessions. Please retry.'); })
      .finally(() => { if (active) setHistoryLoading(false); });
    return () => { active = false; };
  }, [locationFilter, dateFrom, dateTo, refresh]);

  useEffect(() => () => { request.current += 1; }, []);

  async function selectSession(id) {
    if (operation.current || fileOperation.current) return;
    const current = ++request.current;
    setMode('detail'); setSelectedId(id); setResult(null); setDetailLoading(true); setError('');
    try {
      const { data } = await getReconciliationSession(id);
      if (current === request.current) setResult(data);
    } catch (err) { if (current === request.current) setError(message(err)); }
    finally { if (current === request.current) setDetailLoading(false); }
  }

  function newSession() {
    if (operation.current || fileOperation.current) return;
    request.current += 1;
    setMode('new'); setResult(null); setSelectedId(null); setDetailLoading(false); setError('');
    setStep(1); setSetup(initialSetup()); setRfidText(''); setVisualTags([]); setVisualInput('');
  }

  async function readFile(event, kind) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || fileOperation.current) return;
    setError('');
    if (!(kind === 'rfid' ? /\.(txt|csv)$/i : /\.csv$/i).test(file.name)) {
      setError(kind === 'rfid' ? 'Choose a .txt or .csv file.' : 'Choose a .csv file.'); return;
    }
    if (file.size > 5 * 1024 * 1024) { setError('Choose a scan file smaller than 5 MB.'); return; }
    fileOperation.current = true; setReading(true);
    try {
      const text = await file.text();
      if (kind === 'rfid') setRfidText((previous) => previous ? `${previous}\n${text}` : text);
      else {
        const parsed = parseTags(text);
        if (parsed.errors.length) throw new Error(parsed.errors.slice(0, 3).join(' '));
        setVisualTags((previous) => [...previous, ...parsed.entries.map((entry) => entry.raw_value)]);
      }
    } catch (err) { setError(message(err)); }
    finally { fileOperation.current = false; setReading(false); }
  }

  function addVisual() {
    const value = visualInput.trim();
    if (!value || value.length > 100) { setError('Enter a visual tag with 1–100 characters.'); return; }
    setVisualTags((previous) => [...previous, value]); setVisualInput(''); setError('');
  }

  async function submit(event) {
    event.preventDefault();
    if (operation.current || fileOperation.current || !entries.length || parseErrors.length) return;
    if (setup.input_type !== 'rfid' && visualInput.trim()) { setError('Add the pending visual tag before submitting.'); return; }
    operation.current = true; setBusy(true); setError('');
    try {
      const { data } = await createReconciliationSession({ ...setup, location_id: Number(setup.location_id), entries });
      request.current += 1;
      setResult(data); setSelectedId(data.session_id); setMode('detail'); setRefresh((value) => value + 1);
    } catch (err) { setError(message(err)); }
    finally { operation.current = false; setBusy(false); }
  }

  async function reprocess() {
    if (operation.current) return;
    operation.current = true; setBusy(true); setError('');
    try {
      const { data } = await reprocessReconciliationSession(result.session_id);
      setResult(data); setRefresh((value) => value + 1);
    } catch (err) { setError(message(err)); }
    finally { operation.current = false; setBusy(false); }
  }

  return <div className="space-y-6">
    <div><h1 className="font-heading text-3xl font-bold">Tag reconciliation</h1>
      <p className="mt-1 text-muted-foreground">Compare physical tags with the animal register.</p></div>
    <div className="grid items-start gap-6 lg:grid-cols-3">
      <aside className="min-w-0 space-y-4 rounded-xl border bg-card p-4">
        <div className="flex items-center justify-between gap-2"><h2 className="font-semibold">Session history</h2>
          <Button variant="ghost" size="sm" onClick={() => setRefresh((value) => value + 1)}>Refresh</Button></div>
        <DateRangePicker clearable value={range} onChange={setRange} />
        <label className="block text-sm">Farm
          <select className={`${fieldClass} mt-1`} value={locationFilter} onChange={(event) => setLocationFilter(event.target.value)}>
            <option value="">All farms</option>{locations.map((loc) => <option key={loc.id} value={loc.id}>{loc.name}</option>)}
          </select></label>
        {locationError && <p role="alert" className="text-sm text-red-700">{locationError}</p>}
        {canCreate && <Button className="w-full" onClick={newSession} disabled={busy || reading}>+ New Session</Button>}
        {historyLoading ? <p role="status" className="text-sm">Loading sessions…</p> : historyError ?
          <p role="alert" className="text-sm text-red-700">{historyError}</p> : !sessions.length ?
            <p className="text-sm text-muted-foreground">No sessions in this date range.</p> :
            <div className="max-h-[640px] space-y-2 overflow-y-auto">
              {sessions.map((session) => <button key={session.id} type="button" disabled={busy || reading}
                aria-pressed={selectedId === session.id} onClick={() => selectSession(session.id)}
                className={`w-full rounded-lg border p-3 text-left hover:bg-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-50 ${selectedId === session.id ? 'border-primary bg-primary/5' : ''}`}>
                <div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{session.session_date}</span><Coverage value={session.coverage_pct} /></div>
                <p className="mt-1 truncate font-medium">{session.location_name}</p>
                <p className="text-xs text-muted-foreground">{TYPES[session.input_type]} · {session.total_scanned} scanned</p>
              </button>)}
            </div>}
      </aside>
      <section className="min-w-0 rounded-xl border bg-card p-4 sm:p-6 lg:col-span-2" aria-label="Session workspace">
        {error && <div role="alert" className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-800">{error}
          {mode === 'detail' && !result && selectedId && <Button variant="ghost" size="sm" onClick={() => selectSession(selectedId)}>Retry</Button>}</div>}
        {detailLoading ? <p role="status">Loading session…</p> : mode === 'new' ? <>
          <h2 className="text-xl font-semibold">New session</h2>
          <p className="mb-5 text-sm text-muted-foreground">Step {step} of 2 — {step === 1 ? 'Setup' : 'Enter tags'}</p>
          {step === 1 ? <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); setError(''); setStep(2); }}>
            <label className="block text-sm font-medium">Farm
              <select required className={`${fieldClass} mt-1`} value={setup.location_id} onChange={(event) => setSetup({ ...setup, location_id: event.target.value })}>
                <option value="">Select a farm</option>{locations.map((loc) => <option key={loc.id} value={loc.id}>{loc.name}</option>)}
              </select></label>
            <label className="block text-sm font-medium">Date<Input className="mt-1" required type="date" value={setup.session_date} onChange={(event) => setSetup({ ...setup, session_date: event.target.value })} /></label>
            <fieldset><legend className="mb-2 text-sm font-medium">Input type</legend><div className="flex flex-wrap gap-2">
              {[['rfid', 'RFID Scan'], ['visual', 'Visual Tags'], ['mixed', 'Mixed']].map(([value, label]) =>
                <label key={value} className={`cursor-pointer rounded-md border px-3 py-2 text-sm ${setup.input_type === value ? 'border-primary bg-primary/5' : ''}`}>
                  <input className="mr-2" type="radio" name="input_type" value={value} checked={setup.input_type === value} onChange={() => setSetup({ ...setup, input_type: value })} />{label}
                </label>)}
            </div></fieldset>
            <label className="block text-sm font-medium">Notes (optional)<textarea className={`${fieldClass} mt-1`} rows={3} value={setup.notes} onChange={(event) => setSetup({ ...setup, notes: event.target.value })} /></label>
            <Button type="submit" disabled={!locations.length}>Next</Button>
          </form> : <form onSubmit={submit} className="space-y-5">
            <fieldset disabled={busy || reading} className="space-y-5">
              <div className={`grid gap-5 ${setup.input_type === 'mixed' ? 'xl:grid-cols-2' : ''}`}>
                {setup.input_type !== 'visual' && <section className="min-w-0 space-y-3 rounded-lg border p-4" aria-label="RFID tags">
                  <h3 className="font-semibold">RFID tags</h3>
                  <label className="block text-sm">Upload scan file<Input className="mt-1" type="file" accept=".txt,.csv,text/plain,text/csv" onChange={(event) => readFile(event, 'rfid')} /></label>
                  <p className="text-xs text-muted-foreground">One EID or hexadecimal reader code per line, without a header. Uploads append to the text below.</p>
                  <label className="block text-sm">Or paste tags<textarea rows={7} className={`${fieldClass} mt-1 font-mono`} value={rfidText} onChange={(event) => setRfidText(event.target.value)} /></label>
                  <p className="text-sm font-medium">Preview · {rfid.entries.length} values</p>
                  <ul className="text-sm">{rfid.entries.slice(0, 5).map((entry, index) => <li key={index} className="break-all font-mono">{entry.raw_value} <span className="text-xs text-muted-foreground">({entry.id_type})</span></li>)}</ul>
                  {!!parseErrors.length && <div role="alert" className="text-sm text-red-700">{parseErrors.slice(0, 3).map((item) => <p key={item}>{item}</p>)}{parseErrors.length > 3 && <p>And {parseErrors.length - 3} more invalid lines.</p>}</div>}
                </section>}
                {setup.input_type !== 'rfid' && <section className="min-w-0 space-y-3 rounded-lg border p-4" aria-label="Visual tags">
                  <h3 className="font-semibold">Visual tags</h3>
                  <label className="block text-sm" htmlFor="visual-tag">Tag number</label>
                  <div className="flex gap-2"><Input id="visual-tag" value={visualInput} maxLength={100} onChange={(event) => setVisualInput(event.target.value)}
                    onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); addVisual(); } }} /><Button type="button" variant="outline" onClick={addVisual}>Add</Button></div>
                  <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto">{visualTags.map((tag, index) =>
                    <span key={index} className="inline-flex max-w-full items-center gap-2 rounded-full bg-secondary px-3 py-1 text-sm"><span className="break-all">{tag}</span>
                      <button type="button" aria-label={`Remove ${tag}`} className="rounded px-1 focus-visible:outline" onClick={() => setVisualTags((previous) => previous.filter((_, i) => i !== index))}>×</button></span>)}</div>
                  <label className="block text-sm">Or upload CSV<Input type="file" className="mt-1" accept=".csv,text/csv" onChange={(event) => readFile(event, 'visual')} /></label>
                  <p className="text-xs text-muted-foreground">One tag per line, without a header. Uploaded tags are added to the list.</p>
                </section>}
              </div>
              <p role="status" className="font-medium">{entries.length} tags ready to submit</p>
              <div className="flex flex-wrap gap-3"><Button type="button" variant="outline" onClick={() => { setStep(1); setError(''); }}>Back</Button>
                <Button type="submit" disabled={!entries.length || !!parseErrors.length}>{busy ? 'Reconciling…' : 'Submit & Reconcile'}</Button></div>
            </fieldset>
            {reading && <p role="status" className="text-sm">Reading file…</p>}
          </form>}
        </> : result ? <Results key={`${result.session_id}-${refresh}`} result={result} admin={user?.role === 'admin'} busy={busy} onReprocess={reprocess} /> :
          <div className="py-16 text-center text-muted-foreground">Select a session to view its results{canCreate ? ', or create a new session.' : '.'}</div>}
      </section>
    </div>
  </div>;
}
