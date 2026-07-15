import {
	siClickhouse,
	siMariadb,
	siMysql,
	siPostgresql,
	siSqlite,
} from "simple-icons";

export type EngineIcon =
	| { kind: "logo"; title: string; path: string }
	| { kind: "fa"; family: "solid" | "brands"; icon: string };

export const ENGINE_META: Record<string, { icon: EngineIcon; blurb: string }> =
	{
		postgresql: {
			icon: {
				kind: "logo",
				title: siPostgresql.title,
				path: siPostgresql.path,
			},
			blurb: "Open-source relational database. Default port 5432.",
		},
		mysql: {
			icon: { kind: "logo", title: siMysql.title, path: siMysql.path },
			blurb: "Popular open-source RDBMS. Default port 3306.",
		},
		mariadb: {
			icon: { kind: "logo", title: siMariadb.title, path: siMariadb.path },
			blurb: "MySQL-compatible fork. Default port 3306.",
		},
		mssql: {
			icon: { kind: "fa", family: "brands", icon: "fa-microsoft" },
			blurb: "Microsoft SQL Server. Default port 1433.",
		},
		sqlite: {
			icon: { kind: "logo", title: siSqlite.title, path: siSqlite.path },
			blurb: "Local file-based database — no host required.",
		},
		clickhouse: {
			icon: {
				kind: "logo",
				title: siClickhouse.title,
				path: siClickhouse.path,
			},
			blurb: "Columnar OLAP database. Default port 8123.",
		},
	};

export const DEFAULT_ENGINE_META: { icon: EngineIcon; blurb: string } = {
	icon: { kind: "fa", family: "solid", icon: "fa-database" },
	blurb: "",
};

export function EngineIconGlyph({
	icon,
	className,
}: {
	icon: EngineIcon;
	className?: string;
}) {
	if (icon.kind === "logo") {
		return (
			<span
				className={`choice-card__icon choice-card__icon--logo ${className ?? ""}`}
			>
				<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
					<title>{icon.title}</title>
					<path d={icon.path} />
				</svg>
			</span>
		);
	}
	return (
		<i
			className={`fa-${icon.family} ${icon.icon} choice-card__icon ${className ?? ""}`}
		/>
	);
}
