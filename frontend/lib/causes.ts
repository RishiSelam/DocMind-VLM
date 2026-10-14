// Short names and colours for the causes the backend assigns (app/services/diagnosis.py).
export const CAUSE: Record<string, string> = {
  correct: "Right", repaired: "Right: text model fixed OCR's error", beyond_ocr: "Right: read what OCR missed",
  misread: "Misread characters", spacing: "Words run together", lost: "Never reached the OCR text",
  wrong_value: "Picked another value", missed: "Said not found", partial: "Only part of the answer",
  near_miss: "Close, not exact", format: "Same value, other format", unsupported: "Not printed on the page",
  failed: "Failed", ambiguous: "Both values are on the page", caution: "Caution",
};
export const GOOD = new Set(["correct", "repaired", "beyond_ocr"]);
export const causeTone = (c: string) =>
  GOOD.has(c) ? "bg-agree-soft text-agree-text" : c === "format" || c === "caution" || c === "ambiguous" ? "bg-warn-soft text-warn-text" : "bg-bad-soft text-bad-text";
export const WHO_NAME = { vlm: "Vision", ocr: "OCR", both: "Both" } as const;
export const KIND: Record<string, string> = { table: "Table", image: "Image", form: "Label and value", text: "Text line" };
