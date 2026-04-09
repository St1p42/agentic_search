export interface Evidence {
  sourceUrl: string;
  domain: string;
  pageTitle: string;
  snippet: string;
  sourceType: 'official' | 'third-party' | 'article' | 'profile';
  quality: 'high' | 'medium' | 'low';
}

export interface FieldValue {
  value: string | null;
  confidence: number;
  evidence: Evidence[];
}

export interface EntityRow {
  id: string;
  name: FieldValue;
  website: FieldValue;
  description: FieldValue;
  focus: FieldValue;
  headquarters: FieldValue;
  fundingStage: FieldValue;
  [key: string]: FieldValue | string;
}

export interface InferredSchema {
  entityType: string;
  columns: {
    key: string;
    label: string;
    type: 'text' | 'url' | 'number' | 'date';
  }[];
}

export interface ResearchStage {
  id: string;
  name: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  startedAt?: Date;
  completedAt?: Date;
  details?: {
    inputs?: string[];
    outputs?: string[];
    counts?: Record<string, number>;
    topSources?: string[];
    warnings?: string[];
  };
}

export interface SearchState {
  status: 'idle' | 'connecting' | 'running' | 'completed' | 'failed';
  query: string;
  schema: InferredSchema | null;
  rows: EntityRow[];
  stages: ResearchStage[];
  sourcesCount: number;
  freshness: string;
  overallConfidence: number;
  error?: string;
}

export interface Source {
  url: string;
  domain: string;
  title: string;
  snippet: string;
  type: 'official' | 'profile' | 'article' | 'directory';
  fresh: boolean;
}
