export type DiffSegmentKind = "unchanged" | "added" | "removed";

export interface DiffSegment {
  kind: DiffSegmentKind;
  text: string;
}

function tokens(value: string): string[] {
  const trimmed = value.trim();
  return trimmed === "" ? [] : trimmed.split(/\s+/);
}

function merge(parts: ReadonlyArray<DiffSegment>): DiffSegment[] {
  const merged: DiffSegment[] = [];
  for (const part of parts) {
    const last = merged[merged.length - 1];
    if (last && last.kind === part.kind) {
      last.text = `${last.text} ${part.text}`;
    } else {
      merged.push({ kind: part.kind, text: part.text });
    }
  }
  return merged;
}

/** Compare two drafts by whitespace-separated tokens using LCS. */
export function diffSegments(original: string, next: string): DiffSegment[] {
  if (original === next) {
    return [{ kind: "unchanged", text: original }];
  }
  const left = tokens(original);
  const right = tokens(next);
  const rows = left.length;
  const columns = right.length;
  const table: number[][] = Array.from({ length: rows + 1 }, () =>
    Array<number>(columns + 1).fill(0),
  );
  for (let row = rows - 1; row >= 0; row -= 1) {
    for (let column = columns - 1; column >= 0; column -= 1) {
      table[row][column] =
        left[row] === right[column]
          ? (table[row + 1][column + 1] ?? 0) + 1
          : Math.max(table[row + 1][column] ?? 0, table[row][column + 1] ?? 0);
    }
  }
  const parts: DiffSegment[] = [];
  let row = 0;
  let column = 0;
  while (row < rows && column < columns) {
    if (left[row] === right[column]) {
      parts.push({ kind: "unchanged", text: left[row] ?? "" });
      row += 1;
      column += 1;
    } else if ((table[row + 1][column] ?? 0) >= (table[row][column + 1] ?? 0)) {
      parts.push({ kind: "removed", text: left[row] ?? "" });
      row += 1;
    } else {
      parts.push({ kind: "added", text: right[column] ?? "" });
      column += 1;
    }
  }
  while (row < rows) {
    parts.push({ kind: "removed", text: left[row] ?? "" });
    row += 1;
  }
  while (column < columns) {
    parts.push({ kind: "added", text: right[column] ?? "" });
    column += 1;
  }
  return merge(parts);
}
