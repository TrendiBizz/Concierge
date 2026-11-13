/**
 * Copy text, and tell the truth about whether it worked.
 *
 * `navigator.clipboard.writeText` rejects when the browser withholds permission (insecure context,
 * an iframe without `clipboard-write`, a locked-down browser). The call sites ignored that promise
 * and then told the owner "copied", which is worse than not copying at all: they paste nothing and
 * do not know why.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (!navigator.clipboard) return false;
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
