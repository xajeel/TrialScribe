import { useMemo, useState } from "react";

import { BrandLogo } from "../components/BrandLogo";
import { ComparePanel, type CompareView } from "../components/ComparePanel";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EvidenceInspector } from "../components/EvidenceInspector";
import { RewritePanel } from "../components/RewritePanel";
import {
  EVIDENCE_REVIEW_FIXTURES,
  REWRITE_REVIEW_FIXTURE,
  type EvidenceReviewKind,
  type RewriteAlternative,
  type RewriteReviewStage,
} from "../product/evidenceRewriteReviewFixtures";

function ReviewHeader({ page }: { page: string }) {
  return (
    <header className="review-editor__header">
      <BrandLogo to="/" ariaLabel="TrialScribe review home" />
      <div>
        <span>Northstar Clinical Research</span>
        <strong>AURORA-301 — Phase III</strong>
      </div>
      <span className="review-editor__page">{page}</span>
      <span className="avatar" aria-label="Review account MC">
        MC
      </span>
    </header>
  );
}

function EvidenceDocument({
  onInspectCitation,
}: {
  onInspectCitation: () => void;
}) {
  return (
    <article className="review-document" aria-labelledby="evidence-document-title">
      <p className="review-document__eyebrow">Section 5 · ICH M11</p>
      <h1 id="evidence-document-title">Trial Population</h1>
      <p className="review-document__lead">
        The study will enrol adults with a confirmed diagnosis and documented
        clinical stability before screening.
      </p>
      <h2>5.1 Inclusion criteria</h2>
      <p>
        Participants must provide informed consent and meet all protocol
        eligibility criteria before randomisation.
      </p>
      <ul>
        <li>Adults aged 18 to 75 years at the time of screening.</li>
        <li>
          ECOG performance status of 0 or 1 at screening{" "}
          <button
            type="button"
            className="review-document__citation"
            onClick={onInspectCitation}
            aria-label="Inspect citation [S3, p. 14]"
          >
            [S3, p. 14]
          </button>
          .
        </li>
        <li>Life expectancy of at least 12 weeks.</li>
      </ul>
      <p>
        Renal and hepatic function will be assessed before randomisation, with
        any clinically meaningful change reviewed against the stored source.
      </p>
    </article>
  );
}

/** Stable development host for every Page 12 evidence state. */
export function EvidenceReviewPage({
  initialKind,
}: {
  initialKind: EvidenceReviewKind;
}) {
  const [kind, setKind] = useState<EvidenceReviewKind>(initialKind);
  const [open, setOpen] = useState(true);

  return (
    <div className="evidence-review review-editor">
      <ReviewHeader page="Page 12 · Evidence" />
      <main className="review-editor__workspace">
        <nav className="review-editor__rail" aria-label="Protocol sections">
          <p>ICH M11 structure</p>
          <ol>
            <li>Protocol summary</li>
            <li>Trial objectives</li>
            <li aria-current="page">Trial population</li>
            <li>Statistical considerations</li>
          </ol>
        </nav>
        <section className="review-editor__canvas" aria-label="Protocol document">
          {!open && (
            <button
              type="button"
              className="review-editor__reopen"
              onClick={() => setOpen(true)}
            >
              Reopen evidence inspector
            </button>
          )}
          <EvidenceDocument
            onInspectCitation={() => {
              setKind("section");
              setOpen(true);
            }}
          />
        </section>
        {open && (
          <EvidenceInspector
            evidence={EVIDENCE_REVIEW_FIXTURES[kind]}
            active={kind}
            onSelectKind={(nextKind) => setKind(nextKind)}
            onClose={() => setOpen(false)}
          />
        )}
      </main>
    </div>
  );
}

function RewriteDocument({
  selectedAlternative,
}: {
  selectedAlternative: RewriteAlternative;
}) {
  return (
    <article className="review-document" aria-labelledby="rewrite-document-title">
      <p className="review-document__eyebrow">
        Section {REWRITE_REVIEW_FIXTURE.sectionNumber} · Revision{" "}
        {REWRITE_REVIEW_FIXTURE.currentRevision}
      </p>
      <h1 id="rewrite-document-title">
        {REWRITE_REVIEW_FIXTURE.sectionTitle}
      </h1>
      <p>
        This is a multicentre, randomised, double-blind Phase III study
        designed to evaluate the efficacy and safety of AURORA-301.
      </p>
      <blockquote className="review-document__selection">
        {REWRITE_REVIEW_FIXTURE.selectedText}
      </blockquote>
      <p>
        Approximately 240 participants will be randomised in a 1:1 ratio and
        followed through the 52-week treatment period.
      </p>
      <aside className="review-document__candidate" aria-label="Selected review alternative">
        <span>Selected review wording</span>
        <p>{selectedAlternative.text}</p>
      </aside>
    </article>
  );
}

