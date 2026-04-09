'use client';

import { useState, useEffect, useCallback } from 'react';
import { ResearchStage } from '@/types';
import { ResearchActivityPanel } from '@/components/ResearchActivityPanel/ResearchActivityPanel';
import styles from './MobileActivityDrawer.module.css';

interface MobileActivityDrawerProps {
  stages: ResearchStage[];
  isRunning: boolean;
}

export function MobileActivityDrawer({ stages, isRunning }: MobileActivityDrawerProps) {
  const [isOpen, setIsOpen] = useState(false);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    },
    []
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, handleKeyDown]);

  const completedCount = stages.filter((s) => s.status === 'completed').length;
  const activeStage = stages.find((s) => s.status === 'active');

  return (
    <>
      <button className={styles.trigger} onClick={() => setIsOpen(true)}>
        <span className={styles.triggerIcon}>
          {isRunning ? (
            <span className={styles.activeDot} />
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
          )}
        </span>
        <span className={styles.triggerText}>
          {isRunning && activeStage
            ? activeStage.name
            : `${completedCount} stages completed`}
        </span>
      </button>

      {isOpen && (
        <>
          <div className={styles.overlay} onClick={() => setIsOpen(false)} />
          <div className={styles.drawer}>
            <div className={styles.drawerHandle} />
            <ResearchActivityPanel stages={stages} isRunning={isRunning} />
          </div>
        </>
      )}
    </>
  );
}
