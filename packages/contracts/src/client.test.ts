import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, VocalScoreApi } from "./client";

describe("API errors", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("preserves structured revision conflict details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
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
    const fetchMock = vi.fn(async () =>
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
