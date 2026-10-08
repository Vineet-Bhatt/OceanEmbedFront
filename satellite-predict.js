(function () {
  'use strict';

  var form = document.getElementById('oceanembed-params-form');
  var panel = document.getElementById('oceanembed-params');
  var dateInput = form.elements.date;

  // Default to today, and let a shared link prefill the parameters.
  dateInput.value = new Date().toISOString().slice(0, 10);
  var query = new URLSearchParams(window.location.search);
  ['latitude', 'longitude', 'date'].forEach(function (name) {
    if (query.get(name)) form.elements[name].value = query.get(name);
  });

  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Panel eases in; the canvas settles from the zoomed-in view the previous page ended on.
  function enter() {
    if (reduce || !window.gsap) return;
    var canvas = document.getElementById('application-canvas');
    if (canvas) {
      window.gsap.fromTo(canvas,
        { scale: 1.6, transformOrigin: '50% 58%' },
        { scale: 1, duration: 1.4, ease: 'power3.out', clearProps: 'transform' });
    }
    window.gsap.from(panel, { y: 24, opacity: 0, duration: 0.8, delay: 0.5, ease: 'power2.out' });
  }

  // Same scene as the home page, minus the project cards, which only exist to launch this page.
  var attempts = 0;
  var timer = window.setInterval(function () {
    var app = window.__oceanEmbedApp;
    var canvas = document.getElementById('application-canvas');
    var group = app && app.root && app.root.findByName('cardsgroup');
    if (group) {
      group.enabled = false;
      window.clearInterval(timer);
    } else if (++attempts > 120) {
      window.clearInterval(timer);
    }
    if (canvas && !enter.done) { enter.done = true; enter(); }
  }, 250);
}());
