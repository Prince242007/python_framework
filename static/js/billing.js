"use strict";
(() => {
  const catalogue = JSON.parse(document.getElementById("catalogue-data").textContent);
  const initial = JSON.parse(document.getElementById("initial-rows").textContent);
  const form = document.getElementById("bill-form");
  const search = document.getElementById("item-search");
  const results = document.getElementById("search-results");
  const selectedText = document.getElementById("selected-item");
  const quantity = document.getElementById("quantity");
  const price = document.getElementById("selling-price");
  const error = document.getElementById("entry-error");
  const addButton = document.getElementById("add-item");
  const cancelEdit = document.getElementById("cancel-edit");
  const customer = document.getElementById("customer-name");
  const date = document.getElementById("bill-date");
  const formToken = document.getElementById("form-token");
  const draftKey = "prince-masala-bill-draft-v1";
  let rows = Array.isArray(initial) ? initial.filter(row => row && typeof row === "object") : [];
  let selected = null;
  let editing = -1;
  let submitting = false;
  const digits = text => String(text).trim().replace(/[૦-૯]/g, char => String("૦૧૨૩૪૫૬૭૮૯".indexOf(char)));
  const money = value => `₹${(value / 100).toLocaleString("en-IN", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  function paise(value) {
    const text = digits(value);
    if (!/^[0-9]+(?:\.[0-9]{1,2})?$/.test(text) || text.length > 12) return null;
    const [whole, fraction = ""] = text.split(".");
    const amount = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
    return Number.isSafeInteger(amount) && amount > 0 && amount <= 999999999 ? amount : null;
  }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function storeDraft() {
    try {
      sessionStorage.setItem(draftKey, JSON.stringify({rows, customer: customer.value, date: date.value, token: formToken.value}));
      document.getElementById("draft-status").textContent = "આ ટૅબમાં ડ્રાફ્ટ સાચવેલ છે. બિલ પૂર્ણ કરવા ઉપરનું બટન દબાવો.";
    } catch (_) {
      document.getElementById("draft-status").textContent = "ડ્રાફ્ટ સાચવી શકાતો નથી. આ પાનું બંધ કરતાં પહેલાં બિલ સાચવો.";
    }
  }
  function resetEntry() {
    selected = null;
    editing = -1;
    search.value = "";
    quantity.value = "";
    price.value = "";
    results.replaceChildren();
    selectedText.textContent = "વસ્તુ શોધીને યાદીમાંથી પસંદ કરો.";
    addButton.textContent = "+ બિલમાં ઉમેરો";
    document.getElementById("entry-title").textContent = "વસ્તુ ઉમેરો";
    cancelEdit.hidden = true;
    error.textContent = "";
  }
  function choose(item) {
    selected = item;
    search.value = item.gujarati_name;
    results.replaceChildren();
    selectedText.textContent = `પસંદ કરેલી વસ્તુ: ${item.gujarati_name} · સંદર્ભ ભાવ ${money(item.price_paise)}`;
    price.value = "";
    quantity.focus();
  }
  function render() {
    const container = document.getElementById("bill-lines");
    container.replaceChildren();
    let total = 0;
    rows.forEach((row, index) => {
      const item = catalogue.find(item => item.id === Number(row.item_id));
      const amount = (paise(row.price) || 0) * Number(digits(row.quantity));
      total += Number.isFinite(amount) ? amount : 0;
      const line = element("article", undefined, "product-row");
      line.append(element("span", String(index + 1), "product-id"));
      const name = element("div", undefined, "product-name");
      name.append(element("h3", item ? item.gujarati_name : "વસ્તુ હવે ઉપલબ્ધ નથી"));
      name.append(element("p", `${row.quantity} × ${money(paise(row.price) || 0)}`));
      line.append(name, element("strong", money(Number.isFinite(amount) ? amount : 0), "product-price"));
      const actions = element("div", undefined, "row-actions");
      const edit = element("button", "સુધારો", "secondary small-button");
      edit.type = "button";
      edit.setAttribute("aria-label", `વસ્તુ ${index + 1} સુધારો`);
      edit.addEventListener("click", () => {
        if (!item) { error.textContent = "આ વસ્તુ કાઢીને બીજી પસંદ કરો."; return; }
        choose(item);
        editing = index;
        quantity.value = row.quantity;
        price.value = row.price;
        addButton.textContent = "ફેરફાર સાચવો";
        document.getElementById("entry-title").textContent = "વસ્તુ સુધારો";
        cancelEdit.hidden = false;
        search.scrollIntoView({behavior: "smooth", block: "center"});
      });
      const remove = element("button", "કાઢો", "secondary small-button");
      remove.type = "button";
      remove.setAttribute("aria-label", `વસ્તુ ${index + 1} કાઢો`);
      remove.addEventListener("click", () => { rows.splice(index, 1); resetEntry(); render(); storeDraft(); });
      actions.append(edit, remove);
      line.append(actions);
      container.append(line);
    });
    if (!rows.length) container.append(element("p", "હજુ કોઈ વસ્તુ ઉમેરાઈ નથી.", "empty-state"));
    document.getElementById("bill-total").textContent = money(total);
    document.getElementById("line-count").textContent = rows.length;
    document.getElementById("save-bill").disabled = !rows.length;
    document.getElementById("items-json").value = JSON.stringify(rows);
  }
  search.addEventListener("input", () => {
    selected = null;
    selectedText.textContent = "યાદીમાંથી વસ્તુ પસંદ કરો.";
    const query = search.value.trim().toLowerCase();
    results.replaceChildren();
    if (!query) return;
    const matches = catalogue.filter(item => item.gujarati_name.toLowerCase().includes(query) || item.search_name.toLowerCase().includes(query));
    matches.slice(0, 15).forEach(item => {
      const button = element("button", undefined, "search-result");
      button.type = "button";
      button.append(element("strong", item.gujarati_name), element("span", item.search_name));
      button.addEventListener("click", () => choose(item));
      results.append(button);
    });
    if (!matches.length) results.append(element("p", "વસ્તુ મળી નથી.", "hint"));
    if (matches.length > 15) results.append(element("p", "વધુ પરિણામો માટે નામના વધુ અક્ષરો લખો.", "hint"));
  });
  function addItem() {
    const count = digits(quantity.value);
    const rate = paise(price.value);
    error.textContent = "";
    if (!selected) { error.textContent = "યાદીમાંથી વસ્તુ પસંદ કરો."; search.focus(); return; }
    if (!/^[0-9]{1,6}$/.test(count) || Number(count) < 1 || Number(count) > 100000) { error.textContent = "જથ્થો ૧ થી ૧,૦૦,૦૦૦ વચ્ચે પૂર્ણાંકમાં દાખલ કરો."; quantity.focus(); return; }
    if (rate === null) { error.textContent = "યોગ્ય વેચાણ ભાવ દાખલ કરો; વધુમાં વધુ બે દશાંશ."; price.focus(); return; }
    const otherTotal = rows.reduce((sum, row, index) => sum + (index === editing ? 0 : (paise(row.price) || 0) * Number(digits(row.quantity))), 0);
    if (otherTotal + rate * Number(count) > 9999999999999) { error.textContent = "બિલની કુલ રકમ ખૂબ મોટી છે. જથ્થો અને ભાવ તપાસો."; return; }
    if (rows.length >= 200 && editing < 0) { error.textContent = "એક બિલમાં વધુમાં વધુ ૨૦૦ વસ્તુઓ ઉમેરી શકાય."; return; }
    const row = {item_id: selected.id, quantity: Number(count), price: `${Math.floor(rate / 100)}.${String(rate % 100).padStart(2, "0")}`};
    if (editing >= 0) rows[editing] = row; else rows.push(row);
    resetEntry(); render(); storeDraft(); search.focus();
  }
  addButton.addEventListener("click", addItem);
  cancelEdit.addEventListener("click", resetEntry);
  [search, quantity, price].forEach(input => input.addEventListener("keydown", event => {
    if (event.key === "Enter") { event.preventDefault(); if (input === price) addItem(); else if (input === quantity) price.focus(); else results.querySelector("button")?.focus(); }
  }));
  customer.addEventListener("input", storeDraft);
  date.addEventListener("change", storeDraft);
  form.addEventListener("submit", event => {
    if (selected || editing >= 0 || quantity.value || price.value) {
      event.preventDefault(); error.textContent = "પહેલા વસ્તુના ફેરફાર બિલમાં ઉમેરો અથવા રદ કરો."; addButton.focus(); return;
    }
    if (!rows.length) { event.preventDefault(); return; }
    document.getElementById("items-json").value = JSON.stringify(rows);
    storeDraft();
    submitting = true;
    document.getElementById("save-bill").disabled = true;
  });
  window.addEventListener("beforeunload", event => {
    if (!submitting && (rows.length || customer.value || selected || quantity.value || price.value)) { event.preventDefault(); event.returnValue = ""; }
  });
  try {
    if (form.dataset.serverErrors !== "true") {
      const draft = JSON.parse(sessionStorage.getItem(draftKey) || "null");
      if (draft && Array.isArray(draft.rows) && draft.rows.length <= 200 && typeof draft.token === "string") {
        rows = draft.rows.filter(row => row && typeof row === "object");
        customer.value = draft.customer || "";
        date.value = draft.date || date.value;
        formToken.value = draft.token;
        document.getElementById("draft-status").textContent = "આ ટૅબનો અગાઉનો ડ્રાફ્ટ પાછો મેળવ્યો.";
      }
    }
  } catch (_) { /* Storage may be unavailable in private browser modes. */ }
  render();
})();
