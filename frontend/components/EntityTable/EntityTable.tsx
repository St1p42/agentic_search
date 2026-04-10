'use client';

import { EntityRow, InferredSchema, FieldValue } from '@/types';
import styles from './EntityTable.module.css';

interface EntityTableProps {
  schema: InferredSchema;
  rows: EntityRow[];
  showEvidence: boolean;
  onCellClick: (row: EntityRow, columnKey: string, field: FieldValue) => void;
}

function ConfidenceDot({ confidence }: { confidence: number }) {
  let colorClass = styles.confidenceHigh;
  if (confidence < 0.7) {
    colorClass = styles.confidenceLow;
  } else if (confidence < 0.9) {
    colorClass = styles.confidenceMedium;
  }
  return <span className={`${styles.confidenceDot} ${colorClass}`} />;
}

function CellContent({
  field,
  columnType,
  showEvidence,
}: {
  field: FieldValue;
  columnType: InferredSchema['columns'][number]['type'];
  showEvidence: boolean;
}) {
  if (!field.value) {
    return <span className={styles.nullValue}>—</span>;
  }

  const isUrl = columnType === 'url';

  return (
    <span className={styles.cellContent}>
      {isUrl ? (
        <a
          href={`https://${field.value}`}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.link}
          onClick={(e) => e.stopPropagation()}
        >
          {field.value}
        </a>
      ) : (
        <span className={styles.cellText}>{field.value}</span>
      )}
      {showEvidence && (
        <span className={styles.evidenceBadge}>
          <ConfidenceDot confidence={field.confidence} />
          <span className={styles.evidenceCount}>{field.evidence.length}</span>
        </span>
      )}
    </span>
  );
}

export function EntityTable({ schema, rows, showEvidence, onCellClick }: EntityTableProps) {
  return (
    <div className={styles.tableWrapper}>
      <div className={styles.tableScroll}>
      <table className={styles.table}>
        <thead className={styles.thead}>
          <tr>
            <th className={styles.th}>#</th>
            {schema.columns.map((col) => (
              <th key={col.key} className={styles.th}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className={styles.tbody}>
          {rows.map((row, index) => (
            <tr key={row.id} className={styles.tr}>
              <td className={styles.tdIndex}>{index + 1}</td>
              {schema.columns.map((col) => {
                const field = row[col.key] as FieldValue;
                return (
                  <td
                    key={col.key}
                    className={styles.td}
                    onClick={() => onCellClick(row, col.key, field)}
                  >
                    <CellContent field={field} columnType={col.type} showEvidence={showEvidence} />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
