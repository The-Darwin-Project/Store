import { useState, useCallback, useMemo } from 'react';

export function useSearch<T>(items: T[], searchFields: (keyof T)[]) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    if (!query.trim()) return items;
    const lower = query.toLowerCase();
    return items.filter(item =>
      searchFields.some(field => {
        const val = item[field];
        return typeof val === 'string' && val.toLowerCase().includes(lower);
      })
    );
  }, [items, query, searchFields]);

  const handleSearch = useCallback((value: string) => {
    setQuery(value);
  }, []);

  return { query, setQuery: handleSearch, filtered };
}
