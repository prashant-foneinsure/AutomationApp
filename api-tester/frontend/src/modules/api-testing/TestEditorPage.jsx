import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { execute, groups, runs, tests, variables } from '../../api.js'
import { Banner, ConfirmButton } from '../../components/ui.jsx'
import ResultsTable from './ResultsTable.jsx'

const PLACEHOLDER = /\{\{\s*([\w.-]+)\s*\}\}/g

// Create or edit one API test, and run it.
// For a new test, groupId comes from the route; the test is not saved until
// "Save test" is pressed, so you can try an endpoint first if you prefer.
export default function TestEditorPage() {
  const { groupId, testId } = useParams()
  const navigate = useNavigate()
  // The "new" route has no :testId segment, so useParams gives undefined there;
  // treat both that and a literal "new" as create-mode.
  const isNew = testId == null || testId === 'new'
  const gid = Number(groupId)
  const tid = isNew ? null : Number(testId)

  const [group, setGroup] = useState(null)
  const [form, setForm] = useState({ name: '', curl: '', method: '', instruction: '', notes: '' })
  const [extractors, setExtractors] = useState([])
  const [auth, setAuth] = useState({ token: '', username: '', password: '' })
  const [vars, setVars] = useState([])

  const [result, setResult] = useState(null)
  const [insights, setInsights] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [runningAs, setRunningAs] = useState('')
  const [savingAuth, setSavingAuth] = useState({ token: false, username: false, password: false })

  async function saveAuthAsVariable(key) {
    const value = auth[key]
    if (!value) return
    setSavingAuth((s) => ({ ...s, [key]: true }))
    try {
      await variables.update(gid, key, value)
      setNotice(`Saved ${key} as group variable.`)
      setVars(await variables.list(gid))
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingAuth((s) => ({ ...s, [key]: false }))
    }
  }

  const load = useCallback(async () => {
    try {
      const g = await groups.get(gid)
      setGroup(g)
      setVars(await variables.list(gid))
      if (tid) {
        const t = await tests.list(gid)
        const found = t.find((x) => x.test_id === tid)
        if (found) {
          setForm({
            name: found.name,
            curl: found.curl,
            method: found.http_method || '',
            instruction: '',
            notes: found.notes || '',
          })
          setExtractors(found.extractors || [])
        }
        setInsights(await runs.insights(tid))
      }
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [gid, tid])

  useEffect(() => {
    load()
  }, [load])

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  async function save() {
    setBusy(true)
    setError('')
    try {
      const payload = {
        name: form.name.trim(),
        curl: form.curl.trim(),
        http_method: form.method || null,
        notes: form.notes || null,
        extractors,
      }
      if (isNew) {
        const { test_id } = await tests.create(gid, payload)
        setNotice('Test saved.')
        navigate(`/api-testing/groups/${gid}/tests/${test_id}`, { replace: true })
      } else {
        await tests.update(tid, payload)
        setNotice('Test updated.')
        await load()
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function run() {
    if (isNew) {
      // Auto-save first, then run
      if (!form.name.trim()) {
        setError('Enter a test name first.')
        return
      }
      if (!form.curl.trim()) {
        setError('Paste a cURL command first.')
        return
      }
      setBusy(true)
      setError('')
      try {
        const payload = {
          name: form.name.trim(),
          curl: form.curl.trim(),
          http_method: form.method || null,
          notes: form.notes || null,
          extractors,
        }
        const { test_id } = await tests.create(gid, payload)
        setNotice('Test saved.')
        // Update state to reflect saved test
        navigate(`/api-testing/groups/${gid}/tests/${test_id}`, { replace: true })
        // Now run the newly saved test
        setRunningAs('test')
        setResult(null)
        const outcome = await execute.test(test_id, {
          ...auth,
          instruction: form.instruction,
          method: form.method,
        })
        setResult(outcome)
        setInsights(await runs.insights(test_id))
        setVars(await variables.list(gid))
      } catch (e) {
        setError(e.message)
      } finally {
        setBusy(false)
        setRunningAs('')
      }
      return
    }
    setRunningAs('test')
    setError('')
    setResult(null)
    try {
      const outcome = await execute.test(tid, {
        ...auth,
        instruction: form.instruction,
        method: form.method,
      })
      setResult(outcome)
      setInsights(await runs.insights(tid))
      setVars(await variables.list(gid))
    } catch (e) {
      setError(e.message)
    } finally {
      setRunningAs('')
    }
  }

  async function tryWithoutSaving() {
    if (!form.curl.trim()) {
      setError('Paste a cURL command first.')
      return
    }
    // Nothing is persisted and no test is required: this is just to check
    // that the endpoint answers before naming and saving a test for it.
    setRunningAs('adhoc')
    setError('')
    setResult(null)
    try {
      setResult(await execute.adhoc({
        curl: form.curl.trim(),
        method: form.method,
        instruction: form.instruction,
        ...auth,
      }))
      setNotice('Tried without saving. Nothing was written to history.')
    } catch (e) {
      setError(e.message)
    } finally {
      setRunningAs('')
    }
  }

  async function propose() {
    setBusy(true)
    try {
      const { extractors: suggested } = await execute.proposeExtractors(tid, auth)
      if (!suggested.length) {
        setNotice('Nothing reusable was found in the response.')
      } else {
        setExtractors(suggested)
        setNotice(`Suggested ${suggested.length} extractor(s). Save to keep them.`)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function judge(runId, caseId, verdict) {
    try {
      await runs.feedback(runId, caseId, { verdict })
      setNotice(
        verdict === 'accepted'
          ? 'Marked correct — it will be used as an example next time.'
          : 'Marked wrong — the model will be warned about this category next time.',
      )
      setInsights(await runs.insights(tid))
    } catch (e) {
      setError(e.message)
    }
  }

  const usedVars = [...new Set([...form.curl.matchAll(PLACEHOLDER)].map((m) => m[1]))]

  return (
    <>
      <div className="crumbs">
        <Link to="/api-testing">API Testing</Link> /{' '}
        <Link to={`/api-testing/groups/${gid}`}>{group?.name || '…'}</Link> /{' '}
        {isNew ? 'New API test' : form.name || 'Edit'}
      </div>

      <div className="page-head">
        <div>
          <h2>{isNew ? 'Add API Test' : 'Edit API Test'}</h2>
          <p>
            {isNew
              ? 'Name the test, then paste the cURL for the endpoint.'
              : 'Changes are saved with the Save test button.'}
          </p>
        </div>
        <div className="actions">
          <button onClick={() => navigate(`/api-testing/groups/${gid}`)}>Back to group</button>
          {!isNew && (
            <button onClick={() => navigate(`/api-testing/tests/${tid}/history`)}>History</button>
          )}
        </div>
      </div>

      <Banner kind="error">{error}</Banner>
      <Banner kind="info">{notice}</Banner>

      <div className="panel">
        {/* API Test Name comes first, before the cURL, as requested. */}
        <label className="field">
          <span>API Test Name:</span>
          <input
            value={form.name}
            onChange={update('name')}
            placeholder="e.g. Authentication, fetchEventList, createEvent"
            autoFocus={isNew}
          />
          <span className="hint">For recognising this test. Must be unique within the group.</span>
        </label>

        <label className="field">
          <span>Paste your cURL command</span>
          <textarea
            rows={7}
            value={form.curl}
            onChange={update('curl')}
            placeholder={
              "curl -X POST 'https://example.com/api/token' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"user\":\"a\",\"pass\":\"b\"}'"
            }
          />
        </label>

        {usedVars.length > 0 && (
          <div className="notice info">
            This test uses captured values:{' '}
            {usedVars.map((v) => (
              <span
                key={v}
                className={`badge ${vars.some((x) => x.name === v) ? 'ok' : 'warn'}`}
                style={{ marginRight: 6 }}
              >
                {v}
              </span>
            ))}
            {usedVars.filter((v) => !vars.some((x) => x.name === v)).length > 0 && (
              <div style={{ marginTop: 6 }}>
                Run the earlier test in this group that produces the missing value first.
              </div>
            )}
          </div>
        )}

        <div className="row2">
          <label className="field">
            <span>
              What should be tested? <span className="hint">(optional)</span>
            </span>
            <input
              value={form.instruction}
              onChange={update('instruction')}
              placeholder="e.g. Test all positive and negative scenarios"
            />
          </label>
          <label className="field">
            <span>Method</span>
            <select value={form.method} onChange={update('method')}>
              <option value="">Auto (from cURL)</option>
              {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="panel" style={{ background: '#f8fafc', marginBottom: 14 }}>
          <h3>
            Authentication <span className="hint muted">(for this run; save as variables to reuse)</span>
          </h3>
          <div className="row2">
            <label className="field">
              <span>Bearer token</span>
              <input
                type="password"
                value={auth.token}
                onChange={(e) => setAuth((a) => ({ ...a, token: e.target.value }))}
              />
              {auth.token && (
                <button
                  className="small"
                  style={{ marginTop: 6 }}
                  onClick={() => saveAuthAsVariable('token')}
                  disabled={savingAuth.token}
                >
                  {savingAuth.token ? 'Saving…' : 'Save as variable "token"'}
                </button>
              )}
            </label>
            <div className="row-inline">
              <label className="field">
                <span>Username</span>
                <input
                  value={auth.username}
                  onChange={(e) => setAuth((a) => ({ ...a, username: e.target.value }))}
                />
                {auth.username && (
                  <button
                    className="small"
                    style={{ marginTop: 6 }}
                    onClick={() => saveAuthAsVariable('username')}
                    disabled={savingAuth.username}
                  >
                    {savingAuth.username ? 'Saving…' : 'Save as variable "username"'}
                  </button>
                )}
              </label>
              <label className="field">
                <span>Password</span>
                <input
                  type="password"
                  value={auth.password}
                  onChange={(e) => setAuth((a) => ({ ...a, password: e.target.value }))}
                />
                {auth.password && (
                  <button
                    className="small"
                    style={{ marginTop: 6 }}
                    onClick={() => saveAuthAsVariable('password')}
                    disabled={savingAuth.password}
                  >
                    {savingAuth.password ? 'Saving…' : 'Save as variable "password"'}
                  </button>
                )}
              </label>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="primary" onClick={save} disabled={busy}>
            {busy ? 'Saving…' : 'Save test'}
          </button>
          <button onClick={run} disabled={runningAs !== ''}>
            {runningAs === 'test' ? 'Checking the API, then generating tests…' : 'Run test'}
          </button>
          <button onClick={tryWithoutSaving} disabled={runningAs !== ''}>
            {runningAs === 'adhoc' ? 'Checking the API, then generating tests…' : 'Try without saving'}
          </button>
          {!isNew && (
            <button onClick={propose} disabled={busy}>
              Suggest value extractors
            </button>
          )}
        </div>
        {isNew && (
          <p className="hint" style={{ marginTop: 8 }}>
            <strong>Run test</strong> will auto-save the test first, then run it and attach
            the result to history. <strong>Try without saving</strong> checks the endpoint
            immediately and records nothing.
          </p>
        )}
      </div>

      {extractors.length > 0 && (
        <div className="panel">
          <h3>Values captured from this endpoint</h3>
          <p className="muted small-text">
            After a passing run these are stored for the group, and substituted wherever a
            later test writes <code>{'{{name}}'}</code>.
          </p>
          <table className="grid">
            <thead>
              <tr>
                <th>Variable name</th>
                <th>Read from response at</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {extractors.map((x, i) => (
                <tr key={`${x.name}-${i}`}>
                  <td>
                    <input
                      value={x.name}
                      onChange={(e) => {
                        const next = [...extractors]
                        next[i] = { ...next[i], name: e.target.value }
                        setExtractors(next)
                      }}
                    />
                  </td>
                  <td>
                    <input
                      className="mono"
                      value={x.selector}
                      onChange={(e) => {
                        const next = [...extractors]
                        next[i] = { ...next[i], selector: e.target.value }
                        setExtractors(next)
                      }}
                    />
                  </td>
                  <td>
                    <button
                      className="danger small"
                      onClick={() => setExtractors(extractors.filter((_, j) => j !== i))}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {result && <RunResult result={result} onFeedback={judge} />}

      {insights && insights.learned_cases > 0 && (
        <div className="panel">
          <h3>Learned so far</h3>
          <p className="small-text">
            {insights.learned_cases} case
            {insights.learned_cases === 1 ? '' : 's'} you have judged on this test are replayed
            to the model as examples next time.
          </p>
          <table className="grid">
            <thead>
              <tr>
                <th>Category</th>
                <th className="num">Cases</th>
                <th className="num">Passed</th>
                <th className="num">Rejected by you</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(insights.category_stats).map(([cat, s]) => (
                <tr key={cat}>
                  <td>{cat}</td>
                  <td className="num">{s.total}</td>
                  <td className="num">{s.passed}</td>
                  <td className="num">{insights.rejected_categories[cat] || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function RunResult({ result, onFeedback }) {
  if (result.needs_auth) {
    return (
      <div className="panel">
        <h3>Result</h3>
        <div className="notice warn">
          {result.rejected
            ? 'Credentials were rejected (401/403). Check the username/password or token and run again.'
            : 'This API requires authentication. Fill in the Authentication fields above and run again.'}
        </div>
      </div>
    )
  }

  if (result.blocked) {
    return (
      <div className="panel">
        <h3>Result</h3>
        <div className="notice warn">
          Not run: missing {result.missing_variables.join(', ')}. Run the earlier test in
          this group that produces it.
        </div>
      </div>
    )
  }

  const cases = result.results || []
  return (
    <div className="panel">
      <h3>
        Result · <span className={result.passed === result.total ? 'badge ok' : 'badge bad'}>
          {result.passed}/{result.total} passed
        </span>
        {result.run_id && (
          <span className="muted small-text" style={{ fontWeight: 400, marginLeft: 8 }}>
            saved as run {result.run_id}
          </span>
        )}
      </h3>
      {result.error && <div className="notice warn">{result.error}</div>}
      <p className="muted small-text">Click a row for the full request and response.</p>
      <ResultsTable
        runId={result.run_id}
        cases={cases}
        onFeedback={(caseId, verdict) => onFeedback(result.run_id, caseId, verdict)}
      />
      {result.suggested_extractors?.length > 0 && (
        <div className="notice info">
          Values that later tests in this group could reuse:{' '}
          {result.suggested_extractors.map((x) => (
            <span key={x.name} className="var-chip" style={{ marginLeft: 6 }}>
              {x.name} ← {x.selector}
            </span>
          ))}
          <div style={{ marginTop: 6 }}>
            Use <strong>Suggest value extractors</strong> above to store these on the test.
          </div>
        </div>
      )}
    </div>
  )
}
