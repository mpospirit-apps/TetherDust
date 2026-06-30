// Graph schema returned by /api/v1/tethers/<id>/graph/ (see engine tether_engine
// SCHEMA_EXAMPLE). Nodes/edges carry optional kind-specific fields; the canvas
// also stashes layout state on node objects at runtime (see RuntimeNode).

export interface GraphNode {
	id: string;
	label: string;
	kind: "code-file" | "code-symbol" | "db-table" | "db-column";
	parent_id: string | null;
	description?: string;
	language?: string;
	path?: string;
	signature?: string;
	snippet?: string;
	line_range?: string | number;
	schema?: string;
	row_count_hint?: string;
	data_type?: string;
	nullable?: boolean;
	primary_key?: boolean;
	foreign_key?: string;
}

export interface GraphEdge {
	source_id: string;
	target_id: string;
	relationship: "reads" | "writes" | "references" | "maps-to";
	confidence?: number;
	description?: string;
	evidence?: string;
	evidence_snippet?: string;
	evidence_lang?: string;
}

export interface TetherGraph {
	nodes: GraphNode[];
	edges: GraphEdge[];
	codebase_summary?: string;
	database_summary?: string;
	schema_version?: number;
	status?: string;
}
