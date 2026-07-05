import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { renderWithProviders } from "../test/utils";
import { LoginPage } from "./LoginPage";

// Hoisted mutable handles shared with the module mocks below.
const h = vi.hoisted(() => ({
	user: null as unknown,
	login: vi.fn(),
	navigate: vi.fn(),
}));

vi.mock("../auth/AuthContext", () => ({
	useAuth: () => ({
		user: h.user,
		login: h.login,
		logout: vi.fn(),
		loading: false,
	}),
}));

vi.mock("react-router-dom", async (importOriginal) => {
	const actual = await importOriginal<typeof import("react-router-dom")>();
	return { ...actual, useNavigate: () => h.navigate };
});

async function submitCredentials() {
	const user = userEvent.setup();
	await user.type(screen.getByLabelText("Username"), "neo");
	await user.type(screen.getByLabelText("Password"), "trinity");
	await user.click(screen.getByRole("button", { name: "Sign In" }));
}

describe("LoginPage", () => {
	beforeEach(() => {
		h.user = null;
		h.login.mockReset();
		h.navigate.mockReset();
	});

	it("logs in and navigates home on success", async () => {
		h.login.mockResolvedValue(undefined);
		renderWithProviders(<LoginPage />);

		await submitCredentials();

		expect(h.login).toHaveBeenCalledWith("neo", "trinity");
		expect(h.navigate).toHaveBeenCalledWith("/", { replace: true });
	});

	it("shows a credentials error on a 401", async () => {
		h.login.mockRejectedValue(new ApiError(401, { detail: "no" }));
		renderWithProviders(<LoginPage />);

		await submitCredentials();

		expect(await screen.findByText("Invalid credentials.")).toBeInTheDocument();
		expect(h.navigate).not.toHaveBeenCalled();
	});

	it("shows a generic error on any other failure", async () => {
		h.login.mockRejectedValue(new Error("network"));
		renderWithProviders(<LoginPage />);

		await submitCredentials();

		expect(
			await screen.findByText("Login failed. Please try again."),
		).toBeInTheDocument();
	});

	it("redirects away from the form when already authenticated", () => {
		h.user = { username: "neo" };
		renderWithProviders(<LoginPage />);

		expect(screen.queryByRole("button", { name: "Sign In" })).toBeNull();
	});
});
