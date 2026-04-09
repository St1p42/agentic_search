'use client';

import { useState, FormEvent } from 'react';
import styles from './SearchHeader.module.css';

interface SearchHeaderProps {
  initialQuery?: string;
  onSearch: (query: string) => void;
  isLoading?: boolean;
  resultsCount?: number;
  entityType?: string;
  viewMode: 'table' | 'json';
  onViewModeChange: (mode: 'table' | 'json') => void;
  showSources: boolean;
  onShowSourcesChange: (show: boolean) => void;
}

export function SearchHeader({
  initialQuery = '',
  onSearch,
  isLoading = false,
  resultsCount,
  entityType,
  viewMode,
  onViewModeChange,
  showSources,
  onShowSourcesChange,
}: SearchHeaderProps) {
  const [query, setQuery] = useState(initialQuery);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      onSearch(query.trim());
    }
  };

  return (
    <header className={styles.header}>
      <div className={styles.container}>
        <form onSubmit={handleSubmit} className={styles.searchForm}>
          <div className={styles.searchInputWrapper}>
            <svg
              className={styles.searchIcon}
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Search for entities... e.g., AI startups in healthcare"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={isLoading}
            />
            {isLoading && (
              <div className={styles.loadingIndicator}>
                <div className={styles.spinner} />
              </div>
            )}
          </div>
        </form>

        {(resultsCount !== undefined || entityType) && (
          <div className={styles.toolbar}>
            <div className={styles.toolbarLeft}>
              {resultsCount !== undefined && (
                <span className={styles.resultsCount}>
                  {resultsCount} {resultsCount === 1 ? 'result' : 'results'}
                </span>
              )}
              {entityType && (
                <span className={styles.entityType}>{entityType}</span>
              )}
            </div>
            <div className={styles.toolbarRight}>
              <div className={styles.viewToggle}>
                <button
                  className={`${styles.viewButton} ${viewMode === 'table' ? styles.viewButtonActive : ''}`}
                  onClick={() => onViewModeChange('table')}
                >
                  Table
                </button>
                <button
                  className={`${styles.viewButton} ${viewMode === 'json' ? styles.viewButtonActive : ''}`}
                  onClick={() => onViewModeChange('json')}
                >
                  JSON
                </button>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={showSources}
                className={`${styles.sourcesToggle} ${showSources ? styles.sourcesToggleActive : ''}`}
                onClick={() => onShowSourcesChange(!showSources)}
              >
                <span className={styles.sourcesToggleTrack}>
                  <span className={styles.sourcesToggleThumb} />
                </span>
                <span className={styles.sourcesToggleLabel}>Sources</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
