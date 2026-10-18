import { useEffect, useState } from "react";
import type { Finding, ReviewDiffFile } from "./types";

interface ReviewDiffProps {
  files: ReviewDiffFile[];
  findings: Finding[];
  selectedFindingId?: string;
  navigationVersion: number;
  onSelectFinding: (findingId: string) => void;
  isDemo: boolean;
}

export function ReviewDiff({ files, findings, selectedFindingId, onSelectFinding, isDemo, navigationVersion }: ReviewDiffProps) {
  const initialPath = findings.find((item) => item.id === selectedFindingId)?.file_path;
  const [activePath, setActivePath] = useState(initialPath ?? files[0]?.path ?? "");
  const activeFile = files.find((file) => file.path === activePath) ?? files[0];

  useEffect(() => {
    const selectedPath = findings.find((item) => item.id === selectedFindingId)?.file_path;
    if (selectedPath && files.some((file) => file.path === selectedPath)) setActivePath(selectedPath);
    if (!selectedFindingId) return;
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById(`diff-line-${selectedFindingId}`);
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      target?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [files, findings, selectedFindingId, navigationVersion]);

  if (!files.length) {
    return <section className="diff-viewer diff-unavailable" aria-label="Changed file preview">
      <div className="diff-toolbar"><strong>Changed-file context</strong><span>NOT PROVIDED</span></div>
      <p>This review response does not include a source diff. Use the file and line references and the finding evidence below.</p>
    </section>;
  }

  return <section className="diff-viewer" aria-label="Changed-file diff">
    <div className="diff-toolbar"><strong>{isDemo ? "Illustrative changed-file excerpts" : "Changed files"}</strong>
      <span>{isDemo ? "DEMO FIXTURE" : `${files.length} FILE${files.length === 1 ? "" : "S"}`}</span>
    </div>
    {isDemo && <p className="diff-demo-note">Curated sample context · this is not output from a real repository scan.</p>}
    <div className="diff-file-tabs" role="tablist" aria-label="Changed files">
      {files.map((file) => {
        const selected = file.path === activeFile?.path;
        const markerCount = findings.filter((finding) => finding.file_path === file.path).length;
        return <button key={file.path} role="tab" aria-selected={selected} aria-controls="diff-file-panel"
          className={selected ? "diff-file-tab active" : "diff-file-tab"} onClick={() => setActivePath(file.path)}>
          <span>{file.path}</span><small>{markerCount} {markerCount === 1 ? "finding" : "findings"}</small>
        </button>;
      })}
    </div>
    {activeFile && <div id="diff-file-panel" role="tabpanel" className="diff-code" aria-label={`Diff for ${activeFile.path}`}>
      <div className="diff-code-header"><code>{activeFile.path}</code><span>NEW FILE LINE</span></div>
      <ol className="diff-lines">
        {activeFile.lines.map((line, index) => {
          const lineFindings = findings.filter((finding) => finding.file_path === activeFile.path &&
            line.line >= finding.line && line.line <= (finding.end_line ?? finding.line));
          return <li key={`${line.line}-${line.kind}-${index}`} className={`diff-line diff-${line.kind}`}>
            <span className="diff-gutter" aria-hidden="true">{line.line}</span>
            <span className="diff-sign" aria-hidden="true">{line.kind === "addition" ? "+" : line.kind === "deletion" ? "−" : " "}</span>
            <code>{line.text || " "}</code>
            {lineFindings.length > 0 && <span className="diff-markers" aria-label="Findings on this line">
              {lineFindings.map((finding) => <span key={finding.id} id={`diff-line-${finding.id}`}>
                <button className={`inline-finding inline-${finding.severity}`} onClick={() => onSelectFinding(finding.id)}
                  aria-label={`Show ${finding.severity} finding: ${finding.title}, ${finding.file_path}, line ${line.line}`}>
                  {finding.severity} · {finding.id}
                </button>
              </span>)}
            </span>}
          </li>;
        })}
      </ol>
    </div>}
  </section>;
}
