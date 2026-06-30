import { afterEach, describe, expect, it } from "vitest";
import {
	cssEscape,
	DEFAULT_GAP,
	DEFAULT_SPREAD,
	escapeHtml,
	getGap,
	getSpread,
} from "./constants";

afterEach(() => {
	localStorage.clear();
});

describe("escapeHtml", () => {
	it("escapes all five HTML-significant characters", () => {
		expect(escapeHtml(`<a href="x" class='y'>&</a>`)).toBe(
			"&lt;a href=&quot;x&quot; class=&#39;y&#39;&gt;&amp;&lt;/a&gt;",
		);
	});

	it("leaves plain text untouched", () => {
		expect(escapeHtml("hello world")).toBe("hello world");
	});
});

describe("cssEscape", () => {
	it("escapes a value so it is safe inside a selector", () => {
		// jsdom provides CSS.escape; a leading digit must be escaped.
		expect(cssEscape("1abc")).toBe(CSS.escape("1abc"));
		expect(cssEscape("a.b#c")).toBe(CSS.escape("a.b#c"));
	});
});

describe("getSpread", () => {
	it("returns the default when nothing is stored", () => {
		expect(getSpread()).toBe(DEFAULT_SPREAD);
	});

	it("returns a stored positive number", () => {
		localStorage.setItem("tether:spread", "800");
		expect(getSpread()).toBe(800);
	});

	it("falls back to the default for non-positive or non-numeric values", () => {
		localStorage.setItem("tether:spread", "-5");
		expect(getSpread()).toBe(DEFAULT_SPREAD);
		localStorage.setItem("tether:spread", "not-a-number");
		expect(getSpread()).toBe(DEFAULT_SPREAD);
	});
});

describe("getGap", () => {
	it("returns the default when nothing is stored", () => {
		expect(getGap()).toBe(DEFAULT_GAP);
	});

	it("returns a stored positive number", () => {
		localStorage.setItem("tether:gap", "0.5");
		expect(getGap()).toBe(0.5);
	});

	it("falls back to the default for non-positive values", () => {
		localStorage.setItem("tether:gap", "0");
		expect(getGap()).toBe(DEFAULT_GAP);
	});
});