/** Stable development host and local state machine for every Page 13 state. */
export function RewriteReviewPage({
  initialStage,
}: {
  initialStage: RewriteReviewStage;
}) {
  const initialPanelStage =
    initialStage === "whole"
      ? "whole"
      : initialStage === "selection"
        ? "selection"
        : "alternatives";
  const [stage, setStage] = useState<RewriteReviewStage>(initialStage);
  const [setupStage] = useState<"selection" | "whole">(
    initialPanelStage === "whole" ? "whole" : "selection",
  );
  const [instruction, setInstruction] = useState(
    initialPanelStage === "whole"
      ? REWRITE_REVIEW_FIXTURE.wholeInstruction
      : REWRITE_REVIEW_FIXTURE.instruction,
  );
  const [keepCitations, setKeepCitations] = useState(true);
  const [useSources, setUseSources] = useState(true);
  const [selectedAlternativeId, setSelectedAlternativeId] =
    useState<RewriteAlternative["id"]>("alternative-1");
  const [compareView, setCompareView] = useState<CompareView>(() =>
    typeof window !== "undefined" &&
    window.matchMedia?.("(max-width: 47.9375rem)").matches
      ? "inline"
      : "side-by-side",
  );
  const [confirmationOpen, setConfirmationOpen] = useState(
    initialStage === "confirm",
  );
  const [confirmationOpener, setConfirmationOpener] =
    useState<HTMLElement | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [result, setResult] = useState("");

  const selectedAlternative = useMemo(
    () =>
      REWRITE_REVIEW_FIXTURE.alternatives.find(
        (alternative) => alternative.id === selectedAlternativeId,
      ) ?? REWRITE_REVIEW_FIXTURE.alternatives[0],
    [selectedAlternativeId],
  );

  const requestUse = (
    alternativeId: RewriteAlternative["id"],
    opener: HTMLElement,
  ) => {
    setSelectedAlternativeId(alternativeId);
    setConfirmationOpener(opener);
    setConfirmationOpen(true);
  };

  const panelStage =
    stage === "selection" || stage === "whole" ? stage : "alternatives";

  return (
    <div className="rewrite-review review-editor">
      <ReviewHeader page="Page 13 · Rewrite & compare" />
      {stage === "compare" ? (
        <ComparePanel
          fixture={REWRITE_REVIEW_FIXTURE}
          alternative={selectedAlternative}
          view={compareView}
          onChangeView={setCompareView}
          onBack={() => setStage("alternatives")}
          onUse={(opener) => requestUse(selectedAlternative.id, opener)}
        />
      ) : (
        <main className="review-editor__workspace">
          <nav className="review-editor__rail" aria-label="Protocol sections">
            <p>ICH M11 structure</p>
            <ol>
              <li>Introduction</li>
              <li>Trial objectives</li>
              <li aria-current="page">Study design</li>
              <li>Trial population</li>
            </ol>
          </nav>
          <section className="review-editor__canvas" aria-label="Protocol document">
            {!panelOpen && (
              <button
                type="button"
                className="review-editor__reopen"
                onClick={() => setPanelOpen(true)}
              >
                Reopen rewrite panel
              </button>
            )}
            <RewriteDocument selectedAlternative={selectedAlternative} />
            {result !== "" && (
              <p className="rewrite-review__result" role="status">
                {result}
              </p>
            )}
          </section>
          {panelOpen && (
            <RewritePanel
              stage={panelStage}
              fixture={REWRITE_REVIEW_FIXTURE}
              instruction={instruction}
              keepCitations={keepCitations}
              useSources={useSources}
              selectedAlternativeId={selectedAlternativeId}
              onInstructionChange={setInstruction}
              onKeepCitationsChange={setKeepCitations}
              onUseSourcesChange={setUseSources}
              onReviewAlternatives={() => setStage("alternatives")}
              onSelectAlternative={setSelectedAlternativeId}
              onCompare={(id) => {
                setSelectedAlternativeId(id);
                setStage("compare");
              }}
              onUse={requestUse}
              onRevise={() => setStage(setupStage)}
              onKeepOriginal={() => {
                setResult("Original wording kept in this review demonstration.");
                setPanelOpen(false);
              }}
              onClose={() => setPanelOpen(false)}
            />
          )}
        </main>
      )}

      <ConfirmDialog
        open={confirmationOpen}
        title={`Use ${selectedAlternative.label}?`}
        description={`This review demonstration will show ${selectedAlternative.label} as applied. No stored section content will change.`}
        confirmLabel={`Use ${selectedAlternative.label} in demonstration`}
        returnFocusTo={confirmationOpener}
        onCancel={() => setConfirmationOpen(false)}
        onConfirm={() => {
          setConfirmationOpen(false);
          setStage("alternatives");
          setResult("Review demonstration applied. Stored section content was not changed.");
        }}
      />
    </div>
  );
}
