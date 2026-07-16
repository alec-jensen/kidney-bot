import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { fetchCommandDocs, type CommandCategory, type CommandDoc } from "../lib/api";
import { Skeleton } from "../components/Skeleton";
import { ErrorBanner } from "../components/ErrorBanner";

function matchesQuery(command: CommandDoc, query: string): boolean {
  const q = query.toLowerCase();
  return (
    command.name.toLowerCase().includes(q) ||
    (command.brief?.toLowerCase().includes(q) ?? false) ||
    (command.description?.toLowerCase().includes(q) ?? false)
  );
}

function CommandCard({ command }: { command: CommandDoc }) {
  const [expanded, setExpanded] = useState(false);
  const hasLongDescription = !!command.description && command.description.length > 0;

  return (
    <article className="doc-command-card">
      <div className="doc-command-card-head">
        <h3 className="doc-command-name">{command.name}</h3>
        {command.perm && <span className="doc-command-perm">{command.perm}</span>}
      </div>
      {command.usage && <code className="doc-command-usage">{command.usage}</code>}
      {command.brief && <p className="doc-command-brief">{command.brief}</p>}

      {hasLongDescription && (
        <div className="doc-command-description">
          {expanded ? (
            <>
              <p>{command.description}</p>
              <button className="button button--link" type="button" onClick={() => setExpanded(false)}>
                Show less
              </button>
            </>
          ) : (
            <button className="button button--link" type="button" onClick={() => setExpanded(true)}>
              Show more
            </button>
          )}
        </div>
      )}

      {!!command.params?.length && (
        <table className="doc-params-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Required</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {command.params.map((param) => (
              <tr key={param.name}>
                <td>
                  <code>{param.name}</code>
                </td>
                <td>{param.type ?? "—"}</td>
                <td>{param.required ? "Yes" : "No"}</td>
                <td>{param.description ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!!command.examples?.length && (
        <div className="doc-command-examples">
          {command.examples.map((example, i) => (
            <code className="doc-command-example" key={i}>
              {example}
            </code>
          ))}
        </div>
      )}
    </article>
  );
}

export function DocsCommands() {
  const [data, setData] = useState<CommandCategory[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();

  const activeCategory = searchParams.get("category");

  useEffect(() => {
    fetchCommandDocs()
      .then((res) => setData(res.categories))
      .catch(() => setError("Docs are temporarily unavailable. Please check back soon."));
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    const trimmed = search.trim();
    return data
      .map((category) => ({
        ...category,
        commands: trimmed ? category.commands.filter((c) => matchesQuery(c, trimmed)) : category.commands,
      }))
      .filter((category) => (activeCategory ? category.name === activeCategory : true))
      .filter((category) => category.commands.length > 0 || !trimmed);
  }, [data, search, activeCategory]);

  function selectCategory(name: string | null) {
    if (name) {
      setSearchParams({ category: name });
    } else {
      setSearchParams({});
    }
  }

  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="docs-page">
      <h1>Command docs</h1>
      <p className="field-help settings-content-subtitle">
        Browse every command kidney bot supports, grouped by category.
      </p>

      <div className="docs-search">
        <input
          type="text"
          placeholder="Search commands…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search commands"
        />
      </div>

      {data === null ? (
        <Skeleton rows={8} />
      ) : (
        <div className="guild-settings-layout docs-layout">
          <nav className="settings-nav">
            <div className="settings-nav-section">
              <div className="settings-nav-heading">Categories</div>
              <button
                type="button"
                className={!activeCategory ? "settings-nav-item settings-nav-item--active" : "settings-nav-item"}
                onClick={() => selectCategory(null)}
              >
                All commands
              </button>
              {data.map((category) => (
                <button
                  key={category.name}
                  type="button"
                  className={
                    activeCategory === category.name
                      ? "settings-nav-item settings-nav-item--active"
                      : "settings-nav-item"
                  }
                  onClick={() => selectCategory(category.name)}
                >
                  {category.name}
                </button>
              ))}
            </div>
          </nav>

          <div className="settings-content docs-content">
            {filtered.every((category) => category.commands.length === 0) ? (
              <p className="list-empty">No commands match your search.</p>
            ) : (
              filtered.map(
                (category) =>
                  category.commands.length > 0 && (
                    <section className="doc-category" key={category.name}>
                      <h2>{category.name}</h2>
                      {category.description && <p className="field-help">{category.description}</p>}
                      <div className="doc-command-list">
                        {category.commands.map((command) => (
                          <CommandCard command={command} key={command.name} />
                        ))}
                      </div>
                    </section>
                  ),
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
}
