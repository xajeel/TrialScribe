import { useCallback, useEffect, useRef, useState } from "react";

import {
  EXPORT_PROTOCOL_JOB_KIND,
  GENERATE_JOB_POLL_MS,
  createJob,
  downloadExport,
  exportFileFromApi,
  getJob,
  listExports,
} from "../api/jobs";
import type { ExportRecord, JobRecord } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import type {
  ExportFileView,
  ExportJobView,
  ExportScope,
  ExportStage,
} from "../product/deliveryAuditReviewFixtures";
import { isJobInFlight } from "./useGenerationJob";

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
  const jobRef = useRef<JobRecord | null>(null);
  const intervalRef = useRef<number | null>(null);
  const generationRef = useRef(0);
  const scopeRef = useRef<ExportScope>("done-only");

  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  const back = useCallback(() => {
    stopPolling();
    jobRef.current = null;
    setPanelState("configuration");
    setJobView(null);
    setError(null);
    setPending(false);
  }, [stopPolling]);

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
        isJobInFlight(jobRef.current?.status)
      ) {
        return;
      }
      stopPolling();
      const expected = generationRef.current + 1;
      generationRef.current = expected;
      scopeRef.current = scope;
      setPending(true);
      setError(null);
      setPanelState("building");
      setJobView(jobViewFrom(0, PLACEHOLDER_FILE, []));
      try {
        const created = await createJob(
          fetcherRef.current,
          organizationId,
          EXPORT_PROTOCOL_JOB_KIND,
          conversationId,
          { scope },
        );
        if (generationRef.current !== expected) {
          return;
        }
        jobRef.current = created;
        const orgId = organizationId;
        const conversation = conversationId;

        const refresh = async (): Promise<JobRecord | null> => {
          const next = await getJob(fetcherRef.current, orgId, created.id);
          if (generationRef.current !== expected) {
            return null;
          }
          jobRef.current = next;
          setJobView(jobViewFrom(next.progress, PLACEHOLDER_FILE, []));
          if (isJobInFlight(next.status)) {
            return next;
          }
          stopPolling();
          if (next.status === "succeeded") {
            const listed = await listExports(fetcherRef.current, orgId, conversation);
            if (generationRef.current !== expected) {
              return next;
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
              return next;
            }
            setJobView(jobViewFrom(100, readyFile, recentExports));
            setPanelState("ready");
            setPending(false);
          } else {
            setError(JOB_FAILURE);
            setPanelState("failed");
            setPending(false);
          }
          return next;
        };

        const next = await refresh();
        if (
          generationRef.current === expected &&
          next !== null &&
          isJobInFlight(next.status)
        ) {
          intervalRef.current = window.setInterval(() => {
            void refresh().catch(() => undefined);
          }, GENERATE_JOB_POLL_MS);
        } else if (generationRef.current === expected) {
          setPending(false);
        }
      } catch {
        if (generationRef.current === expected) {
          setError(START_FAILURE);
          setPanelState("failed");
          setPending(false);
        }
      }
    },
    [conversationId, enabled, organizationId, pending, stopPolling, accountId],
  );

  const retry = useCallback(async () => {
    jobRef.current = null;
    await start(scopeRef.current);
  }, [start]);

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
