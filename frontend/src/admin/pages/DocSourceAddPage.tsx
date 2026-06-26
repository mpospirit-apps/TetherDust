import { Link } from "react-router-dom";

const CHOICES = [
  {
    to: "/admin/docsources/register",
    icon: "fa-folder-open",
    title: "Register a folder",
    blurb: "Expose an existing folder under documentations/ as a source.",
  },
  {
    to: "/admin/docsources/generate",
    icon: "fa-wand-magic-sparkles",
    title: "Generate with AI",
    blurb: "Let the agent write a single documentation page from your sources.",
  },
  {
    to: "/admin/docsources/library",
    icon: "fa-book-open",
    title: "Generate a library",
    blurb: "Plan and write a multi-page documentation library (a folder tree).",
  },
];

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

      <div className="doc-choice-grid">
        {CHOICES.map((c) => (
          <Link key={c.to} to={c.to} className="doc-choice-card">
            <i className={`fa-solid ${c.icon}`} />
            <h4>{c.title}</h4>
            <p>{c.blurb}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
