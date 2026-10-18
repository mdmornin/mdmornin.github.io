(function () {
  "use strict";

  var root = document.documentElement;

  // ---- theme toggle -------------------------------------------------------
  var toggle = document.querySelector(".theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var dark = root.dataset.theme
        ? root.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
      try { localStorage.setItem("theme", root.dataset.theme); } catch (e) {}
    });
  }

  // ---- email (assembled at runtime to keep scrapers away) -----------------
  document.querySelectorAll(".email-link").forEach(function (a) {
    var addr = a.dataset.u + "@" + a.dataset.d;
    a.href = "mailto:" + addr;
    if (a.classList.contains("big")) a.textContent = addr;
  });

  var year = document.getElementById("year");
  if (year) year.textContent = new Date().getFullYear();

  // ---- publications: filter + search --------------------------------------
  var list = document.getElementById("pub-list");
  var search = document.getElementById("pub-search");
  var chips = document.querySelectorAll(".chip");
  var empty = document.querySelector("#publications .empty");
  var filter = "all";

  function apply() {
    if (!list) return;
    var q = (search && search.value || "").trim().toLowerCase();
    var shown = 0;
    list.querySelectorAll(".pub").forEach(function (li) {
      var tags = " " + li.dataset.tags + " ";
      var ok = (filter === "all" || tags.indexOf(" " + filter + " ") !== -1) &&
               (!q || li.textContent.toLowerCase().indexOf(q) !== -1);
      li.hidden = !ok;
      if (ok) shown++;
    });
    list.querySelectorAll(".pubs").forEach(function (ol) {
      var any = ol.querySelector(".pub:not([hidden])");
      ol.hidden = !any;
      if (ol.previousElementSibling) ol.previousElementSibling.hidden = !any;
    });
    if (empty) empty.hidden = shown !== 0;
  }

  chips.forEach(function (c) {
    c.addEventListener("click", function () {
      filter = c.dataset.filter;
      chips.forEach(function (o) { o.setAttribute("aria-pressed", String(o === c)); });
      apply();
    });
  });
  if (search) search.addEventListener("input", apply);

  // ---- publications: expand authors + copy citation -----------------------
  if (list) {
    list.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button");
      if (!btn) return;
      if (btn.classList.contains("expand-authors")) {
        btn.previousElementSibling.hidden = false;
        btn.remove();
      } else if (btn.classList.contains("cite")) {
        var text = btn.dataset.cite;
        var done = function () {
          var old = btn.textContent;
          btn.textContent = "Copied";
          setTimeout(function () { btn.textContent = old; }, 1400);
        };
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text).then(done, function () { window.prompt("Copy citation:", text); });
        } else {
          window.prompt("Copy citation:", text);
        }
      }
    });
  }

  // ---- highlight current section in the nav -------------------------------
  var links = {};
  document.querySelectorAll(".topbar nav a").forEach(function (a) { links[a.hash.slice(1)] = a; });
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var a = links[en.target.id];
        if (!a || !en.isIntersecting) return;
        Object.keys(links).forEach(function (k) { links[k].classList.toggle("active", links[k] === a); });
      });
    }, { rootMargin: "-40% 0px -55% 0px" });
    Object.keys(links).forEach(function (id) {
      var s = document.getElementById(id);
      if (s) io.observe(s);
    });
  }
})();
