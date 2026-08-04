/**
 * States the real capability of this workspace. Draft generation is roadmap
 * work, so this panel deliberately ships no control: an enabled or disabled
 * generate button would promise behavior no endpoint performs.
 */
export function GenerationPanel({
  sourceCount,
}: {
  sourceCount: number;
}) {
  return (
    <aside
      className="generation-panel"
      aria-labelledby="generation-panel-title"
    >
      <h2 id="generation-panel-title">Generate section drafts</h2>
      <p className="generation-panel__status">
        Draft generation is not available yet. Sections are written and revised
        manually in the workspace.
      </p>
      <p className="generation-panel__note">
        Saved instructions will apply automatically once generation is
        available.
      </p>
      <dl className="generation-panel__facts">
        <div>
          <dt>Saved sources</dt>
          <dd>
            {sourceCount === 0
              ? "None uploaded"
              : `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}`}
          </dd>
        </div>
        <div>
          <dt>Drafting</dt>
          <dd>Manual</dd>
        </div>
      </dl>
    </aside>
  );
}
