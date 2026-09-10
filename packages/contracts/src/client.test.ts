import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, VocalScoreApi } from "./client";

describe("API errors", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("preserves structured revision conflict details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              detail: { code: "REVISION_CONFLICT", current_revision: 4 },
            }),
            { status: 409, headers: { "content-type": "application/json" } },
          ),
      ),
    );
    const error = await new VocalScoreApi("http://api")
      .getProject("project")
      .catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      message: "REVISION_CONFLICT",
      detail: { code: "REVISION_CONFLICT", current_revision: 4 },
    });
  });
});

describe("boundary suggestion review", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends an optimistic review action", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ revision: 3 }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await new VocalScoreApi("http://api").reviewBoundarySuggestion(
      "project",
      "suggestion",
      { expected_revision: 2, action: "accept" },
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api/v1/projects/project/boundary-suggestions/suggestion",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expected_revision: 2, action: "accept" }),
      }),
    );
  });
});

describe("F0 evidence", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("parses newline-delimited F0 frames", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            '{"time_seconds":0,"f0_hz":440,"periodicity":0.9}\n' +
              '{"time_seconds":0.01,"f0_hz":441,"periodicity":0.8}\n',
            { status: 200, headers: { "content-type": "application/x-ndjson" } },
          ),
      ),
    );
    await expect(new VocalScoreApi("http://api").getF0Track("project")).resolves.toEqual([
      { time_seconds: 0, f0_hz: 440, periodicity: 0.9 },
      { time_seconds: 0.01, f0_hz: 441, periodicity: 0.8 },
    ]);
  });
});

describe("project exports", () => {
  it("selects the performance or score MIDI explicitly", () => {
    const api = new VocalScoreApi("http://api");
    expect(api.exportUrl("project", "midi")).toBe(
      "http://api/v1/projects/project/exports/midi?version=score",
    );
    expect(api.exportUrl("project", "midi", "performance")).toBe(
      "http://api/v1/projects/project/exports/midi?version=performance",
    );
    expect(api.exportUrl("project", "musicxml", "performance")).toBe(
      "http://api/v1/projects/project/exports/musicxml",
    );
    expect(api.exportUrl("project", "staff.svg")).toBe(
      "http://api/v1/projects/project/exports/staff.svg",
    );
    expect(api.exportUrl("project", "jianpu.svg")).toBe(
      "http://api/v1/projects/project/exports/jianpu.svg",
    );
    expect(api.exportUrl("project", "staff.png")).toBe(
      "http://api/v1/projects/project/exports/staff.png",
    );
    expect(api.exportUrl("project", "jianpu.pdf")).toBe(
      "http://api/v1/projects/project/exports/jianpu.pdf",
    );
  });
});

describe("audio projects", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("can delete an upload before it has generated a score", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await new VocalScoreApi("http://api").deleteUpload("upload");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api/v1/uploads/upload",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});

describe("experimental job selection", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("maps the experimental mode to GAME plus F0 without changing high quality", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify({ id: "job" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = new VocalScoreApi("http://api");
    await api.createJob("upload", "experimental");
    await api.createJob("upload", "high");
    expect(
      JSON.parse(fetchMock.mock.calls[0][1]!.body as string).options,
    ).toEqual({
      separator: "demucs",
      transcriber: "game_f0",
    });
    expect(
      JSON.parse(fetchMock.mock.calls[1][1]!.body as string).options,
    ).toEqual({
      separator: "demucs",
      transcriber: "basic_pitch",
    });
  });
});
