"use strict";
document.querySelectorAll("[data-print]").forEach(button => {
  button.addEventListener("click", async () => {
    await document.fonts.ready;
    window.print();
  });
});
