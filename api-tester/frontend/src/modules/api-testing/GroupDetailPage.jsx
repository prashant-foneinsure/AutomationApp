import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { execute, groups, tests, variables } from '../../api.js'
import { Banner, ConfirmButton } from '../../components/ui.jsx'
import VariablesPanel from './VariablesPanel.jsx'

// The list of API tests inside one group. This is where "Add API Test" lives.
export default function GroupDetailPage() {
  const { groupId } = useParams()
  const navigate = useNavigate()
  const gid = Number(groupId)

  const [group, setGroup] = useState(null)
  const [items, setItems] = useState([])
  const [vars, setVars] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [running, setRunning] = useState(false)

  const load = useCallback(async () => {
    try {
      const [g, t, v] = await Promise.all([
        groups.get(gid),
        tests.list(gid),
        variables.list(gid),
      ])
      setGroup(g)
      setItems(t)
      setVars(v)
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [gid])

  useEffect(() => {
    load()
  }, [load])

  async function doRunGroup(stopOnFailure) {
    setRunning(true)
    setError('')
    setNotice('')
    try {
      const result = await execute.group(gid, { stop_on_failure: stopOnFailure })
      const ran = result.steps.filter((s) => !s.skipped).length
      const skipped = result.steps.filter((s) => s.skipped).length
      setNotice(
        `Group run finished: ${ran} executed, ${skipped} skipped. ` +
          'Captured values are now available to later tests.',
      )
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  async function removeTest(t) {
    setBusy(true)
    try {
      await tests.remove(t.test_id)
      setNotice(`Test "${t.name}" deleted.`)
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (!group) {
    return <Banner kind="error">{error || 'Loading…'}</Banner>
  }

  return (
    <>
      <div className="crumbs">
        <Link to="/api-testing">API Testing</Link> / {group.name}
      </div>

      <div className="page-head">
        <div>
          <h2>{group.name}</h2>
          <p>
            {group.description || 'No description'} · {items.length} test
            {items.length === 1 ? '' : 's'}
          </p>
        </div>
        <div className="actions">
          <button onClick={() => navigate('/api-testing')}>Back to API Testing</button>
          <button
            className="primary"
            onClick={() => navigate(`/api-testing/groups/${gid}/tests/new`)}
          >
            Add API Test
          </button>
          <button disabled={running} onClick={() => doRunGroup(true)}>
            {running ? 'Running…' : 'Run group in order'}
          </button>
        </div>
      </div>

      <Banner kind="error">{error}</Banner>
      <Banner kind="info">{notice}</Banner>

      <div className="panel">
        <h3>API tests</h3>
        {items.length === 0 ? (
          <p className="muted">
            This group has no tests yet. Add the individual endpoints, e.g.{' '}
            <em>Authentication</em> for <code>/api/token</code> and{' '}
            <em>fetchEventList</em> for <code>/api/event/fetch-upcoming-event-list</code>.
          </p>
        ) : (
          <table className="grid">
            <thead>
              <tr>
                <th className="num">Order</th>
                <th>Test</th>
                <th>Request</th>
                <th>Uses variables</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => {
                const used = [...t.curl.matchAll(/\{\{\s*([\w.-]+)\s*\}\}/g)].map((m) => m[1])
                return (
                  <tr key={t.test_id}>
                    <td className="num">{t.sort_order}</td>
                    <td>
                      <strong>{t.name}</strong>
                    </td>
                    <td className="mono muted">{summarise(t.curl)}</td>
                    <td>
                      {used.length === 0 ? (
                        <span className="muted small-text">—</span>
                      ) : (
                        used.map((u) => (
                          <span key={u} className={`badge ${vars.some((v) => v.name === u) ? 'ok' : 'warn'}`}>
                            {u}
                          </span>
                        ))
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <button
                          className="small primary"
                          onClick={() => navigate(`/api-testing/groups/${gid}/tests/${t.test_id}`)}
                        >
                          Open
                        </button>
                        <button
                          className="small"
                          onClick={() => navigate(`/api-testing/tests/${t.test_id}/history`)}
                        >
                          History
                        </button>
                        <ConfirmButton onConfirm={() => removeTest(t)} busy={busy} />
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <VariablesPanel
        groupId={gid}
        items={vars}
        onChanged={load}
        onError={setError}
      />
    </>
  )
}

function summarise(curl) {
  const method = (curl.match(/-X\s+(\w+)/) || [])[1] || ''
  const url = (curl.match(/https?:\/\/[^\s'"]+/) || [])[0] || ''
  return `${method || 'GET'} ${url}`.trim()
}
