import { useEffect, useState } from 'react'

export function Modal({ title, onClose, children, onSubmit, submitLabel = 'Save', busy }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form
        className="modal"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit()
        }}
      >
        <h3>{title}</h3>
        {children}
        <div className="actions">
          <button type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? 'Saving…' : submitLabel}
          </button>
        </div>
      </form>
    </div>
  )
}

export function ConfirmButton({ label = 'Delete', onConfirm, busy }) {
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return undefined
    const timer = setTimeout(() => setArmed(false), 4000)
    return () => clearTimeout(timer)
  }, [armed])

  return (
    <button
      type="button"
      className="danger small"
      disabled={busy}
      onClick={() => (armed ? onConfirm() : setArmed(true))}
    >
      {armed ? 'Confirm?' : label}
    </button>
  )
}

export function Banner({ kind = 'info', children }) {
  if (!children) return null
  return <div className={`notice ${kind}`}>{children}</div>
}

export function formatWhen(iso) {
  if (!iso) return '—'
  // Stored as UTC with an explicit Z; show it in the viewer's locale.
  return new Date(iso).toLocaleString()
}
