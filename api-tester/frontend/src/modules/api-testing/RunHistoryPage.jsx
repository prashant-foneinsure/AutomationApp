import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { runs } from '../../api.js'
import { Banner, formatWhen } from '../../components/ui.jsx'
import ResultsTable from './ResultsTable.jsx'

// Run history for one test, with a drill-down into a single run.
export default function RunHistoryPage() {
  const { testId } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tid = Number(testId)
  const openRun = params.get('run')

  const [list, setList] = useState([])
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setList(await runs.listForTest(tid))
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [tid])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!openRun) {
      setDetail(null)
      return
    }
    runs
      .get(Number(openRun))
      .then(setDetail)
      .catch((e) => setError(e.message))
  }, [openRun])

  async function judge(runId, caseId, verdict) {
    try {
      await runs.feedback(runId, caseId, { verdict })
      setDetail(await runs.get(Number(runId)))
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <>
      <div className="crumbs">
        <Link to="/api-testing">API Testing</Link> / Run history
      </div>

      <div className="page-head">
        <div>
          <h2>Run history</h2>
          <p>Every saved run of this test, newest first.</p>
        </div>
        <div className="actions">
          <button onClick={() => navigate(-1)}>Back</button>
          {list[0]?.group_id != null && (
            <button
              className="primary"
              onClick={() => navigate(`/api-testing/groups/${list[0].group_id}/tests/${tid}`)}
            >
              Open test
            </button>
          )}
        </div>
      </div>

      <Banner kind="error">{error}</Banner>

      <div className="panel">
        {list.length === 0 ? (
          <p className="muted">This test has not been run yet.</p>
        ) : (
          <table className="grid">
            <thead>
              <tr>
                <th>Started</th>
                <th className="num">Baseline</th>
                <th className="num">Cases passed</th>
                <th className="num">ms</th>
                <th>Outcome</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.run_id} className={r.run_id === Number(openRun) ? 'clickable' : ''}>
                  <td>{formatWhen(r.started_at)}</td>
                  <td className="num">{r.baseline_status ?? '—'}</td>
                  <td className="num">
                    <span className={`badge ${r.passed_count === r.total_count ? 'ok' : 'bad'}`}>
                      {r.passed_count}/{r.total_count}
                    </span>
                  </td>
                  <td className="num">{r.duration_ms}</td>
                  <td>
                    <span className="badge">{r.outcome}</span>
                  </td>
                  <td>
                    <button
                      className="small"
                      onClick={() => setParams({ run: String(r.run_id) })}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {detail && (
        <div className="panel">
          <h3>
            Run {detail.run_id} · {formatWhen(detail.started_at)}
          </h3>
          {detail.cases?.length ? (
            <ResultsTable
              runId={detail.run_id}
              cases={detail.cases}
              onFeedback={judge}
            />
          ) : (
            <p className="muted">This run recorded no cases.</p>
          )}
        </div>
      )}
    </>
  )
}
