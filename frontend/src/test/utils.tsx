import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type RenderOptions, render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

// Wraps a component under test in the providers the app relies on: a fresh
// TanStack Query client (retries off so failed queries surface immediately) and
// a MemoryRouter (so route-aware components / <Navigate> work without a browser).
// Pass `route` to seed the initial history entry.
interface ProviderOptions extends Omit<RenderOptions, "wrapper"> {
	route?: string;
}

export function renderWithProviders(
	ui: ReactElement,
	{ route = "/", ...options }: ProviderOptions = {},
) {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});

	function Wrapper({ children }: { children: ReactNode }) {
		return (
			<QueryClientProvider client={queryClient}>
				<MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
			</QueryClientProvider>
		);
	}

	return { queryClient, ...render(ui, { wrapper: Wrapper, ...options }) };
}
