import { Link } from "react-router-dom";

import type { Conversation } from "../api/types";
import type { ProtocolDetail } from "../workspace/useProtocolLibrary";

export interface AttentionItem {
  conversationId: string;
  title: string;
  reason: string;
  tone: "error" | "warning";
}

const MAX_ITEMS = 3;

/** Attention rows derived only from loaded document state; empty when nothing needs action. */
export function attentionItemsFor(
  protocols: Conversation[],
  details: Record<string, ProtocolDetail>,
): AttentionItem[] {
  const items: AttentionItem[] = [];
  for (const protocol of protocols) {
    const detail = details[protocol.id];
    if (detail === undefined) {
      continue;
    }
    if (detail.failed > 0) {
      items.push({
        conversationId: protocol.id,
        title: protocol.title,
        reason:
          detail.failed === 1
            ? "1 source failed to process"
            : `${detail.failed} sources failed to process`,
        tone: "error",
      });
    }
    if (detail.processing > 0) {
      items.push({
        conversationId: protocol.id,
        title: protocol.title,
        reason:
          detail.processing === 1
            ? "1 source is still processing"
            : `${detail.processing} sources are still processing`,
        tone: "warning",
      });
    }
  }
  return items.slice(0, MAX_ITEMS);
}

/** Compact ruled list of protocols with sources that need a look. */
export function ProtocolAttention({ items }: { items: AttentionItem[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <section className="protocol-attention" aria-labelledby="protocol-attention-title">
      <h2 id="protocol-attention-title">Needs attention ({items.length})</h2>
      <ul>
        {items.map((item) => (
          <li
            key={`${item.conversationId}-${item.reason}`}
            className={
              item.tone === "error"
                ? "protocol-attention__item protocol-attention__item--error"
                : "protocol-attention__item protocol-attention__item--warning"
            }
          >
            <span className="protocol-attention__protocol">{item.title}</span>
            <span className="protocol-attention__reason">{item.reason}</span>
            <Link to={`/workspace/${item.conversationId}`}>View sources</Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
