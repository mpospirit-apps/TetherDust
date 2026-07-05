import { type FormEvent, useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuroraBackground } from "../components/AuroraBackground";

export function LoginPage() {
	const { user, login } = useAuth();
	const navigate = useNavigate();
	const [username, setUsername] = useState("");
	const [password, setPassword] = useState("");
	const [error, setError] = useState<string | null>(null);
	const [submitting, setSubmitting] = useState(false);
	const usernameRef = useRef<HTMLInputElement>(null);

	useEffect(() => {
		document.body.classList.add("login-page", "aurora-bg");
		usernameRef.current?.focus();
		return () => document.body.classList.remove("login-page", "aurora-bg");
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
			<AuroraBackground />
			<div className="login-card">
				<div className="brand">
					<div className="nav-logo">
						<img src="/images/tetherdust.png" alt="TetherDust" />
					</div>
					<span className="nav-title">
						Tether<span className="accent">Dust</span>
					</span>
				</div>
				<div className="subtitle">Welcome back</div>
				{error && <div className="error">{error}</div>}
				<form onSubmit={handleSubmit}>
					<div className="form-group">
						<label htmlFor="username">Username</label>
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
						<label htmlFor="password">Password</label>
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
						{submitting ? "Signing in…" : "Sign In"}
					</button>
				</form>
			</div>
		</>
	);
}
