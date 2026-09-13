/** Decorative product mockups kept in CSS/JSX so they stay crisp at any size. */
export function ProductPreview({
  variant = "conversation",
}: {
  variant?: "conversation" | "protocol";
}) {
  if (variant === "protocol") {
    return (
      <div className="landing-product-preview" aria-hidden="true">
        <div className="landing-product-preview__bar">
          <span className="landing-product-preview__dots">
            <i />
            <i />
            <i />
          </span>
          <span>AURORA-301-PHASE-III</span>
          <i />
        </div>
        <div className="landing-product-preview__body">
          <aside className="landing-product-preview__rail">
            <span className="landing-product-preview__rail-icon landing-product-preview__rail-icon--active">
              ▤
            </span>
            <span className="landing-product-preview__rail-icon">↶</span>
            <span className="landing-product-preview__rail-icon">⚙</span>
          </aside>
          <aside className="landing-product-preview__protocols">
            <span className="landing-product-preview__label">
              Active protocols
            </span>
            <div className="landing-product-preview__protocol landing-product-preview__protocol--active">
              <strong>AURORA-301</strong>
              <small>Updated 2h ago</small>
            </div>
            <div className="landing-product-preview__protocol">
              <strong>ZEPHYR-102</strong>
            </div>
          </aside>
          <section className="landing-product-preview__editor">
            <span className="landing-product-preview__section-label">
              Section 5.0
            </span>
            <h2>Trial Population</h2>
            <p>
              Patients will be eligible for inclusion if they present with
              chronic symptomatic heart failure (NYHA Class II-IV) and a
              documented LVEF ≤ 40% <mark>[S1]</mark>. Exclusion criteria
              includes uncontrolled hypertension or recent myocardial
              infarction within 30 days <mark>[S3]</mark>.
            </p>
            <div className="landing-product-preview__draft">
              Continue drafting…
            </div>
          </section>
          <aside className="landing-product-preview__outline">
            <div className="landing-product-preview__outline-head">
              <span>Outline</span>
              <span>8 of 14</span>
            </div>
            <ol>
              <li className="is-done">1. Synopsis</li>
              <li className="is-done">2. Introduction</li>
              <li className="is-active">5. Trial Population</li>
              <li>6. Study Design</li>
            </ol>
            <span className="landing-product-preview__label">
              Evidence sources
            </span>
            <div className="landing-product-preview__source">
              ▤ IB_v8_Final.pdf
            </div>
          </aside>
        </div>
      </div>
    );
  }

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
