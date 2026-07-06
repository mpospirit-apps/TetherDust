import { Link } from "react-router-dom";

const MANUAL_CHOICES = [
	{
		to: "/admin/dashboards/new",
		icon: "fa-table-cells",
		title: "New dashboard",
		blurb: "Create an empty dashboard, then add charts one at a time.",
	},
];

const AI_CHOICES = [
	{
		to: "/admin/dashboards/generate",
		icon: "fa-wand-magic-sparkles",
		title: "Generate with AI",
		blurb: "Let the agent explore your data and build a dashboard of charts.",
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

export function DashboardAddPage() {
	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Add Dashboard</h1>
					<p>Choose how to create a dashboard</p>
				</div>
				<Link to="/admin/dashboards" className="btn btn-ghost">
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
