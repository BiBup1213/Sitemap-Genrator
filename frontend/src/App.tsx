import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';

type CrawlState = 'queued' | 'running' | 'done' | 'error';

type UrlResult = {
  url: string;
  priority: number;
  lastmod: string;
  changefreq: 'weekly';
};

type CrawlStatus = {
  job_id: string;
  state: CrawlState;
  started_at: string | null;
  finished_at: string | null;
  progress: {
    collected: number;
    queued: number;
    current_url: string | null;
  };
  results: UrlResult[];
  error: string | null;
};

type StartResponse = {
  job_id: string;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ??
  'http://localhost:8000';

const DOMAIN_OR_URL_REGEX = /^(https?:\/\/)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(\/.*)?$/;

export default function App() {
  const [domain, setDomain] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<CrawlStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollTimer = useRef<number | null>(null);

  const isRunning = status?.state === 'running' || status?.state === 'queued' || loading;

  const collectedCount = useMemo(() => status?.progress.collected ?? 0, [status]);

  useEffect(() => {
    return () => {
      if (pollTimer.current) {
        window.clearInterval(pollTimer.current);
      }
    };
  }, []);

  async function fetchStatus(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/crawl/status/${id}`);
    if (!response.ok) {
      throw new Error('Failed to fetch crawl status.');
    }

    const data = (await response.json()) as CrawlStatus;
    setStatus(data);

    if (data.state === 'done' || data.state === 'error') {
      setLoading(false);
      if (pollTimer.current) {
        window.clearInterval(pollTimer.current);
      }
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setStatus(null);

    const value = domain.trim();
    if (!value) {
      setError('Please enter a domain or URL.');
      return;
    }
    if (!DOMAIN_OR_URL_REGEX.test(value)) {
      setError('Enter a valid domain like example.com or https://example.com');
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/crawl/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          site: value,
          max_pages: 500,
          respect_robots: true,
          include_query_params: false
        })
      });

      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        throw new Error(body.detail ?? 'Failed to start crawl');
      }

      const data = (await response.json()) as StartResponse;
      setJobId(data.job_id);
      await fetchStatus(data.job_id);

      pollTimer.current = window.setInterval(() => {
        void fetchStatus(data.job_id).catch((err: Error) => {
          setError(err.message);
          setLoading(false);
          if (pollTimer.current) {
            window.clearInterval(pollTimer.current);
          }
        });
      }, 800);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unexpected error';
      setError(message);
      setLoading(false);
    }
  }

  function handleDownload(): void {
    if (!jobId) {
      return;
    }
    window.open(`${API_BASE_URL}/api/crawl/download/${jobId}`, '_blank');
  }

  return (
    <main className="container">
      <h1>Sitemap Wrangler</h1>

      <form className="controls" onSubmit={handleSubmit}>
        <label htmlFor="domain">Enter Domain Name</label>
        <input
          id="domain"
          value={domain}
          onChange={(event) => setDomain(event.target.value)}
          placeholder="zollsoft.de"
          disabled={isRunning}
        />
        <button type="submit" disabled={isRunning}>
          {isRunning ? 'Generating...' : 'Generate Sitemap'}
        </button>
      </form>

      {isRunning ? (
        <section className="progress">
          <div className="spinner" aria-label="loading" />
          <p>Generating...</p>
          <p>Collected urls: {collectedCount}</p>
          {status?.progress.current_url ? <p>Current: {status.progress.current_url}</p> : null}
        </section>
      ) : null}

      {error ? <p className="error">{error}</p> : null}
      {status?.state === 'error' ? <p className="error">{status.error ?? 'Crawl failed.'}</p> : null}

      {status?.state === 'done' ? (
        <section>
          <button onClick={handleDownload} className="download-btn">
            Download Sitemap
          </button>

          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>URL</th>
                <th>Priority</th>
              </tr>
            </thead>
            <tbody>
              {status.results.map((result, index) => (
                <tr key={result.url}>
                  <td>{index + 1}</td>
                  <td>{result.url}</td>
                  <td>{result.priority.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </main>
  );
}
