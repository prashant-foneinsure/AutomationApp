import { useState } from 'react'
import { runs } from '../../api.js'

// Renders one run's cases. Clicking a row expands the request/response detail,
// matching the behaviour of the original single-file UI.
export default function ResultsTable({ runId, cases, onFeedback }) {
  const [open, setOpen] = useState(null)

  if (!cases || !cases.length) {
    return <p className="muted small-text">No cases in this run.</p>
  }

  return (
    <>
      <table className="grid">
        <thead>
          <tr>
            <th>Test</th>
            <th>Category</th>
            <th>Expected</th>
            <th>Actual</th>
            <th>ms</th>
            <th>Result</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c, i) => (
            <Row
              key={c.case_id ?? i}
              testCase={c}
              runId={runId}
              expanded={open === i}
              onToggle={() => setOpen(open === i ? null : i)}
              onFeedback={onFeedback}
            />
          ))}
        </tbody>
      </table>
    </>
  )
}

function Row({ testCase, runId, expanded, onToggle, onFeedback }) {
  const c = testCase
  const canJudge = c.case_id && c.origin !== 'baseline'
  const verdict = c.verdict

  return (
    <>
      <tr className={`clickable ${c.passed ? 'pass' : 'fail'}`} onClick={onToggle}>
        <td>{c.name}</td>
        <td>
          <span className="badge">{c.category}</span>
        </td>
        <td className="num">{c.expected_status ?? '—'}</td>
        <td className="num">{c.actual_status ?? '—'}</td>
        <td className="num">{c.time_ms}</td>
        <td>
          <span className={`badge ${c.passed ? 'ok' : 'bad'}`}>
            {c.passed ? 'PASS' : 'FAIL'}
          </span>
        </td>
        <td>
          {canJudge && (
            <span onClick={(e) => e.stopPropagation()}>
              <button
                className="small"
                title="This case is a correct expectation — reuse it next time"
                style={verdict === 'accepted' ? { background: '#bbf7d0' } : undefined}
                onClick={() => onFeedback(c.case_id, 'accepted')}
              >
                ✓
              </button>{' '}
              <button
                className="small"
                title="This expectation is wrong — avoid it next time"
                style={verdict === 'rejected' ? { background: '#fecaca' } : undefined}
                onClick={() => onFeedback(c.case_id, 'rejected')}
              >
                ✗
              </button>
            </span>
          )}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={7} style={{ background: '#f8fafc' }}>
            <pre className="detail">
              {`REQUEST
${c.request ? JSON.stringify(c.request, null, 2) : '(not stored for this case)'}

RESPONSE HEADERS
${pretty(c.response_headers)}

RESPONSE BODY
${c.response_body ?? c.response ?? '(empty)'}`}
            </pre>
          </td>
        </tr>
      )}
    </>
  )
}

function pretty(value) {
  if (!value) return '(none)'
  try {
    return JSON.stringify(JSON.parse(value), null, 2)
  } catch {
    return String(value)
  }
}

export function useFeedback() {
  // Accept/reject on a generated case is the learning signal; it is stored and
  // replayed as few-shot context on the next generation for this test.
  return async (runId, caseId, verdict) => {
    await runs.feedback(runId, caseId, { verdict })
  }
}
