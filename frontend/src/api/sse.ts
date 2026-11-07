// Minimal text/event-stream parser for fetch() bodies. The contract only uses
// `data:` lines (one JSON object per event) and `:` comments for heartbeats.

export class SseParser {
  private buffer = "";

  /** Feed decoded text; returns the parsed JSON payload of every complete event. */
  push(chunk: string): unknown[] {
    this.buffer += chunk.replace(/\r\n?/g, "\n");
    const events: unknown[] = [];
    let boundary = this.buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).replace(/^ /, ""))
        .join("\n");
      if (data) events.push(JSON.parse(data));
      boundary = this.buffer.indexOf("\n\n");
    }
    return events;
  }
}

/** Reads an SSE response to its end, calling onEvent for each payload. */
export async function readSse(response: Response, onEvent: (event: unknown) => void): Promise<void> {
  if (!response.body) throw new Error("Response has no body to stream.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const event of parser.push(decoder.decode(value, { stream: true }))) onEvent(event);
  }
  for (const event of parser.push(decoder.decode() + "\n\n")) onEvent(event);
}
