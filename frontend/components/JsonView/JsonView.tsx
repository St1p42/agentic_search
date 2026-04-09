import { EntityRow, InferredSchema } from '@/types';
import styles from './JsonView.module.css';

interface JsonViewProps {
  schema: InferredSchema;
  rows: EntityRow[];
}

export function JsonView({ schema, rows }: JsonViewProps) {
  const exportData = {
    inferred_schema: {
      entity_type: schema.entityType,
      columns: schema.columns.map((col) => ({
        key: col.key,
        label: col.label,
        type: col.type,
      })),
    },
    final_top_10_rows: rows.map((row) => {
      const fields: Record<string, { value: string | null; confidence: number; source_urls: string[] }> = {};
      schema.columns.forEach((col) => {
        const field = row[col.key];
        if (typeof field === 'object' && field !== null && 'value' in field) {
          fields[col.key] = {
            value: field.value,
            confidence: field.confidence,
            source_urls: field.evidence.map((e) => e.sourceUrl),
          };
        }
      });
      return {
        name: typeof row.name === 'object' ? row.name.value : row.name,
        fields,
      };
    }),
  };

  return (
    <div className={styles.container}>
      <pre className={styles.code}>
        {JSON.stringify(exportData, null, 2)}
      </pre>
    </div>
  );
}
