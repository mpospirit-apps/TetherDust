import type { Building, City } from "./city/plan";

// The one part of the view that moved OUT of imperative code. The scene owns the
// SVG because a frame rewrites a thousand attributes; the panel is ordinary
// content that changes once per click, which is exactly what React is for.

function storeyLabel(b: Building): string {
	return b.kind === "code" ? "symbols" : "columns";
}

export function CityInspector({
	city,
	id,
	onClose,
}: {
	city: City;
	id: string;
	onClose(): void;
}) {
	const b = city.byId.get(id);
	if (!b) return null;

	// every edge this building carries, flattened out of its bundles
	const strands = b.bundles.flatMap((bu) => {
		const otherId = bu.src === b.id ? bu.dst : bu.src;
		const other = city.byId.get(otherId);
		const outgoing = bu.src === b.id;
		return bu.strands.map((t) => ({
			t,
			other,
			mine: outgoing ? t.si : t.di,
			theirs: outgoing ? t.di : t.si,
			named: outgoing ? t.namedSrc : t.namedDst,
			theirNamed: outgoing ? t.namedDst : t.namedSrc,
		}));
	});

	return (
		<aside className="city-inspector" aria-label="Selection details">
			<button
				type="button"
				className="city-inspector__close"
				onClick={onClose}
				title="Close"
			>
				<i className="fa-solid fa-xmark" />
			</button>
			<span className="city-inspector__kind">
				{b.kind === "code" ? "code file" : "table"}
				{b.block ? ` · ${b.block}` : ""}
			</span>
			<h2>{b.label}</h2>
			{b.desc ? <p>{b.desc}</p> : null}

			<h3>
				{b.h} {storeyLabel(b)}
			</h3>
			<ul>
				{b.rows.map((row, i) => {
					const rel = b.lit.get(i);
					return (
						<li key={row.id} className={rel ? "hot" : undefined}>
							<span className="nm">{row.name}</span>
							{row.pk ? <span className="fg">pk</span> : null}
							{row.fk ? <span className="fg">fk</span> : null}
							{row.type ? <span className="ty">{row.type}</span> : null}
						</li>
					);
				})}
			</ul>

			<h3>
				{strands.length} {strands.length === 1 ? "tether" : "tethers"}
				{b.bundles.length !== strands.length
					? ` · ${b.bundles.length} cords`
					: ""}
			</h3>
			<ul>
				{strands.length === 0 ? (
					<li>
						<span className="nm">No tethers on this building.</span>
					</li>
				) : (
					strands.map((s) => (
						<li key={s.t.key}>
							<span className={`rl-${s.t.rel}`}>{s.t.rel}</span>
							<span className="nm">
								{/* an end that named only the file or table has no storey to
								    quote, so it is shown as the building itself */}
								{s.named ? b.rows[s.mine]?.name : "—"} → {s.other?.label ?? "?"}
								{s.theirNamed && s.other
									? `.${s.other.rows[s.theirs]?.name}`
									: ""}
							</span>
							<span className="ty">{s.t.conf.toFixed(2)}</span>
						</li>
					))
				)}
			</ul>
		</aside>
	);
}
