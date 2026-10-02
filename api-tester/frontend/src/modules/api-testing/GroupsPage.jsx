import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { groups} from '../../api.js'
import { Banner, ConfirmButton, Modal, formatWhen } from '../../components/ui.jsx'

// Landing page for the API Testing module: every saved group, plus the most
// recent activity across all of them.
export default function GroupsPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState(null)
  const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setItems(await groups.list())
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function createGroup(name, description) {
    setBusy(true)
    try {
      const { group_id } = await groups.create({ name, description })
      setCreating(false)
      setNotice(`Group "${name}" created.`)
      navigate(`/api-testing/groups/${group_id}`)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function saveGroup(name, description) {
    setBusy(true)
    try {
      await groups.update(editing.group_id, { name, description })
      setEditing(null)
      setNotice(`Group renamed to "${name}".`)
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function removeGroup(group) {
    setBusy(true)
    try {
      await groups.remove(group.group_id)
      setNotice(`Group "${group.name}" deleted.`)
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h2>API Testing</h2>
          <p>Groups of interrelated API tests, and everything you have run so far.</p>
        </div>
        <div className="actions">
          <button className="primary" onClick={() => setCreating(true)}>
            Add API Testing Group
          </button>
        </div>
      </div>

      <Banner kind="error">{error}</Banner>
      <Banner kind="info">{notice}</Banner>

      <div className="panel">
        <h3>Test groups</h3>
        {items.length === 0 ? (
          <p className="muted">
            No groups yet. Use <strong>Add API Testing Group</strong> to start one, e.g.{' '}
            <em>Event API testing</em>, then add the individual API tests inside it.
          </p>
        ) : (
          <table className="grid">
            <thead>
              <tr>
                <th>Group</th>
                <th>Description</th>
                <th className="num">Tests</th>
                <th>Last run</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((g) => (
                <tr key={g.group_id}>
                  <td>
                    <strong>{g.name}</strong>
                  </td>
                  <td className="muted">{g.description || '—'}</td>
                  <td className="num">{g.test_count}</td>
                  <td className="muted small-text">{formatWhen(g.last_run_at)}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <button
                        className="small"
                        onClick={() => navigate(`/api-testing/groups/${g.group_id}`)}
                        title="Open the list of API tests in this group"
                      >
                        Open
                      </button>
                      <button className="small" onClick={() => setEditing(g)}>
                        Rename
                      </button>
                      <ConfirmButton
                        onConfirm={() => removeGroup(g)}
                        busy={busy}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      

      {creating && (
        <GroupForm
          title="Add API Testing Group"
          onClose={() => setCreating(false)}
          onSubmit={createGroup}
          busy={busy}
        />
      )}
      {editing && (
        <GroupForm
          title={`Rename "${editing.name}"`}
          initial={editing}
          onClose={() => setEditing(null)}
          onSubmit={saveGroup}
          busy={busy}
        />
      )}
    </>
  )
}

function GroupForm({ title, initial, onClose, onSubmit, busy }) {
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')

  return (
    <Modal
      title={title}
      onClose={onClose}
      busy={busy}
      onSubmit={() => name.trim() && onSubmit(name.trim(), description.trim() || null)}
    >
      <label className="field">
        <span>Group name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Event API testing"
          autoFocus
        />
        <span className="hint">
          Groups exist to hold API tests that belong together, e.g. all the calls for
          one feature area.
        </span>
      </label>
      <label className="field">
        <span>Description <span className="hint">(optional)</span></span>
        <textarea
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What this group covers"
        />
      </label>
    </Modal>
  )
}
