'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createSearchApiClient, SearchClient } from '@/lib/search-client';
import { SearchState, Source } from '@/types';

const INITIAL_STATE: SearchState = {
  status: 'idle',
  query: '',
  schema: null,
  rows: [],
  stages: [],
  sourcesCount: 0,
  freshness: '',
  overallConfidence: 0,
};

interface SearchSessionResult {
  searchState: SearchState;
  sources: Source[];
  activityCollapsed: boolean;
  setActivityCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  runSearch: (query: string) => void;
  resetSearch: () => void;
}

export function useSearchSession(client: SearchClient = createSearchApiClient()): SearchSessionResult {
  const [searchState, setSearchState] = useState<SearchState>(INITIAL_STATE);
  const [sources, setSources] = useState<Source[]>([]);
  const [activityCollapsed, setActivityCollapsed] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (searchState.status === 'running' || searchState.status === 'connecting') {
      setActivityCollapsed(false);
    } else if (searchState.status === 'completed') {
      setActivityCollapsed(true);
    }
  }, [searchState.status]);

  useEffect(() => {
    return () => {
      cleanupRef.current?.();
    };
  }, []);

  const runSearch = useCallback(
    (query: string) => {
      cleanupRef.current?.();
      setSources([]);

      cleanupRef.current = client.runSearch(query, (snapshot) => {
        const { sources: nextSources, ...nextState } = snapshot;
        setSources(nextSources);
        setSearchState(nextState);
      });
    },
    [client]
  );

  const resetSearch = useCallback(() => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    setSearchState(INITIAL_STATE);
    setSources([]);
    setActivityCollapsed(false);
  }, []);

  return useMemo(
    () => ({
      searchState,
      sources,
      activityCollapsed,
      setActivityCollapsed,
      runSearch,
      resetSearch,
    }),
    [activityCollapsed, resetSearch, runSearch, searchState, sources]
  );
}
