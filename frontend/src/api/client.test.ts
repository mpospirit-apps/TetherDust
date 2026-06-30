import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiErrorDetail, apiFetch } from "./client";

interface FakeResponseInit {
	ok?: boolean;
	status?: number;
	contentType?: string;
}

function fakeResponse(body: unknown, init: FakeResponseInit = {}) {
	const { ok = true, status = 200, contentType = "application/json" } = init;
	return {
		ok,
		status,
		headers: {
			get: (h: string) =>
				h.toLowerCase() === "content-type" ? contentType : null,
		},
		json: async () => body,
		text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
	} as unknown as Response;
}

describe("apiFetch", () => {
	let cookieValue = "";
	const fetchMock = vi.fn();

	beforeEach(() => {
		cookieValue = "";
		Object.defineProperty(document, "cookie", {
			configurable: true,
			get: () => cookieValue,
		});
		fetchMock.mockReset();
		vi.stubGlobal("fetch", fetchMock);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	function lastInit(): RequestInit {
		return fetchMock.mock.calls[0][1] as RequestInit;
	}

	it("sends the CSRF header from the cookie on unsafe methods", async () => {
		cookieValue = "csrftoken=tok123";
		fetchMock.mockResolvedValue(fakeResponse({ ok: true }));

		await apiFetch("/api/x", { method: "POST", body: "{}" });

		const headers = lastInit().headers as Headers;
		expect(headers.get("X-CSRFToken")).toBe("tok123");
		expect(lastInit().credentials).toBe("include");
	});

	it("does not send the CSRF header on GET", async () => {
		cookieValue = "csrftoken=tok123";
		fetchMock.mockResolvedValue(fakeResponse({ ok: true }));

		await apiFetch("/api/x");

		const headers = lastInit().headers as Headers;
		expect(headers.get("X-CSRFToken")).toBeNull();
	});

	it("defaults Content-Type to JSON when a body is present", async () => {
		fetchMock.mockResolvedValue(fakeResponse({ ok: true }));

		await apiFetch("/api/x", { method: "PUT", body: "{}" });

		const headers = lastInit().headers as Headers;
		expect(headers.get("Content-Type")).toBe("application/json");
	});

	it("parses a JSON body and returns it typed", async () => {
		fetchMock.mockResolvedValue(fakeResponse({ value: 42 }));

		const data = await apiFetch<{ value: number }>("/api/x");
		expect(data.value).toBe(42);
	});

	it("returns text when the response is not JSON", async () => {
		fetchMock.mockResolvedValue(
			fakeResponse("plain body", { contentType: "text/plain" }),
		);

		const data = await apiFetch<string>("/api/x");
		expect(data).toBe("plain body");
	});

	it("throws an ApiError carrying status and parsed body on failure", async () => {
		fetchMock.mockResolvedValue(
			fakeResponse({ detail: "nope" }, { ok: false, status: 403 }),
		);

		await expect(apiFetch("/api/x")).rejects.toMatchObject({
			name: "ApiError",
			status: 403,
			data: { detail: "nope" },
		});
	});
});

describe("apiErrorDetail", () => {
	it("reads the DRF {detail} shape", () => {
		expect(apiErrorDetail(new ApiError(400, { detail: "bad request" }))).toBe(
			"bad request",
		);
	});

	it("reads the {error} shape", () => {
		expect(apiErrorDetail(new ApiError(400, { error: "boom" }))).toBe("boom");
	});

	it("formats a field-validation dict with key prefixes", () => {
		const msg = apiErrorDetail(
			new ApiError(400, { username: ["required", "too short"] }),
		);
		expect(msg).toBe("username: required too short");
	});

	it("omits the prefix for non_field_errors and joins multiple fields", () => {
		const msg = apiErrorDetail(
			new ApiError(400, { non_field_errors: ["bad combo"], password: "weak" }),
		);
		expect(msg).toBe("bad combo • password: weak");
	});

	it("falls back for non-ApiError values", () => {
		expect(apiErrorDetail(new Error("x"))).toBe("Request failed.");
		expect(apiErrorDetail(new ApiError(500, null), "Custom fallback")).toBe(
			"Custom fallback",
		);
	});
});
