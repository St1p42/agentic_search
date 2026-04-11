import { mockRows, mockSchema, mockSources, mockStages } from '@/data/mockData';
import { InferredSchema, EntityRow, ResearchStage, ResearchStageDetails, Source } from '@/types';
import {
  mapPipelineResponse,
  mapSchemaPreview,
  type BackendPipelineResponse,
  type BackendSchemaPreview,
} from '@/lib/search-mappers';

export type SearchStatus = 'idle' | 'connecting' | 'running' | 'completed' | 'failed';

export interface SearchSnapshot {
  status: Exclude<SearchStatus, 'idle'>;
  query: string;
  schema: InferredSchema | null;
  rows: EntityRow[];
  stages: ResearchStage[];
  sources: Source[];
  sourcesCount: number;
  freshness: string;
  overallConfidence: number;
  error?: string;
}

export interface SearchClient {
  runSearch: (query: string, onUpdate: (snapshot: SearchSnapshot) => void) => () => void;
}

interface BackendPipelineError {
  code: string;
  message: string;
  stage?: string | null;
  details?: Record<string, string>;
}

interface BackendSsePayload {
  request_id: string;
  stage: string | null;
  message: string;
  data: Record<string, unknown>;
  error?: BackendPipelineError | null;
}

interface BackendSseEvent {
  event: 'run_started' | 'stage_started' | 'stage_completed' | 'repair_started' | 'run_completed' | 'run_failed';
  payload: BackendSsePayload;
  schema_version: '1.0';
}

function toUserFacingErrorMessage(error?: BackendPipelineError | null): string {
  if (!error) {
    return 'Search failed';
  }

  if (error.code === 'invalid_query' && error.message) {
    return error.message;
  }

  return 'Something went wrong while running the research pipeline. Please try again.';
}

function createRunningStages(activeIndex: number): ResearchStage[] {
  return mockStages.map((stage, index) => ({
    ...stage,
    status: index < activeIndex ? 'completed' : index === activeIndex ? 'active' : 'pending',
  })) as ResearchStage[];
}

function createLiveStages(activeIndex: number, failed = false): ResearchStage[] {
  const stages: ResearchStage[] = [
    { id: 'submit', name: 'Submitting query', status: 'pending' },
    { id: 'pipeline', name: 'Running search pipeline', status: 'pending' },
    { id: 'format', name: 'Formatting result table', status: 'pending' },
  ];

  return stages.map((stage, index) => ({
    ...stage,
    status: failed && index === activeIndex
      ? 'failed'
      : index < activeIndex
        ? 'completed'
        : index === activeIndex
          ? 'active'
          : 'pending',
  })) as ResearchStage[];
}

function toStageId(stage: string | null, message: string): string {
  return `${stage || 'run'}:${message.replace(/ completed$/, '')}`;
}

function completeAllStages(stages: ResearchStage[]): ResearchStage[] {
  return stages.map((stage) => ({
    ...stage,
    status: (stage.status === 'failed' ? 'failed' : 'completed') as ResearchStage['status'],
  }));
}

function upsertStage(
  stages: ResearchStage[],
  stageName: string | null,
  message: string,
  status: ResearchStage['status'],
  details?: ResearchStage['details']
): ResearchStage[] {
  const normalizedMessage = message === 'Search completed'
    ? 'Search Complete'
    : message.replace(/ completed$/, '');
  const id = toStageId(stageName, message);
  let found = false;

  const nextStages = stages.map((stage) => {
    if (stage.id !== id) {
      return status === 'active' && stage.status === 'active'
        ? { ...stage, status: 'completed' as ResearchStage['status'] }
        : stage;
    }

    found = true;
    return {
      ...stage,
      name: normalizedMessage,
      status,
      details: details ?? stage.details,
    };
  });

  if (found) {
    return nextStages;
  }

    return [
      ...nextStages.map((stage) =>
      status === 'active' && stage.status === 'active'
        ? { ...stage, status: 'completed' as ResearchStage['status'] }
        : stage
    ),
    {
      id,
      name: normalizedMessage,
      status,
      details,
    },
  ];
}

function extractStageDetails(data: Record<string, unknown>): ResearchStageDetails | undefined {
  const details = data.details && typeof data.details === 'object'
    ? data.details
    : data;

  if (!details || typeof details !== 'object') {
    return undefined;
  }

  const candidate = details as Partial<ResearchStageDetails>;
  return {
    summary: typeof candidate.summary === 'string' ? candidate.summary : undefined,
    metrics: Array.isArray(candidate.metrics)
      ? candidate.metrics.filter(
          (metric): metric is NonNullable<ResearchStageDetails['metrics']>[number] =>
            typeof metric === 'object' &&
            metric !== null &&
            'key' in metric &&
            'label' in metric &&
            'value' in metric
        )
      : undefined,
  };
}

function extractSchemaPreview(data: Record<string, unknown>): InferredSchema | undefined {
  const preview = data.schema_preview;
  if (!preview || typeof preview !== 'object') {
    return undefined;
  }

  const candidate = preview as BackendSchemaPreview;
  if (!candidate.entity_type || !Array.isArray(candidate.columns)) {
    return undefined;
  }

  return mapSchemaPreview(candidate);
}

