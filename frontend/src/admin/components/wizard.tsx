// Section heading for the stacked-section "Add …" forms (database, docsource,
// mcp server, ...). Each form section renders one of these directly above its
// own card — a bold zero-padded step number, the section's title, and a short
// explanation of what the section covers — instead of a single title bar
// listing every step, so the title isn't duplicated between an overview bar
// and the card itself.
export interface WizardStepDef {
	key: string;
	label: string;
	description: string;
}

export function WizardSectionHeading({
	step,
	index,
}: {
	step: WizardStepDef;
	index: number;
}) {
	return (
		<div className="wizard-section-heading">
			<div className="wizard-section-heading__row">
				<span className="wizard-section-heading__num">
					{String(index + 1).padStart(2, "0")}
				</span>
				<h3 className="wizard-section-heading__title">{step.label}</h3>
			</div>
			<p className="wizard-section-heading__desc">{step.description}</p>
		</div>
	);
}
