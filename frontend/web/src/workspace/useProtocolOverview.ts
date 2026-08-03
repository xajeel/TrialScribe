import { useCallback, useEffect, useRef, useState } from "react";

import {
  appendConversationMessage,
  getConversation,
  listConversationMessages,
} from "../api/conversations";
import { listDocuments } from "../api/documents";
import { listM11Sections } from "../api/m11Sections";
import type {
  Conversation,
  ConversationMessage,
  DocumentRecord,
  M11Section,
} from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";

export type OverviewStatus = "idle" | "loading" | "ready" | "error";
export type OverviewAction = "idle" | "saving";

export interface OverviewFeedback {
  kind: "success" | "error";
  message: string;
}

export interface ProtocolOverviewController {
  status: OverviewStatus;
  conversation: Conversation | null;
  instructions: ConversationMessage[];
  documents: DocumentRecord[];
  sections: M11Section[];
  sectionsInitialized: boolean;
  action: OverviewAction;
  feedback: OverviewFeedback | null;
  retry: () => void;
  addInstruction: (text: string) => Promise<boolean>;
  dismissFeedback: () => void;
}

export const INSTRUCTION_LIMIT = 4000;

const PUBLIC_FAILURES = {
  load: "Could not load this protocol workspace.",
  add: "Could not save the instruction. Please try again.",
} as const;

/** Load one protocol's conversation, instructions, sources, and sections once for every tab. */
export function useProtocolOverview(
  organizationId: string | null,
  conversationId: string | null,
  fetcher: AuthorizedFetch,
): ProtocolOverviewController {
  const [status, setStatus] = useState<OverviewStatus>("idle");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [instructions, setInstructions] = useState<ConversationMessage[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [sections, setSections] = useState<M11Section[]>([]);
  const [sectionsInitialized, setSectionsInitialized] = useState(false);
  const [action, setAction] = useState<OverviewAction>("idle");
  const [feedback, setFeedback] = useState<OverviewFeedback | null>(null);
  const [reload, setReload] = useState(0);

  // Every async result checks this counter before writing state, so a slow
  // response for a previous protocol can never overwrite the current one.
  const generation = useRef(0);

  useEffect(() => {
    generation.current += 1;
    const expected = generation.current;

    setConversation(null);
    setInstructions([]);
    setDocuments([]);
    setSections([]);
    setSectionsInitialized(false);
    setFeedback(null);
    setAction("idle");

    if (organizationId === null || conversationId === null) {
      setStatus("idle");
      return;
    }

    setStatus("loading");
    void Promise.all([
      getConversation(fetcher, organizationId, conversationId),
      listConversationMessages(fetcher, organizationId, conversationId),
      listDocuments(fetcher, organizationId, conversationId),
      // A protocol whose outline was never prepared is a real state, not a
      // failure, so this read resolves to null instead of rejecting the page.
      listM11Sections(fetcher, organizationId, conversationId).catch(
        () => null,
      ),
    ])
      .then(([record, messagePage, documentPage, workspace]) => {
        if (generation.current !== expected) {
          return;
        }
        setConversation(record);
        setInstructions(
          [...messagePage.items].sort(
            (left, right) => left.sequence - right.sequence,
          ),
        );
        setDocuments(documentPage.items);
        setSections(
          workspace === null
            ? []
            : [...workspace.items].sort(
                (left, right) => left.position - right.position,
              ),
        );
        setSectionsInitialized(workspace !== null && workspace.items.length > 0);
        setStatus("ready");
      })
      .catch(() => {
        if (generation.current === expected) {
          setStatus("error");
        }
      });
  }, [conversationId, fetcher, organizationId, reload]);

  const retry = useCallback(() => {
    setReload((value) => value + 1);
  }, []);

  const dismissFeedback = useCallback(() => {
    setFeedback(null);
  }, []);

  const addInstruction = useCallback(
    async (text: string): Promise<boolean> => {
      if (
        organizationId === null ||
        conversationId === null ||
        action !== "idle"
      ) {
        return false;
      }
      const normalized = text.trim();
      if (normalized === "" || normalized.length > INSTRUCTION_LIMIT) {
        return false;
      }

      const expected = generation.current;
      setAction("saving");
      setFeedback(null);
      try {
        const saved = await appendConversationMessage(
          fetcher,
          organizationId,
          conversationId,
          normalized,
        );
        if (generation.current !== expected) {
          return false;
        }
        setInstructions((current) => [...current, saved]);
        setFeedback({ kind: "success", message: "Instruction saved." });
        return true;
      } catch {
        if (generation.current === expected) {
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.add });
        }
        return false;
      } finally {
        if (generation.current === expected) {
          setAction("idle");
        }
      }
    },
    [action, conversationId, fetcher, organizationId],
  );

  return {
    status,
    conversation,
    instructions,
    documents,
    sections,
    sectionsInitialized,
    action,
    feedback,
    retry,
    addInstruction,
    dismissFeedback,
  };
}

export { PUBLIC_FAILURES as OVERVIEW_FAILURES };