export function createSearchApiClient(): SearchClient {
  return {
    runSearch(query, onUpdate) {
      let currentSnapshot: SearchSnapshot = {
        status: 'connecting',
        query,
        schema: null,
        rows: [],
        stages: [],
        sources: [],
        sourcesCount: 0,
        freshness: '',
        overallConfidence: 0,
      };

      let streamOpened = false;
      const eventSource = new EventSource(`/api/v1/search/stream?query=${encodeURIComponent(query)}`);

      const pushUpdate = (patch: Partial<SearchSnapshot>) => {
        currentSnapshot = {
          ...currentSnapshot,
          ...patch,
        };
        onUpdate(currentSnapshot);
      };

      pushUpdate(currentSnapshot);

      eventSource.onopen = () => {
        streamOpened = true;
        pushUpdate({
          status: 'running',
        });
      };

      eventSource.addEventListener('run_started', (event) => {
        const payload = JSON.parse(event.data) as BackendSseEvent;
        pushUpdate({
          status: 'running',
          error: undefined,
          stages: upsertStage(
            currentSnapshot.stages,
            payload.payload.stage,
            payload.payload.message,
            'active',
            extractStageDetails(payload.payload.data)
          ),
        });
      });

      eventSource.addEventListener('stage_started', (event) => {
        const payload = JSON.parse(event.data) as BackendSseEvent;
        pushUpdate({
          status: 'running',
          stages: upsertStage(currentSnapshot.stages, payload.payload.stage, payload.payload.message, 'active'),
        });
      });

      eventSource.addEventListener('stage_completed', (event) => {
        const payload = JSON.parse(event.data) as BackendSseEvent;
        const schemaPreview = extractSchemaPreview(payload.payload.data);
        pushUpdate({
          status: 'running',
          schema: schemaPreview ?? currentSnapshot.schema,
          stages: upsertStage(
            currentSnapshot.stages,
            payload.payload.stage,
            payload.payload.message,
            'completed',
            extractStageDetails(payload.payload.data)
          ),
        });
      });

      eventSource.addEventListener('repair_started', (event) => {
        const payload = JSON.parse(event.data) as BackendSseEvent;
        const followupQueries = Array.isArray(payload.payload.data.followup_queries)
          ? payload.payload.data.followup_queries.filter((value): value is string => typeof value === 'string')
          : [];

        pushUpdate({
          status: 'running',
          stages: upsertStage(currentSnapshot.stages, payload.payload.stage, payload.payload.message, 'active', {
            inputs: followupQueries,
          }),
        });
      });

      eventSource.addEventListener('run_completed', (event) => {
        const payload = JSON.parse(event.data) as BackendSseEvent;
        const response = payload.payload.data as unknown as BackendPipelineResponse;
        const mapped = mapPipelineResponse(response);

        pushUpdate({
          status: 'completed',
          schema: mapped.schema,
          rows: mapped.rows,
          stages: completeAllStages(
            upsertStage(currentSnapshot.stages, payload.payload.stage, payload.payload.message, 'completed')
          ),
          sources: mapped.sources,
          sourcesCount: mapped.sourcesCount,
          freshness: mapped.freshness,
          overallConfidence: mapped.overallConfidence,
          error: undefined,
        });
        eventSource.close();
      });

      eventSource.addEventListener('run_failed', (event) => {
        const payload = JSON.parse(event.data) as BackendSseEvent;
        pushUpdate({
          status: 'failed',
          schema: null,
          rows: [],
          stages: upsertStage(
            currentSnapshot.stages,
            payload.payload.error?.stage || payload.payload.stage,
            payload.payload.message,
            'failed'
          ),
          sources: [],
          sourcesCount: 0,
          freshness: '',
          overallConfidence: 0,
          error: toUserFacingErrorMessage(payload.payload.error),
        });
        eventSource.close();
      });

      eventSource.onerror = () => {
        if (!streamOpened) {
          pushUpdate({
            status: 'connecting',
          });
        }
      };

      return () => {
        eventSource.close();
      };
    },
  };
}

export function createMockSearchClient(): SearchClient {
  return {
    runSearch(query, onUpdate) {
      onUpdate({
        status: 'connecting',
        query,
        schema: null,
        rows: [],
        stages: [],
        sources: [],
        sourcesCount: 0,
        freshness: '',
        overallConfidence: 0,
      });

      let currentStage = 0;
      let stageInterval: ReturnType<typeof setInterval> | undefined;

      const connectTimeout = setTimeout(() => {
        onUpdate({
          status: 'running',
          query,
          schema: mockSchema,
          rows: [],
          stages: createRunningStages(0),
          sources: [],
          sourcesCount: 0,
          freshness: '',
          overallConfidence: 0,
        });

        stageInterval = setInterval(() => {
          currentStage += 1;

          if (currentStage >= mockStages.length) {
            if (stageInterval) {
              clearInterval(stageInterval);
            }

            onUpdate({
              status: 'completed',
              query,
              schema: mockSchema,
              rows: mockRows,
              stages: mockStages,
              sources: mockSources,
              sourcesCount: mockSources.length,
              freshness: 'Updated today',
              overallConfidence: 0.93,
            });
            return;
          }

          onUpdate({
            status: 'running',
            query,
            schema: mockSchema,
            rows: [],
            stages: createRunningStages(currentStage),
            sources: [],
            sourcesCount: 0,
            freshness: '',
            overallConfidence: 0,
          });
        }, 800);
      }, 1000);

      return () => {
        clearTimeout(connectTimeout);
        if (stageInterval) {
          clearInterval(stageInterval);
        }
      };
    },
  };
}
