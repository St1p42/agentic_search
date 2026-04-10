import { EntityRow, InferredSchema } from '@/types';
import { buildJsonExport } from '@/lib/search-mappers';
import styles from './JsonView.module.css';

interface JsonViewProps {
  schema: InferredSchema;
  rows: EntityRow[];
  isLoading?: boolean;
}

export function JsonView({ schema, rows, isLoading = false }: JsonViewProps) {
  if (isLoading) {
    const preview = {
      inferred_schema: {
        entity_type: schema.entityType,
        columns: schema.columns.map((col) => ({
          key: col.key,
          label: col.label,
          type: col.type,
        })),
      },
      final_top_10_rows: [
        {
          name: '...',
          fields: Object.fromEntries(
            schema.columns.map((col) => [
              col.key,
              { value: '...', confidence: 0, source_urls: [] },
            ])
          ),
        },
      ],
    };

    return (
      <div className={styles.container}>
        <pre className={`${styles.code} ${styles.codeLoading}`}>
          {JSON.stringify(preview, null, 2)}
        </pre>
        <div className={styles.loadingOverlay}>
          <div className={styles.loadingLine} />
          <div className={styles.loadingLineShort} />
        </div>
      </div>
    );
  }

  const exportData = buildJsonExport(schema, rows);

  return (
    <div className={styles.container}>
      <pre className={styles.code}>
        {JSON.stringify(exportData, null, 2)}
      </pre>
    </div>
  );
}
