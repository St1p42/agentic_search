import { Source } from '@/types';
import styles from './SupportingSources.module.css';

interface SupportingSourcesProps {
  sources: Source[];
}

function SourceTypeBadge({ type, fresh }: { type: Source['type']; fresh: boolean }) {
  const typeLabels: Record<Source['type'], string> = {
    official: 'Official',
    profile: 'Profile',
    article: 'Article',
    directory: 'Directory',
  };

  return (
    <div className={styles.badges}>
      <span className={`${styles.badge} ${styles[`badge_${type}`]}`}>
        {typeLabels[type]}
      </span>
      {fresh && (
        <span className={`${styles.badge} ${styles.badge_fresh}`}>
          Fresh
        </span>
      )}
    </div>
  );
}

export function SupportingSources({ sources }: SupportingSourcesProps) {
  return (
    <section className={styles.section}>
      <div className={styles.grid}>
        {sources.map((source, index) => (
          <a
            key={index}
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.card}
          >
            <div className={styles.cardHeader}>
              <span className={styles.domain}>{source.domain}</span>
              <SourceTypeBadge type={source.type} fresh={source.fresh} />
            </div>
            <h4 className={styles.cardTitle}>{source.title}</h4>
            <p className={styles.snippet}>{source.snippet}</p>
          </a>
        ))}
      </div>
    </section>
  );
}
