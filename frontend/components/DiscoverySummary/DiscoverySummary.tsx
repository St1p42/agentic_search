import { InferredSchema } from '@/types';
import styles from './DiscoverySummary.module.css';

interface DiscoverySummaryProps {
  schema: InferredSchema;
  entitiesCount: number;
  sourcesCount: number;
  freshness: string;
  confidence: number;
}

export function DiscoverySummary({
  schema,
  entitiesCount,
  sourcesCount,
  freshness,
  confidence,
}: DiscoverySummaryProps) {
  return (
    <div className={styles.summary}>
      <div className={styles.summaryTop}>
        <div className={styles.entityInfo}>
          <span className={styles.entityType}>{schema.entityType}</span>
          <span className={styles.separator}>·</span>
          <span className={styles.stat}>{entitiesCount} entities found</span>
          <span className={styles.separator}>·</span>
          <span className={styles.stat}>{sourcesCount} sources</span>
          <span className={styles.separator}>·</span>
          <span className={styles.stat}>{freshness}</span>
          <span className={styles.separator}>·</span>
          <span className={styles.confidence}>
            <span className={styles.confidenceValue}>{Math.round(confidence * 100)}%</span>
            <span className={styles.confidenceLabel}>confidence</span>
          </span>
        </div>
      </div>
      <div className={styles.schemaChips}>
        {schema.columns.map((col) => (
          <span key={col.key} className={styles.chip}>
            {col.label}
          </span>
        ))}
      </div>
    </div>
  );
}
