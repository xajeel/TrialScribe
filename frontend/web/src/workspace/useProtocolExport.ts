import { useCallback, useRef, useState } from "react";

import {
  EXPORT_PROTOCOL_JOB_KIND,
  createJob,
  downloadExport,
  exportFileFromApi,
  listExports,
} from "../api/jobs";
import type { ExportRecord } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import type {
  ExportFileView,
  ExportJobView,
  ExportScope,
  ExportStage,
} from "../product/deliveryAuditReviewFixtures";
import { isJobInFlight } from "./useGenerationJob";
import { useJobRun } from "./useJobRun";

const START_FAILURE = "Could not start the export. Please try again.";
const JOB_FAILURE = "Could not complete the export. Please try again.";
const DOWNLOAD_FAILURE = "Could not download the export. Please try again.";

export type ExportPanelState = "configuration" | "building" | "ready" | "failed";

export interface ProtocolExportController {
  panelState: ExportPanelState;
  jobView: ExportJobView | null;
  error: string | null;
  pending: boolean;
  start: (scope: ExportScope) => Promise<void>;
  retry: () => Promise<void>;
  back: () => void;
  createAnother: () => void;
  download: (file: ExportFileView) => Promise<void>;
}

const PLACEHOLDER_FILE: ExportFileView = {
  exportId: "",
  filename: "protocol.docx",
  byteSize: 1,
  sections: 0,
  createdAt: "1970-01-01T00:00:00Z",
  requester: "You",
  scope: "done-only",
};

function stagesFromProgress(progress: number): ExportStage[] {
  const collecting = progress >= 40 ? "complete" : "current";
  const writing = progress >= 90 ? "complete" : progress >= 40 ? "current" : "upcoming";
  const saving = progress >= 100 ? "complete" : progress >= 90 ? "current" : "upcoming";
  return [
    {
      id: "queued",
      label: "Collecting sections",
      detail: "Loading finished chapters in ICH M11 order",
      state: collecting,
    },
    {
      id: "assembling",
      label: "Writing document",
      detail: "Building headings, citations, and references",
      state: writing,
    },
    {
      id: "document",
      label: "Saving file",
      detail: "Storing the Word document for download",
      state: saving,
    },
  ];
}

function jobViewFrom(
  progress: number,
  readyFile: ExportFileView,
  recentExports: ReadonlyArray<ExportFileView>,
): ExportJobView {
  return {
    stages: stagesFromProgress(progress),
    readyFile,
    recentExports,
  };
}

function filesFromRecords(
  items: ExportRecord[],
  jobId: string,
  viewerLabel: string | null,
): { readyFile: ExportFileView | null; recentExports: ExportFileView[] } {
  const mapped = items.map((item) =>
    exportFileFromApi(item, viewerLabel ?? "You"),
  );
  const readyFile =
    mapped.find((_, index) => items[index]?.job_id === jobId) ?? mapped[0] ?? null;
  const recentExports = mapped.filter((file) => file.exportId !== readyFile?.exportId);
  return { readyFile, recentExports };
}

/** Queue a protocol Word export, poll the ticket, and download the stored file. */
export function useProtocolExport({
  organizationId,
  conversationId,
  fetcher,
  enabled,
  accountId,
}: {
  organizationId: string | null;
  conversationId: string | null;
  fetcher: AuthorizedFetch;
  enabled: boolean;
  accountId: string | null;
}): ProtocolExportController {
  const [panelState, setPanelState] = useState<ExportPanelState>("configuration");
  const [jobView, setJobView] = useState<ExportJobView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const scopeRef = useRef<ExportScope>("done-only");
  const run = useJobRun(fetcher);

  const back = useCallback(() => {
    run.stop();
    run.forget();
    setPanelState("configuration");
    setJobView(null);
    setError(null);
    setPending(false);
  }, [run]);

  const createAnother = useCallback(() => {
    back();
  }, [back]);

  const start = useCallback(
    async (scope: ExportScope) => {
      if (
        !enabled ||
        organizationId === null ||
        conversationId === null ||
        pending ||
        isJobInFlight(run.latest()?.status)
      ) {
        return;
      }
      const token = run.claim();
      const orgId = organizationId;
      const conversation = conversationId;
      scopeRef.current = scope;
      setPending(true);
      setError(null);
      setPanelState("building");
      setJobView(jobViewFrom(0, PLACEHOLDER_FILE, []));
      try {
        const created = await createJob(
          fetcherRef.current,
          orgId,
          EXPORT_PROTOCOL_JOB_KIND,
          conversation,
          { scope },
        );
        if (!run.isCurrent(token)) {
          return;
        }
        run.adopt(created);
        const running = await run.follow(token, orgId, created.id, {
          onUpdate: (next) => {
            setJobView(jobViewFrom(next.progress, PLACEHOLDER_FILE, []));
          },
          onSucceeded: async () => {
            const listed = await listExports(fetcherRef.current, orgId, conversation);
            if (!run.isCurrent(token)) {
              return;
            }
            const { readyFile, recentExports } = filesFromRecords(
              listed.items,
              created.id,
              accountId,
            );
            if (readyFile === null) {
              setError(JOB_FAILURE);
              setPanelState("failed");
              setPending(false);
              return;
            }
            setJobView(jobViewFrom(100, readyFile, recentExports));
            setPanelState("ready");
            setPending(false);
          },
          onFailed: () => {
            setError(JOB_FAILURE);
            setPanelState("failed");
            setPending(false);
          },
        });
        if (!running && run.isCurrent(token)) {
          setPending(false);
        }
      } catch {
        if (run.isCurrent(token)) {
          setError(START_FAILURE);
          setPanelState("failed");
          setPending(false);
        }
      }
    },
    [accountId, conversationId, enabled, organizationId, pending, run],
  );

  const retry = useCallback(async () => {
    run.forget();
    await start(scopeRef.current);
  }, [run, start]);

  const download = useCallback(
    async (file: ExportFileView) => {
      if (!enabled || organizationId === null || file.exportId === "") {
        return;
      }
      try {
        const blob = await downloadExport(
          fetcherRef.current,
          organizationId,
          file.exportId,
        );
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = file.filename;
        link.click();
        URL.revokeObjectURL(objectUrl);
      } catch {
        setError(DOWNLOAD_FAILURE);
      }
    },
    [enabled, organizationId],
  );

  return {
    panelState,
    jobView,
    error,
    pending,
    start,
    retry,
    back,
    createAnother,
    download,
  };
}
