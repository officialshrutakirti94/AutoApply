const EXPLICIT_MODAL =
  ".jobs-easy-apply-modal, [data-test-modal-id='easy-apply-modal']";
const GENERIC_MODAL = "[role='dialog'], .artdeco-modal";

function normalizedText(node: Element | null): string {
  return (node?.textContent ?? "").replace(/\s+/g, " ").trim();
}

function isVisible(node: Element): boolean {
  const element = node as HTMLElement;
  return typeof element.getClientRects !== "function" || element.getClientRects().length > 0;
}

function hasApplyHeading(modal: Element): boolean {
  const heading =
    modal.querySelector("h1, h2, h3, [role='heading'], [aria-label]") ?? modal;
  const label =
    heading.getAttribute("aria-label")?.trim() || normalizedText(heading);
  return /^apply\s+to\b/i.test(label);
}

export function isLinkedInEasyApplyModal(modal: Element): boolean {
  if (modal.matches(EXPLICIT_MODAL)) return true;
  if (!modal.matches(GENERIC_MODAL) || !isVisible(modal) || !hasApplyHeading(modal)) {
    return false;
  }
  return Array.from(modal.querySelectorAll("button, [role='button']")).some((button) =>
    /\b(next|review|submit)\b/i.test(
      button.getAttribute("aria-label")?.trim() || normalizedText(button),
    ),
  );
}

export function findLinkedInEasyApplyModal(root: ParentNode): Element | null {
  const explicit = root.querySelector(EXPLICIT_MODAL);
  if (explicit && isVisible(explicit)) return explicit;
  return (
    Array.from(root.querySelectorAll(GENERIC_MODAL)).find(isLinkedInEasyApplyModal) ?? null
  );
}

export function closestLinkedInEasyApplyModal(node: Element): Element | null {
  const explicit = node.closest(EXPLICIT_MODAL);
  if (explicit) return explicit;
  const generic = node.closest(GENERIC_MODAL);
  return generic && isLinkedInEasyApplyModal(generic) ? generic : null;
}
