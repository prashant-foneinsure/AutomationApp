import { useState } from 'react'
import { variables } from '../../api.js'
import { ConfirmButton } from '../../components/ui.jsx'

// The values one test captures and a later test reuses. Values arrive from
// passing runs, but they are also editable and addable by hand: sometimes you
// already hold a working token and do not want to run the whole chain to get it.
export default function VariablesPanel({ groupId, items, onChanged, onError }) {
  const [draft, setDraft] = useState({ name: '', value: '' })
  const [edits, setEdits] = useState({})
  const [busy, setBusy] = useState(false)

  async function saveValue(name) {
    const value = edits[name]
    if (value === undefined) return
    setBusy(true)
    try {
      await variables.update(groupId, name, value)
      setEdits((e) => {
        const next = { ...e }
        delete next[name]
        return next
      })
      onError('')
      await onChanged()
    } catch (e) {
      onError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function addValue() {
    const name = draft.name.trim()
    if (!name) return
    setBusy(true)
    try {
      await variables.update(groupId, name, draft.value)
      setDraft({ name: '', value: '' })
      onError('')
      await onChanged()
    } catch (e) {
      onError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(name) {
    try {
      await variables.remove(groupId, name)
      onError('')
      await onChanged()
    } catch (e) {
      onError(e.message)
    }
  }

  return (
    <div className="panel">
      <h3>Values carried between tests</h3>
      {items.length === 0 ? (
        <p className="muted">
          None yet. When a test's response yields something reusable (such as a
          token) it is stored here and substituted into later tests that write{' '}
          <code>{'{{token}}'}</code>. You can also add a value yourself below.
        </p>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>Name</th>
              <th>Value</th>
              <th>Captured by</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((v) => (
              <tr key={v.name}>
                <td className="mono">
                  <code>{`{{${v.name}}}`}</code>
                </td>
                <td>
                  <input
                    value={edits[v.name] ?? v.value ?? ''}
                    onChange={(e) => setEdits((s) => ({ ...s, [v.name]: e.target.value }))}
                    title={v.value}
                  />
                </td>
                <td className="muted small-text">
                  {v.source_test_id ? `test ${v.source_test_id}` : 'set by hand'}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {edits[v.name] !== undefined && (
                      <button
                        className="small primary"
                        disabled={busy}
                        onClick={() => saveValue(v.name)}
                      >
                        Save
                      </button>
                    )}
                    <ConfirmButton
                      onConfirm={() => remove(v.name)}
                      busy={busy}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="row-inline" style={{ marginTop: 12 }}>
        <label className="field" style={{ marginBottom: 0 }}>
          <span>Add a value by hand</span>
          <input
            value={draft.name}
            onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            placeholder="name, e.g. token"
          />
        </label>
        <label className="field" style={{ marginBottom: 0, flex: 1 }}>
          <span>Value</span>
          <input
            value={draft.value}
            onChange={(e) => setDraft((d) => ({ ...d, value: e.target.value }))}
            onKeyDown={(e) => e.key === 'Enter' && addValue()}
            placeholder="value to substitute"
          />
        </label>
        <button
          style={{ alignSelf: 'flex-end', marginBottom: 2 }}
          disabled={busy || !draft.name.trim()}
          onClick={addValue}
        >
          Add
        </button>
      </div>
    </div>
  )
}
