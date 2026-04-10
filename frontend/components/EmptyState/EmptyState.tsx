import styles from './EmptyState.module.css';

interface EmptyStateProps {
  type: 'idle' | 'connecting' | 'error' | 'no-results';
  errorMessage?: string;
  onExampleClick?: (query: string) => void;
}

export function EmptyState({ type, errorMessage, onExampleClick }: EmptyStateProps) {
  const examples = [
    'AI startups in healthcare',
    'Top venture capital firms in NYC',
    'Climate tech companies in Europe',
  ];

  if (type === 'connecting') {
    return (
      <div className={styles.container}>
        <div className={styles.spinner} />
        <h2 className={styles.title}>Connecting to research engine</h2>
        <p className={styles.description}>Preparing to analyze your query...</p>
      </div>
    );
  }

  if (type === 'error') {
    return (
      <div className={styles.container}>
        <div className={styles.errorIcon}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>
        <h2 className={styles.title}>Research failed</h2>
        <p className={styles.description}>
          {errorMessage || 'An error occurred while processing your query. Please try again.'}
        </p>
      </div>
    );
  }

  if (type === 'no-results') {
    return (
      <div className={styles.container}>
        <div className={styles.icon}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
            <path d="M8.5 11h5" />
          </svg>
        </div>
        <h2 className={styles.title}>No entities found</h2>
        <p className={styles.description}>
          The backend completed the search but did not return any final rows for this query.
          Try a broader topic or a more specific industry or region.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.icon}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
        </svg>
      </div>
      <h2 className={styles.title}>Discover structured entities</h2>
      <p className={styles.description}>
        Enter a topic to extract entities, attributes, and evidence from web sources.
        Results are presented as a structured, traceable table.
      </p>
      <div className={styles.examples}>
        <span className={styles.examplesLabel}>Try:</span>
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            className={styles.example}
            onClick={() => onExampleClick?.(example)}
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
