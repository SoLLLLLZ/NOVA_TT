import { DEFAULT_API_BASE } from "../config";
import { readSse } from "./sse";
import type { ErrorBody, LiveEvent, ReplayResponse, RunEvent, RunSnapshot, StatusResponse } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly body: ErrorBody;
  readonly activeRunId: string | null;

  constructor(status: number, body: ErrorBody, activeRunId: string | null = null) {
    super(body.message);
    this.status = status;
    this.body = body;
    this.activeRunId = activeRunId;
  }
}

/** Errors that never reached the backend (it is down, or the tunnel is closed). */
export function networkError(cause: unknown): ApiError {
  const detail = cause instanceof Error ? cause.message : String(cause);
  return new ApiError(0, {
    code: "backend_unreachable",
    message: `Can't reach the backend (${detail}). Is it running on ${DEFAULT_API_BASE}?`,
    retryable: true,
  });
}

type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
  idempotencyKey?: string;
  signal?: AbortSignal;
};

export class Client {
  constructor(
    private readonly base: string,
    private readonly token: string | null,
  ) {}

  private async request(path: string, options: RequestOptions = {}): Promise<Response> {
    const headers: Record<string, string> = {};
    if (this.token) headers["X-Pairing-Token"] = this.token;
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
    let response: Response;
    try {
      response = await fetch(this.base + path, {
        method: options.method ?? "GET",
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: options.signal,
      });
    } catch (cause) {
      if (options.signal?.aborted) throw cause;
      throw networkError(cause);
    }
    if (!response.ok) throw await toApiError(response);
    return response;
  }

  async json<T>(path: string, options?: RequestOptions): Promise<T> {
    const response = await this.request(path, options);
    return (await response.json()) as T;
  }

  health(): Promise<{ ok: boolean; contract_version: string }> {
    return this.json("/health");
  }

  status(): Promise<StatusResponse> {
    return this.json("/status");
  }

  run(runId: string): Promise<RunSnapshot> {
    return this.json(`/runs/${encodeURIComponent(runId)}`);
  }

  /**
   * POST a streaming operation (/optimize, /revert, /action). Returns the
   * replay body when the backend answers a repeated Idempotency-Key with JSON
   * instead of a new stream, otherwise null after the stream ends.
   */
  async operation(
    path: string,
    body: unknown,
    idempotencyKey: string,
    onEvent: (event: RunEvent) => void,
    signal?: AbortSignal,
  ): Promise<ReplayResponse | null> {
    const response = await this.request(path, { method: "POST", body, idempotencyKey, signal });
    if (!(response.headers.get("Content-Type") ?? "").includes("text/event-stream")) {
      return (await response.json()) as ReplayResponse;
    }
    await readSse(response, (event) => onEvent(event as RunEvent));
    return null;
  }

  /** GET /live (contract 2.1). Resolves when the backend closes the stream. */
  async live(model: string, onEvent: (event: LiveEvent) => void, signal: AbortSignal): Promise<void> {
    const response = await this.request(`/live?model=${encodeURIComponent(model)}`, { signal });
    await readSse(response, (event) => onEvent(event as LiveEvent));
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const parsed = (await response.json()) as { error?: ErrorBody; active_run_id?: string };
    if (parsed.error?.code) return new ApiError(response.status, parsed.error, parsed.active_run_id ?? null);
  } catch {
    /* fall through to a generic error */
  }
  return new ApiError(response.status, {
    code: "internal",
    message: `Backend answered ${response.status} ${response.statusText}.`.trim(),
  });
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

/** "2.1" → { major: 2, minor: 1 }; unknown formats give NaN. */
export function parseVersion(version: string): { major: number; minor: number } {
  const [major, minor] = version.split(".").map((part) => Number.parseInt(part, 10));
  return { major, minor: Number.isNaN(minor) ? 0 : minor };
}
