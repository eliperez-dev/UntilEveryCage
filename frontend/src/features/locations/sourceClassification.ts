export type SourceClassificationAssignment = Readonly<{ sourceLabel?: string | null; sourceCode?: string | null }>;

function displayLabel(value: string | null | undefined): string | null {
  if (!value?.trim()) return null;
  const words = value.replaceAll(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
    .replace(/\b(nrte|rte)\b/gi, acronym => acronym.toUpperCase());
  return words ? words[0]!.toLocaleUpperCase() + words.slice(1) : null;
}

function identity(value: string): string {
  return value.toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

function terms(value: string | null | undefined): string[] {
  return value?.split(';').map(term => term.trim()).filter(Boolean) ?? [];
}

/** Preserve native terminology while avoiding a second rendering of activity facts. */
export function sourceClassificationLabels(
  nativeLabels: readonly (string | null | undefined)[],
  assignments: readonly SourceClassificationAssignment[],
  activities: readonly (string | null | undefined)[],
): string[] {
  const activityKeys = new Set(activities.filter((value): value is string => Boolean(value)).map(displayLabel).filter((value): value is string => Boolean(value)).map(identity));
  const seen = new Set<string>();
  const output: string[] = [];
  const add = (value: string | null | undefined) => {
    for (const term of terms(value)) {
      const label = displayLabel(term);
      if (!label) continue;
      const key = identity(label);
      if (!key || activityKeys.has(key) || seen.has(key)) continue;
      seen.add(key);
      output.push(label);
    }
  };
  nativeLabels.forEach(add);
  for (const assignment of assignments) {
    const labels = terms(assignment.sourceLabel).map(displayLabel).filter((value): value is string => Boolean(value));
    const codes = terms(assignment.sourceCode).map(displayLabel).filter((value): value is string => Boolean(value));
    const label = labels.length === 1 ? labels[0] : null;
    const code = codes.length === 1 ? codes[0] : null;
    if (labels.length > 1 || codes.length > 1) {
      labels.forEach(add);
      codes.forEach(add);
      continue;
    }
    if (label && code && ` ${identity(label)} `.includes(` ${identity(code)} `)) {
      add(label);
    } else if (label && code && identity(label) !== identity(code)) {
      const labelRepeated = activityKeys.has(identity(label)) || seen.has(identity(label));
      const codeRepeated = activityKeys.has(identity(code)) || seen.has(identity(code));
      if (!labelRepeated && !codeRepeated) add(`${label} (${code})`);
      else if (!labelRepeated) add(label);
      else if (!codeRepeated) add(code);
    } else add(label ?? code);
  }
  return output;
}
