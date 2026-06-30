import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../test/utils";
import { ChatComposer } from "./ChatComposer";

// The composer fetches the `/`-prompt list via TanStack Query on mount; stub the
// API module so no real fetch happens and the prompt/doc lookups stay empty.
vi.mock("../api/chat", () => ({
	listChatPrompts: vi.fn().mockResolvedValue({ prompts: [] }),
	searchDocSources: vi.fn().mockResolvedValue({ resources: [] }),
}));

function setup(props: Partial<Parameters<typeof ChatComposer>[0]> = {}) {
	const onSend = vi.fn();
	const onCancel = vi.fn();
	renderWithProviders(
		<ChatComposer
			connected
			streaming={false}
			onSend={onSend}
			onCancel={onCancel}
			{...props}
		/>,
	);
	return { onSend, onCancel };
}

describe("ChatComposer", () => {
	it("shows a connecting placeholder until connected", () => {
		setup({ connected: false });
		const textarea = screen.getByRole("textbox");
		expect(textarea).toHaveAttribute("placeholder", "Connecting…");
		expect(textarea).toBeDisabled();
	});

	it("invites a message once connected", () => {
		setup();
		expect(screen.getByRole("textbox")).toHaveAttribute(
			"placeholder",
			expect.stringContaining("Message the agent"),
		);
	});

	it("disables Send until there is non-whitespace text", async () => {
		const user = userEvent.setup();
		setup();
		const send = screen.getByRole("button", { name: "Send" });
		expect(send).toBeDisabled();

		await user.type(screen.getByRole("textbox"), "hello");
		expect(send).toBeEnabled();
	});

	it("submits the message on Enter and clears the input", async () => {
		const user = userEvent.setup();
		const { onSend } = setup();

		const textarea = screen.getByRole("textbox");
		await user.type(textarea, "what tables exist?{Enter}");

		expect(onSend).toHaveBeenCalledWith("what tables exist?", [], []);
		expect(textarea).toHaveValue("");
	});

	it("does not submit on Shift+Enter", async () => {
		const user = userEvent.setup();
		const { onSend } = setup();

		await user.type(
			screen.getByRole("textbox"),
			"line one{Shift>}{Enter}{/Shift}",
		);
		expect(onSend).not.toHaveBeenCalled();
	});

	it("shows a Stop button while streaming and calls onCancel", async () => {
		const user = userEvent.setup();
		const { onCancel } = setup({ streaming: true });

		expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
		await user.click(screen.getByRole("button", { name: "Stop" }));
		expect(onCancel).toHaveBeenCalledOnce();
	});
});
