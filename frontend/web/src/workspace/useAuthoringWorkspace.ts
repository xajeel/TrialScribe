import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  appendConversationMessage,
  createConversation,
  listConversationMessages,
  listConversations,
  renameConversation,
} from "../api/conversations";
import { deleteDocument, listDocuments, uploadDocument } from "../api/documents";
import {
  initializeM11Workspace,
  markM11SectionDone,
  reopenM11Section,
  reviseM11Section,
} from "../api/m11Sections";
import type {
  Conversation,
  ConversationMessage,
  DocumentKind,
  DocumentRecord,
  M11Section,
} from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";

export type LoadStatus = "idle" | "loading" | "ready" | "error";
export type WorkspaceAction =
  | "idle"
  | "creating"
  | "renaming"
  | "sending"
  | "uploading"
  | "removing"
  | "saving"
  | "transitioning";

export interface WorkspaceFeedback {
  kind: "success" | "error";
  message: string;
}

export interface AuthoringWorkspaceController {
  conversationStatus: LoadStatus;
  workspaceStatus: LoadStatus;
  conversations: Conversation[];
  selectedConversationId: string | null;
  selectedConversation: Conversation | null;
  messages: ConversationMessage[];
  documents: DocumentRecord[];
  sections: M11Section[];
  selectedSectionNumber: string | null;
  selectedSection: M11Section | null;
  action: WorkspaceAction;
  feedback: WorkspaceFeedback | null;
  selectConversation: (conversationId: string) => void;
  selectSection: (sectionNumber: string) => void;
  retryConversations: () => void;
  retryWorkspace: () => void;
  dismissFeedback: () => void;
  create: (title: string) => Promise<boolean>;
  rename: (title: string) => Promise<boolean>;
  appendInstruction: (content: string) => Promise<boolean>;
  upload: (kind: DocumentKind, file: File) => Promise<boolean>;
  removeDocument: (documentId: string) => Promise<boolean>;
  saveSection: (instructions: string, content: string) => Promise<boolean>;
  markDone: () => Promise<boolean>;
  reopen: () => Promise<boolean>;
}

const PUBLIC_FAILURES = {
  create: "Could not create the conversation. Please try again.",
  rename: "Could not rename the conversation. Please try again.",
  message: "Could not save the instruction. Please try again.",
  upload: "Could not upload the document. Check the file and try again.",
  remove: "Could not remove the document. Please try again.",
  section: "Could not save the section. Reload it and try again.",
  transition: "Could not change the section status. Please try again.",
} as const;

