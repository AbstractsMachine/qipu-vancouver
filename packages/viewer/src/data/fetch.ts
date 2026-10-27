export class HttpError extends Error {
  constructor(
    readonly url: string,
    readonly status: number,
  ) {
    super(`${url}: HTTP ${status}`);
    this.name = "HttpError";
  }
}

export type Fetch = (input: string, init?: RequestInit) => Promise<Response>;

export async function fetchJson(url: string, fetcher: Fetch = fetch, signal?: AbortSignal): Promise<unknown> {
  const res = await fetcher(url, signal ? { signal } : undefined);
  if (!res.ok) throw new HttpError(url, res.status);
  return res.json();
}

/** Like `fetchJson`, but a missing file (404) is `null`: optional files must not take a panel down. */
export async function fetchOptionalJson(url: string, fetcher: Fetch = fetch): Promise<unknown> {
  const res = await fetcher(url);
  if (res.status === 404) return null;
  if (!res.ok) throw new HttpError(url, res.status);
  return res.json();
}

export async function fetchText(url: string, fetcher: Fetch = fetch): Promise<string> {
  const res = await fetcher(url);
  if (!res.ok) throw new HttpError(url, res.status);
  return res.text();
}

export async function fetchBuffer(url: string, fetcher: Fetch = fetch): Promise<ArrayBuffer> {
  const res = await fetcher(url);
  if (!res.ok) throw new HttpError(url, res.status);
  return res.arrayBuffer();
}

/** Memoise an async loader by key; a failed load is forgotten so it can be retried. */
export function memo<K, V>(load: (key: K) => Promise<V>): (key: K) => Promise<V> {
  const cache = new Map<K, Promise<V>>();
  return (key) => {
    let p = cache.get(key);
    if (!p) {
      p = load(key);
      cache.set(key, p);
      p.catch(() => cache.delete(key));
    }
    return p;
  };
}
