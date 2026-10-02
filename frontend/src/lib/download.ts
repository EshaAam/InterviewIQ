/**
 * Hand a Blob to the browser as a file download.
 *
 * The object URL points at memory the page holds; revoke it once the click
 * has started the download, or every download leaks its file until the tab
 * closes. The delay gives slower browsers time to begin reading it.
 */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
