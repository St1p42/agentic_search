import { EntityRow, Evidence, FieldValue, InferredSchema, Source } from '@/types';

interface BackendEvidenceItem {
  source_url: string;
  source_title: string;
  supporting_snippet: string;
  source_quality: 'high' | 'medium' | 'low';
  officiality: 'official' | 'near_official' | 'third_party' | 'low_quality';
}

interface BackendFieldValue {
  value: string | number | boolean | string[] | null;
  confidence: number;
  evidence: BackendEvidenceItem[];
}

interface BackendCanonicalEntity {
  name: string;
  fields: Record<string, BackendFieldValue>;
  source_urls: string[];
}

export interface BackendPipelineResponse {
  request_id: string;
  original_query: string;
  normalized_query: string;
  normalization_note: string | null;
  inferred_schema: string[];
  final_top_10_rows: BackendCanonicalEntity[];
  budget: {
    used_search_rounds: number;
    used_search_queries: number;
    used_deep_fetches: number;
  };
  repair_used: boolean;
  status: 'completed' | 'failed';
}

interface FrontendSearchResult {
  schema: InferredSchema;
  rows: EntityRow[];
  sources: Source[];
  sourcesCount: number;
  freshness: string;
  overallConfidence: number;
}

export interface BackendSchemaPreview {
  entity_type: string;
  columns: Array<{
    key: string;
    label: string;
    type: InferredSchema['columns'][number]['type'];
  }>;
}

function formatColumnLabel(columnKey: string): string {
  return columnKey
    .split('_')
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ');
}

function inferColumnType(columnKey: string): InferredSchema['columns'][number]['type'] {
  if (/(^|_)(website|url|link)$/.test(columnKey)) {
    return 'url';
  }
  if (/(^|_)(date|updated_at|created_at)$/.test(columnKey)) {
    return 'date';
  }
  if (/(^|_)(count|size|employees|revenue|amount|score)$/.test(columnKey)) {
    return 'number';
  }
  return 'text';
}

function inferSourceType(officiality: BackendEvidenceItem['officiality']): Evidence['sourceType'] {
  if (officiality === 'official') {
    return 'official';
  }
  if (officiality === 'near_official') {
    return 'profile';
  }
  if (officiality === 'low_quality') {
    return 'third-party';
  }
  return 'article';
}

function inferSupportingSourceType(officiality: BackendEvidenceItem['officiality']): Source['type'] {
  if (officiality === 'official') {
    return 'official';
  }
  if (officiality === 'near_official') {
    return 'profile';
  }
  return 'article';
}

function normalizeFieldValue(value: BackendFieldValue['value']): string | null {
  if (value === null) {
    return null;
  }
  if (Array.isArray(value)) {
    return value.join(', ');
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  return String(value);
}

function domainFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function mapEvidenceItem(item: BackendEvidenceItem): Evidence {
  return {
    sourceUrl: item.source_url,
    domain: domainFromUrl(item.source_url),
    pageTitle: item.source_title,
    snippet: item.supporting_snippet,
    sourceType: inferSourceType(item.officiality),
    quality: item.source_quality,
  };
}

function emptyFieldValue(): FieldValue {
  return {
    value: null,
    confidence: 0,
    evidence: [],
  };
}

export function mapPipelineResponse(response: BackendPipelineResponse): FrontendSearchResult {
  const schema = buildInferredSchema({
    entityType: response.normalized_query,
    columnKeys: response.inferred_schema,
  });

  const rows = response.final_top_10_rows.map((row, index) => {
    const frontendRow: EntityRow = {
      id: `${index + 1}`,
      name: emptyFieldValue(),
      website: emptyFieldValue(),
      description: emptyFieldValue(),
      focus: emptyFieldValue(),
      headquarters: emptyFieldValue(),
      fundingStage: emptyFieldValue(),
    };

    schema.columns.forEach((column) => {
      const backendField = column.key === 'name'
        ? row.fields.name ?? { value: row.name, confidence: 1, evidence: [] }
        : row.fields[column.key];

      frontendRow[column.key] = backendField
        ? {
            value: normalizeFieldValue(backendField.value),
            confidence: backendField.confidence,
            evidence: backendField.evidence.map(mapEvidenceItem),
          }
        : emptyFieldValue();
    });

    return frontendRow;
  });

  const sourcesByUrl = new Map<string, Source>();
  rows.forEach((row) => {
    schema.columns.forEach((column) => {
      const field = row[column.key];
      if (typeof field === 'object' && field !== null && 'evidence' in field) {
        field.evidence.forEach((evidence) => {
          if (!sourcesByUrl.has(evidence.sourceUrl)) {
            sourcesByUrl.set(evidence.sourceUrl, {
              url: evidence.sourceUrl,
              domain: evidence.domain,
              title: evidence.pageTitle,
              snippet: evidence.snippet,
              type: inferSupportingSourceType(
                evidence.sourceType === 'official'
                  ? 'official'
                  : evidence.sourceType === 'profile'
                    ? 'near_official'
                    : 'third_party'
              ),
              fresh: true,
            });
          }
        });
      }
    });
  });

  const confidenceValues = rows.flatMap((row) =>
    schema.columns
      .map((column) => row[column.key])
      .filter((field): field is FieldValue => typeof field === 'object' && field !== null && 'confidence' in field)
      .filter((field) => field.value !== null)
      .map((field) => field.confidence)
  );

  return {
    schema,
    rows,
    sources: Array.from(sourcesByUrl.values()),
    sourcesCount: sourcesByUrl.size,
    freshness: `Request ${response.request_id}`,
    overallConfidence:
      confidenceValues.length > 0
        ? confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length
        : 0,
  };
}

export function buildInferredSchema(input: { entityType: string; columnKeys: string[] }): InferredSchema {
  return {
    entityType: input.entityType,
    columns: input.columnKeys.map((columnKey) => ({
      key: columnKey,
      label: formatColumnLabel(columnKey),
      type: inferColumnType(columnKey),
    })),
  };
}

export function mapSchemaPreview(preview: BackendSchemaPreview): InferredSchema {
  return {
    entityType: preview.entity_type,
    columns: preview.columns.map((column) => ({
      key: column.key,
      label: column.label,
      type: column.type,
    })),
  };
}

export function buildJsonExport(schema: InferredSchema, rows: EntityRow[]) {
  return {
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
}
