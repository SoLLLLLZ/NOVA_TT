import { describe, expect, it } from "vitest";
import { SseParser } from "./sse";

describe("SseParser", () => {
  it("parses events split across chunks", () => {
    const parser = new SseParser();
    expect(parser.push('data: {"type":"st')).toEqual([]);
    expect(parser.push('art","sequence":1}\n')).toEqual([]);
    expect(parser.push("\ndata: {\"type\":\"step\"}\n\n")).toEqual([
      { type: "start", sequence: 1 },
      { type: "step" },
    ]);
  });

  it("ignores heartbeat comments and handles CRLF", () => {
    const parser = new SseParser();
    expect(parser.push(": heartbeat\r\n\r\ndata: {\"a\":1}\r\n\r\n")).toEqual([{ a: 1 }]);
  });

  it("joins multi-line data fields", () => {
    const parser = new SseParser();
    expect(parser.push('data: {"a":\ndata: 2}\n\n')).toEqual([{ a: 2 }]);
  });
});
