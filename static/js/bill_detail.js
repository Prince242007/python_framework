"use strict";
document.getElementById("print-bill").addEventListener("click", async () => {
  await document.fonts.ready;
  window.print();
});
// Clear only the draft that created this bill, leaving an unrelated draft intact.
try {
  const draft = JSON.parse(sessionStorage.getItem("prince-masala-bill-draft-v1") || "null");
  if (draft && draft.token) {
    if (draft.token === document.getElementById("saved-invoice").dataset.submissionToken) {
      sessionStorage.removeItem("prince-masala-bill-draft-v1");
    }
  }
} catch (_) { /* Printing remains available when session storage is disabled. */ }
