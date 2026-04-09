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
import { mockSchema, mockRows, mockStages, mockSources } from '@/data/mockData';
import { EntityRow, FieldValue, SearchState, InferredSchema, ResearchStage } from '@/types';
import styles from './page.module.css';

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

export default function Home() {
  const [searchState, setSearchState] = useState<SearchState>(INITIAL_STATE);
  const [viewMode, setViewMode] = useState<'table' | 'json'>('table');
  const [showSources, setShowSources] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedColumn, setSelectedColumn] = useState<string>('');
  const [selectedField, setSelectedField] = useState<FieldValue | null>(null);
  const [tableExpanded, setTableExpanded] = useState(true);
  const [sourcesExpanded, setSourcesExpanded] = useState(true);

  const handleSearch = useCallback((query: string) => {
    // Simulate connecting state
    setSearchState({
      ...INITIAL_STATE,
      status: 'connecting',
      query,
    });

    // Simulate the research pipeline
    setTimeout(() => {
      setSearchState({
        status: 'running',
        query,
        schema: mockSchema,
        rows: [],
        stages: mockStages.map((stage, index) => ({
          ...stage,
          status: index === 0 ? 'active' : 'pending',
        })) as ResearchStage[],
        sourcesCount: 0,
        freshness: '',
        overallConfidence: 0,
      });

      // Simulate stages completing over time
      let currentStage = 0;
      const stageInterval = setInterval(() => {
        currentStage++;
        if (currentStage >= mockStages.length) {
          clearInterval(stageInterval);
          // Final completed state
          setSearchState({
            status: 'completed',
            query,
            schema: mockSchema,
            rows: mockRows,
            stages: mockStages,
            sourcesCount: 23,
            freshness: 'Updated today',
            overallConfidence: 0.93,
          });
        } else {
          setSearchState((prev) => ({
            ...prev,
            stages: mockStages.map((stage, index) => ({
              ...stage,
              status: index < currentStage ? 'completed' : index === currentStage ? 'active' : 'pending',
            })) as ResearchStage[],
          }));
        }
      }, 800);
    }, 1000);
  }, []);

  const handleCellClick = useCallback((row: EntityRow, columnKey: string, field: FieldValue) => {
    const column = mockSchema.columns.find((c) => c.key === columnKey);
    setSelectedColumn(column?.label || columnKey);
    setSelectedField(field);
    setDrawerOpen(true);
  }, []);

  const isRunning = searchState.status === 'running';
  const hasResults = searchState.status === 'completed' && searchState.rows.length > 0;

  return (
    <div className={styles.app}>
      <SearchHeader
        initialQuery={searchState.query}
        onSearch={handleSearch}
        isLoading={searchState.status === 'connecting' || isRunning}
        resultsCount={hasResults ? searchState.rows.length : undefined}
        entityType={hasResults ? searchState.schema?.entityType : undefined}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        showSources={showSources}
        onShowSourcesChange={setShowSources}
      />

      <div className={styles.layout}>
        <main className={styles.main}>
          {searchState.status === 'idle' && <EmptyState type="idle" />}

          {searchState.status === 'connecting' && <EmptyState type="connecting" />}

          {searchState.status === 'failed' && (
            <EmptyState type="error" errorMessage={searchState.error} />
          )}

          {(isRunning || hasResults) && searchState.schema && (
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

                  {hasResults && showSources && (
                    <div className={styles.collapsibleSection} style={{ marginTop: '24px' }}>
                      <button
                        className={`${styles.collapsibleHeader} ${sourcesExpanded ? styles.collapsibleHeaderExpanded : ''}`}
                        onClick={() => setSourcesExpanded(!sourcesExpanded)}
                        aria-expanded={sourcesExpanded}
                      >
                        <span className={styles.collapsibleTitle}>
                          Supporting Sources
                          <span className={styles.collapsibleCount}>{mockSources.length}</span>
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
                          <SupportingSources sources={mockSources} />
                        </div>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                hasResults && <JsonView schema={searchState.schema} rows={searchState.rows} />
              )}
            </>
          )}
        </main>

        {(isRunning || hasResults) && (
          <aside className={styles.sidebar}>
            <ResearchActivityPanel
              stages={searchState.stages}
              isRunning={isRunning}
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
