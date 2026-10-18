import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { isValidDismissalReason } from "./review";

interface DismissReasonDialogProps {
  open: boolean;
  findingTitle: string;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}

export function DismissReasonDialog({ open, findingTitle, onCancel, onConfirm }: DismissReasonDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isValidDismissalReason(reason)) {
      setError("Add a short reason (5–500 characters) so this dismissal can be reviewed later.");
      return;
    }
    onConfirm(reason.trim());
    setReason("");
    setError("");
    dialogRef.current?.close();
  }

  function close() {
    setReason("");
    setError("");
    onCancel();
  }

  return <dialog ref={dialogRef} className="dismiss-dialog" aria-labelledby="dismiss-dialog-title" onClose={close}>
    <form onSubmit={submit}>
      <p className="section-kicker">TRIAGE DECISION</p>
      <h2 id="dismiss-dialog-title">Dismiss this finding?</h2>
      <p className="dialog-finding-title">{findingTitle}</p>
      <label htmlFor="dismiss-reason">Reason <span>Required</span></label>
      <textarea id="dismiss-reason" value={reason} onChange={(event) => { setReason(event.target.value); setError(""); }}
        maxLength={500} minLength={5} required autoFocus rows={4}
        aria-describedby={error ? "dismiss-reason-error" : "dismiss-reason-help"} />
      {error ? <p id="dismiss-reason-error" className="form-error" role="alert">{error}</p> :
        <p id="dismiss-reason-help" className="form-help">Keep the reason concise. It is saved in this browser for this review.</p>}
      <div className="dialog-actions">
        <button type="button" className="secondary-button" onClick={() => dialogRef.current?.close()}>Cancel</button>
        <button type="submit" className="dismiss-confirm">Dismiss finding</button>
      </div>
    </form>
  </dialog>;
}
