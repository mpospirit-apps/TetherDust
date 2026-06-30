import {
	type CSSProperties,
	type FormEvent,
	useEffect,
	useRef,
	useState,
} from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const GLIMMERS: CSSProperties[] = [
	{ top: "15%", left: "10%", animationDuration: "4s" },
	{ top: "30%", left: "80%", animationDuration: "3.6s" },
	{ top: "70%", left: "20%", animationDuration: "5s" },
	{ top: "50%", left: "85%", animationDuration: "3.3s" },
	{ top: "85%", left: "50%", animationDuration: "4.6s" },
];

export function LoginPage() {
	const { user, login } = useAuth();
	const navigate = useNavigate();
	const [username, setUsername] = useState("");
	const [password, setPassword] = useState("");
	const [error, setError] = useState<string | null>(null);
	const [submitting, setSubmitting] = useState(false);
	const usernameRef = useRef<HTMLInputElement>(null);

	useEffect(() => {
		document.body.classList.add("login-page");
		usernameRef.current?.focus();
		return () => document.body.classList.remove("login-page");
	}, []);

	if (user) {
		return <Navigate to="/" replace />;
	}

	async function handleSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		setSubmitting(true);
		try {
			await login(username, password);
			navigate("/", { replace: true });
		} catch (err) {
			setError(
				err instanceof ApiError && err.status === 401
					? "Invalid credentials."
					: "Login failed. Please try again.",
			);
		} finally {
			setSubmitting(false);
		}
	}

	return (
		<>
			<div className="glimmer-container" aria-hidden="true">
				{GLIMMERS.map((style) => (
					<div
						key={`${style.top}-${style.left}`}
						className="glimmer-dot"
						style={style}
					/>
				))}
			</div>
			<div className="login-card">
				<div className="brand">
					<img
						src="/images/tetherdust.png"
						alt="TetherDust"
						className="brand-icon"
					/>
					Tether<span>Dust</span>
				</div>
				<div className="subtitle">Sign In</div>
				{error && <div className="error">{error}</div>}
				<form onSubmit={handleSubmit}>
					<div className="form-group">
						<label htmlFor="username">Callsign</label>
						<input
							ref={usernameRef}
							id="username"
							type="text"
							placeholder="Username"
							autoComplete="username"
							required
							value={username}
							onChange={(event) => setUsername(event.target.value)}
						/>
					</div>
					<div className="form-group">
						<label htmlFor="password">Passphrase</label>
						<input
							id="password"
							type="password"
							placeholder="Password"
							autoComplete="current-password"
							required
							value={password}
							onChange={(event) => setPassword(event.target.value)}
						/>
					</div>
					<button type="submit" className="btn" disabled={submitting}>
						{submitting ? "Authenticating…" : "Initiate Access"}
					</button>
				</form>
			</div>
		</>
	);
}
