import { Link } from "react-router-dom";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";

// Manual sources need no button — sync_from_filesystem auto-registers any
// folder it finds under /sources/docs. These are just the steps to do it.
const MANUAL_STEPS: WizardStepDef[] = [
	{
		key: "create",
		label: "Create the folder",
		description: "Add a folder under /sources/docs with Markdown files.",
	},
	{
		key: "auto-register",
		label: "It's auto-registered",
		description:
			"The next time this list loads, the folder appears as a source with default settings (type Database, no description). Only Markdown (*.md) files are ever parsed.",
	},
	{
		key: "edit",
		label: "Edit it",
		description:
			"Open the new source from the list and set its type and description as you like.",
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
		title: "Generate documentation library",
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
				<h3 className="choice-section__title">Manual</h3>
				<div className="card">
					<p className="text-sec">
						Follow these steps to add an existing documentation to TetherDust.
					</p>
					<div className="hint-steps">
						{MANUAL_STEPS.map((step, i) => (
							<WizardSectionHeading key={step.key} step={step} index={i} />
						))}
					</div>
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
