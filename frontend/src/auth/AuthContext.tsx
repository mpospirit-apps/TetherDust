import {
	createContext,
	type ReactNode,
	useContext,
	useEffect,
	useState,
} from "react";
import {
	login as apiLogin,
	logout as apiLogout,
	type CurrentUser,
	fetchCsrf,
	fetchMe,
} from "../api/auth";
import { ApiError } from "../api/client";

interface AuthState {
	user: CurrentUser | null;
	loading: boolean;
	login: (username: string, password: string) => Promise<void>;
	logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
	const [user, setUser] = useState<CurrentUser | null>(null);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		let active = true;
		async function bootstrap() {
			try {
				await fetchCsrf();
				const me = await fetchMe();
				if (active) setUser(me);
			} catch (err) {
				// A 403 just means "not logged in yet" — anything else is worth logging.
				if (!(err instanceof ApiError && err.status === 403)) {
					console.error("auth bootstrap failed", err);
				}
				if (active) setUser(null);
			} finally {
				if (active) setLoading(false);
			}
		}
		void bootstrap();
		return () => {
			active = false;
		};
	}, []);

	async function login(username: string, password: string) {
		setUser(await apiLogin(username, password));
	}

	async function logout() {
		await apiLogout();
		setUser(null);
	}

	return (
		<AuthContext.Provider value={{ user, loading, login, logout }}>
			{children}
		</AuthContext.Provider>
	);
}

export function useAuth(): AuthState {
	const ctx = useContext(AuthContext);
	if (ctx === undefined) {
		throw new Error("useAuth must be used within an AuthProvider");
	}
	return ctx;
}