/** Coordinate tenant- and conversation-scoped authoring state for the workspace. */
export function useAuthoringWorkspace(
  organizationId: string | null,
  fetcher: AuthorizedFetch,
  initialConversationId: string | null = null,
): AuthoringWorkspaceController {
  const [conversationStatus, setConversationStatus] =
    useState<LoadStatus>("idle");
  const [workspaceStatus, setWorkspaceStatus] = useState<LoadStatus>("idle");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<
    string | null
  >(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [sections, setSections] = useState<M11Section[]>([]);
  const [selectedSectionNumber, setSelectedSectionNumber] = useState<
    string | null
  >(null);
  const [action, setAction] = useState<WorkspaceAction>("idle");
  const [feedback, setFeedback] = useState<WorkspaceFeedback | null>(null);
  const [conversationReload, setConversationReload] = useState(0);
  const [workspaceReload, setWorkspaceReload] = useState(0);

  const organizationRef = useRef(organizationId);
  const conversationRef = useRef(selectedConversationId);
  organizationRef.current = organizationId;
  conversationRef.current = selectedConversationId;

  const clearWorkspace = useCallback(() => {
    setMessages([]);
    setDocuments([]);
    setSections([]);
    setSelectedSectionNumber(null);
  }, []);

  useEffect(() => {
    let ignore = false;
    setConversations([]);
    setSelectedConversationId(null);
    clearWorkspace();
    setFeedback(null);
    setAction("idle");

    if (organizationId === null) {
      setConversationStatus("idle");
      setWorkspaceStatus("idle");
      return () => {
        ignore = true;
      };
    }

    setConversationStatus("loading");
    setWorkspaceStatus("idle");
    void listConversations(fetcher, organizationId)
      .then((page) => {
        if (ignore) {
          return;
        }
        setConversations(page.items);
        const requested = page.items.find(
          (item) => item.id === initialConversationId,
        );
        setSelectedConversationId(requested?.id ?? page.items[0]?.id ?? null);
        setConversationStatus("ready");
      })
      .catch(() => {
        if (!ignore) {
          setConversationStatus("error");
        }
      });

    return () => {
      ignore = true;
    };
  }, [
    clearWorkspace,
    conversationReload,
    fetcher,
    initialConversationId,
    organizationId,
  ]);

  useEffect(() => {
    let ignore = false;
    clearWorkspace();
    setFeedback(null);
    setAction("idle");

    if (organizationId === null || selectedConversationId === null) {
      setWorkspaceStatus("idle");
      return () => {
        ignore = true;
      };
    }

    setWorkspaceStatus("loading");
    void Promise.all([
      listConversationMessages(
        fetcher,
        organizationId,
        selectedConversationId,
      ),
      listDocuments(fetcher, organizationId, selectedConversationId),
      initializeM11Workspace(
        fetcher,
        organizationId,
        selectedConversationId,
      ),
    ])
      .then(([messagePage, documentPage, workspace]) => {
        if (ignore) {
          return;
        }
        const orderedSections = [...workspace.items].sort(
          (left, right) => left.position - right.position,
        );
        setMessages(messagePage.items);
        setDocuments(documentPage.items);
        setSections(orderedSections);
        setSelectedSectionNumber(
          (current) =>
            orderedSections.find(
              (section) => section.section_number === current,
            )?.section_number ??
            orderedSections[0]?.section_number ??
            null,
        );
        setWorkspaceStatus("ready");
      })
      .catch(() => {
        if (!ignore) {
          setWorkspaceStatus("error");
        }
      });

    return () => {
      ignore = true;
    };
  }, [
    clearWorkspace,
    fetcher,
    organizationId,
    selectedConversationId,
    workspaceReload,
  ]);

  const selectedConversation = useMemo(
    () =>
      conversations.find((item) => item.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  );

  const selectedSection = useMemo(
    () =>
      sections.find(
        (item) => item.section_number === selectedSectionNumber,
      ) ?? null,
    [sections, selectedSectionNumber],
  );

  const contextIsCurrent = useCallback(
    (expectedOrganization: string, expectedConversation: string): boolean =>
      organizationRef.current === expectedOrganization &&
      conversationRef.current === expectedConversation,
    [],
  );

  const selectConversation = useCallback((conversationId: string) => {
    setSelectedConversationId(conversationId);
  }, []);

  const selectSection = useCallback((sectionNumber: string) => {
    setSelectedSectionNumber(sectionNumber);
    setFeedback(null);
  }, []);

  const retryConversations = useCallback(() => {
    setConversationReload((value) => value + 1);
  }, []);

  const retryWorkspace = useCallback(() => {
    setWorkspaceReload((value) => value + 1);
  }, []);

  const dismissFeedback = useCallback(() => {
    setFeedback(null);
  }, []);

  const create = useCallback(
    async (title: string): Promise<boolean> => {
      if (organizationId === null || action !== "idle") {
        return false;
      }
      const expectedOrganization = organizationId;
      setAction("creating");
      setFeedback(null);
      try {
        const created = await createConversation(
          fetcher,
          expectedOrganization,
          title,
        );
        if (organizationRef.current !== expectedOrganization) {
          return false;
        }
        setConversations((current) => [
          created,
          ...current.filter((item) => item.id !== created.id),
        ]);
        setSelectedConversationId(created.id);
        setFeedback({
          kind: "success",
          message: "Conversation created.",
        });
        return true;
      } catch {
        if (organizationRef.current === expectedOrganization) {
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.create });
        }
        return false;
      } finally {
        if (organizationRef.current === expectedOrganization) {
          setAction("idle");
        }
      }
    },
    [action, fetcher, organizationId],
  );

  const rename = useCallback(
    async (title: string): Promise<boolean> => {
      if (
        organizationId === null ||
        selectedConversationId === null ||
        action !== "idle"
      ) {
        return false;
      }
      const expectedOrganization = organizationId;
      const expectedConversation = selectedConversationId;
      setAction("renaming");
      setFeedback(null);
      try {
        const renamed = await renameConversation(
          fetcher,
          expectedOrganization,
          expectedConversation,
          title,
        );
        if (!contextIsCurrent(expectedOrganization, expectedConversation)) {
          return false;
        }
        setConversations((current) =>
          current.map((item) =>
            item.id === expectedConversation ? renamed : item,
          ),
        );
        setFeedback({ kind: "success", message: "Conversation renamed." });
        return true;
      } catch {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.rename });
        }
        return false;
      } finally {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setAction("idle");
        }
      }
    },
    [
      action,
      contextIsCurrent,
      fetcher,
      organizationId,
      selectedConversationId,
    ],
  );

  const appendInstruction = useCallback(
    async (content: string): Promise<boolean> => {
      if (
        organizationId === null ||
        selectedConversationId === null ||
        action !== "idle"
      ) {
        return false;
      }
      const expectedOrganization = organizationId;
      const expectedConversation = selectedConversationId;
      setAction("sending");
      setFeedback(null);
      try {
        const message = await appendConversationMessage(
          fetcher,
          expectedOrganization,
          expectedConversation,
          content,
        );
        if (!contextIsCurrent(expectedOrganization, expectedConversation)) {
          return false;
        }
        setMessages((current) => [...current, message]);
        setFeedback({ kind: "success", message: "Instruction saved." });
        return true;
      } catch {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.message });
        }
        return false;
      } finally {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setAction("idle");
        }
      }
    },
    [
      action,
      contextIsCurrent,
      fetcher,
      organizationId,
      selectedConversationId,
    ],
  );

  const removeDocument = useCallback(
    async (documentId: string): Promise<boolean> => {
      if (
        organizationId === null ||
        selectedConversationId === null ||
        action !== "idle"
      ) {
        return false;
      }
      const expectedOrganization = organizationId;
      const expectedConversation = selectedConversationId;
      setAction("removing");
      setFeedback(null);
      try {
        await deleteDocument(
          fetcher,
          expectedOrganization,
          expectedConversation,
          documentId,
        );
        if (!contextIsCurrent(expectedOrganization, expectedConversation)) {
          return false;
        }
        setDocuments((current) =>
          current.filter((item) => item.id !== documentId),
        );
        setFeedback({ kind: "success", message: "Source removed." });
        return true;
      } catch {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.remove });
        }
        return false;
      } finally {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setAction("idle");
        }
      }
    },
    [
      action,
      contextIsCurrent,
      fetcher,
      organizationId,
      selectedConversationId,
    ],
  );

  const upload = useCallback(
    async (kind: DocumentKind, file: File): Promise<boolean> => {
      if (
        organizationId === null ||
        selectedConversationId === null ||
        action !== "idle"
      ) {
        return false;
      }
      const expectedOrganization = organizationId;
      const expectedConversation = selectedConversationId;
      setAction("uploading");
      setFeedback(null);
      try {
        const uploaded = await uploadDocument(
          fetcher,
          expectedOrganization,
          expectedConversation,
          kind,
          file,
        );
        if (!contextIsCurrent(expectedOrganization, expectedConversation)) {
          return false;
        }
        setDocuments((current) => [
          uploaded,
          ...current.filter((item) => item.id !== uploaded.id),
        ]);
        setFeedback({
          kind: "success",
          message: `${uploaded.filename} uploaded.`,
        });
        return true;
      } catch {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.upload });
        }
        return false;
      } finally {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setAction("idle");
        }
      }
    },
    [
      action,
      contextIsCurrent,
      fetcher,
      organizationId,
      selectedConversationId,
    ],
  );

  const replaceSection = useCallback((updated: M11Section) => {
    setSections((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    );
  }, []);

  const saveSection = useCallback(
    async (instructions: string, content: string): Promise<boolean> => {
      if (
        organizationId === null ||
        selectedConversationId === null ||
        selectedSection === null ||
        action !== "idle"
      ) {
        return false;
      }
      const expectedOrganization = organizationId;
      const expectedConversation = selectedConversationId;
      const section = selectedSection;
      setAction("saving");
      setFeedback(null);
      try {
        const updated = await reviseM11Section(
          fetcher,
          expectedOrganization,
          expectedConversation,
          section.section_number,
          section.current_revision,
          instructions,
          content,
        );
        if (!contextIsCurrent(expectedOrganization, expectedConversation)) {
          return false;
        }
        replaceSection(updated);
        setFeedback({ kind: "success", message: "Section saved." });
        return true;
      } catch {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.section });
        }
        return false;
      } finally {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setAction("idle");
        }
      }
    },
    [
      action,
      contextIsCurrent,
      fetcher,
      organizationId,
      replaceSection,
      selectedConversationId,
      selectedSection,
    ],
  );

  const transitionSection = useCallback(
    async (next: "done" | "draft"): Promise<boolean> => {
      if (
        organizationId === null ||
        selectedConversationId === null ||
        selectedSection === null ||
        action !== "idle"
      ) {
        return false;
      }
      const expectedOrganization = organizationId;
      const expectedConversation = selectedConversationId;
      const section = selectedSection;
      setAction("transitioning");
      setFeedback(null);
      try {
        const updated =
          next === "done"
            ? await markM11SectionDone(
                fetcher,
                expectedOrganization,
                expectedConversation,
                section.section_number,
                section.current_revision,
              )
            : await reopenM11Section(
                fetcher,
                expectedOrganization,
                expectedConversation,
                section.section_number,
                section.current_revision,
              );
        if (!contextIsCurrent(expectedOrganization, expectedConversation)) {
          return false;
        }
        replaceSection(updated);
        setFeedback({
          kind: "success",
          message: next === "done" ? "Section marked done." : "Section reopened.",
        });
        return true;
      } catch {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.transition });
        }
        return false;
      } finally {
        if (contextIsCurrent(expectedOrganization, expectedConversation)) {
          setAction("idle");
        }
      }
    },
    [
      action,
      contextIsCurrent,
      fetcher,
      organizationId,
      replaceSection,
      selectedConversationId,
      selectedSection,
    ],
  );

  const markDone = useCallback(
    () => transitionSection("done"),
    [transitionSection],
  );
  const reopen = useCallback(
    () => transitionSection("draft"),
    [transitionSection],
  );

  return {
    conversationStatus,
    workspaceStatus,
    conversations,
    selectedConversationId,
    selectedConversation,
    messages,
    documents,
    sections,
    selectedSectionNumber,
    selectedSection,
    action,
    feedback,
    selectConversation,
    selectSection,
    retryConversations,
    retryWorkspace,
    dismissFeedback,
    create,
    rename,
    appendInstruction,
    upload,
    removeDocument,
    saveSection,
    markDone,
    reopen,
  };
}
