import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, money } from "./client";

describe("money", () => {
  it("formats integer minor units as SEK", () => {
    expect(money(3800)).toMatch(/38,00/);
    expect(money(3800)).toContain("kr");
  });
});

describe("api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("resolves with the parsed JSON body on a 2xx response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api("/ping")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/ping",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("throws an ApiError carrying the response status on a non-2xx response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api("/missing")).rejects.toMatchObject(
      new ApiError(404, "Not found"),
    );
  });

  it("keeps Content-Type when the caller passes extra headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api("/admin/orders/1", {
      method: "PATCH",
      headers: { "X-CSRF-Token": "token-123" },
      body: JSON.stringify({ status: "fulfilled" }),
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/admin/orders/1",
      expect.objectContaining({
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": "token-123" },
      }),
    );
  });

  it("stringifies structured error details instead of rendering [object Object]", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: [{ loc: ["body"], msg: "field required" }] }), {
        status: 422,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api("/invalid")).rejects.toMatchObject({
      status: 422,
      message: expect.stringContaining("field required"),
    });
  });

  it("falls back to a generic message when the error body isn't JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("not json", { status: 500 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api("/boom")).rejects.toMatchObject({
      status: 500,
      message: "Request failed",
    });
  });
});
