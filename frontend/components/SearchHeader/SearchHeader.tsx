'use client';

import { FormEvent } from 'react';
import styles from './SearchHeader.module.css';

interface SearchHeaderProps {
  query: string;
  onQueryChange: (query: string) => void;
  onSearch: (query: string) => void;
  onReset?: () => void;
  isLoading?: boolean;
  resultsCount?: number;
  entityType?: string;
  viewMode: 'table' | 'json';
  onViewModeChange: (mode: 'table' | 'json') => void;
  showEvidence: boolean;
  onShowEvidenceChange: (show: boolean) => void;
}

export function SearchHeader({
  query,
  onQueryChange,
  onSearch,
  onReset,
  isLoading = false,
  resultsCount,
  entityType,
  viewMode,
  onViewModeChange,
  showEvidence,
  onShowEvidenceChange,
}: SearchHeaderProps) {
  const showToolbar = resultsCount !== undefined || entityType || Boolean(onReset);

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
              onChange={(e) => onQueryChange(e.target.value)}
              disabled={isLoading}
            />
            <button
              type="submit"
              className={styles.searchButton}
              aria-label={isLoading ? 'Running search' : 'Run search'}
              disabled={isLoading || !query.trim()}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.3"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 19V5" />
                <path d="m5 12 7-7 7 7" />
              </svg>
            </button>
            {isLoading && (
              <div className={styles.loadingIndicator}>
                <div className={styles.spinner} />
              </div>
            )}
          </div>
        </form>

        {showToolbar && (
          <div className={styles.toolbar}>
            <div className={styles.toolbarLeft}>
              {onReset && (
                <button
                  type="button"
                  className={styles.resetButton}
                  onClick={onReset}
                >
                  New search
                </button>
              )}
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
                aria-checked={showEvidence}
                className={`${styles.sourcesToggle} ${showEvidence ? styles.sourcesToggleActive : ''}`}
                onClick={() => onShowEvidenceChange(!showEvidence)}
              >
                <span className={styles.sourcesToggleTrack}>
                  <span className={styles.sourcesToggleThumb} />
                </span>
                <span className={styles.sourcesToggleLabel}>
                  Evidence {showEvidence ? 'On' : 'Off'}
                </span>
              </button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
