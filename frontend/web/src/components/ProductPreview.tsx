/**
 * Decorative product mockup — a faux TrialScribe window with a sidebar and a
 * short protocol Q&A exchange. Pure CSS/JSX so it stays crisp at any size.
 */
export function ProductPreview() {
  return (
    <div className="preview" aria-hidden="true">
      <div className="preview__bar">
        <span className="preview__dot" />
        <span className="preview__dot" />
        <span className="preview__dot" />
        <span className="preview__bar-title">TrialScribe Protocol Q&amp;A</span>
      </div>
      <div className="preview__body">
        <div className="preview__side">
          <span className="preview__side-label">Conversations</span>
          <span className="preview__navline" style={{ width: "85%" }} />
          <span
            className="preview__navline preview__navline--active"
            style={{ width: "70%" }}
          />
          <span className="preview__navline" style={{ width: "78%" }} />
          <span className="preview__navline" style={{ width: "58%" }} />
        </div>
        <div className="preview__chat">
          <p className="preview__bubble preview__bubble--user">
            What changed in the v2.3 inclusion criteria?
          </p>
          <div className="preview__bubble preview__bubble--ai">
            <span className="preview__line" style={{ width: "94%" }} />
            <span className="preview__line" style={{ width: "88%" }} />
            <span className="preview__line" style={{ width: "62%" }} />
            <span className="preview__cite">protocol_v2.3.pdf · p. 14</span>
          </div>
          <p className="preview__bubble preview__bubble--user">
            Draft a site memo for the change.
          </p>
          <div className="preview__bubble preview__bubble--ai">
            <span className="preview__line" style={{ width: "90%" }} />
            <span className="preview__line" style={{ width: "44%" }} />
          </div>
        </div>
      </div>
    </div>
  );
}
