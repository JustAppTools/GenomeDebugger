/** Reject malformed bytes rather than substituting characters in analysis data. */
export async function readUtf8(file: File, preserveBOM = false): Promise<string> {
  const bytes = await file.arrayBuffer()
  try {
    return new TextDecoder('utf-8', { fatal: true, ignoreBOM: preserveBOM }).decode(bytes)
  } catch {
    throw new Error('File must contain valid UTF-8 text; save it as UTF-8 and try again.')
  }
}
