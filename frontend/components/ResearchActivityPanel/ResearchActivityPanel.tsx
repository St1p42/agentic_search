'use client';

import { useState } from 'react';
import { ResearchStage } from '@/types';
import styles from './ResearchActivityPanel.module.css';

interface ResearchActivityPanelProps {
  stages: ResearchStage[];
  isRunning: boolean;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

function StageIcon({ status }: { status: ResearchStage['status'] }) {
  if (status === 'completed') {
    return (
      <svg className={styles.iconCompleted} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    );
  }
  if (status === 'active') {
    return <div className={styles.iconActive} />;
  }
  if (status === 'failed') {
    return (
      <svg className={styles.iconFailed} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    );
  }
  return <div className={styles.iconPending} />;
}

function StageDetails({ details }: { details: ResearchStage['details'] }) {
  if (!details) return null;

  return (
    <div className={styles.stageDetails}>
      {details.outputs && details.outputs.length > 0 && (
        <ul className={styles.detailList}>
          {details.outputs.map((output, i) => (
            <li key={i}>{output}</li>
          ))}
        </ul>
      )}
      {details.counts && Object.keys(details.counts).length > 0 && (
        <div className={styles.countsGrid}>
          {Object.entries(details.counts).map(([key, value]) => (
            <div key={key} className={styles.countItem}>
              <span className={styles.countValue}>{value}</span>
              <span className={styles.countLabel}>
                {key.replace(/([A-Z])/g, ' $1').toLowerCase()}
              </span>
            </div>
          ))}
        </div>
      )}
      {details.topSources && details.topSources.length > 0 && (
        <div className={styles.topSources}>
          <span className={styles.topSourcesLabel}>Top sources:</span>
          <span className={styles.topSourcesList}>{details.topSources.join(', ')}</span>
        </div>
      )}
      {details.warnings && details.warnings.length > 0 && (
        <ul className={styles.warningsList}>
          {details.warnings.map((warning, i) => (
            <li key={i} className={styles.warning}>{warning}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ResearchActivityPanel({
  stages,
  isRunning,
  collapsed = false,
  onToggleCollapsed,
}: ResearchActivityPanelProps) {
  const [expandedStages, setExpandedStages] = useState<Set<string>>(new Set());

  const toggleStage = (stageId: string) => {
    setExpandedStages((prev) => {
      const next = new Set(prev);
      if (next.has(stageId)) {
        next.delete(stageId);
      } else {
        next.add(stageId);
      }
      return next;
    });
  };

  const activeStage = stages.find((s) => s.status === 'active');
  const completedStages = stages.filter((s) => s.status === 'completed');
  const allCompleted = stages.every((s) => s.status === 'completed');

  return (
    <aside className={`${styles.panel} ${collapsed ? styles.panelCollapsed : ''}`}>
      <header className={styles.header}>
        <div className={styles.headerMeta}>
          <h2 className={styles.title}>Research activity</h2>
          {allCompleted && !collapsed && (
            <span className={styles.completedBadge}>Complete</span>
          )}
        </div>
        {onToggleCollapsed && (
          <button
            type="button"
            className={styles.collapseButton}
            onClick={onToggleCollapsed}
            aria-expanded={!collapsed}
            aria-label={collapsed ? 'Expand research activity' : 'Collapse research activity'}
            title={collapsed ? 'Expand research activity' : 'Collapse research activity'}
          >
            <svg
              className={`${styles.collapseIcon} ${collapsed ? styles.collapseIconCollapsed : ''}`}
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="m9 6 6 6-6 6" />
            </svg>
          </button>
        )}
      </header>

      {collapsed ? (
        <div className={styles.collapsedSummary} title="Research activity">
          {isRunning && activeStage ? (
            <div className={styles.activeIndicator} />
          ) : (
            <svg className={styles.iconCompleted} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          )}
          <span className={styles.collapsedLabel}>Activity</span>
        </div>
      ) : (
        <>
      {isRunning && activeStage && (
        <div className={styles.activeStatus}>
          <div className={styles.activeIndicator} />
          <span className={styles.activeText}>{activeStage.name}</span>
        </div>
      )}

      <div className={styles.timeline}>
        {completedStages.map((stage) => {
          const isExpanded = expandedStages.has(stage.id);
          return (
            <div key={stage.id} className={styles.stageItem}>
              <button
                className={styles.stageButton}
                onClick={() => toggleStage(stage.id)}
                aria-expanded={isExpanded}
              >
                <StageIcon status={stage.status} />
                <span className={styles.stageName}>{stage.name}</span>
                <svg
                  className={`${styles.chevron} ${isExpanded ? styles.chevronOpen : ''}`}
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
              {isExpanded && <StageDetails details={stage.details} />}
            </div>
          );
        })}

        {stages.filter((s) => s.status === 'pending').map((stage) => (
          <div key={stage.id} className={styles.stageItem}>
            <div className={styles.stagePending}>
              <StageIcon status={stage.status} />
              <span className={styles.stageName}>{stage.name}</span>
            </div>
          </div>
        ))}
      </div>
        </>
      )}
    </aside>
  );
}
