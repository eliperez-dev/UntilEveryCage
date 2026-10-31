/** A generated placeholder is UI text; a source-provided name stays verbatim.
 * The optional flag is client-only metadata, never inferred from name text. */
export function recordNamePresentation(
  record: Readonly<{ name?: string | null | undefined; nameProvided?: boolean | undefined }>,
  translate: (label: string) => string = label => label,
): string {
  return record.nameProvided === false || record.name == null
    ? translate('Name not provided')
    : record.name;
}
