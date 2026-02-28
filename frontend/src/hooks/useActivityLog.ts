import { useState, useCallback } from 'react';
import type { LogEntry } from '../types';

export function useActivityLog() {
  const [entries, setEntries] = useState<LogEntry[]>([]);

  const log = useCallback((message: string, type: LogEntry['type'] = 'info') => {
    const time = new Date().toLocaleTimeString();
    setEntries(prev => [{ time, message, type }, ...prev].slice(0, 50));
  }, []);

  return { entries, log };
}
