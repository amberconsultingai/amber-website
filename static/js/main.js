// ── Tab Switching ──
const tabBtns = document.querySelectorAll(".tab-btn, [data-tab]");
const tabPanels = document.querySelectorAll(".tab-panel");

function switchTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach(btn =>
    btn.classList.toggle("active", btn.dataset.tab === tabId)
  );
  tabPanels.forEach(panel =>
    panel.classList.toggle("active", panel.id === "tab-" + tabId)
  );
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-tab]");
  if (el && !el.classList.contains("tab-panel")) {
    e.preventDefault();
    switchTab(el.dataset.tab);
  }
});

// ── FAQ Accordion ──
document.querySelectorAll('.faq-question').forEach(btn => {
  btn.addEventListener('click', () => {
    const item = btn.closest('.faq-item');
    const isOpen = item.classList.contains('open');
    document.querySelectorAll('.faq-item.open').forEach(i => i.classList.remove('open'));
    if (!isOpen) item.classList.add('open');
  });
});

// ── Contact Form ──
const form = document.getElementById("contact-form");
const status = document.getElementById("form-status");
const submitBtn = document.getElementById("submit-btn");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  submitBtn.disabled = true;
  submitBtn.textContent = "Sending...";
  status.textContent = "";
  status.className = "";

  const data = new FormData(form);

  try {
    const res = await fetch("/contact", { method: "POST", body: data });
    const json = await res.json();

    if (json.success) {
      status.textContent = "Message sent! We'll be in touch soon.";
      status.className = "success";
      form.reset();
    } else {
      status.textContent = json.error || "Something went wrong.";
      status.className = "error";
    }
  } catch {
    status.textContent = "Network error. Please try again.";
    status.className = "error";
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Send Message";
  }
});
