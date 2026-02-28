import type { LogEntry } from '../../types';

export function ActivityLog({ entries }: { entries: LogEntry[] }) {
  return (
    <div className="ds-log-panel" id="log-panel">
      <h2>Activity Log</h2>
      <div id="log">
        {entries.length === 0 && (
          <div className="ds-empty-state">No activity yet.</div>
        )}
        {entries.map((e, i) => (
          <div key={i} className={`log-entry ${e.type}`}>
            <span className="log-time">[{e.time}]</span> {e.message}
          </div>
        ))}
      </div>
    </div>
  );
}
