'use client';

import { useState, useCallback } from 'react';
import { SearchHeader } from '@/components/SearchHeader/SearchHeader';
import { DiscoverySummary } from '@/components/DiscoverySummary/DiscoverySummary';
import { EntityTable } from '@/components/EntityTable/EntityTable';
import { EvidenceDrawer } from '@/components/EvidenceDrawer/EvidenceDrawer';
import { ResearchActivityPanel } from '@/components/ResearchActivityPanel/ResearchActivityPanel';
import { SupportingSources } from '@/components/SupportingSources/SupportingSources';
import { JsonView } from '@/components/JsonView/JsonView';
import { EmptyState } from '@/components/EmptyState/EmptyState';
import { MobileActivityDrawer } from '@/components/MobileActivityDrawer/MobileActivityDrawer';
import { useSearchSession } from '@/hooks/use-search-session';
import { EntityRow, FieldValue } from '@/types';
import styles from './page.module.css';

export default function Home() {
  const { searchState, sources, activityCollapsed, setActivityCollapsed, runSearch, resetSearch } = useSearchSession();
  const [searchInput, setSearchInput] = useState('');
  const [viewMode, setViewMode] = useState<'table' | 'json'>('table');
  const [showEvidence, setShowEvidence] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedColumn, setSelectedColumn] = useState<string>('');
  const [selectedField, setSelectedField] = useState<FieldValue | null>(null);
  const [tableExpanded, setTableExpanded] = useState(true);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);

  const handleReset = useCallback(() => {
    resetSearch();
    setSearchInput('');
    setViewMode('table');
    setShowEvidence(true);
    setDrawerOpen(false);
    setSelectedColumn('');
    setSelectedField(null);
    setTableExpanded(true);
    setSourcesExpanded(false);
    setActivityCollapsed(false);
  }, [resetSearch, setActivityCollapsed]);

  const handleCellClick = useCallback((row: EntityRow, columnKey: string, field: FieldValue) => {
    const column = searchState.schema?.columns.find((c) => c.key === columnKey);
    setSelectedColumn(column?.label || columnKey);
    setSelectedField(field);
    setDrawerOpen(true);
  }, [searchState.schema]);

  const isRunning = searchState.status === 'running';
  const isCompleted = searchState.status === 'completed';
  const hasResults = isCompleted && searchState.rows.length > 0;
  const hasNoResults = isCompleted && searchState.rows.length === 0;
  const hasPreviewSchema = Boolean(searchState.schema);

  return (
    <div className={styles.app}>
      <SearchHeader
        query={searchInput}
        onQueryChange={setSearchInput}
        onSearch={runSearch}
        onReset={searchState.status !== 'idle' ? handleReset : undefined}
        isLoading={searchState.status === 'connecting' || isRunning}
        resultsCount={isCompleted ? searchState.rows.length : undefined}
        entityType={isCompleted ? searchState.schema?.entityType : undefined}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        showEvidence={showEvidence}
        onShowEvidenceChange={setShowEvidence}
      />

      <div className={styles.layout}>
        <main className={styles.main}>
          {searchState.status === 'idle' && (
            <EmptyState type="idle" onExampleClick={setSearchInput} />
          )}

          {searchState.status === 'connecting' && <EmptyState type="connecting" />}

          {isRunning && !hasPreviewSchema && <EmptyState type="planning" />}

          {searchState.status === 'failed' && (
            <EmptyState type="error" errorMessage={searchState.error} />
          )}

          {hasNoResults && <EmptyState type="no-results" />}

          {(isRunning || hasResults) && hasPreviewSchema && searchState.schema && (
            <>
              {hasResults && (
                <DiscoverySummary
                  schema={searchState.schema}
                  entitiesCount={searchState.rows.length}
                  sourcesCount={searchState.sourcesCount}
                  freshness={searchState.freshness}
                  confidence={searchState.overallConfidence}
                />
              )}

              {viewMode === 'table' ? (
                <>
                  {hasResults ? (
                    <div className={styles.collapsibleSection}>
                      <button
                        className={`${styles.collapsibleHeader} ${tableExpanded ? styles.collapsibleHeaderExpanded : ''}`}
                        onClick={() => setTableExpanded(!tableExpanded)}
                        aria-expanded={tableExpanded}
                      >
                        <span className={styles.collapsibleTitle}>
                          Discovered Entities
                          <span className={styles.collapsibleCount}>{searchState.rows.length}</span>
                        </span>
                        <span className={styles.collapsibleToggle}>
                          {tableExpanded ? 'Collapse' : 'Expand'}
                          <svg
                            className={`${styles.collapsibleIcon} ${tableExpanded ? styles.collapsibleIconExpanded : ''}`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                          </svg>
                        </span>
                      </button>
                      <div className={`${styles.collapsibleContent} ${tableExpanded ? styles.collapsibleContentExpanded : ''}`}>
                        <div className={styles.collapsibleInner}>
                          <EntityTable
                            schema={searchState.schema}
                            rows={searchState.rows}
                            showEvidence={showEvidence}
                            onCellClick={handleCellClick}
                          />
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className={styles.loadingTable}>
                      <div className={styles.loadingTableHeader}>
                        {searchState.schema.columns.map((col) => (
                          <div key={col.key} className={styles.loadingColumn}>
                            {col.label}
                          </div>
                        ))}
                      </div>
                      <div className={styles.loadingRows}>
                        {[...Array(5)].map((_, i) => (
                          <div key={i} className={styles.loadingRow}>
                            {searchState.schema!.columns.map((col) => (
                              <div key={col.key} className={styles.loadingCell} />
                            ))}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {hasResults && (
                    <div className={styles.collapsibleSection} style={{ marginTop: '24px' }}>
                      <button
                        className={`${styles.collapsibleHeader} ${sourcesExpanded ? styles.collapsibleHeaderExpanded : ''}`}
                        onClick={() => setSourcesExpanded(!sourcesExpanded)}
                        aria-expanded={sourcesExpanded}
                      >
                        <span className={styles.collapsibleTitle}>
                          Supporting Sources
                          <span className={styles.collapsibleCount}>{sources.length}</span>
                        </span>
                        <span className={styles.collapsibleToggle}>
                          {sourcesExpanded ? 'Collapse' : 'Expand'}
                          <svg
                            className={`${styles.collapsibleIcon} ${sourcesExpanded ? styles.collapsibleIconExpanded : ''}`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                          </svg>
                        </span>
                      </button>
                      <div className={`${styles.collapsibleContent} ${sourcesExpanded ? styles.collapsibleContentExpanded : ''}`}>
                        <div className={styles.collapsibleInner}>
                          <SupportingSources sources={sources} />
                        </div>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <JsonView
                  schema={searchState.schema}
                  rows={searchState.rows}
                  isLoading={isRunning}
                />
              )}
            </>
          )}
        </main>

        {(isRunning || hasResults) && (
          <aside className={`${styles.sidebar} ${activityCollapsed ? styles.sidebarCollapsed : ''}`}>
            <ResearchActivityPanel
              stages={searchState.stages}
              isRunning={isRunning}
              collapsed={activityCollapsed}
              onToggleCollapsed={() => setActivityCollapsed((prev) => !prev)}
            />
          </aside>
        )}

        {(isRunning || hasResults) && (
          <MobileActivityDrawer
            stages={searchState.stages}
            isRunning={isRunning}
          />
        )}
      </div>

      <EvidenceDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        columnLabel={selectedColumn}
        field={selectedField}
      />
    </div>
  );
}
