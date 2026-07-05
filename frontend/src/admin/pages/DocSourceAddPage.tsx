import { Link } from "react-router-dom";

const MANUAL_CHOICES = [
	{
		to: "/admin/docsources/register",
		icon: "fa-folder-open",
		title: "Register a folder",
		blurb: "Expose an existing folder under documentations/ as a source.",
	},
];

const AI_CHOICES = [
	{
		to: "/admin/docsources/generate",
		icon: "fa-wand-magic-sparkles",
		title: "Generate single document",
		blurb: "Let the agent write a single documentation page from your sources.",
	},
	{
		to: "/admin/docsources/library",
		icon: "fa-book-open",
		title: "Generate a library",
		blurb: "Plan and write a multi-page documentation library (a folder tree).",
	},
];

function ChoiceCard(c: {
	to: string;
	icon: string;
	title: string;
	blurb: string;
}) {
	return (
		<Link key={c.to} to={c.to} className="choice-card">
			<i className={`fa-solid ${c.icon} choice-card__icon`} />
			<div className="choice-card__body">
				<h4>{c.title}</h4>
				<p>{c.blurb}</p>
			</div>
			<i className="fa-solid fa-chevron-right choice-card__chevron" />
		</Link>
	);
}

export function DocSourceAddPage() {
	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Add Documentation</h1>
					<p>Choose how to add a documentation source</p>
				</div>
				<Link to="/admin/docsources" className="btn btn-ghost">
					Back
				</Link>
			</div>

			<div className="choice-section">
				<div className="choice-list">
					{MANUAL_CHOICES.map((c) => (
						<ChoiceCard key={c.to} {...c} />
					))}
				</div>
			</div>

			<div className="choice-section">
				<h3 className="choice-section__title">Generate using AI</h3>
				<div className="choice-list">
					{AI_CHOICES.map((c) => (
						<ChoiceCard key={c.to} {...c} />
					))}
				</div>
			</div>
		</div>
	);
}
