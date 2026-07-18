// ── Supabase Client ──────────────────────────────────────────
// Lightweight client for browser-side Supabase operations.
// Uses the existing env vars from the project.

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';

interface SupabaseClient {
  from: (table: string) => SupabaseQuery;
}

interface SupabaseQuery {
  select: (cols?: string) => SupabaseFilter;
  insert: (data: unknown) => SupabaseExecutor;
  update: (data: unknown) => SupabaseFilter;
  delete: () => SupabaseFilter;
}

interface SupabaseFilter {
  _params: URLSearchParams;
  eq: (col: string, val: unknown) => SupabaseFilter;
  neq: (col: string, val: unknown) => SupabaseFilter;
  order: (col: string, opts?: { ascending?: boolean }) => SupabaseFilter;
  limit: (n: number) => SupabaseFilter;
  single: () => SupabaseExecutor;
  maybeSingle: () => SupabaseExecutor;
  or: (filters: string) => SupabaseFilter;
  in: (col: string, vals: unknown[]) => SupabaseFilter;
  gte: (col: string, val: unknown) => SupabaseFilter;
  lte: (col: string, val: unknown) => SupabaseFilter;
}

interface SupabaseExecutor {
  then: <T>(fn: (result: { data: T | null; error: Error | null }) => unknown) => Promise<unknown>;
}

// ── Small Supabase-like client (no external dep needed) ──────

function createClient(url: string, key: string): SupabaseClient {
  const headers = {
    'apikey': key,
    'Authorization': `Bearer ${key}`,
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
  };

  function buildFilter(baseUrl: string, method: string, body?: unknown): SupabaseExecutor {
    return {
      then: async (fn) => {
        try {
          const res = await fetch(baseUrl, {
            method,
            headers,
            body: body ? JSON.stringify(body) : undefined,
          });
          if (!res.ok) {
            const err = await res.text();
            return fn({ data: null, error: new Error(err) });
          }
          const data = await res.json();
          return fn({ data, error: null });
        } catch (e) {
          return fn({ data: null, error: e as Error });
        }
      },
    };
  }

  function buildFilterChain(path: string): SupabaseFilter {
    const q = {
      _path: path,
      _params: new URLSearchParams(),

      eq(col: string, val: unknown) {
        this._params.set(`${col}`, `eq.${val}`);
        return this;
      },
      neq(col: string, val: unknown) {
        this._params.set(`${col}`, `neq.${val}`);
        return this;
      },
      order(col: string, opts?: { ascending?: boolean }) {
        this._params.set('order', `${col}.${opts?.ascending === false ? 'desc' : 'asc'}`);
        return this;
      },
      limit(n: number) {
        this._params.set('limit', String(n));
        return this;
      },
      or(filters: string) {
        this._params.set('or', filters);
        return this;
      },
      in(col: string, vals: unknown[]) {
        this._params.set(`${col}`, `in.(${vals.join(',')})`);
        return this;
      },
      gte(col: string, val: unknown) {
        this._params.set(`${col}`, `gte.${val}`);
        return this;
      },
      lte(col: string, val: unknown) {
        this._params.set(`${col}`, `lte.${val}`);
        return this;
      },
      single() {
        this._params.set('limit', '1');
        const p = this._path;
        const params = this._params.toString();
        return buildFilter(`${url}${p}?${params}`, 'GET');
      },
      maybeSingle() {
        this._params.set('limit', '1');
        const p = this._path;
        const params = this._params.toString();
        return buildFilter(`${url}${p}?${params}`, 'GET');
      },
    };

    // Override select to return the filter
    (q as unknown as SupabaseFilter & { select: (cols?: string) => SupabaseFilter }).select = (cols = '*') => {
      q._params.set('select', cols);
      return q as unknown as SupabaseFilter;
    };

    return q as unknown as SupabaseFilter;
  }

  return {
    from(table: string) {
      const basePath = `/rest/v1/${table}`;
      return {
        select: (cols = '*') => {
          const f: any = buildFilterChain(basePath);
          f._params.set('select', cols);
          return f;
        },
        insert: (data: unknown) => {
          return buildFilter(basePath, 'POST', data);
        },
        update: (data: unknown) => {
          const f: any = buildFilterChain(basePath);
          const origThen = buildFilter(basePath, 'PATCH', data).then;
          f._params.set('select', '*');

          // Override then to include body
          const exec = {
            ...f,
            _origThen: origThen,
            then: (fn: (r: { data: unknown; error: Error | null }) => unknown) => {
              const params = f._params.toString();
              const url = `${SUPABASE_URL}${basePath}?${params}`;
              return fetch(url, {
                method: 'PATCH',
                headers: {
                  ...headers,
                  'Prefer': 'return=representation',
                },
                body: JSON.stringify(data),
              })
                .then(async (res) => {
                  if (!res.ok) {
                    const err = await res.text();
                    return fn({ data: null, error: new Error(err) });
                  }
                  const d = await res.json();
                  return fn({ data: d, error: null });
                })
                .catch((e) => fn({ data: null, error: e }));
            },
          };
          return exec as unknown as SupabaseFilter;
        },
        delete: () => {
          const f: any = buildFilterChain(basePath);
          const exec = {
            ...f,
            then: (fn: (r: { data: unknown; error: Error | null }) => unknown) => {
              const params = f._params.toString();
              return fetch(`${SUPABASE_URL}${basePath}?${params}`, {
                method: 'DELETE',
                headers,
              })
                .then(async (res) => {
                  if (!res.ok) {
                    const err = await res.text();
                    return fn({ data: null, error: new Error(err) });
                  }
                  try {
                    const d = await res.json();
                    return fn({ data: d, error: null });
                  } catch {
                    return fn({ data: null, error: null });
                  }
                })
                .catch((e) => fn({ data: null, error: e }));
            },
          };
          return exec as unknown as SupabaseFilter;
        },
      };
    },
  };
}

// Singleton
let client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (!client) {
    if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
      throw new Error('Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.');
    }
    client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
  return client;
}

function buildNoopExecutor(): SupabaseExecutor {
  return {
    then: async (fn) => fn({ data: null, error: new Error('Supabase not configured') }),
  };
}

export default getSupabase;
