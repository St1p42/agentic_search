'use client';

import { useEffect, useCallback } from 'react';
import { FieldValue, Evidence } from '@/types';
import styles from './EvidenceDrawer.module.css';

interface EvidenceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  columnLabel: string;
  field: FieldValue | null;
}

function QualityBadge({ quality, sourceType }: { quality: Evidence['quality']; sourceType: Evidence['sourceType'] }) {
  const typeLabels: Record<Evidence['sourceType'], string> = {
    official: 'Official',
    'third-party': 'Third-party',
    article: 'Article',
    profile: 'Profile',
  };

  const qualityLabels: Record<Evidence['quality'], string> = {
    high: 'High quality',
    medium: 'Medium quality',
    low: 'Low quality',
  };

  return (
    <div className={styles.badges}>
      <span className={`${styles.badge} ${styles[`badge_${sourceType}`]}`}>
        {typeLabels[sourceType]}
      </span>
      <span className={`${styles.badge} ${styles[`badge_${quality}`]}`}>
        {qualityLabels[quality]}
      </span>
    </div>
  );
}

export function EvidenceDrawer({ isOpen, onClose, columnLabel, field }: EvidenceDrawerProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    },
    [onClose]
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

  if (!isOpen || !field) return null;

  const confidencePercent = Math.round(field.confidence * 100);

  return (
    <>
      <div className={styles.overlay} onClick={onClose} />
      <aside className={styles.drawer} role="dialog" aria-modal="true">
        <header className={styles.header}>
          <div className={styles.headerTop}>
            <h2 className={styles.title}>{columnLabel}</h2>
            <button className={styles.closeButton} onClick={onClose} aria-label="Close">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className={styles.value}>{field.value || '—'}</div>
          <div className={styles.confidenceBar}>
            <div className={styles.confidenceLabel}>
              <span>Confidence</span>
              <span className={styles.confidenceValue}>{confidencePercent}%</span>
            </div>
            <div className={styles.confidenceTrack}>
              <div
                className={styles.confidenceFill}
                style={{ width: `${confidencePercent}%` }}
              />
            </div>
          </div>
        </header>

        <div className={styles.content}>
          <h3 className={styles.sectionTitle}>
            Supporting Evidence
            <span className={styles.evidenceCount}>{field.evidence.length}</span>
          </h3>

          <div className={styles.evidenceList}>
            {field.evidence.map((evidence, index) => (
              <div key={index} className={styles.evidenceCard}>
                <div className={styles.evidenceHeader}>
                  <a
                    href={evidence.sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.evidenceLink}
                  >
                    <span className={styles.evidenceDomain}>{evidence.domain}</span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                  </a>
                  <QualityBadge quality={evidence.quality} sourceType={evidence.sourceType} />
                </div>
                <div className={styles.evidenceTitle}>{evidence.pageTitle}</div>
                <blockquote className={styles.evidenceSnippet}>
                  "{evidence.snippet}"
                </blockquote>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </>
  );
}
